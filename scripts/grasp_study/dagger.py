"""Bounded dataset aggregation for camera-guided corrections after the ROSMASTER arm moves."""

import argparse
import fcntl
import json
import random
import sys
import types
from pathlib import Path
from unittest.mock import patch

import cv2
import mujoco
import numpy as np
from scipy.interpolate import RBFInterpolator
from scipy.stats import binomtest

from explorer4.conditioned_grasp import (
    LOOK_COMMAND,
    MOTOR_SHA256,
    PHYSICS_SHA256,
    SLEW_DEGREES_PER_SECOND,
    VISION_SHA256,
    file_hash,
    load_localizer,
    locate_cube,
)
from explorer4.grasp_shadow import close_to_look_state
from explorer4.paths import DATA, ROOT
from scripts.grasp_study.evaluate import (
    OUTPUT,
    SOURCE,
    VISION,
    GraspMetrics,
    environment,
    observe,
    save_json,
    sha_array,
)
from scripts.grasp_study.moving_view import (
    WristTracker,
    clipped_delta,
    features,
    fit,
    predict,
)
from scripts.grasp_study.native_execution import NATIVE, REFERENCE, mock_executor
from scripts.grasp_study.refresh import capture, restore

OUT = DATA / "simlab/reports/grasp-dagger-v1"
GATE = tuple(range(971000, 971008))
TRAIN = [tuple(range(971100, 971112)), tuple(range(971200, 971212))]
DEV = tuple(range(940100, 940108))
QUERIES = (7, 14)
SHIFT_TICK = 6


def protocol():
    paths = [
        Path(__file__),
        Path(__file__).with_name("moving_view.py"),
        Path(__file__).with_name("refresh.py"),
        Path(__file__).with_name("native_execution.py"),
        Path(__file__).with_name("evaluate.py"),
        ROOT / "explorer4/conditioned_grasp.py",
        ROOT / "explorer4/grasp_shadow.py",
        ROOT / "explorer4/sim/rosmaster_arm.py",
        ROOT / "explorer4/sim/factory.py",
        ROOT / "explorer4/sim/models.py",
        ROOT / "explorer4/sim/variation.py",
        OUTPUT / "development/observations.json",
        ROOT / "explorer4/sim/vendor_rosmaster/arm_model.py",
        ROOT / "explorer4/sim/aligned.py",
        ROOT / "explorer4/sim/environment.py",
        ROOT / "agents/rosmaster/runtime.py",
        NATIVE / "cubebot/arm_model.py",
        NATIVE / "cubebot/robot_io.py",
        REFERENCE,
    ]
    return {
        "version": 1,
        "task": "MuJoCo wrist-camera recovery from a lateral cube displacement after movement starts",
        "question": "Can two in-motion observations with bounded Cartesian corrections improve terminal holding over a stale plan, generic tracking and matched expert-only imitation?",
        "upstream": [
            "https://proceedings.mlr.press/v15/ross11a.html",
            "https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html",
            "https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.lstsq.html",
        ],
        "inputs": "Student: first fixed-look RGB and frozen XY, wrist RGB at two moving poses, native proprioception, previous aim and command clock. Nominal vendor FK and measured nominal intrinsics. The pose-dependent planar warp uses the known top height of the 32 mm cube. No ground truth, segmentation, seed, displacement magnitude or intervention sign in student features.",
        "action": "Two radial target changes up to 15 mm each. Re-evaluate the same thin-plate-spline motor trajectory at the current phase. Native slew, tracking, floor and chassis guards remain enabled. Teacher measures current simulator XY only for expert actions/labels. It shares the bounded action space and low-level trajectory; it is a privileged feasible controller, not an optimality bound.",
        "intervention": {
            "after_completed_native_ticks": SHIFT_TICK,
            "shift_y_m_even_odd": [0.010, -0.010],
            "correction_ticks": QUERIES,
            "static_delta": 0,
        },
        "calibration": {
            "seeds": GATE,
            "conditions": ["shifted"],
            "arms": ["stale", "oracle"],
            "minimum_oracle_holds": 5,
            "must_match_or_exceed_stale": True,
            "minimum_rescued_shifted_scenes": 1,
            "moving_observation": "Across 16 oracle queries, require at least 12 pre-contact observations with >=64 externally scored visible cube pixels (640x480) and a valid RGB match, and median matched XY error <=12 mm. Missing queries count against coverage.",
        },
        "fit": {
            "round_seeds": TRAIN,
            "shift": "three of every four are shifted with balanced positive/negative across both rounds; fixed sign and condition per seed",
            "query_budget_per_algorithm": 48,
            "policy_round_1": "untrained geometric tracker",
            "policy_round_2": "round 1 student without expert mixing",
            "training": "DAgger labels all visited query states; the matched BC control sees the same seeds/conditions but the expert chooses corrections. Imperfect tracking causes abstention. Train on valid queries only. Both use the same standardized fixed-penalty (1) SciPy ridge model, no hyperparameter search. Log actual valid labels and second-query pose hashes.",
            "minimum_valid_labels": 8,
        },
        "development": {
            "seeds": DEV,
            "conditions": ["static", "shifted"],
            "arms": ["stale", "visual_servo", "bc", "dagger"],
            "fallback_if_visibility_or_label_gate_fails": ["stale", "return_to_look"],
            "primary": "Paired stable terminal hold in shifted development scenes, DAgger versus stale. Report discordant pairs and exact two-sided binomial; diagnostics versus geometric and BC. Advancement requires strictly more shifted holds than stale and no fewer static holds. Distinguish improvement over expert-only BC from improvement over stale control. A neutral/negative screen is a completed study. No confirmation or physical performance claim.",
        },
        "limits": "8 calibration scenes; at most 48 short acquisition prefixes and 64 full development episodes. Fallback returns through the native controller to the measured calibrated look with at most 40 extra approach ticks; rereads RGB and restarts the plan under the original episode deadline. No hardware transport, GPU training or changes to any frozen weights.",
        "source_sha256": {
            str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p.relative_to(DATA)): file_hash(p)
            for p in paths
        },
        "motor_sha256": MOTOR_SHA256,
        "vision_sha256": VISION_SHA256,
        "physics_sha256": PHYSICS_SHA256,
        "physical_trials": 0,
    }


def shift(env, delta):
    address = int(env.model.joint("cube_free").qposadr[0]) + 1
    desired = env.data.qpos.copy()
    velocity = env.data.qvel.copy()
    desired[address] += delta
    env.data.qpos[address] += delta
    mujoco.mj_forward(env.model, env.data)
    if not np.array_equal(env.data.qpos, desired) or not np.array_equal(velocity, env.data.qvel):
        raise ValueError("Displacement changed another position or velocity")


def visible_pixels(env):
    # Independent visibility scorer. Its result is appended only after the action is fixed.
    renderer = env.renderer
    renderer.enable_segmentation_rendering()
    try:
        renderer.update_scene(env.data, camera=env.camera_name)
        segmentation = renderer.render()
        return int(
            np.count_nonzero(
                (segmentation[:, :, 0] == env.model.geom("cube").id)
                & (segmentation[:, :, 1] == int(mujoco.mjtObj.mjOBJ_GEOM))
            )
        )
    finally:
        renderer.disable_segmentation_rendering()


class NativeEpisode:
    def __init__(self, env, settings, height):
        self.env = env
        self.executor = mock_executor(env, settings)
        self.metrics = GraspMetrics(env, height)
        self.command = env.observation()["state"].astype(float)
        self.reason = None

    def step(self, target):
        env, executor = self.env, self.executor
        limit = SLEW_DEGREES_PER_SECOND * env.dt
        self.command += np.clip(target - self.command, -limit, limit)
        now = env.steps * env.dt
        executor.direct = (now, executor.validate_direct({"arm": self.command.tolist()}))
        try:
            executor.direct_step(env.dt, now)
        except (ValueError, RuntimeError) as exc:
            self.reason = f"native_guard: {exc}"
            return
        _, _, done, truncated, info = env.step(executor.io.arm_command())
        self.metrics.measure(env, info)
        if done or truncated:
            self.reason = info["termination_reason"]


def run_episode(env, study, method, delta, model=None, collect=False, visibility=False):
    first, initial_state, first_xy, tracker, rbf, localizer, settings = study
    restore(env, initial_state)
    sim = NativeEpisode(env, settings, first["cube"][2])
    current = first_xy.copy()
    plan = rbf(current[None] / 0.05)[0]
    queries, branch, tick, elapsed_return = [], {}, 0, 0
    restart = False
    while not sim.reason:
        if tick == SHIFT_TICK and not restart:
            branch["pre_shift_physics_sha256"] = sha_array(env.snapshot()["physics"])
            branch["arm_motion_deg"] = float(
                np.max(np.abs(env.observation()["state"][:5] - tracker.joints[:5]))
            )
            if branch["arm_motion_deg"] <= 1 or sim.metrics.contact:
                sim.reason = "invalid_perturbation_before_motion_or_after_contact"
                break
            shift(env, delta)
            branch["post_shift_physics_sha256"] = sha_array(env.snapshot()["physics"])
        if tick in QUERIES and not restart:
            if method == "return_to_look":
                for _ in range(40):
                    sim.step(np.asarray(LOOK_COMMAND))
                    elapsed_return += 1
                    if sim.reason or close_to_look_state(env.observation()["state"]):
                        break
                if sim.reason:
                    break
                if not close_to_look_state(env.observation()["state"]):
                    sim.reason = "return_look_pose_not_reached"
                    break
                current = locate_cube(localizer, env.render()).astype(float)
                plan = rbf(current[None] / 0.05)[0]
                tick, restart = 0, True
            elif method != "stale":
                pose = env.observation()["state"].astype(float)
                rgb = env.render()
                observed, valid, confidence = tracker.read(rgb, pose)
                sample = features(tracker, pose, current, observed, confidence, tick)
                # No privileged input enters either learned or visual-servo inference.
                if method == "visual_servo":
                    action = clipped_delta(observed - current) if valid else np.zeros(2)
                elif method in ("bc", "dagger"):
                    action = predict(model, sample) if valid else np.zeros(2)
                elif method != "oracle":
                    raise ValueError(method)
                truth = env.data.body("task_cube").xpos[:2].copy()
                expert = clipped_delta(truth - current)
                if method == "oracle":
                    action = expert
                query = {
                    "tick": tick,
                    "pose_native": pose.tolist(),
                    "rgb_sha256": sha_array(rgb),
                    "before_scored_contact": not sim.metrics.contact,
                    "tracking_valid": valid,
                    "tracking_confidence": confidence,
                    "feature": sample.tolist(),
                    "camera_xy_m": observed.tolist(),
                    "current_xy_m": current.tolist(),
                    "expert_delta_m": expert.tolist(),
                    "action_m": action.tolist(),
                    "track_error_mm": float(1000 * np.linalg.norm(observed - truth)),
                }
                if visibility:
                    query["cube_visible_pixels"] = visible_pixels(env)
                queries.append(query)
                current += action
                plan = rbf(current[None] / 0.05)[0]
                if collect and tick == QUERIES[-1]:
                    sim.reason = "prefix_complete"
                    break
        sim.step(plan[min(tick, len(plan) - 1)])
        tick += 1
    return {
        **branch,
        **sim.metrics.result(sim.reason, env.steps),
        "queries": queries,
        "return_native_ticks": elapsed_return,
        "return_and_replay_extra_s": (elapsed_return + QUERIES[0]) * env.dt if restart else None,
        "elapsed_sim_s": float(env.elapsed),
    }


def paired(rows, first, second):
    a = [r[first]["outcome"] == "success" for r in rows]
    b = [r[second]["outcome"] == "success" for r in rows]
    gains, losses = sum(y and not x for x, y in zip(a, b)), sum(x and not y for x, y in zip(a, b))
    return {
        "n": len(a),
        "baseline_holds": sum(a),
        "candidate_holds": sum(b),
        "gains": gains,
        "losses": losses,
        "exact_p": binomtest(gains, gains + losses).pvalue if gains + losses else 1.0,
    }


class Study:
    def __init__(self, env):
        self.env = env
        self.development = json.loads((OUTPUT / "development/observations.json").read_text())
        self.digest = file_hash(OUT / "protocol.json")
        if file_hash(SOURCE) != MOTOR_SHA256 or file_hash(VISION) != VISION_SHA256:
            raise ValueError("Frozen weights or motor bank changed")
        with np.load(SOURCE, allow_pickle=False) as bank:
            self.rbf = RBFInterpolator(
                bank["xy"] / 0.05, bank["action"], kernel="thin_plate_spline", smoothing=0.005
            )
        self.localizer = load_localizer(VISION)
        with REFERENCE.open() as stream:
            self.settings = json.loads(next(stream))["control_limits"]["arm_settings"]

    def conditions(self, group, seed, delta, arms, *, prefix=False, visibility=False):
        import torch

        existing, scene = {}, None
        for name, (method, model) in arms.items():
            path = OUT / group / str(seed) / f"{name}.json"
            expected = {
                "protocol_sha256": self.digest,
                "seed": seed,
                "delta_y_m": delta,
                "policy": method,
                "model_sha256": digest_json(model),
                "prefix": prefix,
            }
            if path.exists():
                row = json.loads(path.read_text())
                if row["identity"] != expected or row["data_sha256"] != digest_json(row["data"]):
                    raise ValueError(f"Wrong saved episode {path}")
            else:
                if scene is None:
                    random.seed(seed)
                    np.random.seed(seed)
                    torch.manual_seed(seed)
                    first, rgb = observe(self.env, seed)
                    pose = self.env.observation()["state"]
                    if not close_to_look_state(pose):
                        raise ValueError("Initial look violates the frozen camera contract")
                    first_xy = locate_cube(self.localizer, rgb).astype(float)
                    if seed in DEV:
                        ref = self.development[str(seed)]
                        pixels = cv2.resize(rgb, (160, 120), interpolation=cv2.INTER_AREA)
                        if (
                            first != ref["initial"]
                            or sha_array(pixels) != ref["rgb_sha256"]
                            or sha_array(self.env.snapshot()["physics"]) != ref["lookup_state_sha256"]
                            or not np.allclose(first_xy, ref["predicted_xy"], rtol=0, atol=1e-7)
                        ):
                            raise ValueError(
                                "Development reset, first wrist image, lookup state or XY differs"
                            )
                    scene = (
                        first,
                        capture(self.env),
                        first_xy,
                        WristTracker(rgb, pose, first_xy),
                        self.rbf,
                        self.localizer,
                        self.settings,
                    )
                data = run_episode(self.env, scene, method, delta, model, prefix, visibility)
                row = {"identity": expected, "data_sha256": digest_json(data), "data": data}
                save_json(path, row)
                print(f"Completed {group}/{seed}/{name}", flush=True)
            existing[name] = row["data"]
        if len({r.get("post_shift_physics_sha256") for r in existing.values()}) != 1:
            raise ValueError(f"Different physics at the intervention for seed {seed}")
        return existing

    def execute(self):
        gate = [
            self.conditions(
                "calibration",
                seed,
                displacement(seed),
                {m: (m, None) for m in ["stale", "oracle"]},
                visibility=True,
            )
            for seed in GATE
        ]
        qs = [q for scene in gate for q in scene["oracle"]["queries"]]
        visible = [
            q
            for q in qs
            if q["before_scored_contact"] and q["tracking_valid"] and q["cube_visible_pixels"] >= 64
        ]
        median = float(np.median([q["track_error_mm"] for q in visible])) if visible else None
        oracle = paired(gate, "stale", "oracle")
        feasible = oracle["candidate_holds"] >= max(5, oracle["baseline_holds"]) and oracle["gains"] >= 1
        observable = len(visible) >= 12 and median is not None and median <= 12
        result = {
            "protocol_sha256": self.digest,
            "status": "completed",
            "domain": "simulator_development",
            "physical_trials": 0,
            "calibration": {
                "oracle": oracle,
                "observable": observable,
                "feasible": feasible,
                "expected_queries": 16,
                "observed_queries": len(qs),
                "valid_visible_queries": len(visible),
                "median_valid_visible_error_mm": median,
            },
            "models": {},
            "fit_rounds": [],
        }
        status = (
            "ready" if feasible and observable else "visibility_gate" if not observable else "teacher_gate"
        )
        if status == "ready":
            aggregated = {"bc": [], "dagger": []}
            for i, seeds in enumerate(TRAIN):
                methods = {
                    "bc": ("oracle", None),
                    "dagger": ("dagger", result["models"]["dagger"]) if i else ("visual_servo", None),
                }
                differing = 0
                for index, seed in enumerate(seeds):
                    delta = 0.0 if index % 4 == i else displacement(seed)
                    rows = self.conditions(f"round-{i + 1}", seed, delta, methods, prefix=True)
                    for name, row in rows.items():
                        aggregated[name].append(row)
                    if all(len(row["queries"]) == 2 for row in rows.values()):
                        differing += not np.array_equal(
                            rows["bc"]["queries"][1]["pose_native"],
                            rows["dagger"]["queries"][1]["pose_native"],
                        )
                result["models"] = {name: fit(rows) for name, rows in aggregated.items()}
                result["fit_rounds"].append(
                    {
                        "round": i + 1,
                        "second_pose_differs_on_seeds": differing,
                        "labelled": {
                            name: sum(len(r["queries"]) for r in rows) for name, rows in aggregated.items()
                        },
                        "valid_labels": {
                            name: sum(q["tracking_valid"] for r in rows for q in r["queries"])
                            for name, rows in aggregated.items()
                        },
                        "model_sha256": {
                            name: digest_json(model) for name, model in result["models"].items()
                        },
                    }
                )
                if any(model is None for model in result["models"].values()):
                    status = "insufficient_valid_training_labels"
                    break
        if status == "teacher_gate":
            result["decision"] = "stopped_before_collection_teacher_failed"
            return result
        if status == "ready":
            methods = {
                "stale": ("stale", None),
                "visual_servo": ("visual_servo", None),
                **{name: (name, model) for name, model in result["models"].items()},
            }
            candidate = "dagger"
        else:
            methods = {"stale": ("stale", None), "return_to_look": ("return_to_look", None)}
            candidate = "return_to_look"
        result["development"] = {}
        for condition in ["static", "shifted"]:
            rows = [
                self.conditions(
                    f"development/{condition}",
                    seed,
                    displacement(seed) if condition == "shifted" else 0.0,
                    methods,
                )
                for seed in DEV
            ]
            comparisons = {other: paired(rows, other, candidate) for other in methods if other != candidate}
            result["development"][condition] = {
                "terminal_hold_pairs": comparisons,
                "per_arm": {
                    name: {
                        "holds": sum(row[name]["outcome"] == "success" for row in rows),
                        "bilateral_contacts": sum(row[name]["bilateral_contact"] for row in rows),
                        "native_guards": sum(row[name]["reason"].startswith("native_guard:") for row in rows),
                        "reasons": [row[name]["reason"] for row in rows],
                        "terminal_hold_by_seed": [row[name]["outcome"] == "success" for row in rows],
                        "median_sim_s": float(np.median([row[name]["elapsed_sim_s"] for row in rows])),
                        "return_and_replay_extra_s": [row[name]["return_and_replay_extra_s"] for row in rows]
                        if name == "return_to_look"
                        else [],
                    }
                    for name in methods
                },
            }
        d = result["development"]
        shifted, static = [d[c]["terminal_hold_pairs"]["stale"] for c in ("shifted", "static")]
        result.update(
            candidate=candidate,
            candidate_reason=status,
            decision="positive_development_screen"
            if shifted["candidate_holds"] > shifted["baseline_holds"]
            and static["candidate_holds"] >= static["baseline_holds"]
            else "no_development_improvement",
        )
        return result


def digest_json(value):
    import hashlib

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    ).hexdigest()


def displacement(seed):
    return -0.010 if seed % 2 else 0.010


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["freeze", "run"])
    args = parser.parse_args()
    frozen = OUT / "protocol.json"
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        spec = json.loads(json.dumps(protocol()))
        if not frozen.exists() and args.stage == "freeze":
            save_json(frozen, spec)
        if not frozen.is_file() or json.loads(frozen.read_text()) != spec:
            raise ValueError(
                "Freeze the current protocol separately, or choose a new study version for changed source"
            )
        if args.stage == "freeze":
            print(file_hash(frozen))
            return
        result_file = OUT / "result.json"
        if result_file.is_file():
            result = json.loads(result_file.read_text())
            if result["protocol_sha256"] != file_hash(frozen) or result["status"] != "completed":
                raise ValueError("Conflicting existing result")
            print(result["decision"], flush=True)
            return
        import torch

        cv2.setNumThreads(1)
        torch.set_num_threads(1)

        def no_hardware(*args, **kwargs):
            raise AssertionError("No physical transport in this experiment")

        with (
            patch.dict(sys.modules, {"serial": types.SimpleNamespace(Serial=no_hardware)}),
            patch.object(sys, "path", [str(ROOT / "agents/rosmaster"), str(NATIVE), *sys.path]),
        ):
            env = environment()
            try:
                result = Study(env).execute()
            finally:
                env.close()
        save_json(result_file, result)
        print(result["decision"], flush=True)


if __name__ == "__main__":
    main()
