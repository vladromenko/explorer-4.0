"""Select one native wrist-camera retake on development starts, then test all assigned starts."""

import argparse
import json
import sys
import types
from pathlib import Path
from statistics import mean
from unittest.mock import patch

import cv2
import numpy as np
from scipy.stats import binomtest

from explorer4.conditioned_grasp import (
    LOOK_COMMAND,
    LOOK_STEPS,
    SLEW_DEGREES_PER_SECOND,
    file_hash,
    locate_cube,
)
from explorer4.grasp_measured import TRIAL_TICKS, MeasuredActions, next_target
from explorer4.grasp_shadow import close_to_look_state
from explorer4.paths import DATA, ROOT
from scripts.grasp_study.admission_native_v3 import IntegerVisibility
from scripts.grasp_study.evaluate import (
    SOURCE,
    VISION,
    environment,
    observe,
    save_json,
    sha_array,
)
from scripts.grasp_study.native_execution import NATIVE, REFERENCE, mock_executor
from scripts.peer_dock_study import frozen

OUT = DATA / "simlab/reports/grasp-active-initial-look-v1"
POSES = {
    "left": [72, 57, 24, 0, 75, 30],
    "right": [108, 57, 24, 0, 75, 30],
    "upper": [90, 67, 32, 12, 75, 30],
    "wrist": [90, 52, 17, 10, 100, 30],
}
BLOCKS = {
    "selection": range(986600, 986632),
    "calibration": range(986700, 986764),
    "validation": range(986764, 986796),
    "fresh": range(986800, 986832),
    "historical": range(88300, 88320),
}
SOURCES = (
    "scripts/grasp_study/active_initial_look.py",
    "scripts/grasp_study/admission_native_v3.py",
    "scripts/grasp_study/evaluate.py",
    "scripts/grasp_study/native_execution.py",
    "explorer4/grasp_shadow.py",
    "explorer4/grasp_measured.py",
)
MAX_MOVE_TICKS = 24


def register(out):
    out.mkdir(parents=True, exist_ok=True)
    frozen(
        out / "protocol.json",
        {
            "study": "grasp-active-initial-look-v1",
            "stages": {k: list(v) for k, v in BLOCKS.items()},
            "poses_native_deg": POSES,
            "selection": "Try each predeclared pose from a restored ordinary look on 32 separate development scenes. Choose the highest number of newly complete views on initial misses with a verified roundtrip and zero contacts other than cube/floor. Break ties by order above. Fixed pose for all subsequent scenes. At execution the only trigger is the full-view yes/no bit; no target XY, pixels of the hidden silhouette, extent of occlusion, or object coordinates enter the selector.",
            "visibility": "Unchanged v3 IntegerVisibility on 640x480, absolutely complete on-support silhouette in-frame. Its yes/no flag and confirmed bounding box simulate an operator or independently validated detector; the hidden mask is used to label completeness, never to choose where to look. Physical detector performance unknown.",
            "motion": "Retain original scripted initial look (20 ticks); new inspection and return use normal native direct guard with simulated measured joints only. Each leg at most 24 ticks at 20Hz with <=1.25 degrees measured maximum error for two consecutive samples. Stop on unexpected post-step MuJoCo contact (any pair except cube/floor), native rejection or task termination. Log incremental and total simulated seconds. No manipulation after failed return.",
            "calibration": "Independently fit a new OpenCV planar homography from full-box pixel centres at the selected pose to labelled cube XY on 64 calibration scenes, using full examples with a safe return; at least eight noncollinear samples. Accept only with >=8 full examples on 32 separate validation starts and p95 XY error <=8 mm. Coordinates used only for supervision and scoring. Original fixed-pose ResNet used only at its original look. Object size and camera are task-specific.",
            "endpoints": "On every fresh start, report base full-view, active full-view acquisition, and safe complete-view plus return, including refusers in the denominator. Record guard/contact/return failures, calibrated localization errors and RBF hull checks separately. Secondary grasp: same 32-example frozen cubic-position motor library as original (SciPy thin-plate spline), normal six-servo range/slew and native executor, 360 ticks, final qualifying carry/lift >50 mm continuously >=1s. No post hoc selection or replacement. For initially complete inputs both methods follow exactly the same single physical simulation path. For an initial miss compare baseline abstention with one retake. No more than 21.4 simulated seconds including first look, outbound/return and motor ticks. Historical 20 originally requested seeds are reported separately.",
            "sources": {n: file_hash(ROOT / n) for n in SOURCES},
            "localizer_sha256": file_hash(VISION),
            "motor_data_sha256": file_hash(SOURCE),
            "native_runtime_sha256": file_hash(ROOT / "agents/rosmaster/runtime.py"),
            "physical_trials": 0,
            "original_eligibility_note": "On the historical v3 development bank, 43/128 were fully visible and 29/128 also passed the existing predicted motor-support gate.",
        },
    )


def unexpected_contact(env):
    floor, cube = env.model.geom("floor").id, env.model.geom("cube").id
    for c in env.data.contact:
        if {c.geom1, c.geom2} != {floor, cube}:
            return [env.model.geom(c.geom1).name, env.model.geom(c.geom2).name]
    return None


def move(env, executor, target):
    command = np.asarray(env.observation()["state"], dtype=float)
    settled = 0
    for tick in range(1, MAX_MOVE_TICKS + 1):
        command += np.clip(
            np.asarray(target) - command,
            -SLEW_DEGREES_PER_SECOND * env.dt,
            SLEW_DEGREES_PER_SECOND * env.dt,
        )
        now = env.steps * env.dt
        try:
            executor.direct = (now, executor.validate_direct({"arm": command.tolist()}))
            executor.direct_step(env.dt, now)
        except (RuntimeError, ValueError) as exc:
            return {"ok": False, "ticks": tick - 1, "reason": f"native_guard: {exc}"}
        obs, _, done, timeout, info = env.step(executor.io.arm_command())
        hit = unexpected_contact(env)
        if hit or done or timeout:
            return {
                "ok": False,
                "ticks": tick,
                "reason": ("contact " + str(hit))
                if hit
                else info["termination_reason"],
            }
        error = float(np.max(np.abs(obs["state"] - target)))
        settled = settled + 1 if error <= 1.25 else 0
        if settled >= 2:
            return {"ok": True, "ticks": tick, "max_error_deg": error}
    return {
        "ok": False,
        "ticks": MAX_MOVE_TICKS,
        "reason": "pose_timeout",
        "max_error_deg": error,
    }


def retake(env, scorer, settings, pose):
    executor = mock_executor(env, settings)
    out = move(env, executor, pose)
    if not out["ok"]:
        return {"outbound": out, "view": None, "return": None}
    view = scorer(env)
    back = move(env, executor, LOOK_COMMAND)
    return {"outbound": out, "view": view, "return": back}


def usable(result):
    return bool(result["view"] and result["view"]["full"] and result["return"]["ok"])


def centre(view):
    l, t, r, b = view["box"]
    return [(l + r - 1) / 2, (t + b - 1) / 2]


def location(matrix, view):
    return cv2.perspectiveTransform(
        np.asarray([[centre(view)]], dtype=np.float64), matrix
    )[0, 0]


def summary_errors(errors):
    return (
        None
        if not errors
        else {
            "n": len(errors),
            "median_mm": float(np.median(errors)),
            "p95_mm": float(np.percentile(errors, 95)),
            "max_mm": max(errors),
        }
    )


def row_file(out, stage, seed, fn):
    path = out / stage / f"{seed}.json"
    receipt = file_hash(out / "protocol.json")
    if not path.is_file():
        row = fn()
        save_json(path, {**row, "protocol_sha256": receipt, "seed": seed})
    row = json.loads(path.read_text())
    if row["protocol_sha256"] != receipt or row["seed"] != seed:
        raise ValueError("Saved phase differs")
    return row


def drive_grasp(env, model, settings, xy):
    if not close_to_look_state(env.observation()["state"]):
        return {
            "executed": False,
            "hold": False,
            "reason": "return_outside_original_look",
        }
    if model.support.find_simplex(xy) < 0:
        return {"executed": False, "hold": False, "reason": "outside_motor_hull"}
    # This new observation adapter has already bound the alternative image and returned to the
    # measured original pose. Reuse the original plan and slew calculation without falsely
    # claiming the old camera observed the alternate image.
    model.reset()
    model.plan = model.plan_for_xy(xy)
    model.last = np.asarray(env.observation()["state"], dtype=float)
    executor = mock_executor(env, settings)
    consecutive = count = 0
    last = None
    outcome = "full_command_budget"
    for i in range(TRIAL_TICKS):
        obs = {
            "domain": model.input_domain,
            "robot_id": "rosmaster",
            "observation.state": env.observation()["state"],
        }
        now = env.steps * env.dt
        try:
            last = next_target(model, obs, i, last)
            executor.direct = (now, executor.validate_direct({"arm": last}))
            executor.direct_step(env.dt, now)
        except (ValueError, RuntimeError) as exc:
            outcome = f"native_guard: {exc}"
            break
        _, _, done, timeout, info = env.step(executor.io.arm_command())
        count += 1
        qualified = (
            env.data.body("task_cube").xpos[2] - env.object_half()[2] > 0.05
            and info["held"]
            and info["in_carry_pose"]
        )
        consecutive = consecutive + 1 if qualified else 0
        if timeout or (done and info["termination_reason"] != "held_in_carry_pose"):
            outcome = info["termination_reason"]
            break
    return {
        "executed": True,
        "hold": bool(count == TRIAL_TICKS and consecutive >= 20 and info["success"]),
        "reason": outcome,
        "ticks": count,
        "terminal_qualifying_s": consecutive * env.dt,
    }


def run(out):
    import torch

    from explorer4.resources import ResourceLease

    if not (out / "protocol.json").is_file():
        raise ValueError("Register the protocol first")
    register(out)
    cv2.setNumThreads(1)
    torch.set_num_threads(1)
    with REFERENCE.open() as f:
        settings = json.loads(next(f))["control_limits"]["arm_settings"]

    def no_transport(*args, **kwargs):
        raise RuntimeError("No hardware transport in this experiment")

    with (
        ResourceLease("grasp-active-initial-look"),
        patch.dict(sys.modules, {"serial": types.SimpleNamespace(Serial=no_transport)}),
        patch.object(
            sys, "path", [str(ROOT / "agents/rosmaster"), str(NATIVE), *sys.path]
        ),
    ):
        env = environment()
        scorer = IntegerVisibility()
        try:

            def dev(seed):
                initial, _ = observe(env, seed, render=False)
                base = scorer(env)
                candidates = {}
                for name, pose in POSES.items():
                    other, _ = observe(env, seed, render=False)
                    if initial != other:
                        raise ValueError("Candidate starts do not match")
                    candidates[name] = retake(env, scorer, settings, pose)
                return {"base": base, "candidates": candidates}

            demos = [
                row_file(out, "selection", s, lambda s=s: dev(s))
                for s in BLOCKS["selection"]
            ]
            gains = {
                n: sum(
                    not r["base"]["full"] and usable(r["candidates"][n]) for r in demos
                )
                for n in POSES
            }
            chosen = max(POSES, key=gains.get)
            frozen(
                out / "selection.json",
                {
                    "selected": chosen,
                    "gains_over_initial": gains,
                    "initial_full": sum(r["base"]["full"] for r in demos),
                    "n": len(demos),
                },
            )
            print("Selected", chosen, gains, flush=True)

            def labels(seed):
                initial, _ = observe(env, seed, render=False)
                r = retake(env, scorer, settings, POSES[chosen])
                return {
                    "raw": r,
                    "pixel": centre(r["view"]) if usable(r) else None,
                    "label_xy_m": initial["cube"][:2],
                }

            def samples(stage):
                return [
                    row_file(out, stage, s, lambda s=s: labels(s))
                    for s in BLOCKS[stage]
                ]

            train = [r for r in samples("calibration") if r["pixel"] is not None]
            matrix = None
            if len(train) >= 8:
                matrix, _ = cv2.findHomography(
                    np.array([r["pixel"] for r in train]),
                    np.array([r["label_xy_m"] for r in train]),
                    method=0,
                )
            validation = [r for r in samples("validation") if r["pixel"] is not None]
            errors = summary_errors(
                [
                    float(
                        1000
                        * np.linalg.norm(
                            location(matrix, r["raw"]["view"]) - r["label_xy_m"]
                        )
                    )
                    for r in validation
                ]
                if matrix is not None
                else []
            )
            accepted = bool(errors and errors["n"] >= 8 and errors["p95_mm"] <= 8)
            calibration = {
                "homography": matrix.tolist() if matrix is not None else None,
                "n_train_full": len(train),
                "n_train_assigned": len(BLOCKS["calibration"]),
                "n_validation_assigned": len(BLOCKS["validation"]),
                "errors": errors,
                "accepted": accepted,
            }
            frozen(out / "calibration-result.json", calibration)
            print("Calibration", accepted, errors, flush=True)
            model = MeasuredActions(None, SOURCE, VISION, "rbf", None)

            def test(seed):
                initial, rgb = observe(env, seed)
                base = scorer(env)
                fallback = None
                old = {
                    "executed": False,
                    "hold": False,
                    "reason": "initial_view_incomplete",
                }
                recovered = base["full"]
                safe = recovered
                xy = None
                if base["full"]:
                    xy = locate_cube(model.localizer, rgb)
                    old = drive_grasp(env, model, settings, xy)
                    active = old
                else:
                    fallback = retake(env, scorer, settings, POSES[chosen])
                    recovered = bool(fallback["view"] and fallback["view"]["full"])
                    safe = usable(fallback)
                    active = {
                        "executed": False,
                        "hold": False,
                        "reason": "missing_full_returned_view"
                        if not safe
                        else "uncalibrated_alternative",
                    }
                    if accepted and safe:
                        xy = location(matrix, fallback["view"])
                        active = drive_grasp(env, model, settings, xy)
                ticks = (
                    0
                    if fallback is None
                    else fallback["outbound"]["ticks"]
                    + (fallback["return"]["ticks"] if fallback["return"] else 0)
                )
                return {
                    "reset_sha256": initial["reset_sha256"],
                    "initial_rgb_sha256": sha_array(rgb),
                    "base": base,
                    "retake": fallback,
                    "active_full": recovered,
                    "safe_complete_with_return": safe,
                    "inspection_s": (LOOK_STEPS + ticks) * env.dt,
                    "base_outcome": old,
                    "active_outcome": active,
                    "xy_estimate_m": None if xy is None else xy.tolist(),
                    "xy_error_mm_scoring_only": None
                    if xy is None
                    else float(
                        1000 * np.linalg.norm(xy - np.asarray(initial["cube"][:2]))
                    ),
                }

            results = {}
            for stage in ("fresh", "historical"):
                group = [
                    row_file(out, stage, s, lambda s=s: test(s)) for s in BLOCKS[stage]
                ]
                gains = sum(
                    not x["base"]["full"] and x["safe_complete_with_return"]
                    for x in group
                )
                attempts = [x["retake"] for x in group if x["retake"]]
                reason_counts = {}
                for a in attempts:
                    for leg in (a["outbound"], a["return"]):
                        if leg and not leg["ok"]:
                            reason_counts[leg["reason"]] = (
                                reason_counts.get(leg["reason"], 0) + 1
                            )
                results[stage] = {
                    "n_all": len(group),
                    "initial_full": sum(x["base"]["full"] for x in group),
                    "retakes": len(attempts),
                    "active_full": sum(x["active_full"] for x in group),
                    "active_full_and_safe_return": sum(
                        x["safe_complete_with_return"] for x in group
                    ),
                    "paired_view_gains": gains,
                    "paired_view_losses": 0,
                    "paired_exact_p": float(binomtest(gains, gains).pvalue)
                    if gains
                    else 1,
                    "returned": sum(
                        bool(a["return"] and a["return"]["ok"]) for a in attempts
                    ),
                    "inspection_move_failures": reason_counts,
                    "mean_inspection_s": mean(x["inspection_s"] for x in group),
                    "initial_look_s": LOOK_STEPS * env.dt,
                    "original_grasp_attempts": sum(
                        r["base_outcome"]["executed"] for r in group
                    ),
                    "active_grasp_attempts": sum(
                        r["active_outcome"]["executed"] for r in group
                    ),
                    "original_terminal_holds": sum(
                        r["base_outcome"]["hold"] for r in group
                    ),
                    "active_terminal_holds": sum(
                        r["active_outcome"]["hold"] for r in group
                    ),
                    "alternate_xy_error_mm": summary_errors(
                        [
                            x["xy_error_mm_scoring_only"]
                            for x in group
                            if x["retake"] and x["xy_error_mm_scoring_only"] is not None
                        ]
                    ),
                    "seeds": [x["seed"] for x in group],
                }
                print(stage, results[stage], flush=True)
            frozen(
                out / "result.json",
                {
                    "status": "completed",
                    "domain": "MuJoCo; full-box confirmation is a simulated proxy",
                    "protocol_sha256": file_hash(out / "protocol.json"),
                    "physical_trials": 0,
                    "selection": json.loads((out / "selection.json").read_text()),
                    "calibration": calibration,
                    "results": results,
                },
            )
        finally:
            scorer.close()
            env.close()


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("phase", choices=("register", "run"))
    cli.add_argument("--output", type=Path, default=OUT)
    args = cli.parse_args()
    (register if args.phase == "register" else run)(args.output)
