"""Fit one MuJoCo task from a frozen physical training partition.

Report: .venv-sim/bin/python -m scripts.sim_align --plan-id <SHA256>
Apply the measured scene: add --apply. The diagnostic --all-data-pilot PROFILE only reports.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from explorer4 import datasets

BLOCKS = {
    "so101_pick_place": "so101_handover",
    "rosmaster_pick_place": "rosmaster_floor_pick",
}
MIN_DEMOS = 5


def demos(plan_id=None, *, pilot=None):
    if bool(plan_id) == bool(pilot):
        raise ValueError(
            "Choose one frozen real plan or one explicit all-data diagnostic"
        )
    if plan_id:
        # Scope both provenance checks and reads of action/state frames to the training partition.
        plan = datasets.load_plan(plan_id, verify=False)
        profile = plan["profile"]
        if (
            profile not in BLOCKS
            or plan["domain"] != "real"
            or plan.get("smoke")
            or not all(plan["splits"].values())
        ):
            raise ValueError(
                "Alignment requires a real non-smoke plan with independent partitions"
            )
        rows = [e for e in plan["splits"]["train"] if e.get("domain", "real") == "real"]
    else:
        profile = pilot
        rows = datasets.eligible(profile)
    words = datasets.TASK_BLOCKS[profile]
    found = []
    for e in rows:
        root = Path(e["dataset"])
        raw = json.loads((root / "provenance.json").read_text())
        collection = raw.get("hardware", {}).get("collection", {})
        task = " ".join(
            str(v or "")
            for v in (
                raw.get("profile", {}).get("task"),
                collection.get("description"),
                collection.get("instruction"),
            )
        ).lower()
        if (
            e["profile"] == profile
            and raw.get("domain", "real") == "real"
            and raw.get("synthetic") is False
            and raw.get("category") in ("demonstration", "correction")
            and raw.get("outcome") == "success"
            and any(w in task for w in words)
        ):
            sha = datasets.fingerprint(root)
            if plan_id and sha != e["sha256"]:
                raise ValueError("Training recording changed after freeze: " + e["id"])
            frames = [
                json.loads(s)
                for s in (root / "research.jsonl").read_text().splitlines()
            ]
            S = np.asarray([r["observation.state"][:6] for r in frames], dtype=float)
            A = np.asarray([r["action"][:6] for r in frames], dtype=float)
            if (
                len(S)
                and S.shape == A.shape == (len(frames), 6)
                and np.isfinite(S).all()
                and np.isfinite(A).all()
            ):
                found.append(({"id": e["id"], "sha256": sha}, S, A))
    return profile, found


def fk(env, state):
    import mujoco

    d = mujoco.MjData(env.model)
    d.qpos[:6] = env.to_radians(state)
    mujoco.mj_kinematics(env.model, d)
    return d.site("gripperframe").xpos.copy()


def estimate(profile, found):
    from explorer4.sim.aligned import RosmasterFloorPick, SO101Handover

    handover = profile == "so101_pick_place"
    fps = 30 if handover else 20
    env = SO101Handover() if handover else RosmasterFloorPick()
    starts, grasps, gives, parents = [], [], [], []
    try:
        for identity, states, actions in found:
            open_level = np.median(actions[:10, 5]) if handover else actions[0, 5]
            closed = np.flatnonzero(
                actions[:, 5] < open_level - 8
                if handover
                else actions[:, 5] > open_level + 20
            )
            if len(closed):
                g = min(len(states) - 1, int(closed[0]) + fps // 2)
                parents.append(identity)
                starts.append(states[0])
                grasps.append(fk(env, states[g]))
                if handover:
                    held = np.median(actions[g : g + fps, 5])
                    opened = np.flatnonzero(actions[g + fps :, 5] > held + 8)
                    if len(opened):
                        gives.append(fk(env, states[g + fps + opened[0]]))
    finally:
        env.close()
    sufficient = len(grasps) >= MIN_DEMOS and (not handover or len(gives) >= MIN_DEMOS)
    report = {
        "inspected": len(found),
        "with_grasp": len(grasps),
        "source_episodes": parents,
    }
    if handover:
        report["with_handover"] = len(gives)
    if sufficient:
        S, G = np.array(starts), np.array(grasps)
        if handover:
            spread = np.percentile(G[:, :2], 90, 0) - np.percentile(G[:, :2], 10, 0)
            report["measured"] = {
                "rest_pose": np.round(np.median(S, 0), 1).tolist(),
                "pad_center": np.round(np.median(G[:, :2], 0), 3).tolist(),
                "pad_zone_step_m": round(float(max(0.01, spread.max() / 2)), 3),
                "handover_point": np.round(np.median(gives, 0), 3).tolist(),
            }
            report["measured_pad_z_m"] = float(np.median(G[:, 2]))
        else:
            report["measured"] = {
                "start_pose": np.round(np.median(S, 0), 1).tolist(),
                "object_x_m": np.round(np.percentile(G[:, 0], [5, 95]), 3).tolist(),
                "object_y_m": np.round(np.percentile(G[:, 1], [5, 95]), 3).tolist(),
            }
    else:
        report["kept"] = (
            "Insufficient terminal events in the registered training recordings"
        )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--plan-id")
    scope.add_argument("--all-data-pilot", choices=BLOCKS)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.all_data_pilot and args.apply:
        parser.error("An all-data diagnostic cannot modify a co-training scene")
    name, recordings = demos(args.plan_id, pilot=args.all_data_pilot)
    block = BLOCKS[name]
    path = ROOT / "configs/sim-alignment.json"
    config = json.loads(path.read_text())
    report = estimate(name, recordings)
    ancestry = {
        "mode": "frozen_train" if args.plan_id else "all_data_diagnostic",
        "plan_id": args.plan_id,
        "source_episodes": report["source_episodes"],
    }
    if args.apply and report.get("measured"):
        from explorer4.fleet_config import atomic_write

        config[block].update(
            report["measured"], source="measured", alignment_provenance=ancestry
        )
        atomic_write(path, config)
    print(
        json.dumps(
            {
                block: report,
                "alignment": ancestry,
                "applied": bool(args.apply and report.get("measured")),
                "scene_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
