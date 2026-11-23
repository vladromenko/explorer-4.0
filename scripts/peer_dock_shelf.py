"""Reproduce the surveyed shelf pose from stopped camera pairs and validate a shadow goal."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np

from explorer4 import drive, fleet_map, navigation
from explorer4.paths import ROOT
from explorer4.peer_dock_config import MAX_AGE_S
from explorer4.peer_dock_real import write_json
from explorer4.peer_dock_shelf import goal_from_shelf, observe, tank_base_from_depth
from explorer4.resources import ResourceLease
from explorer4.sensors import SensorClient, decode_packet, stream_age

ROBOTS = ("tank", "rosmaster")


def confirm_stopped():
    from urllib.request import urlopen

    with urlopen("http://127.0.0.1:8030/api/health", timeout=4) as response:
        health = json.load(response)
    if health["armed"] or health["session"]["phase"] != "idle":
        raise RuntimeError("Both robots must be at STOP for this passive experiment")


def capture(directory):
    confirm_stopped()
    keys = ("rgb", "rgb_info", "depth", "depth_info", "tf_static", "scan", "arm", "odometry")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    clients = [SensorClient(robot=r) for r in ROBOTS]
    try:
        with ThreadPoolExecutor(2) as pool:
            for i in range(4):
                pending = [pool.submit(c.snapshot, keys) for c in clients]
                for r, task in zip(ROBOTS, pending, strict=True):
                    p = task.result()
                    for stream in ("depth", "rgb"):
                        if stream_age(p, stream, p["received_ns"]) > MAX_AGE_S:
                            raise ValueError(f"{r} {stream} expired during acquisition")
                    (directory / f"paired-{i}-{r}.npz").write_bytes(p["payload"])
                time.sleep(.65)
        confirm_stopped()
    finally:
        for c in clients:
            c.close()


def shadow_tank(packet, goal):
    """Check withheld evidence from a stationary lidar and the actual navigation guard."""
    points = fleet_map.scan_points("tank", packet)
    if len(points) < 40:
        raise ValueError("Too few lidar returns for a stopped path estimate")
    # Start by turning at rest. Test centre-line clearance separately, conservatively
    # comparing position to all finite scan returns and the existing footprint radius.
    heading = float(np.arctan2(goal[1], goal[0]))
    _, w, note = navigation.guard(points, "tank", 0., heading)
    waypoints = np.linspace([0., 0.], goal[:2], 25)
    clearance = np.linalg.norm(waypoints[:, None] - points[None], axis=-1).min(axis=1)
    return {
        "scan_points": len(points), "first_turn_guard_allows": bool(w),
        "first_turn_guard_reason": note, "minimum_straight_segment_clearance_m": float(clearance.min()),
        "footprint_radius_m": navigation.RADIUS["tank"],
        "segment_clear_of_detected_lidar_points": bool(clearance.min() > navigation.RADIUS["tank"]),
        "scope": "A static scan and the initial guard decision do not establish free space or safe motion.",
    }


def replay_stopped_scan(packet, goal, *, lateral_m=0.):
    """Diagnose the unchanged controller using perfect pose and the captured scan as obstacles."""
    goal = np.asarray(goal, dtype=float).copy()
    yaw = goal[2]
    goal[:2] += lateral_m * np.array([-np.sin(yaw), np.cos(yaw)])
    points = fleet_map.scan_points("tank", packet)
    grid = fleet_map.Grid()
    grid.add(points, [0., 0.])
    pose = np.zeros(3)
    now = 100.
    elapsed = 0.
    clearance = float("inf")
    reverse_steps = 0

    def scan(_):
        return fleet_map.transform(points - pose[:2], [0., 0., -pose[2]])

    replay = SimpleNamespace(grid=grid, track={}, scan=scan)
    controller = drive.DriveTo(
        "tank", goal, tol=.045, heading_tol=.15, time_limit_s=20, v_max=.08,
        fleet=replay, pose_lookup=lambda *_: pose.tolist(), clock=lambda: now,
    )
    for _ in range(401):
        v, w = controller.command(None)
        reverse_steps += int(v < 0.)
        pose += [.05 * v * np.cos(pose[2]), .05 * v * np.sin(pose[2]), .05 * w]
        elapsed += .05
        now += .05
        clearance = min(clearance, float(np.linalg.norm(points - pose[:2], axis=1).min()))
        if not controller.active:
            break
    return {
        "goal": goal.tolist(), "terminal_pose": pose.tolist(), "state": controller.state,
        "message": controller.message, "simulated_seconds": elapsed,
        "terminal_position_error_m": float(np.linalg.norm(goal[:2] - pose[:2])),
        "minimum_scan_return_clearance_m": clearance,
        "reverse_steps": reverse_steps,
        "lateral_offset_m": lateral_m,
        "scope": "Offline kinematics with perfect odometry, static scan returns and no actuator I/O.",
    }


def score(reference, archives):
    report = {"pairs": [], "physical_trials": 0, "command_count": 0}
    widths = []
    poses = []
    tank_base_from_donor = None
    for cohort, directory in archives:
        for i in range(4):
            packets, observations = {}, {}
            for r in ROBOTS:
                raw = (directory / f"paired-{i}-{r}.npz").read_bytes()
                p = decode_packet(raw)
                if (p["meta"]["robot"] != r or not p["meta"]["read_only"]
                        or p["meta"]["motion_commands_sent"] != 0):
                    raise ValueError("Expected this robot's passive sensor packet")
                item = observe(p, reference[r])
                item["depth_source_timestamp_ns"] = p["meta"]["streams"]["depth"]["source_timestamp_ns"]
                item["packet_sha256"] = hashlib.sha256(raw).hexdigest()
                packets[r], observations[r] = p, item
            a, b = [np.asarray(observations[r]["witness_in_shelf_m"]) for r in ROBOTS]
            tank_from_shelf = np.asarray(observations["tank"]["depth_from_shelf"])
            donor_from_shelf = np.asarray(observations["rosmaster"]["depth_from_shelf"])
            tank_from_donor = tank_from_shelf @ np.linalg.inv(donor_from_shelf)
            poses.append(tank_from_donor)
            base_from_tank = tank_base_from_depth(packets["tank"])
            # Fit one camera-to-camera transform from the first development pair;
            # later donor goals use only this transform and ROSMASTER's new image.
            calibration_pair = tank_base_from_donor is None
            if calibration_pair:
                tank_base_from_donor = base_from_tank @ tank_from_donor
            local = goal_from_shelf(base_from_tank @ tank_from_shelf, -a[0])
            cooperative = goal_from_shelf(tank_base_from_donor @ donor_from_shelf, -b[0])
            goal_error = float(np.linalg.norm(np.subtract(local[:2], cooperative[:2])))
            heading_error = abs(navigation.wrap(local[2] - cooperative[2]))
            delta = float(np.linalg.norm(a - b))
            widths.append(delta)
            report["pairs"].append({
                "cohort": cohort, "index": i, "observations": observations,
                "same_divider_difference_m": delta,
                "tank_optical_from_rosmaster_optical": tank_from_donor.tolist(),
                "tank_local_goal_xy_yaw": local, "tank_goal_from_donor_only_xy_yaw": cooperative,
                "registration_fit_pair": calibration_pair, "donor_goal_error_m": goal_error,
                "donor_heading_error_deg": float(np.degrees(heading_error)),
                "shadow_path": shadow_tank(packets["tank"], cooperative),
                "offline_center_replay": replay_stopped_scan(packets["tank"], cooperative),
                "offline_left_replay": replay_stopped_scan(packets["tank"], cooperative, lateral_m=.10),
            })
    if any(d > .010 for d in widths):
        raise ValueError("Independent divider residual exceeded 10 mm")
    for r in ROBOTS:
        fresh = [x["observations"][r]["depth_source_timestamp_ns"] for x in report["pairs"] if x["cohort"] == "fresh"]
        if fresh and len(set(fresh)) != len(fresh):
            raise ValueError("Fresh replay contains duplicate depth source stamps")
    withheld = [x for x in report["pairs"] if not x["registration_fit_pair"]]
    fresh = [x for x in report["pairs"] if x["cohort"] == "fresh"]
    report.update(
        offline_replay={
            "fresh_pairs": len(fresh),
            "center_arrived": sum(x["offline_center_replay"]["state"] == "arrived" for x in fresh),
            "left_arrived": sum(x["offline_left_replay"]["state"] == "arrived" for x in fresh),
            "left_target_selection": "Exploratory offset selected using fresh index 0. Indices 1–3 are stopped scans from the same placement.",
        },
        max_donor_goal_error_on_withheld_pairs_m=max(x["donor_goal_error_m"] for x in withheld),
        max_donor_heading_error_on_withheld_pairs_deg=max(
            x["donor_heading_error_deg"] for x in withheld
        ),
        method="Frozen per-view shelf crops; fit the front plane from depth, find outer shelf lines in RGB; reconstruct the left divider as a separate geometric check.",
        new_viewpoint_validated=False,
        permit_physical_dispatch=False,
        max_divider_difference_m=max(widths),
        max_camera_translation_spread_m=max(float(np.linalg.norm(p[:3, 3]-poses[0][:3, 3])) for p in poses),
        timestamp_msk=datetime.now(ZoneInfo("Europe/Moscow")).isoformat(timespec="seconds"),
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--capture", type=Path, help="Record a fresh, stopped pair before validation")
    parser.add_argument("--fresh-archive", type=Path, help="Reuse a previously captured validation set")
    args = parser.parse_args()
    reference = json.loads(args.reference.read_text())
    archives = [("development", args.archive)]
    if args.capture:
        with ResourceLease("peer-dock-markerless-observation"):
            capture(args.capture)
        archives.append(("fresh", args.capture))
    elif args.fresh_archive:
        archives.append(("fresh", args.fresh_archive))
    report = score(reference, archives)
    report["source_sha256"] = {
        file: hashlib.sha256((ROOT / file).read_bytes()).hexdigest()
        for file in ("explorer4/peer_dock_shelf.py", "explorer4/drive.py", "scripts/peer_dock_shelf.py")
    }
    report["reference_sha256"] = hashlib.sha256(args.reference.read_bytes()).hexdigest()
    write_json(args.output, report)
    print(json.dumps({k: v for k, v in report.items() if k != "pairs"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
