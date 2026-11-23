"""Capture stationary ROSMASTER depth with native feedback after the operator stops."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import cv2
import httpx
import numpy as np

from explorer4.floor_cube_localization import cube_center, top_surface
from explorer4.paths import DATA, ROOT
from explorer4.peer_dock_shelf import normalized_rays
from explorer4.rosmaster_control import connection
from explorer4.sensors import SensorClient, stream_age
from explorer4.sim.vendor_rosmaster.arm_model import ArmModel, SERVO_LIMITS


def native_state(client):
    response = client.get('/health')
    response.raise_for_status()
    health = response.json()
    status = health.get('status') or {}
    arm = np.asarray(status.get('arm_measured'), dtype=float)
    age = np.asarray(status.get('arm_measured_ages_s', status.get('arm_feedback_age_s')), dtype=float)
    velocity = np.asarray(status.get('measured_velocity'), dtype=float)
    if (health.get('robot') != 'rosmaster' or health.get('armed') is not False
            or health.get('hardware_open') is not True or status.get('preparing') is not False
            or status.get('controller_ready') is not True or velocity.shape != (3,)
            or not np.isfinite(velocity).all() or np.max(np.abs(velocity)) > .005
            or arm.shape != (6,) or not np.isfinite(arm).all()
            or age.shape != (6,) or not np.all((0 <= age) & (age <= .25))
            or status.get('base_command') != [0., 0., 0.]):
        raise ValueError('ROSMASTER must be stopped with fresh native joint feedback')
    return health['monotonic_ns'], arm, status['motion_commands_sent'], status['battery_voltage']


def depth_capture(sensors, control, expected):
    before, start, commands, voltage = native_state(control)
    if np.max(np.abs(start - expected)) > 6.:
        raise ValueError('Waiting for the specified arm pose')
    packet = sensors.snapshot(('depth', 'depth_info', 'rgb', 'rgb_info'))
    after, stop, last_commands, _ = native_state(control)
    meta = packet['meta']
    streams = meta['streams']
    info, frame = streams['depth_info'], streams['depth']
    raw = packet['arrays']['depth']
    if (not meta.get('read_only') or meta.get('motion_commands_sent') != 0
            or np.max(np.abs(start - stop)) > .5 or commands != last_commands
            or not before - 250_000_000 <= frame['received_ns'] <= after
            or after - before > 500_000_000 or not 0 <= stream_age(packet, 'depth', packet['received_ns']) <= .30
            or raw.shape != (info['height'], info['width']) or frame['frame_id'] != info['frame_id']
            or frame['unit'] != 'mm' or np.any(np.abs(info['d']) > 1e-8)):
        raise ValueError('Depth and native position evidence did not match in time or calibration')
    lower, upper = np.asarray(SERVO_LIMITS).T
    if np.any((stop < lower - 3.) | (stop > upper + 3.)):
        raise ValueError('Native arm position is outside the simulated joint range')
    return packet, (start + stop) / 2, voltage


def measure(packet, arm, bounds, size):
    frame = packet['meta']['streams']['depth']
    k = packet['meta']['streams']['depth_info']['k']
    depth = packet['arrays']['depth'] * .001
    transform = ArmModel().camera_pose(arm)
    points = top_surface(depth, (k[0], k[4], k[2], k[5]), transform, size, bounds)
    cube = cube_center(points, size, bounds)
    return {
        'depth_stamp_ns': frame['source_timestamp_ns'],
        'arm_native_degrees': arm.tolist(),
        'input_sha256': hashlib.sha256(packet['payload']).hexdigest(),
        'top_surface_samples': len(points),
        'cube_candidate_base_xy_m': None if cube is None else cube.tolist(),
    }


def measure_blue_cube(packet, arm):
    """Use the pilot cube's blue top to check the geometric detector on real depth."""
    rgb, raw = (packet['arrays'][name] for name in ('rgb', 'depth'))
    streams = packet['meta']['streams']
    info = streams['depth_info']
    skew = abs(streams['depth']['source_timestamp_ns'] - streams['rgb']['source_timestamp_ns'])
    if rgb.shape[:2] != raw.shape or streams['rgb']['frame_id'] != info['frame_id'] or skew > 150_000_000:
        return None
    blue = cv2.inRange(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV), (95, 100, 35), (135, 255, 255))
    height, width = blue.shape
    blue[:height // 2] = 0
    blue[:, :width // 4] = blue[:, 3 * width // 4:] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(blue)
    if count < 2:
        return None
    index = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    x, y, w, h, area = stats[index]
    if (not 500 <= area <= 4500 or x <= width // 4 or x + w >= 3 * width // 4
            or y <= height // 2 or y + h >= height):
        return None
    mask = (labels == index).astype(np.uint8)
    patch = cv2.dilate(mask, np.ones((97, 97), np.uint8)) > 0
    margin = cv2.dilate(mask, np.ones((31, 31), np.uint8)) > 0
    top = cv2.erode(mask, np.ones((7, 7), np.uint8)) > 0
    valid = (raw > 150) & (raw < 1200)
    transform = ArmModel().camera_pose(arm)

    def base_points(selected):
        row, col = np.nonzero(selected & valid)
        rays = normalized_rays(info, np.c_[col, row])
        points = rays * (raw[row, col] * .001)[:, None]
        return points @ transform[:3, :3].T + transform[:3, 3]

    floor = base_points(patch & ~margin)
    face = base_points(top)
    if len(face) < 150 or len(floor) < 1000:
        return None
    inliers = floor
    for _ in range(3):
        origin = np.median(inliers, axis=0)
        _, _, axes = np.linalg.svd(inliers - origin, full_matrices=False)
        normal = axes[-1] * np.sign(axes[-1, 2])
        inliers = floor[np.abs((floor - origin) @ normal) < .006]
        if len(inliers) < .8 * len(floor) or normal[2] < .97:
            return None
    z = (face - origin) @ normal
    lo, median, hi = np.percentile(z, [10, 50, 90])
    if not .022 <= lo <= median <= hi <= .040 or hi - lo > .010:
        return None
    return {'top_center_base_xyz_m': np.median(face, axis=0).tolist(), 'top_height_above_floor_m': float(median),
            'floor_tilt_from_nominal_deg': float(np.degrees(np.arccos(np.clip(normal[2], 0., 1.)))),
            'rgb_box_xywh_px': [int(v) for v in (x, y, w, h)], 'face_depth_pixels': len(face)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pose', nargs=6, type=float, required=True)
    parser.add_argument('--wait', type=int, default=30)
    parser.add_argument('--max-blue-cube-x', type=float, help='Wait for a verified blue top closer than this nominal distance')
    args = parser.parse_args()
    cfg = json.loads((ROOT / 'configs/sim-alignment.json').read_text())['rosmaster_floor_pick']
    bounds = cfg['object_x_m'], cfg['object_y_m']
    expected = np.asarray(args.pose)
    folder = args.output.resolve()
    folder.mkdir(mode=0o700, parents=True, exist_ok=False)
    output = {'motion_commands_sent': 0, 'physical_grasp_attempts': 0, 'floor_calibrated': False,
              'expected_pose': args.pose, 'nominal_workspace_m': bounds, 'rows': []}
    rows = output['rows']
    deadline = time.monotonic() + args.wait
    with connection(timeout=1.2) as control:
        sensors = SensorClient(robot='rosmaster', isolated=True)
        try:
            while time.monotonic() < deadline and len(rows) < 10:
                try:
                    packet, pose, voltage = depth_capture(sensors, control, expected)
                    row = measure(packet, pose, bounds, .032)
                    if args.max_blue_cube_x is not None:
                        cube = measure_blue_cube(packet, pose)
                        if cube is None or cube['top_center_base_xyz_m'][0] > args.max_blue_cube_x:
                            raise ValueError('Waiting for the blue cube at the closer placement')
                        row['blue_cube'] = cube
                    if not rows or rows[-1]['depth_stamp_ns'] < row['depth_stamp_ns']:
                        (folder / f'{len(rows):02d}.npz').write_bytes(packet['payload'])
                        row['battery_v'] = voltage
                        rows.append(row)
                        print(row, flush=True)
                except (ValueError, httpx.HTTPError, KeyError) as exc:
                    output['last_refusal'] = str(exc)
                time.sleep(.15)
        finally:
            sensors.close()
    output['status'] = 'captured' if len(rows) == 10 else 'incomplete'
    (folder / 'result.json').write_text(json.dumps(output, indent=2, allow_nan=False) + '\n')
    print(output['status'], len(rows), folder, flush=True)


if __name__ == '__main__':
    main()
