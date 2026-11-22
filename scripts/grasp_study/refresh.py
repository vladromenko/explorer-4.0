"""Development ablation: refresh one stationary wrist image before starting the frozen RBF trajectory."""

import argparse
import copy
import hashlib
import json
import random
import sys
import time
import types
from pathlib import Path
from unittest.mock import patch

import cv2
import mujoco
import numpy as np
from scipy.interpolate import RBFInterpolator
from scipy.spatial import Delaunay
from scipy.stats import binomtest

from explorer4.conditioned_grasp import (
    MOTOR_SHA256,
    PHYSICS_SHA256,
    VISION_SHA256,
    file_hash,
    load_localizer,
    locate_cube,
)
from explorer4.paths import DATA, ROOT
from scripts.grasp_study.evaluate import (
    OUTPUT,
    SOURCE,
    VISION,
    environment,
    observe,
    save_json,
    sha_array,
)
from scripts.grasp_study.native_execution import NATIVE, REFERENCE, simulate

SEEDS = tuple(range(940100, 940108))
DEV = OUTPUT / "development"
DEST = DATA / "simlab/reports/grasp-look-refresh-development-v1-1"
LABELS = ("first_xy", "refreshed_xy")


def frozen_protocol():
    sources = {
        "runner": Path(__file__),
        "scene_and_look": ROOT / "scripts/grasp_study/evaluate.py",
        "planner_and_localizer": ROOT / "explorer4/conditioned_grasp.py",
        "executor_adapter": ROOT / "scripts/grasp_study/native_execution.py",
        "runtime": ROOT / "agents/rosmaster/runtime.py",
        "native_io": NATIVE / "cubebot/robot_io.py",
        "native_arm": NATIVE / "cubebot/arm_model.py",
        "native_limits_recording": REFERENCE,
        "scene": ROOT / "explorer4/sim/aligned.py",
        "snapshot": ROOT / "explorer4/sim/environment.py",
        "archived_looks": DEV / "observations.json",
        "archived_plans": DEV / "plans.npz",
        "development_protocol": ROOT / "scripts/grasp_study/protocol.json",
    }
    return {
        "name": "Stationary wrist-image refresh before floor pickup",
        "version": "1.1",
        "scientific_protocol_sha256": "000cb105879534a6ecb6a6730dcc475964d90e0b6597a44cf9c4c39837202f35",
        "implementation_correction": "Version 1.0 stopped at seed 940102 on an archive equality check after two completed scenes. Its new caller divided the localizer float32 XY before conversion to the float64 used by the historical build_plans. The maximum trajectory discrepancy was 0.000023935 degrees. This version restores original float64 scaling for both cameras, requires exact equality with all historical first-view trajectories, repeats every scene, and preserves version 1.0 receipts separately. Conditions, thresholds and seeds were fixed before either run.",
        "partition": "previously open development",
        "scene_seeds": list(SEEDS),
        "y_shift_m": [0.010 if i % 2 == 0 else -0.010 for i in range(len(SEEDS))],
        "conditions": ["static", "shifted"],
        "branches": list(LABELS),
        "planned_rollouts": 32,
        "comparison": "Both branches share the complete post-intervention state, native executor and zero elapsed simulation time for sensing. All target components other than Y and all velocities are preserved. Archive image and contemporaneous new wrist image are taken from the same stationary calibrated look pose. Each branch executes a single unmodified trajectory.",
        "independent_unit": "One scene. Primary: paired terminal hold differences on all eight shifted seeds. Report the predeclared subgroup where both true centres lie inside the convex hull of the frozen training XY, and the static controls. No swaps or replacement seeds.",
        "support": "Before rollouts, metadata showed that 940101, 940102 and 940104 start outside the demonstration hull. Report extrapolation explicitly.",
        "primary": "Guards and simulator reason held_in_carry_pose. Count discordant pairs and two-sided exact binomial conditional on discordance; p=1 when there are no discordant pairs.",
        "timing": "Monotonic wall time per phase after one warm-up. Report new RGB capture through XY and RBF plan, and compute-only time. Same simulated arm time before both branches. 40 ms is the engineering budget. No real-time guarantee.",
        "decision": "No confirmation in this run. A positive development difference is a prerequisite for proposing separate confirmation; no physical deployment from this analysis.",
        "upstream": "https://diffusion-policy.cs.columbia.edu/",
        "method": "Single pre-motion update inspired by visual feedback in receding-horizon control; fixed RBF trajectory. No diffusion policy or feedback after motion begins.",
        "motor_sha256": MOTOR_SHA256,
        "vision_sha256": VISION_SHA256,
        "physics_sha256": PHYSICS_SHA256,
        "source_sha256": {key: file_hash(path) for key, path in sources.items()},
        "optimizer_updates": 0,
        "physical_trials": 0,
    }


def snapshot_hash(snapshot):
    def encode(x):
        if hasattr(x, "detach"):
            x = x.detach().cpu().numpy()
        if isinstance(x, np.ndarray):
            return {"dtype": x.dtype.str, "shape": x.shape, "bytes_sha256": sha_array(x)}
        if isinstance(x, np.generic):
            return x.item()
        raise TypeError(type(x).__name__)

    return hashlib.sha256(
        json.dumps(snapshot, default=encode, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def capture(env):
    return {**env.snapshot(), "episode_parameters": copy.deepcopy(env.episode_parameters)}


def restore(env, state):
    env.restore(state)
    env.episode_parameters = copy.deepcopy(state["episode_parameters"])
    if snapshot_hash(capture(env)) != snapshot_hash(state):
        raise ValueError("Full dynamical, control, sensor or RNG state differs at the branch point")


def elapsed_ms(start):
    return (time.perf_counter_ns() - start) / 1e6


def trial(env, seed, first, archived_plan, rbf, support, localizer, settings):
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    reset, _ = observe(env, seed, render=False)
    initial = capture(env)
    if reset != first["initial"] or sha_array(initial["physics"]) != first["lookup_state_sha256"]:
        raise ValueError("Reset or calibrated look differs from the recorded development scene")
    first_rgb = cv2.imread(str(DEV / "frames" / f"{seed}.png"))[:, :, ::-1]
    first_xy = locate_cube(localizer, first_rgb)
    if sha_array(first_rgb) != first["rgb_sha256"] or not np.allclose(
        first_xy, first["predicted_xy"], atol=1e-7, rtol=0
    ):
        raise ValueError("Archived first view or frozen prediction changed")
    first_xy = np.asarray(first["predicted_xy"], dtype=np.float64)
    centroid = env.data.body("task_cube").xpos[:2].copy()
    row = {
        "seed": seed,
        "reset_sha256": reset["reset_sha256"],
        "look_physics_sha256": first["lookup_state_sha256"],
        "look_full_state_sha256": snapshot_hash(initial),
        "first_rgb_sha256": sha_array(first_rgb),
        "first_xy": first_xy.tolist(),
        "unshifted_truth_xy": centroid.tolist(),
        "conditions": {},
    }
    for condition in ("static", "shifted"):
        restore(env, initial)
        delta = (0.01 if (seed - SEEDS[0]) % 2 == 0 else -0.01) if condition == "shifted" else 0.0
        address = int(env.model.joint("cube_free").qposadr[0]) + 1
        positions = env.data.qpos.copy()
        velocities = env.data.qvel.copy()
        env.data.qpos[address] += delta
        mujoco.mj_forward(env.model, env.data)
        truth = env.data.body("task_cube").xpos[:2].copy()
        expected = positions.copy()
        expected[address] += delta
        if not (
            np.array_equal(env.data.qpos, expected)
            and np.array_equal(env.data.qvel, velocities)
            and np.allclose(truth, centroid + [0, delta], atol=1e-12, rtol=0)
            and env.elapsed == initial["elapsed"]
        ):
            raise ValueError("Intervention changed the arm, velocity, clock or achieved displacement")
        branch = capture(env)
        start = time.perf_counter_ns()
        second_rgb = cv2.resize(env.render(), (160, 120), interpolation=cv2.INTER_AREA)
        render_ms = elapsed_ms(start)
        compute_start = time.perf_counter_ns()
        second_xy = locate_cube(localizer, second_rgb).astype(np.float64)
        new_plan = rbf(second_xy[None] / 0.05)[0]
        compute_ms = elapsed_ms(compute_start)
        decision_ms = elapsed_ms(start)
        stale_start = time.perf_counter_ns()
        old_plan = rbf(first_xy[None] / 0.05)[0]
        stale_ms = elapsed_ms(stale_start)
        if not np.array_equal(old_plan, archived_plan):
            raise ValueError("Frozen spline no longer reproduces the original development trajectory")
        frame = DEST / "frames" / f"{seed}-{condition}.png"
        frame.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(frame), second_rgb[:, :, ::-1]):
            raise OSError(frame)
        entry = {
            "shift_y_m": delta,
            "target_xy_for_scoring": truth.tolist(),
            "truth_in_hull": bool(support.find_simplex(truth) >= 0),
            "second_rgb_sha256": sha_array(second_rgb),
            "second_rgb_file": str(frame.relative_to(DEST)),
            "first_input_in_hull": bool(support.find_simplex(first_xy) >= 0),
            "refreshed_input_in_hull": bool(support.find_simplex(second_xy) >= 0),
            "second_xy": second_xy.tolist(),
            "first_error_mm": float(np.linalg.norm(first_xy - truth) * 1000),
            "second_error_mm": float(np.linalg.norm(second_xy - truth) * 1000),
            "time_ms": {
                "capture_resize": render_ms,
                "refresh_compute": compute_ms,
                "refresh_capture_to_plan": decision_ms,
                "stale_plan": stale_ms,
            },
            "branch_full_state_sha256": snapshot_hash(branch),
            "branch_physics_sha256": sha_array(branch["physics"]),
            "branch_simulated_time_s": env.elapsed,
            "branch_control_tick": env.steps,
            "arms": {},
        }
        for method, plan in zip(LABELS, (old_plan, new_plan), strict=True):
            restore(env, branch)
            entry["arms"][method] = {
                "plan_sha256": sha_array(plan),
                **simulate(env, plan, reset["cube"][2], settings),
            }
        row["conditions"][condition] = entry
    return row


def totals(rows, condition):
    arms = [r["conditions"][condition]["arms"] for r in rows]
    trials = [tuple(r[k]["outcome"] == "success" for k in LABELS) for r in arms]
    gained = trials.count((False, True))
    lost = trials.count((True, False))
    return {
        "n": len(rows),
        "first_holds": sum(a for a, b in trials),
        "refresh_holds": sum(b for a, b in trials),
        "gained": gained,
        "lost": lost,
        "both_hold": trials.count((True, True)),
        "neither_holds": trials.count((False, False)),
        "paired_exact_p": binomtest(gained, gained + lost).pvalue if gained + lost else 1.0,
        "native_guard_stops": {
            k: sum(v[k]["reason"].startswith("native_guard:") for v in arms) for k in LABELS
        },
    }


def run(protocol):
    import torch

    torch.set_num_threads(1)
    cv2.setNumThreads(1)
    if file_hash(SOURCE) != MOTOR_SHA256 or file_hash(VISION) != VISION_SHA256:
        raise ValueError("Frozen motor bank or vision weights changed")
    with np.load(SOURCE, allow_pickle=False) as bank:
        xy = bank["xy"]
        rbf = RBFInterpolator(xy / 0.05, bank["action"], kernel="thin_plate_spline", smoothing=0.005)
    with REFERENCE.open() as f:
        settings = json.loads(next(f))["control_limits"]["arm_settings"]
    localizer = load_localizer(VISION)
    first = json.loads((DEV / "observations.json").read_text())
    warm = cv2.imread(str(DEV / "frames" / f"{SEEDS[0]}.png"))[:, :, ::-1]
    rbf(locate_cube(localizer, warm)[None] / 0.05)

    def reject_serial(*args, **kwargs):
        raise AssertionError("No hardware transport is available for this study")

    rows = []
    env = environment()
    checksum = file_hash(DEST / "protocol.json")
    try:
        with (
            patch.dict(sys.modules, {"serial": types.SimpleNamespace(Serial=reject_serial)}),
            patch.object(sys, "path", [str(ROOT / "agents/rosmaster"), str(NATIVE), *sys.path]),
            np.load(DEV / "plans.npz", allow_pickle=False) as plans,
        ):
            support = Delaunay(xy)
            for seed in SEEDS:
                stored = DEST / "scenes" / f"{seed}.json"
                if stored.is_file():
                    row = json.loads(stored.read_text())
                    if row["seed"] != seed or row["protocol_sha256"] != checksum:
                        raise ValueError("Wrong saved scene")
                else:
                    row = trial(
                        env, seed, first[str(seed)], plans[f"{seed}_rbf"], rbf, support, localizer, settings
                    )
                    row["protocol_sha256"] = checksum
                    save_json(stored, row)
                rows.append(row)
                print(f"Completed development scene {seed}", flush=True)
    finally:
        env.close()
    inside = [r for r in rows if all(v["truth_in_hull"] for v in r["conditions"].values())]
    timing = [v["time_ms"]["refresh_capture_to_plan"] for r in rows for v in r["conditions"].values()]
    compute = [v["time_ms"]["refresh_compute"] for r in rows for v in r["conditions"].values()]
    result = {
        "protocol_sha256": checksum,
        "scope": protocol["partition"],
        "optimizer_updates": 0,
        "physical_trials": 0,
        "n_rollouts": 4 * len(rows),
        "all_scenes": {c: totals(rows, c) for c in ("static", "shifted")},
        "both_targets_in_hull": {
            "seeds": [r["seed"] for r in inside],
            **{c: totals(inside, c) for c in ("static", "shifted")},
        },
        "timing_ms": {
            "observations": len(timing),
            "capture_to_plan_p50_p95_max": np.percentile(timing, [50, 95, 100]).tolist(),
            "refresh_compute_p50_p95_max": np.percentile(compute, [50, 95, 100]).tolist(),
            "capture_to_plan_within_40ms": sum(t <= 40 for t in timing),
        },
        "scenes": rows,
    }
    save_json(DEST / "result.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "scenes"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["freeze", "run"])
    args = parser.parse_args()
    protocol = frozen_protocol()
    path = DEST / "protocol.json"
    if args.stage == "freeze":
        if path.exists() and json.loads(path.read_text()) != protocol:
            raise ValueError("Frozen protocol differs")
        if not path.exists():
            save_json(path, protocol)
        print(file_hash(path))
    else:
        if json.loads(path.read_text()) != protocol:
            raise ValueError("Study differs from the frozen protocol")
        run(protocol)
