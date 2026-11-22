"""Compare random and farthest-first selection of 32 simulator demonstrations on the native arm path."""

import argparse
import fcntl
import json
import os
import sys
import time
import types
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from scipy.interpolate import RBFInterpolator
from scipy.spatial import ConvexHull, Delaunay
from scipy.stats import binomtest

from explorer4.conditioned_grasp import (
    LOOK_STEPS,
    PHYSICS_SHA256,
    PROFILE,
    VISION_SHA256,
    file_hash,
    load_localizer,
    locate_cube,
)
from explorer4.paths import DATA, ROOT
from explorer4.sim.factory import EXPERTS
from scripts.grasp_study import native_execution as native
from scripts.grasp_study.evaluate import (
    VISION,
    environment,
    observe,
    save_json,
    sha_array,
)
from scripts.grasp_study.refresh import capture, restore, snapshot_hash

OUTPUT = DATA / "simlab/reports/rosmaster-grasp-coverage-design-v1-1"
TRAIN = list(range(974000, 974128))
TEST = list(range(975000, 975020))
METHODS = ("random", "farthest_first")
N = 32
HORIZON = 220
MAX_TICKS = 360
# This included training demonstration provides only the deployed arm configuration.
SETTINGS_SOURCE = (
    DATA
    / "datasets/rosmaster_pick_place/5f7b11c3f7024539942456435c9617af/research.jsonl"
)
SOURCES = (
    "scripts/grasp_study/coverage_design.py",
    "scripts/grasp_study/evaluate.py",
    "scripts/grasp_study/native_execution.py",
    "scripts/grasp_study/refresh.py",
    "explorer4/conditioned_grasp.py",
    "explorer4/grasp_shadow.py",
    "explorer4/sim/factory.py",
    "explorer4/sim/aligned.py",
    "explorer4/sim/environment.py",
    "explorer4/sim/vendor_rosmaster/arm_model.py",
    "agents/rosmaster/runtime.py",
)


def read(path):
    return json.loads(path.read_text())


def frozen(path, value):
    if path.exists():
        if read(path) != value:
            raise ValueError(f"Registered data changed: {path}")
    else:
        save_json(path, value)


def settings():
    with SETTINGS_SOURCE.open() as f:
        return json.loads(next(f))["control_limits"]["arm_settings"]


def protocol():
    sha = {name: file_hash(ROOT / name) for name in SOURCES}
    for name in ("cubebot/robot_io.py", "cubebot/arm_model.py"):
        sha["native/" + name] = file_hash(native.NATIVE / name)
    return {
        "version": "1.1",
        "initial_protocol_sha256": "6acfbf9e4563d8c32e9b766d8a53856887eadd7e6d0633714d3563e290dd6b82",
        "pre_evaluation_correction": "Initial collector stopped at the first successful expert trace because its phase is named grasp, not close. The original protocol, runner and attempt remain archived. Both allocations, budgets and outcomes are unchanged. Restarted collection in a separate directory before any test reset.",
        "task": PROFILE,
        "domain": "MuJoCo. No physical transport.",
        "physics_sha256": PHYSICS_SHA256,
        "sources_sha256": sha,
        "vision_sha256": VISION_SHA256,
        "arm_settings": settings(),
        "candidate_seeds": TRAIN,
        "test_seeds": TEST,
        "methods": list(METHODS),
        "successful_demos_per_method": N,
        "attempt_cap_per_method": 64,
        "allocation_seed": 237100,
        "selection": "Same 128 nominal seeded resets. Freeze both complete orders before any expert rollout. Random PCG64 permutation; farthest-first starts with its first seed and maximises Euclidean distance in reset XY to the selected set. Resolve distance ties in that same random order. Take the first 32 actual successful expert runs, with at most 64 attempted per method. A shared seed may reuse its identical already measured run, and counts toward both budgets.",
        "expert": "Registered EXPERTS[rosmaster_floor_pick_recorded_start_sim]. True reset XY and the teacher's own privileged cube pose are permitted only in design and demonstration labels. Preserve all failure reasons, phase counts, simulation ticks and acquisition elapsed time.",
        "fit": "Float64 SciPy thin-plate RBF, XY divided by 0.05 m, smoothing 0.005; fit first 220 six-servo targets, repeating terminal command if shorter. Calibration and controls identical. No test results in training.",
        "evaluation": "Twenty new ordinary nominal starts, new seed block disjoint from collection. One frozen ResNet-18 look per scene shared by both libraries, identical complete state, native guard/slew, 20 Hz and at most 360 arm ticks after looking. Fit both banks and pass shape, provenance and sensitivity checks before opening any test seed.",
        "primary": "Independent simulator terminal stable carry on every paired scene under native limits. Secondary: additionally count success only if estimated XY lies inside each bank's convex hull as required by the field admission. Report abstentions as unsuccessful on the full 20. Simulation executes both counterfactual paths for diagnosis.",
        "analysis": "Paired terminal wins/losses/both/neither; exact two-sided binomial sign test on discordant primary outcomes; reached 50 mm and lost hold, guards, occupancy, nearest-distance, call time and attempt costs. One pool and one policy per acquisition rule. No test-based selection, retuning or new physical claims.",
        "upstream": {
            "farthest_first": "https://sites.cs.ucsb.edu/~teo/papers/TCS-ktmm.pdf",
            "initial_state_diversity": "https://proceedings.mlr.press/v229/mandlekar23a.html",
        },
    }


def allocation(env, spec):
    points = []
    for seed in TRAIN:
        env.reset(seed=seed)
        points.append(env.data.body("task_cube").xpos[:2].copy())
    points = np.array(points)
    random = np.random.default_rng(spec["allocation_seed"]).permutation(len(TRAIN))
    ordered = points[random]
    selected = [0]
    distances = np.linalg.norm(ordered - ordered[0], axis=1)
    while len(selected) < len(ordered):
        distances[selected] = -1
        following = int(np.argmax(distances))
        selected.append(following)
        distances = np.minimum(
            distances, np.linalg.norm(ordered - ordered[following], axis=1)
        )
    return {
        "points": dict(zip(map(str, TRAIN), points.tolist(), strict=True)),
        "orders": {
            "random": [TRAIN[i] for i in random],
            "farthest_first": [TRAIN[random[i]] for i in selected],
        },
        "protocol_sha256": file_hash(OUTPUT / "protocol.json"),
    }


def save_bank(path, **arrays):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with np.load(path, allow_pickle=False) as old:
            if set(old.files) != set(arrays) or any(
                not np.array_equal(old[k], v) for k, v in arrays.items()
            ):
                raise ValueError(f"Saved demonstration array changed: {path}")
    else:
        tmp = path.with_suffix(".tmp")
        with tmp.open("wb") as f:
            np.savez(f, **arrays)
        os.replace(tmp, path)


def expert_run(env, seed, xy):
    path = OUTPUT / "expert" / f"{seed}.json"
    trajectory = path.with_suffix(".npz")
    if path.exists():
        row = read(path)
        if (
            row["seed"] != seed
            or row["xy"] != xy
            or row["allocation_sha256"] != file_hash(OUTPUT / "allocation.json")
            or row["trajectory_sha256"] != file_hash(trajectory)
        ):
            raise ValueError("Saved expert trace differs")
        return row
    start = time.monotonic()
    env.reset(seed=seed)
    if env.data.body("task_cube").xpos[:2].tolist() != xy:
        raise ValueError("Reset target differs from the preallocated point")
    teacher = EXPERTS[PROFILE](env)
    actions = []
    phases = []
    while True:
        try:
            action = teacher.action()
        except RuntimeError as exc:
            if str(exc) != "ROSMASTER IK cannot reach the floor object":
                raise
            outcome, reason = "failure", "teacher_ik_unreachable"
            break
        actions.append(action.copy())
        if not phases or phases[-1]["phase"] != teacher.phase:
            phases.append({"phase": teacher.phase, "first_tick": len(actions) - 1})
        _, _, done, timed, info = env.step(action)
        if done or timed:
            outcome, reason = info["outcome"], info["termination_reason"]
            break
    array = np.asarray(actions, dtype=np.float64).reshape(-1, 6)
    if not np.isfinite(array).all():
        raise ValueError("Invalid expert trace")
    save_bank(trajectory, action=array)
    row = {
        "seed": seed,
        "xy": xy,
        "outcome": outcome,
        "reason": reason,
        "phases": phases,
        "ticks": len(array),
        "seconds_sim": len(array) * env.dt,
        "elapsed_s": time.monotonic() - start,
        "trajectory_sha256": file_hash(trajectory),
        "allocation_sha256": file_hash(OUTPUT / "allocation.json"),
    }
    frozen(path, row)
    return row


def collect():
    spec = protocol()
    frozen(OUTPUT / "protocol.json", spec)
    env = environment()
    try:
        design = allocation(env, spec)
        frozen(OUTPUT / "allocation.json", design)
        registries = {}
        for method in METHODS:
            tried = []
            xy = []
            actions = []
            for seed in design["orders"][method][: spec["attempt_cap_per_method"]]:
                r = expert_run(env, seed, design["points"][str(seed)])
                tried.append(r)
                if r["outcome"] != "success":
                    continue
                if r["reason"] != "held_in_carry_pose" or not {
                    "grasp",
                    "lift",
                    "carry",
                } <= {v["phase"] for v in r["phases"]}:
                    raise ValueError("Successful expert lacks completed grasp phases")
                with np.load(
                    OUTPUT / "expert" / f"{seed}.npz", allow_pickle=False
                ) as b:
                    seq = b["action"]
                    actions.append(seq[np.minimum(np.arange(HORIZON), len(seq) - 1)])
                xy.append(r["xy"])
                if len(xy) == N:
                    break
            if len(xy) != N:
                raise RuntimeError(
                    f"Collection gate: {method} produced {len(xy)}/32 eligible traces"
                )
            pts = np.array(xy)
            targets = np.array(actions)
            bank = OUTPUT / "banks" / f"{method}.npz"
            save_bank(bank, xy=pts, action=targets)
            if targets.shape != (N, HORIZON, 6) or len(np.unique(pts, axis=0)) != N:
                raise ValueError("Degenerate motor bank")
            model = fit(bank)
            if (
                np.max(np.abs(model(pts[[0], :] / 0.05) - model(pts[[1], :] / 0.05)))
                < 0.1
            ):
                raise ValueError("Motor bank insensitive to position")
            dist = np.linalg.norm(
                np.array(list(design["points"].values()))[:, None, :] - pts, axis=2
            ).min(axis=1)
            registries[method] = {
                "bank_sha256": file_hash(bank),
                "attempts": [
                    {
                        k: r[k]
                        for k in ("seed", "outcome", "reason", "ticks", "elapsed_s")
                    }
                    for r in tried
                ],
                "accepted_seeds": [
                    r["seed"] for r in tried if r["outcome"] == "success"
                ],
                "attempts_n": len(tried),
                "charged_expert_ticks": sum(r["ticks"] for r in tried),
                "charged_expert_elapsed_s": sum(r["elapsed_s"] for r in tried),
                "training_hull_area_cm2": float(ConvexHull(pts).volume * 10000),
                "candidate_cover_radius_mm": float(1000 * dist.max()),
                "candidate_mean_distance_mm": float(1000 * dist.mean()),
            }
            print(f"{method}: {len(xy)} accepted in {len(tried)} attempts", flush=True)
        frozen(
            OUTPUT / "training.json",
            {
                "protocol_sha256": file_hash(OUTPUT / "protocol.json"),
                "allocation_sha256": file_hash(OUTPUT / "allocation.json"),
                "methods": registries,
            },
        )
    finally:
        env.close()


def fit(path):
    with np.load(path, allow_pickle=False) as bank:
        return RBFInterpolator(
            bank["xy"] / 0.05,
            bank["action"],
            kernel="thin_plate_spline",
            smoothing=0.005,
        )


def evaluate():
    import torch

    spec = protocol()
    if read(OUTPUT / "protocol.json") != spec:
        raise ValueError("Frozen evaluation recipe changed")
    training = read(OUTPUT / "training.json")
    source_hash = file_hash(OUTPUT / "training.json")
    if training["protocol_sha256"] != file_hash(OUTPUT / "protocol.json") or training[
        "allocation_sha256"
    ] != file_hash(OUTPUT / "allocation.json"):
        raise ValueError("Training gate mismatch")
    models = {}
    points = {}
    for method in METHODS:
        path = OUTPUT / "banks" / f"{method}.npz"
        if file_hash(path) != training["methods"][method]["bank_sha256"]:
            raise ValueError("Changed weights")
        models[method] = fit(path)
        with np.load(path, allow_pickle=False) as bank:
            points[method] = bank["xy"].copy()
    torch.set_num_threads(1)
    cv2.setNumThreads(1)
    estimator = load_localizer(VISION)
    env = environment()
    env.deadline_s = (LOOK_STEPS + MAX_TICKS) * env.dt
    rows = []

    def no_serial(*args, **kwargs):
        raise AssertionError("Physical transport is disabled")

    try:
        with (
            patch.dict(
                sys.modules, {"serial": types.SimpleNamespace(Serial=no_serial)}
            ),
            patch.object(
                sys,
                "path",
                [str(ROOT / "agents/rosmaster"), str(native.NATIVE), *sys.path],
            ),
        ):
            for seed in TEST:
                path = OUTPUT / "test" / f"{seed}.json"
                png = OUTPUT / "frames" / f"{seed}.png"
                if path.exists():
                    row = read(path)
                    if (
                        row["seed"] != seed
                        or row["training_sha256"] != source_hash
                        or row["png_sha256"] != file_hash(png)
                    ):
                        raise ValueError("Saved test row differs")
                else:
                    initial, image = observe(env, seed)
                    state = capture(env)
                    branch = snapshot_hash(state)
                    # Neither truth nor another condition's result enters these two plans.
                    rgb = cv2.resize(image, (160, 120), interpolation=cv2.INTER_AREA)
                    query = locate_cube(estimator, rgb).astype(np.float64)
                    plans = {
                        m: model(query[None] / 0.05)[0] for m, model in models.items()
                    }
                    png.parent.mkdir(parents=True, exist_ok=True)
                    ok, encoded = cv2.imencode(".png", rgb[:, :, ::-1])
                    if not ok:
                        raise OSError("Could not encode evidence")
                    if png.exists() and png.read_bytes() != encoded.tobytes():
                        raise ValueError("Original RGB differs")
                    if not png.exists():
                        png.write_bytes(encoded.tobytes())
                    truth = np.array(initial["cube"][:2])
                    row = {
                        "seed": seed,
                        "initial": initial,
                        "branch_sha256": branch,
                        "training_sha256": source_hash,
                        "rgb_sha256": sha_array(rgb),
                        "png_sha256": file_hash(png),
                        "predicted_xy": query.tolist(),
                        "localization_error_mm": float(
                            1000 * np.linalg.norm(query - truth)
                        ),
                        "methods": {},
                    }
                    for m in METHODS:
                        restore(env, state)
                        result = native.simulate(
                            env, plans[m], initial["cube"][2], spec["arm_settings"]
                        )
                        if result["executed_control_steps"] > MAX_TICKS:
                            raise ValueError("Exceeded physical action limit")
                        hull = Delaunay(points[m])
                        admitted = bool(hull.find_simplex(query) >= 0)
                        row["methods"][m] = {
                            **result,
                            "plan_sha256": sha_array(plans[m]),
                            "query_in_hull": admitted,
                            "truth_in_hull": bool(hull.find_simplex(truth) >= 0),
                            "nearest_demo_mm": float(
                                1000 * np.linalg.norm(points[m] - truth, axis=1).min()
                            ),
                            "hull_gated_hold": admitted
                            and result["outcome"] == "success",
                        }
                    frozen(path, row)
                rows.append(row)
                print(f"paired {seed}", flush=True)
    finally:
        env.close()

    def comparison(field):
        copies = [
            [
                r["methods"][m]["outcome"] == "success"
                if field == "terminal"
                else r["methods"][m][field]
                for m in METHODS
            ]
            for r in rows
        ]
        counts = [
            sum(tuple(x) == v for x in copies)
            for v in ((True, False), (False, True), (True, True), (False, False))
        ]
        a, b = counts[:2]
        return dict(
            zip(("random_only", "coverage_only", "both", "neither"), counts),
            exact_two_sided_p=binomtest(b, a + b).pvalue if a + b else 1.0,
        )

    summary = {}
    for m in METHODS:
        rr = [r["methods"][m] for r in rows]
        summary[m] = {
            "holds": sum(v["outcome"] == "success" for v in rr),
            "hull_gated_holds": sum(v["hull_gated_hold"] for v in rr),
            "query_in_hull": sum(v["query_in_hull"] for v in rr),
            "truth_in_hull": sum(v["truth_in_hull"] for v in rr),
            "lift_over_50mm_but_no_hold": sum(
                v["peak_lift_m"] > 0.05 and v["outcome"] != "success" for v in rr
            ),
            "native_guard_stops": sum(
                v["reason"].startswith("native_guard") for v in rr
            ),
            "mean_nearest_demo_mm": float(np.mean([v["nearest_demo_mm"] for v in rr])),
        }
    frozen(
        OUTPUT / "result.json",
        {
            "status": "completed",
            "domain": "simulation",
            "training_sha256": source_hash,
            "test_seeds": TEST,
            "methods": summary,
            "paired_primary": comparison("terminal"),
            "paired_hull_gated": comparison("hull_gated_hold"),
            "rows": rows,
            "physical_trials": 0,
        },
    )
    print(summary, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("collect", "evaluate"))
    stage = parser.parse_args().stage
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        (collect if stage == "collect" else evaluate)()
