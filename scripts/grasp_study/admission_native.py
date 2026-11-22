"""Evaluate the actual field action provider in MuJoCo, both unconditionally and within its declared support."""

import argparse
import fcntl
import hashlib
import json
import sys
import types
from unittest.mock import patch

import cv2
import mujoco
import numpy as np

from explorer4.conditioned_grasp import (
    MOTOR_SHA256,
    PHYSICS_SHA256,
    VISION_SHA256,
    file_hash,
    load_localizer,
    locate_cube,
)
from explorer4.grasp_measured import TRIAL_TICKS, MeasuredActions, next_target
from explorer4.paths import DATA, ROOT
from scripts.grasp_study.evaluate import (
    SOURCE,
    VISION,
    GraspMetrics,
    environment,
    observe,
    save_json,
    sha_array,
)
from scripts.grasp_study.native_execution import NATIVE, REFERENCE, mock_executor

OUT = DATA / "simlab/reports/grasp-admission-native-v2"
OLD = DATA / "runs/recorded-start-cube-20261121/night/control-comparison.json"
ART = ROOT / "docs/results/conditioned_grasp_v1"
HISTORY = tuple(range(88300, 88320))
BANK = tuple(range(973000, 973064))
FIELD_FILES = (
    "explorer4/grasp_measured.py",
    "explorer4/grasp_shadow.py",
    "explorer4/conditioned_grasp.py",
    "agents/rosmaster/runtime.py",
)
SOURCE_FILES = (
    *FIELD_FILES,
    "scripts/grasp_study/admission_native.py",
    "scripts/grasp_study/native_execution.py",
    "scripts/grasp_study/evaluate.py",
    "explorer4/sim/aligned.py",
    "explorer4/sim/environment.py",
    "explorer4/sim/models.py",
    "explorer4/sim/variation.py",
)
SCHEMA = "rosmaster.bound-rbf-native.v2"


class SimulatedActions(MeasuredActions):
    input_domain = "mujoco_measured_wrist"


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def historical():
    comparison = json.loads(OLD.read_text())
    if (
        comparison["seeds"] != list(HISTORY)
        or comparison["model_hash"] != PHYSICS_SHA256
        or comparison["successes"] != {"before": 0, "after": 3, "control": 1}
    ):
        raise ValueError("Historical reference changed")
    results = {}
    for name, meta in comparison["models"].items():
        path = DATA / "jobs" / meta["job"] / "result.json"
        data = json.loads(path.read_text())
        if (
            [t["seed"] for t in data["trials"]] != list(HISTORY)
            or data["model"]["xml_sha256"] != PHYSICS_SHA256
            or data["checkpoint_sha256"] != meta["weights_sha256"]
        ):
            raise ValueError("Archived baseline weights, physics or seeds changed")
        if [r["outcome"] for r in data["trials"]] != [r[name] for r in comparison["paired_trials"]]:
            raise ValueError("Historical terminal outcomes changed")
        results[name] = (data["trials"], file_hash(path))
    return comparison, results


def protocol():
    _, old = historical()
    return {
        "schema": SCHEMA,
        "method": "rbf",
        "domain": "mujoco",
        "physical_trials": 0,
        "physics_sha256": PHYSICS_SHA256,
        "motor_sha256": MOTOR_SHA256,
        "vision_sha256": VISION_SHA256,
        "source_sha256": {f: file_hash(ROOT / f) for f in SOURCE_FILES},
        "native_inputs_sha256": {
            n: file_hash(p)
            for n, p in {
                "arm": NATIVE / "cubebot/arm_model.py",
                "io": NATIVE / "cubebot/robot_io.py",
                "limits": REFERENCE,
            }.items()
        },
        "archived_results_sha256": {k: v[1] for k, v in old.items()},
        "coverage_sha256": file_hash(ART / "fresh-coverage.json"),
        "historical_native_sha256": file_hash(ART / "native-execution.json"),
        "selection": "Freeze all 84 initial RGB files and per-candidate decisions before the first motor rollout. Historical: every seed 88300-88319, refusal counts against 20. Conditional fresh: first 20 eligible in numerical order from all 64 seeds 973000-973063; no replacement for a rollout failure. All eligibility rows, including later eligible seeds, are retained. Fewer than 20 opens no admission.",
        "eligibility": "Known simulated native wrist camera; measured look pose; full, unoccluded projected cube on-frame; float32 predicted XY inside the existing 32-demonstration convex hull. Compare actual versus cube-only segmentation only to verify the operator-equivalent bounding box, never provide a metric coordinate to the localizer. Learned XY uses only RGB. No error, distance, true XY, or rollout outcome participates in selection.",
        "terminal": "20 Hz, at most 360 native guarded commands from the field provider; 220 advancing targets followed by its last target. Primary success requires all 360 commands executed, held_in_carry_pose at the final sample plus >50 mm lift above the initial support continuously for at least one second in carry. Record earlier success separately. Native stop or refusal is a failure. The operator must independently measure the physical outcome after STOP.",
        "gate": {"minimum_selected": 20, "minimum_terminal_holds": 10, "command_budget": 360},
        "historical_seeds": list(HISTORY),
        "candidate_seeds": list(BANK),
    }


def visibility(env):
    model, renderer = env.model, env.renderer
    cube = model.geom("cube").id
    groups = model.geom_group.copy()
    opt = mujoco.MjvOption()

    def mask(option):
        renderer.update_scene(env.data, camera=env.camera_name, scene_option=option)
        seg = renderer.render()
        return (seg[:, :, 0] == cube) & (seg[:, :, 1] == int(mujoco.mjtObj.mjOBJ_GEOM))

    renderer.enable_segmentation_rendering()
    try:
        actual = mask(opt)
        model.geom_group[:] = 4
        model.geom_group[cube] = 0
        opt.geomgroup[:] = 0
        opt.geomgroup[0] = 1
        isolated = mask(opt)
    finally:
        model.geom_group[:] = groups
        renderer.disable_segmentation_rendering()
    yy, xx = np.nonzero(isolated)
    box = [int(xx.min()), int(yy.min()), int(xx.max() + 1), int(yy.max() + 1)] if len(xx) else None
    full = bool(
        box and 0 < box[0] < box[2] < 640 and 0 < box[1] < box[3] < 480 and np.array_equal(actual, isolated)
    )
    return {
        "full": full,
        "box": box,
        "visible_pixels": int(actual.sum()),
        "unoccluded_pixels": int(isolated.sum()),
    }


def camera(env):
    m = env.model
    ident = m.camera(env.camera_name).id
    return {
        "device_id": "mujoco:" + env.camera_name,
        "camera_calibration_sha256": digest(
            {
                "physics": PHYSICS_SHA256,
                "size": [640, 480],
                "fovy": m.cam_fovy[ident].item(),
                "position": m.cam_pos[ident].tolist(),
                "rotation": m.cam_quat[ident].tolist(),
            }
        ),
    }


def make_observation(row, rgb):
    return {
        "domain": SimulatedActions.input_domain,
        "robot_id": "rosmaster",
        **row["camera"],
        "observation.state": row["look_pose_native"],
        "images": {"front": rgb},
        "confirmed_cube_bbox_xyxy_px": row["visibility"]["box"] if row["visibility"]["full"] else None,
        "predicted_xy_m": row["predicted_xy_m"],
    }


def frame_path(seed):
    return OUT / "frames" / f"{seed}.png"


def collect(env, model, archived):
    rows = []
    for seed in (*HISTORY, *BANK):
        receipt = OUT / "candidates" / f"{seed}.json"
        if receipt.exists():
            record = json.loads(receipt.read_text())
            row = record["row"]
            if (
                record["protocol_sha256"] != file_hash(OUT / "protocol.json")
                or record["row_sha256"] != digest(row)
                or row["seed"] != seed
                or file_hash(frame_path(seed)) != row["png_sha256"]
            ):
                raise ValueError("Invalid saved candidate")
            rows.append(row)
            continue
        initial, rgb = observe(env, seed)
        if seed in HISTORY:
            for name in ("after", "control"):
                original = archived[name][0][seed - HISTORY[0]]
                if not (
                    np.array_equal(initial["arm"], original["initial_state"])
                    and np.allclose(initial["cube"], original["cube_xyz0"], atol=1e-7, rtol=0)
                ):
                    raise ValueError(f"Archived initial pose differs for {name}/{seed}")
        path = frame_path(seed)
        path.parent.mkdir(parents=True, exist_ok=True)
        # A PNG without its atomic candidate receipt is an incomplete write. No rollout can
        # start until the entire candidate list, frame hashes and selected seeds are frozen.
        if not cv2.imwrite(str(path), rgb[:, :, ::-1]):
            raise OSError(path)
        view = visibility(env)
        xy = locate_cube(model.localizer, rgb)
        row = {
            "seed": seed,
            "initial": initial,
            "look_physics_sha256": sha_array(env.snapshot()["physics"]),
            "look_pose_native": env.observation()["state"].tolist(),
            "camera": camera(env),
            "visibility": view,
            "rgb_sha256": sha_array(rgb),
            "png_sha256": file_hash(path),
            "predicted_xy_m": xy.tolist(),
            "inside_motor_hull": bool(model.support.find_simplex(xy) >= 0),
            "localization_error_mm": float(1000 * np.linalg.norm(xy - np.asarray(initial["cube"][:2]))),
        }
        model.calibration = row["camera"]
        model.reset()
        try:
            model._start(make_observation(row, rgb), np.asarray(row["look_pose_native"]))
        except ValueError as exc:
            row.update(eligible=False, reason=str(exc))
        else:
            row.update(eligible=True, reason="eligible")
        save_json(
            receipt,
            {"protocol_sha256": file_hash(OUT / "protocol.json"), "row_sha256": digest(row), "row": row},
        )
        rows.append(row)
    return rows


def episode(env, model, row, limits):
    rgb = cv2.imread(str(frame_path(row["seed"])))[:, :, ::-1].copy()
    if sha_array(rgb) != row["rgb_sha256"] or file_hash(frame_path(row["seed"])) != row["png_sha256"]:
        raise ValueError("Changed frozen first image")
    initial, _ = observe(env, row["seed"], render=False)
    if (
        initial != row["initial"]
        or row["look_physics_sha256"] != sha_array(env.snapshot()["physics"])
        or row["camera"] != camera(env)
    ):
        raise ValueError("Changed reset, look physics or camera")
    model.calibration = row["camera"]
    obs = make_observation(row, rgb)
    model.reset()
    target = None
    executor = mock_executor(env, limits)
    metrics = GraspMetrics(env, initial["cube"][2])
    count, first_success, strict_run = 0, None, 0
    reason = "field_sequence_complete"
    command_hash = hashlib.sha256()
    for tick in range(TRIAL_TICKS):
        try:
            target = next_target(model, obs, tick, target)
            now = env.steps * env.dt
            executor.direct = (now, executor.validate_direct({"arm": target}))
            executor.direct_step(env.dt, now)
        except (RuntimeError, ValueError) as exc:
            reason = "native_or_policy_stop: " + str(exc)
            break
        native = executor.io.arm_command()
        command_hash.update(np.ascontiguousarray(native, dtype="<f8").tobytes())
        _, _, done, timeout, info = env.step(native)
        count += 1
        metrics.measure(env, info)
        above = env.data.body("task_cube").xpos[2] - env.object_half()[2] > 0.050
        strict_run = strict_run + 1 if above and info["held"] and info["in_carry_pose"] else 0
        if info["termination_reason"] == "held_in_carry_pose" and first_success is None:
            first_success = count
        if timeout or (done and info["termination_reason"] != "held_in_carry_pose"):
            reason = info["termination_reason"]
            break
    win = count == TRIAL_TICKS and strict_run >= 20 and bool(info["success"])
    return {
        "seed": row["seed"],
        "executed_ticks": count,
        "first_stable_hold_tick": first_success,
        "terminal_success": bool(win),
        "termination": reason,
        "terminal_qualified_hold_s": strict_run * env.dt,
        "native_action_sha256": command_hash.hexdigest(),
        "projected_ticks": model.clipped_steps,
        "max_projection_deg": model.max_projection_deg.tolist(),
        "bilateral_contact": metrics.bilateral,
        "peak_lift_m": float(metrics.peak_lift),
    }


def original_files():
    from explorer4.datasets import fingerprint

    plan = DATA / "plans/a0d158614edbc51c066fd6c7ce66c326f78e8fd5aa01e97b51f5ce4ab6589999.json"
    records = json.loads(plan.read_text())["splits"]
    checks = {}
    for role, items in records.items():
        for ep in items:
            if fingerprint(ep["dataset"]) != ep["sha256"]:
                raise ValueError(f"Changed original dataset {ep['id']}")
        checks[role] = len(items)
    if checks != {"train": 32, "test": 4, "validation": 4}:
        raise ValueError("Original dataset split changed")
    observations = DATA / "simlab/reports/conditioned-grasp-v1"
    frame_count = 0
    for group in ("development", "fresh", "historical_confirmation"):
        rows = json.loads((observations / group / "observations.json").read_text())
        for seed, row in rows.items():
            rgb = cv2.imread(str(observations / group / "frames" / f"{seed}.png"))[:, :, ::-1]
            if sha_array(rgb) != row["rgb_sha256"]:
                raise ValueError(f"Archived image changed: {group}/{seed}")
            frame_count += 1
    return {
        "plan_sha256": file_hash(plan),
        "verified_original_split": checks,
        "verified_previous_rgb_frames": frame_count,
    }


def coverage_context():
    support = json.loads((ART / "fresh-coverage.json").read_text())["rows"]
    old = json.loads((ART / "native-execution.json").read_text())["trials"]
    if [r["seed"] for r in old] != [s["seed"] for s in support] or len(old) != 20:
        raise ValueError("Coverage join differs")
    native = [r["methods"]["rbf"] for r in old]
    within = [r["outcome"] == "success" and r["executed_control_steps"] <= TRIAL_TICKS for r in native]
    inside = [s["input_in_train_hull"] for s in support]
    return {
        "n": 20,
        "input_inside": sum(inside),
        "old_budget_holds": sum(within),
        "old_within_budget_and_support": sum(a and b for a, b in zip(inside, within)),
        "scope": "Retrospective unrestricted raw native trajectories, first hold by 360; includes refusals in the denominator, no end-of-sequence retest.",
    }


def run(spec):
    import torch

    torch.set_num_threads(1)
    cv2.setNumThreads(1)
    freeze_hash = file_hash(OUT / "protocol.json")
    comparison, archive = historical()
    selection_path = OUT / "selection.json"
    selection_hash_path = OUT / "selection.sha256"
    with REFERENCE.open() as f:
        settings = json.loads(next(f))["control_limits"]["arm_settings"]
    model = SimulatedActions(None, SOURCE, VISION, "rbf", None, localizer=load_localizer(VISION))
    env = environment()
    try:
        if not selection_path.exists():
            candidates = collect(env, model, archive)
            selection = {
                "protocol_sha256": freeze_hash,
                "candidates": candidates,
                "selected": [r["seed"] for r in candidates if r["seed"] in BANK and r["eligible"]][:20],
            }
            save_json(selection_path, selection)
        else:
            selection = json.loads(selection_path.read_text())
        sha = file_hash(selection_path)
        if selection_hash_path.exists() and selection_hash_path.read_text().strip() != sha:
            raise ValueError("Frozen selection changed")
        if not selection_hash_path.exists():
            with selection_hash_path.open("x") as f:
                f.write(sha + "\n")
        rows = selection["candidates"]
        selected = selection["selected"]
        if (
            selection["protocol_sha256"] != freeze_hash
            or [r["seed"] for r in rows] != list(HISTORY + BANK)
            or selected != [r["seed"] for r in rows if r["seed"] in BANK and r["eligible"]][:20]
        ):
            raise ValueError("Invalid ordered selection")
        outcomes = {}
        for row in rows:
            seed = row["seed"]
            if seed in BANK and seed not in selected:
                continue
            dest = OUT / "trials" / f"{seed}.json"
            if dest.exists():
                receipt = json.loads(dest.read_text())
                if receipt["selection_sha256"] != sha or digest(receipt["trial"]) != receipt["trial_sha256"]:
                    raise ValueError("Changed native rollout receipt")
                trial = receipt["trial"]
            else:
                if row["eligible"]:
                    trial = episode(env, model, row, settings)
                else:
                    trial = {
                        "seed": seed,
                        "terminal_success": False,
                        "executed_ticks": 0,
                        "termination": "preflight_refusal: " + row["reason"],
                    }
                save_json(dest, {"selection_sha256": sha, "trial_sha256": digest(trial), "trial": trial})
                print(f"Completed native {seed}", flush=True)
            outcomes[seed] = trial
    finally:
        env.close()
    history = [outcomes[s] for s in HISTORY]
    fresh = [outcomes[s] for s in selected]
    hist_wins = sum(t["terminal_success"] for t in history)
    wins = sum(t["terminal_success"] for t in fresh)
    paired = {
        k: [
            {"seed": s, "old": t["outcome"], "native": outcomes[s]["terminal_success"]}
            for s, t in zip(HISTORY, rs[0], strict=True)
        ]
        for k, rs in archive.items()
    }
    result = {
        "schema": SCHEMA,
        "status": "completed",
        "profile": "rosmaster_floor_pick_recorded_start_sim",
        "physics_sha256": PHYSICS_SHA256,
        "vision_sha256": VISION_SHA256,
        "motor_sha256": MOTOR_SHA256,
        "protocol_sha256": freeze_hash,
        "selection_sha256": sha,
        "field_source_sha256": {f: spec["source_sha256"][f] for f in FIELD_FILES},
        "command_budget": TRIAL_TICKS,
        "physical_trials": 0,
        "optimizer_updates": 0,
        "historical": {
            "evaluated_seeds": list(HISTORY),
            "eligible": sum(r["eligible"] for r in rows[:20]),
            "terminal_holds": hist_wins,
            "denominator": len(HISTORY),
            "references": comparison["successes"],
            "reference_jobs": {k: v["job"] for k, v in comparison["models"].items()},
            "baseline_reset_vectors_recorded": False,
            "comparison_reset_vectors_verified": ["after", "control"],
            "paired": paired,
        },
        "old_fresh_unrestricted": coverage_context(),
        "conditional": {
            "source_bank": list(BANK),
            "eligible_all_64": sum(r["eligible"] for r in rows[20:]),
            "selected": selected,
            "n": len(fresh),
            "terminal_holds": wins,
            "minimum_holds": 10,
            "pass": len(fresh) == 20 and wins >= 10,
        },
        "candidates": rows,
        "trials": history + fresh,
        "original_data": original_files(),
    }
    save_json(OUT / "result.json", result)
    print("Completed historical", hist_wins, "of 20, conditional", wins, "of", len(fresh), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=["freeze", "run"])
    args = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        spec = protocol()
        path = OUT / "protocol.json"
        if not path.exists() and args.stage == "freeze":
            save_json(path, spec)
        if json.loads(path.read_text()) != spec:
            raise ValueError("Changed study or protocol")
        if args.stage == "freeze":
            print(file_hash(path))
            return
        result = OUT / "result.json"
        if result.is_file():
            if json.loads(result.read_text())["protocol_sha256"] != file_hash(path):
                raise ValueError("Conflicting report")
            return

        def no_transport(*args, **kwargs):
            raise AssertionError("No physical transport in the simulation")

        with (
            patch.dict(sys.modules, {"serial": types.SimpleNamespace(Serial=no_transport)}),
            patch.object(sys, "path", [str(ROOT / "agents/rosmaster"), str(NATIVE), *sys.path]),
        ):
            run(spec)


if __name__ == "__main__":
    main()
