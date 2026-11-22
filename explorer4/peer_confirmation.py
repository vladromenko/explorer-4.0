"""Register the sequential peer rule while held, then compare it after the primary evaluation."""
import argparse
import fcntl
import hashlib
import json
import math
import re
import tempfile
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from statistics import mean
from unittest.mock import patch

from . import catalog, study_queue
from .paths import DATA, ROOT
from .peer_request_policy import read, verified_model

REPORTS = DATA / "simlab/reports"
DEVELOPMENT = DATA / "runs/peer-screen-dock-v2"
REFERENCE = Path("docs/results/peer-camera-docking")
SEQUENTIAL = "scripts/peer_sequential_control.py"
METHODS = ("learned", "local_scan", "immediate_peer", "sequential")
digest = study_queue.digest


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def primary(cfg):
    return REPORTS / "workspace" / cfg["study_plan"] / "peer_learning"


def directory(key):
    require(isinstance(key, str) and re.fullmatch("[0-9a-f]{64}", key), "Invalid confirmation digest")
    return REPORTS / "peer-sequential-confirmation" / key


def job(db, ident):
    row = db.execute("""SELECT status, config, not_before FROM jobs
        LEFT JOIN training_starts ON job_id=id WHERE id=?""", (ident,)).fetchone()
    require(row is not None, "Job not found")
    cfg = json.loads(row["config"])
    require(cfg.get("kind") == "workspace_study" and cfg.get("track") == "peer_learning",
            "Confirmation belongs to the peer_learning study")
    return row, cfg


def protocol(ident, cfg):
    from scripts.peer_dock_policy import EXECUTION
    original = read(DEVELOPMENT / "protocol.json")
    queue = study_queue.verify(cfg["study_plan"])
    split = original["splits"]["test"]
    require(len(split["seeds"]) == len(set(split["seeds"])) == 16 and
            all(set(split["seeds"]).isdisjoint(original["splits"][s]["seeds"]) for s in ("train","calibration")),
            "The registered 16 scenes must be disjoint from development")
    files = {f: queue["sources"][f] for f in EXECUTION}
    files.update({f: digest(ROOT / f) for f in (SEQUENTIAL, "explorer4/peer_confirmation.py")})
    for f, sha in read(ROOT / REFERENCE / "sequential-development-protocol.json")["source_sha256"].items():
        require(digest(ROOT / f) == sha, "Development sequential source changed: " + f)
    return {
        "version": 1, "phase": "supplementary prospective held-out confirmation after open development",
        "job_id": ident, "queue_plan_sha256": cfg["study_plan"],
        "source_protocol_sha256": digest(DEVELOPMENT / "protocol.json"),
        "development_protocol_sha256": digest(ROOT / REFERENCE / "sequential-development-protocol.json"),
        "development_results_sha256": digest(ROOT / REFERENCE / "sequential-development.json"),
        "code_sha256": files, "room": split["room"], "seeds": split["seeds"], "methods": list(METHODS),
        "activation": "Complete original evaluate first. Verify its model, original plan, all pre-request decision byte hashes recomputed from onboard inputs, the original outcome files and their paired aggregate before executing the extra rule.",
        "pairing": "Replay the archived initial MuJoCo integration and controller state for every ordered seed in its original world model. Require exact original initial image bytes. Do not exclude any scene, refit, retune thresholds or rerun failed outcomes.",
        "rule": "Use the first valid local measurement. With none, scan in place for at most 3 s. On a miss, hold Tank and request the same 3 s ROSMASTER observation in the current continuous world. Dock with the returned packet. No retry or rewind.",
        "budgets": {"learned": 3, "immediate_peer": 3, "local_scan": 3, "sequential": 6,
                    "units": "maximum simulated seconds sensing before driving",
                    "camera_accounting": "Count one initial recipient image, further local observations every 0.2 s of active scanning, and one donor image per request. Exclude diagnostic renderings."},
        "outcome": "Original independent verifier for <0.08 m and <0.15 rad at rest for >=0.5 s. Time is measured from reset, including all local/donor sensing and docking actions.",
        "utility": {"call_cost": original["call_cost"], "per_second_cost": original["per_second_cost"],
                    "formula": "success - call_cost * requests - per_second_cost * total_simulated_seconds"},
        "analysis": "Report all 16 ordered paired rows, all branches and pairwise differences in success, calls, elapsed and sensing time and utility. Primary supplementary contrast is learned minus sequential mean utility. Exact two-sided sign test only on discordant docking outcomes, exploratory and unadjusted. No learned advantage presumed.",
    }


def attach(ident):
    """Add one content-addressed field under the same transaction as the hold check."""
    with catalog.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row, cfg = job(db, ident)
        require(row["status"] == "queued" and row["not_before"] is None, "Job must be held and unscheduled")
        require(not any((primary(cfg) / name).exists() for name in ("fit.json", "model.json", "evaluation.json")),
                "Cannot preregister after fitting has started")
        spec = protocol(ident, cfg)
        raw = json.dumps(spec, sort_keys=True, indent=2, allow_nan=False) + "\n"
        key = hashlib.sha256(raw.encode()).hexdigest()
        require(cfg.get("peer_confirmation", key) == key, "A different confirmation is already attached")
        path = directory(key) / "protocol.json"
        if not path.exists():
            study_queue.write_json(path, spec)
        require(digest(path) == key, "Stored protocol bytes differ")
        receipt = path.with_name("registration.json")
        evidence = {"protocol_sha256": key, "queue_plan_sha256": cfg["study_plan"], "job_id": ident,
                    "job_status_at_attachment": row["status"], "not_before_at_attachment": row["not_before"]}
        if not receipt.exists():
            study_queue.write_json(receipt, {**evidence, "registered_at_utc": datetime.now(timezone.utc).isoformat()})
        saved = read(receipt)
        require(all(k in saved and saved[k] == v for k,v in evidence.items()), "Registration receipt differs")
        if "peer_confirmation" not in cfg:
            db.execute("UPDATE jobs SET config=json_set(config,'$.peer_confirmation',?) WHERE id=?", (key, ident))
    return key


def verify_camera(folder, filename, packet, robot):
    """Bind the archived measurement to the raw RGB bytes actually used by DockSensors."""
    import cv2
    frame = cv2.imread(str(folder / filename))
    require(frame is not None, "Missing camera evidence: " + filename)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    if packet is not None:
        require(packet["source_robot"] == robot and packet["frame_sha256"] == hashlib.sha256(rgb.tobytes()).hexdigest(),
                "Camera packet and archived RGB differ: " + filename)
    return rgb


def original_rows(root, spec):
    """Read the closed-split files only after the original evaluation has finished."""
    from scripts import peer_dock_policy as policy
    from .sim.peer_screens import screen_fraction
    evaluation = read(root / "evaluation.json")
    require(evaluation["status"] == "completed" and evaluation["fit_on_test"] is False
            and evaluation["test_seeds"] == spec["seeds"] and evaluation["test_room"] == spec["room"]
            and evaluation["scenes"] == len(spec["seeds"]), "Primary evaluation is incomplete or mismatched")
    sha, model = verified_model(root)
    plan = policy.verify_plan(root)
    with tempfile.TemporaryDirectory() as temp:
        rebuilt = policy.prepare(Path(temp), DEVELOPMENT)
    require(rebuilt == plan and plan["test_seeds"] == spec["seeds"] and plan["test_room"] == spec["room"]
            and plan["source_protocol_sha256"] == spec["source_protocol_sha256"]
            and all(plan[k] == spec["utility"][k] for k in ("call_cost", "per_second_cost")),
            "Primary selector or objective differs from the registered development plan")
    scenes, rows, receipts = [], [], []
    for seed in spec["seeds"]:
        folder = root / "test" / str(seed)
        start, decision, prediction, donor, outcome = (read(folder / f) for f in
            ("start.json", "decision.json", "model-decision.json", "donor.json", "outcomes.json"))
        image = digest(folder / "recipient-before.png")
        rgb = verify_camera(folder, "recipient-before.png", decision["local_packet"], "tank")
        verify_camera(folder, "donor-observation.png", donor["packet"], "rosmaster")
        require(screen_fraction(rgb) == decision["local_measurement"]["screen_fraction"],
                f"Initial onboard screen feature differs from the actual RGB on {seed}")
        require(start["seed"] == outcome["seed"] == seed and start["room"] == outcome["room"] == spec["room"]
                and start == outcome["initial"] and start["initial_state_sha256"] == digest(folder / "initial-state.json")
                and donor["after_donor_state_sha256"] == digest(folder / "after-donor.json")
                and donor["packet"] == outcome["donor_packet"] and outcome["decision"] == decision
                and decision["time_s"] == 0 and image == decision["local_image_sha256"],
                f"Initial world, image, decision or donor state differs on {seed}")
        with tempfile.TemporaryDirectory() as temp:
            policy.freeze_prediction(Path(temp), seed, model, decision)
            expected_prediction = digest(Path(temp) / "model-decision.json")
        require(expected_prediction == digest(folder / "model-decision.json"),
                f"Pre-request decision does not match the frozen model and onboard evidence on {seed}")
        scenes.append({**start, "split": "test", "initial_rgb_sha256": image})
        rows.append({**outcome, "model_decision": prediction})
        receipts.append({"seed": seed, "initial_state_sha256": start["initial_state_sha256"],
                         "world_model_sha256": start["world_model_sha256"], "initial_rgb_sha256": image,
                         **{f: digest(folder / f) for f in ("decision.json", "model-decision.json", "outcomes.json", "donor.json", "policy-comparison.json")}})
    original = policy.evaluation_summary(rows, plan)
    require(all(evaluation[k] == original[k] for k in original), "Primary paired statistics differ")
    for row in rows:
        require(row["policies"] == read(root / "test" / str(row["seed"]) / "policy-comparison.json"),
                "Stored policy choice differs")
    receipt = {"evaluation_sha256": digest(root / "evaluation.json"), "model_sha256": sha,
               "model_file_sha256": digest(root / "model.json"), "plan_file_sha256": digest(root / "plan.json"),
               "fit_file_sha256": digest(root / "fit.json"), "seeds": receipts}
    return scenes, rows, receipt


def measure(verifier, calls, costs):
    seconds = verifier["simulation_time_s"]
    sensing = seconds - .05 * verifier["actions_sent"]
    success = int(verifier["task"] == "success")
    require(math.isfinite(seconds) and seconds >= 0 and sensing >= -1e-6
            and verifier["source"] == "fixed_outcome_verifier" and verifier["task"] in ("success", "failure"),
            "Invalid terminal verifier or elapsed time")
    if success:
        require(verifier["raw_environment_outcome"] == "success" and verifier["stationary"] and
                verifier["distance_m"] < .08 and abs(verifier["yaw_error_rad"]) < .15 and verifier["stable_s"] >= .5,
                "A reported dock fails its independent endpoint thresholds")
    local_seconds = sensing - 3 * calls
    frames = round(local_seconds / .2)
    require(0 <= frames <= 15 and math.isclose(local_seconds, .2 * frames, abs_tol=1e-6), "Invalid sensing clock")
    return {"success": success, "calls": calls, "seconds": seconds, "sensing_s": max(0., sensing),
            "decision_frames": 1 + frames + calls,
            "utility": success - costs["call_cost"] * calls - costs["per_second_cost"] * seconds}


def paired(scene, row, out, key, costs):
    folder = out / str(scene["seed"])
    seq = read(folder / "result.json")
    calls = seq["calls"]
    require(seq["seed"] == scene["seed"] and seq["room"] == scene["room"] and seq["split"] == "test"
            and seq["initial_state_sha256"] == scene["initial_state_sha256"] and seq["initial_rgb_identical"]
            and seq["protocol_sha256"] == key and seq["clock_start_s"] == 0
            and seq["initial_rgb_sha256"] == scene["initial_rgb_sha256"] == digest(folder / "initial.png")
            and seq["initial_marker"] == (row["decision"]["local_packet"] is not None)
            and calls == int(not seq["onboard_packet"]), "Sequential replay or branch differs")
    if calls:
        require(math.isclose(seq["local_search_end_s"], 3., abs_tol=1e-6)
                and math.isclose(seq["donor_end_s"], 6., abs_tol=1e-6)
                and seq["donor_image_sha256"] == digest(folder / "donor-observation.png"),
                "Delayed observation did not follow the complete local search")
    branches = row["branches"]
    local = measure(branches["local_scan"], 0, costs)
    immediate = measure(branches["always"], 1, costs)
    require(immediate["decision_frames"] == 2, "Immediate peer branch exceeded its camera budget")
    sequential = measure(seq["verifier"], calls, costs)
    require(math.isclose(seq["dock_start_s"], sequential["sensing_s"], abs_tol=1e-6)
            and seq["verifier"]["local_scan_frames"] + 1 + calls == sequential["decision_frames"],
            "Sequential clock or image count differs")
    if not calls:
        require(branches["local_scan"]["commands_sha256"] == seq["verifier"]["commands_sha256"]
                and local == sequential, "Identical local paths diverged")
    return {"seed": scene["seed"], "initial_state_sha256": scene["initial_state_sha256"],
            "sequential_result_sha256": digest(folder / "result.json"),
            "learned_request": row["model_decision"]["request"],
            "methods": {"learned": immediate if row["model_decision"]["request"] else local,
                        "local_scan": local, "immediate_peer": immediate, "sequential": sequential}}


def summarize(rows):
    from scipy.stats import binomtest
    summary = {}
    for method in METHODS:
        trials = [r["methods"][method] for r in rows]
        summary[method] = {"scenes": len(rows), "successes": sum(t["success"] for t in trials),
                           "calls": sum(t["calls"] for t in trials),
                           **{"mean_"+k: mean(t[k] for t in trials) for k in ("seconds", "sensing_s", "decision_frames", "utility")}}
    contrasts = {}
    for left, right in combinations(METHODS, 2):
        pairs = [(r["methods"][left], r["methods"][right]) for r in rows]
        wins = sum(a["success"] > b["success"] for a, b in pairs)
        losses = sum(a["success"] < b["success"] for a, b in pairs)
        contrasts[left+"_minus_"+right] = {"discordant_wins": wins, "discordant_losses": losses,
            "exact_two_sided_p": binomtest(wins, wins+losses).pvalue if wins+losses else 1.,
            **{"mean_delta_"+k: mean(a[k]-b[k] for a,b in pairs) for k in pairs[0][0]}}
    return {"methods": summary, "paired": contrasts}


def primary_saved(cfg, work):
    """On an ordinary retry, preserve both immutable, completed primary result files."""
    public = primary(cfg)
    paths = [public / "result.json", work / "result.json"]
    saved = [read(path) for path in paths if path.is_file()]
    if not saved:
        return False
    evaluation = read(public / "evaluation.json")
    result = saved[0]
    require(all(value == result for value in saved) and evaluation["status"] == "completed"
            and result["study_plan"] == cfg["study_plan"] and result["track"] == "peer_learning"
            and all(result.get(k) == v for k,v in evaluation.items()), "Saved primary results disagree")
    for path in paths:
        if not path.exists():
            study_queue.write_json(path, result)
    return True


def confirm(ident):
    from scripts import peer_sequential_control as sequential
    from scripts.peer_dock_study import frozen
    with catalog.connect() as db:
        row, cfg = job(db, ident)
    require(row["status"] in ("running", "completed", "failed", "interrupted"),
            "Held or unstarted jobs cannot open the test split")
    key = cfg["peer_confirmation"]
    out = directory(key)
    path = out / "protocol.json"
    require(digest(path) == key, "Confirmation protocol differs from the attached digest")
    spec = read(path)
    registered = read(out / "registration.json")
    require(registered["protocol_sha256"] == key and registered["job_id"] == ident
            and registered["queue_plan_sha256"] == cfg["study_plan"] and registered["job_status_at_attachment"] == "queued"
            and registered["not_before_at_attachment"] is None, "Missing held preregistration receipt")
    require(spec == protocol(ident, cfg), "Confirmation source, original plan or identity changed")
    root = primary(cfg)
    with (out / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        scenes, rows, receipt = original_rows(root, spec)
        frozen(out / "primary-evidence.json", receipt)
        if any(not (out / str(scene["seed"]) / "result.json").exists() for scene in scenes):
            require(not (out / "summary.json").exists(), "A completed confirmation has lost a scene")
            with patch.object(sequential, "SOURCE", root):
                sequential.run_room({"scenes": scenes}, out, "test")
        paired_rows = [paired(s, r, out, key, spec["utility"]) for s,r in zip(scenes, rows, strict=True)]
        result = {"status": "completed", "scope": "held-out MuJoCo simulation",
                  "protocol_sha256": key, "registration_sha256": digest(out / "registration.json"),
                  "primary_evidence_sha256": digest(out / "primary-evidence.json"),
                  "model_sha256": receipt["model_sha256"], "rows": paired_rows, **summarize(paired_rows),
                  "training_updates_in_confirmation": 0, "physical_robot_commands": 0}
        frozen(out / "summary.json", result)
    return out / "summary.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("attach", "resume"))
    parser.add_argument("job_id")
    args = parser.parse_args()
    print(attach(args.job_id) if args.action == "attach" else confirm(args.job_id))
