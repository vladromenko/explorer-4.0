"""Register matched target takes, synthetic effort and receiver-only scenes before any motion."""

import hashlib
import itertools
import json
from pathlib import Path

from explorer4 import catalog, datasets, knowledge, skill_packets, training_drafts
from explorer4.paths import DATA, ROOT
from explorer4.sim.floor_carry import ENDPOINT
from explorer4.sim_protocol import scene_revision, sha256_file

TARGET = "rosmaster_pick_place"
SIM = "rosmaster_floor_pick_sim"
PLAN = "64c019b2f8841db8e082e92f7e21e0eadc76bb72f9734808927c4f7278f4b284"
ARMS = ("T0", "T1", "T2", "T3", "G")
AUX = ARMS[1:]
K = (1, 3, 5)
TRAIN_SEEDS = tuple(range(987040, 987048))
PILOT_SEEDS = tuple(range(987120, 987132))
CONTROL_PILOT_SEEDS = tuple(range(987140, 987152))
SOURCES = [
    "scripts/demo_efficiency/" + n + ".py" for n in ("design", "examples", "prepare", "accounting", "report")
]
SOURCES += [
    "explorer4/" + n + ".py"
    for n in (
        "skill_packets",
        "sim/skill_transfer",
        "sim/floor_carry",
        "sim/aligned",
        "sim/evaluate",
        "sim/policy_worker",
        "sim/seeded_start",
        "sim/capture",
        "sim/import_episode",
        "training",
        "training_drafts",
        "study_day",
        "sim/vendor_rosmaster/arm_model",
        "rosmaster_arm",
    )
]


def upstream_runtime():
    packages = list((ROOT / ".venv/lib").glob("python*/site-packages/lerobot"))
    if len(packages) != 1:
        raise ValueError("Locate one installed native LeRobot trainer")
    paths = [
        "scripts/lerobot_train.py",
        "policies/act/configuration_act.py",
        "policies/act/modeling_act.py",
        "datasets/compute_stats.py",
    ]
    return {name: sha256_file(packages[0] / name) for name in paths}


def original_takes(plan):
    if (
        plan["profile"] != TARGET
        or plan["domain"] != "real"
        or plan.get("task_variant") != "rosmaster_floor_cube_pilot"
    ):
        raise ValueError("Use the frozen physical floor-cube protocol")
    train = sorted(plan["splits"]["train"], key=lambda e: (e["created"], e["id"]))
    originals = []
    for e in train:
        raw = json.loads((Path(e["dataset"]) / "provenance.json").read_text())
        root = raw.get("source_episode") or raw.get("hardware", {}).get("source_episode") or e["id"]
        if (
            raw.get("domain", "real") == "real"
            and raw.get("synthetic") is False
            and raw.get("category") == "demonstration"
            and raw.get("command_source") == "human"
            and root == e["id"]
            and root not in originals
            and e["recorded_role"] == "train"
        ):
            originals.append(root)
    return originals


def preflight(plan_id=PLAN):
    plan = datasets.load_plan(plan_id, verify=False)
    takes = original_takes(plan)
    donors = [
        e
        for e in catalog.rows("episodes")
        if e["profile"] == "so101_pick_place"
        and e["outcome"] == "success"
        and e["category"] in ("demonstration", "correction")
        and not e["excluded"]
    ]
    geometry = []
    for e in donors:
        p = Path(e["dataset"]) / "donor_geometry/provenance.json"
        if p.is_file():
            raw = json.loads(p.read_text())
            geometry.append(
                {
                    "episode": e["id"],
                    "overview_frames": raw.get("frames"),
                    "pose_admission": raw.get("pose_admission"),
                    "physical_verified": raw.get("physical_verified"),
                }
            )
    packets = []
    for f in sorted((DATA / "world/skill_packets").glob("*.json")):
        packet = knowledge.load_packet(f.stem)
        decision = skill_packets.admission(packet, domain="real")
        packets.append(
            {
                "sha256": f.stem,
                "domain": packet["donor"]["domain"],
                "source": packet["donor"]["behavior_source"],
                "eligible": decision["eligible"] and packet["donor"]["behavior_source"] == "human",
                "reasons": decision["reasons"],
            }
        )
    durations = {}
    for e in plan["splits"]["train"]:
        if e["id"] in takes:
            frames = [
                json.loads(line)["observation_timestamp_ns"]
                for line in (Path(e["dataset"]) / "research.jsonl").read_text().splitlines()
            ]
            if len(frames) > 1 and all(b > a for a, b in itertools.pairwise(frames)):
                durations[e["id"]] = (frames[-1] - frames[0]) / 1e9
    return {
        "physical_target_plan": plan_id,
        "unique_real_train_takes": takes,
        "target_recording_span_seconds": durations,
        "recording_span_note": "Time between first and last recorded samples, excluding setup/reset and other labour.",
        "real_split_counts": {k: len(v) for k, v in plan["splits"].items()},
        "successful_real_so101_recordings": len(donors),
        "archived_donor_geometry": geometry,
        "packets": packets,
        "motor_comparison_ready": len(takes) >= max(K) and any(p["eligible"] for p in packets),
        "human_minutes": None,
        "unknown_costs": ["donor_demo", "target_demo", "calibration", "annotation", "reset", "correction"],
        "physical_success_measured": False,
        "training_started": False,
    }


def freeze(packet_id, plan_id=PLAN):
    audit = preflight(plan_id)
    controls = packet_id is None
    if not controls and (
        not audit["motor_comparison_ready"]
        or packet_id not in {p["sha256"] for p in audit["packets"] if p["eligible"]}
    ):
        raise ValueError("No admitted real human donor SkillPacket and five unique recipient training takes")
    if len(audit["unique_real_train_takes"]) < max(K):
        raise ValueError("Five unique recipient training takes are required")
    plan = datasets.load_plan(plan_id)
    packet = knowledge.load_packet(packet_id) if packet_id else None
    pool = {e["id"]: e for e in catalog.rows("episodes")}
    from explorer4.alignment_lineage import relatives

    forbidden = set().union(
        *(relatives(e, pool) for role in ("validation", "test") for e in plan["splits"][role])
    )
    for parent in (packet["donor"]["episodes"] if packet else []):
        e = pool[parent["id"]]
        if datasets.fingerprint(e["dataset"]) != parent["sha256"] or relatives(e, pool) & forbidden:
            raise ValueError("Changed or held-out donor source")
    value = {
        "version": 2,
        "endpoint": ENDPOINT,
        "profile": TARGET,
        "simulation": SIM,
        "target_plan_id": plan_id,
        "packet": packet_id,
        "k": list(K),
        "ordered_training_takes": audit["unique_real_train_takes"][: max(K)],
        "arms": list(ARMS[:2] if controls else ARMS),
        "aux_seeds": list(TRAIN_SEEDS),
        "pilot_seeds": list(CONTROL_PILOT_SEEDS if controls else PILOT_SEEDS),
        "paired_aux_scenes": 2,
        "ticks_per_synthetic_take": 360,
        "training": {
            "policy": "act",
            "steps": 1000,
            "batch": 8,
            "train_seed": 1000,
            "device": "cuda",
            "initial_checkpoint": None,
        },
        "upstream_runtime_sha256": upstream_runtime(),
        "backbone_sha256": sha256_file(DATA / "cache/torch/hub/checkpoints/resnet18-f37072fd.pth"),
        "scene_revision": scene_revision(SIM),
        "source_sha256": {p: sha256_file(ROOT / p) for p in SOURCES},
        "human_time": "observed non-overlapping person intervals only; unknown categories render total unknown",
        "terminal": "Final 1 s of 360 control ticks, object lower face above support by >50 mm, tip distance <60 mm, carry joint tolerance and contact on both jaws.",
        "primary": ("T1 minus T0 at k=3; separate donor-free development pilot" if controls else
                    "T2 minus T1 at k=3; donor-disconnected development pilot"),
        "power": {"minimum_useful_gain": 0.20, "alpha_two_sided": 0.05, "target_power": 0.8},
        "arms_description": {
            "T0": "target only",
            "T1": "generic recipient scripted motion",
            "T2": "admitted donor-relative motion",
            "T3": "same donor, cyclically wrong target XY from the next training seed",
            "G": "donor box dimensions and closing axis only, independent recipient motion",
        },
        "shared_budget": "T1 adds two independently verified 360-tick simulated examples" if controls else "same real prefix and optimizer steps for all arms. T1/T2/T3/G use the same first two jointly successful training seeds and 720 synthetic frames. T0 uses zero synthetic frames by definition.",
        "stopping": "screen eight training positions once; fewer than two common terminal successes closes the comparison without training",
        "independent_physical_admission": False,
    }
    return training_drafts.save_content(DATA / "demo-efficiency/plans", value)


def load(ident):
    if len(ident) != 64 or any(c not in "0123456789abcdef" for c in ident):
        raise ValueError("Invalid comparison identity")
    raw = (DATA / "demo-efficiency/plans" / (ident + ".json")).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ident:
        raise ValueError("Changed frozen comparison")
    p = json.loads(raw)
    if (
        p["upstream_runtime_sha256"] != upstream_runtime()
        or p["backbone_sha256"] != sha256_file(DATA / "cache/torch/hub/checkpoints/resnet18-f37072fd.pth")
        or p["scene_revision"] != scene_revision(SIM)
        or any(sha256_file(ROOT / n) != sha for n, sha in p["source_sha256"].items())
    ):
        raise ValueError("Scene or comparison implementation changed since registration")
    return p, DATA / "demo-efficiency/runs" / ident
