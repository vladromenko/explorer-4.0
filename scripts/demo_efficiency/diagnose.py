"""Reconstruct where a recipient-only cube rollout stopped making progress."""

from collections import Counter
import json

import mujoco

from explorer4.paths import DATA
from explorer4.sim.floor_carry import FloorCarry

from .report import terminal


def diagnose(env, job, seeds, ticks):
    folder = DATA / "jobs" / job["id"]
    result = json.loads((folder / "result.json").read_text())
    if result["status"] != "completed" or [v["seed"] for v in result["trials"]] != seeds:
        raise ValueError("Completed evaluation did not use the registered scenes")
    rows = []
    for trial in result["trials"]:
        seed = trial["seed"]
        path = folder / f"floor-trial-{seed}.json"
        score = terminal(env, path, seed, result["checkpoint_sha256"], ticks)
        if score["success"] != (trial["outcome"] == "success"):
            raise ValueError("Evaluation and trajectory disagree")
        qpos = json.loads(path.read_text())["qpos"]
        env.reset(seed=seed)
        carry = FloorCarry(env)
        for q in qpos[1:]:
            env.data.qpos[:] = q
            mujoco.mj_forward(env.model, env.data)
            carry.measure()
        first_contact = next((i + 1 for i, v in enumerate(carry.samples) if v[3]), None)
        first_lift = next((i + 1 for i, v in enumerate(carry.samples) if v[0] > .05), None)
        closest = min(v[1] for v in carry.samples)
        peak = max(v[0] for v in carry.samples)
        if score["success"]:
            stage = "retained"
        elif first_lift is not None:
            if carry.samples[-1][0] <= .05:
                stage = "dropped_after_lift"
            elif carry.samples[-1][2] >= env.cfg["carry_tolerance_deg"]:
                stage = "outside_carry_pose"
            else:
                stage = "insufficient_terminal_hold"
        elif first_contact is not None:
            stage = "grasped_without_lift"
        elif closest < .06:
            stage = "near_cube_without_bilateral_contact"
        else:
            stage = "never_reached_cube"
        rows.append({
            **score, "stage": stage, "closest_tip_m": closest, "peak_bottom_height_m": peak,
            "first_bilateral_contact_tick": first_contact, "first_lift_tick": first_lift,
        })
    return {
        "job": job["id"], "checkpoint_sha256": result["checkpoint_sha256"],
        "successes": sum(row["success"] for row in rows), "attempts": len(rows),
        "stages": dict(Counter(row["stage"] for row in rows)), "trials": rows,
    }


def select_pair(results):
    """Prefer the registered primary dose, then 5 and 1, with measurable room to improve."""
    for k in (3, 5, 1):
        left, right = (results[f"T{arm}-k{k}"] for arm in (0, 1))
        if left["attempts"] != 12 or right["attempts"] != 12:
            raise ValueError("Expected 12 complete paired scenes")
        if [r["scene"] for r in left["trials"]] != [r["scene"] for r in right["trials"]]:
            raise ValueError("Pair did not use the same scenes")
        peak = max(left["successes"], right["successes"])
        if peak >= 2 and min(left["successes"], right["successes"]) < 12:
            return k
    return None
