"""Score saved direct-image policy trajectories at 20 Hz using the original seeded geometry."""

import argparse
import json
from pathlib import Path

import mujoco
import numpy as np

from explorer4.conditioned_grasp import PHYSICS_SHA256, file_hash
from scripts.grasp_study.evaluate import GraspMetrics, environment, save_json, sha_array

ARMS = ("smolvla_finetuned", "smolvla_0_updates", "act", "diffusion")
SEEDS = list(range(940100, 940108))


def measure(env, trace, row):
    env.reset(seed=row["seed"])
    poses = np.asarray(trace["qpos"], dtype="<f8")
    if (
        poses.shape != (row["steps"] + 1, env.model.nq)
        or not np.all(np.isfinite(poses))
        or not np.array_equal(poses[0], env.data.qpos)
        or sha_array(poses[0]) != row["initial_qpos_sha256"]
    ):
        raise ValueError("Trace differs from the live healthy reset or trajectory length")
    cube = env.data.body("task_cube").xpos.copy()
    if not np.allclose(cube, row["cube_xyz0"], rtol=0, atol=1e-10):
        raise ValueError("Recorded cube start differs")
    metric = GraspMetrics(env, cube[2])
    bilateral_ticks = 0
    strict_bilateral_ticks = 0
    longest = run = 0
    for pose in poses[1:]:
        env.data.qpos[:] = pose
        mujoco.mj_fwdPosition(env.model, env.data)
        info = env.info()
        sides, touching = set(), set()
        for c in env.data.contact:
            a, b = env.model.geom_bodyid[[c.geom1, c.geom2]]
            other = b if a == metric.cube else a if b == metric.cube else None
            side = metric.jaw_side.get(other)
            if side:
                sides.add(side)
                if c.dist <= 0:
                    touching.add(side)
        bilateral_ticks += len(sides) == 2
        strict_bilateral_ticks += len(touching) == 2
        run = run + 1 if info["held"] and info["in_carry_pose"] else 0
        longest = max(longest, run)
        metric.measure(env, info)
    return {
        "seed": row["seed"],
        "terminal_success": row["outcome"] == "success",
        "recorded_reason": row["reason"],
        "contact": metric.contact,
        "bilateral": bool(bilateral_ticks),
        "bilateral_ticks": bilateral_ticks,
        "bilateral_nonpositive_distance_ticks": strict_bilateral_ticks,
        "peak_lift_cm": 100 * float(metric.peak_lift),
        "recorded_peak_lift_cm": row["max_lift_cm"],
        "recorded_ever_held": row["ever_held"],
        "reconstructed_ever_held": bool(metric.held),
        "longest_carry_s": longest * env.dt,
        "final_continuous_carry_s": run * env.dt,
        "initial_qpos_sha256": row["initial_qpos_sha256"],
    }


def run(directory):
    result = json.loads((directory / "result.json").read_text())
    if result["seeds"] != SEEDS or set(result["results"]) != set(ARMS) or result["physical_trials"] != 0:
        raise ValueError("Incomplete frozen evaluation")
    report = {
        "method": "MuJoCo position-stage reconstruction at saved 20 Hz joint/free-body poses. Counts geometric contacts at those poses, without reconstructing forces or unsampled substeps.",
        "physical_trials": 0,
        "results_sha256": file_hash(directory / "result.json"),
        "arms": {},
    }
    env = environment()
    try:
        for arm in ARMS:
            root = directory / arm
            summary = json.loads((root / "evaluation.json").read_text())
            if (
                summary["model"]["xml_sha256"] != PHYSICS_SHA256
                or [t["seed"] for t in summary["trials"]] != SEEDS
            ):
                raise ValueError("Scene order or simulator geometry differs")
            rows = []
            for trial in summary["trials"]:
                trace = json.loads((root / f"floor-trial-{trial['seed']}.json").read_text())
                if (
                    trace["seed"] != trial["seed"]
                    or trace["fps"] != 20
                    or trace["outcome"] != trial["outcome"]
                    or trace["model"] != PHYSICS_SHA256
                    or trace["checkpoint_sha256"] != summary["checkpoint_sha256"]
                ):
                    raise ValueError("Saved trace belongs to a different policy or scene")
                rows.append(measure(env, trace, trial))
            report["arms"][arm] = {
                "terminal_holds": sum(r["terminal_success"] for r in rows),
                "contact_scenes": sum(r["contact"] for r in rows),
                "bilateral_scenes": sum(r["bilateral"] for r in rows),
                "bilateral_nonpositive_scenes": sum(
                    r["bilateral_nonpositive_distance_ticks"] > 0 for r in rows
                ),
                "checkpoint_sha256": summary["checkpoint_sha256"],
                "scenes": rows,
            }
    finally:
        env.close()
    target = directory / "contact-replay.json"
    if target.exists() and json.loads(target.read_text()) != report:
        raise ValueError("Conflicting existing replay")
    save_json(target, report)
    print({k: {m: v for m, v in a.items() if m != "scenes"} for k, a in report["arms"].items()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    run(parser.parse_args().report)
