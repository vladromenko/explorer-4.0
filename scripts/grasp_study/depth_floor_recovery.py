"""Paired floor-cube recovery using a bounded camera look, metric depth and the existing IK."""

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from multiprocessing import get_context
from pathlib import Path

import mujoco
import numpy as np

from explorer4.conditioned_grasp import LOOK_COMMAND, SLEW_DEGREES_PER_SECOND
from explorer4.floor_cube_localization import cube_center, top_surface
from explorer4.paths import DATA, ROOT
from explorer4.resources import ResourceLease
from explorer4.sim.factory import make
from explorer4.sim.floor_carry import FloorCarry
from explorer4.sim.skill_transfer import TransferVerifier
from explorer4.sim_protocol import scene_revision, sha256_file

from .evaluate import ik_targets, save_json, sha_array

PROFILE = "rosmaster_floor_pick_sim"
SAME = tuple(range(987140, 987152))
FRESH = tuple(range(987200, 987216))
LOOKS = (([90, 130, 0, -15, 90, 30], 25), (LOOK_COMMAND, 45))
SIZE = .032
TICKS = 360
OUTPUT = DATA / "simlab/reports/floor-depth-recovery-v1"
BASELINE = DATA / "simlab/reports/demo-efficiency-controls-20261123/followup.json"


def capture(env, renderer):
    renderer.update_scene(env.data, camera=env.camera_name)
    depth = renderer.render()
    camera = env.model.camera(env.camera_name).id
    h, w = depth.shape
    if env.model.cam_sensorsize[camera, 1] > 0:
        raise ValueError("This test expects the floor scene's FOV camera")
    focal = (.5 * h) / np.tan(np.deg2rad(env.model.cam_fovy[camera]) / 2)
    transform = np.eye(4)
    transform[:3, :3] = env.data.cam_xmat[camera].reshape(3, 3) @ np.diag([1, -1, -1])
    transform[:3, 3] = env.data.cam_xpos[camera]
    return depth, (focal, focal, (w - 1) / 2, (h - 1) / 2), transform


def simulate(seed):
    with make(PROFILE, images=False) as env:
        env.reset(seed=seed)
        baseline_reset = sha_array(np.asarray(env.data.qpos, dtype="<f8"))
        bounds = (env.cfg["object_x_m"], env.cfg["object_y_m"])
        carry = FloorCarry(env)
        guard = TransferVerifier(env)
        env.physics_observer = guard
        command = env.observation()["state"].astype(float)
        slew = SLEW_DEGREES_PER_SECOND * env.dt
        digest = hashlib.sha256()

        def move(target):
            command[:] += np.clip(np.asarray(target) - command, -slew, slew)
            _, _, terminated, timeout, info = env.step(command)
            carry.measure()
            digest.update(np.asarray(env.data.qpos, dtype="<f8").tobytes())
            return not timeout and not (terminated and info["outcome"] == "failure") and not guard.forbidden_pairs

        renderer = mujoco.Renderer(env.model, height=240, width=320)
        renderer.enable_depth_rendering()
        measured = None
        look_log = []
        views = []
        reason = "unobserved_cube"
        try:
            for pose, ticks in LOOKS:
                if not all(move(pose) for _ in range(ticks)):
                    reason = "look_motion_guard"
                    break
                depth, intrinsics, transform = capture(env, renderer)
                points = top_surface(depth, intrinsics, transform, SIZE, bounds)
                views.append(points)
                measured = cube_center(points, SIZE, bounds)
                if measured is None and len(views) > 1:
                    measured = cube_center(np.concatenate(views), SIZE, bounds)
                look_log.append({"ticks": env.steps, "depth_sha256": sha_array(depth),
                                 "surface_samples": len(points), "accepted": measured is not None})
                if measured is not None:
                    break
        finally:
            renderer.close()

        estimate_error = None
        if measured is not None:
            # Cube pose is read here only to score the sensor, never to drive the arm.
            estimate_error = float(np.linalg.norm(measured - env.data.body("task_cube").xpos[:2]))
            reason = "unreachable_target"
            for target in ik_targets(env, measured):
                if not move(target):
                    reason = "motion_guard"
                    break
                if env.steps == TICKS:
                    reason = "retained" if carry.success else "terminal_hold_not_verified"
                    break
        return {
            "seed": seed, "initial_qpos_sha256": baseline_reset, "steps": env.steps,
            "looks": look_log, "target_xy_m": None if measured is None else measured.tolist(),
            "xy_error_m_scoring_only": estimate_error, "success": reason == "retained", "reason": reason,
            "physics_trace_sha256": digest.hexdigest(),
            "contacts": guard.report()["forbidden_contact_pairs"],
            "terminal_samples": carry.samples[-(env.fps + 1):],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    protocol = {
        "scene": PROFILE, "scene_revision": scene_revision(PROFILE),
        "same_scenes": list(SAME), "fresh_scenes": list(FRESH),
        "looks": [[p, n] for p, n in LOOKS], "ticks": TICKS, "cube_side_m": SIZE,
        "endpoint": "Bilateral floor carry v2, last one second at 20 Hz and forbidden arm contact guard",
        "scope": "Simulated calibrated metric depth. No cube coordinates or semantic ID enter the controller.",
        "source_sha256": {file: sha256_file(ROOT / file) for file in (
            "explorer4/floor_cube_localization.py", "explorer4/sim/floor_carry.py",
            "scripts/grasp_study/evaluate.py", "scripts/grasp_study/depth_floor_recovery.py",
        )},
        "baseline_sha256": sha256_file(BASELINE),
    }
    with ResourceLease("simulation_world"):
        registered = OUTPUT / "protocol.json"
        if registered.exists() and json.loads(registered.read_text()) != protocol:
            raise ValueError("Registered protocol changed")
        save_json(registered, protocol)
        complete = []
        missing = [s for s in SAME + FRESH if not (OUTPUT / "trials" / f"{s}.json").exists()]
        with ProcessPoolExecutor(max_workers=args.workers, mp_context=get_context("spawn")) as workers:
            for row in workers.map(simulate, missing):
                save_json(OUTPUT / "trials" / f"{row['seed']}.json", row)
                print(row["seed"], row["success"], row["reason"], flush=True)
        for seed in SAME + FRESH:
            complete.append(json.loads((OUTPUT / "trials" / f"{seed}.json").read_text()))
        baseline = json.loads(BASELINE.read_text())["initial"]
        for branch in baseline.values():
            if [(r["scene"], r["initial_qpos_sha256"]) for r in branch["trials"]] != [
                (r["seed"], r["initial_qpos_sha256"]) for r in complete[:len(SAME)]
            ]:
                raise ValueError("Baseline and corrected policy did not use the same resets")
        save_json(OUTPUT / "result.json", {
            "protocol_sha256": sha256_file(registered), "rows": complete,
            "same": {"successes": sum(r["success"] for r in complete[:len(SAME)]), "attempts": len(SAME)},
            "fresh": {"successes": sum(r["success"] for r in complete[len(SAME):]), "attempts": len(FRESH)},
            "baseline": {name: {"successes": b["successes"], "attempts": b["attempts"]}
                         for name, b in baseline.items()},
            "physical_trials": 0,
        })


if __name__ == "__main__":
    main()
