"""Read-only field setup check using the recorded shelf and the native ROSMASTER near preset."""

import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np

from explorer4.navigation import wrap
from explorer4.peer_dock_shelf import goal_from_shelf, observe
from explorer4.peer_shelf_endpoint import starting_alignment
from explorer4.peer_shelf_run import EVIDENCE, REFERENCE, read_resume_scan, read_still, tank_health, tank_mount
from explorer4.rosmaster_control import connection
from explorer4.sensors import SensorClient

from .peer_dock_markerless_pair import load_packet
from .rosmaster_depth_readiness import depth_capture


def load_reference():
    near = json.loads((REFERENCE / 'near-donor-check.json').read_text())
    raw = (REFERENCE / 'near-donor-reference.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != near['near_reference_sha256']:
        raise ValueError('The near-preset reference changed after the archive check')
    base = EVIDENCE / '8b89d84f817e444ca26aea0965df1f05'
    original = json.loads((base / 'result.json').read_text())
    anchor = load_packet(base / 'tank.npz', 'tank')
    if hashlib.sha256(anchor['payload']).hexdigest() != original['packets']['tank']:
        raise ValueError('The Tank anchor changed')
    anchor['mount_source'] = json.loads((base / 'tank-mount.json').read_text())
    return near, json.loads(raw), anchor, original


def read_donor(arm):
    try:
        packet = read_still('rosmaster')
        return packet, packet['arrays']['arm']
    except (KeyError, ValueError, httpx.HTTPError):
        # With the native agent owning the serial port, use its stopped joint
        # feedback and the ROS camera instead of an old factory pose topic.
        sensors = SensorClient(robot='rosmaster', isolated=True)
        try:
            with connection(timeout=1.2) as control:
                packet, measured, _ = depth_capture(sensors, control, arm)
                return packet, measured
        finally:
            sensors.close()


def score(anchor, original, tank_scans, donor, arm, near, reference):
    positions = [starting_alignment(anchor, current) for current in tank_scans]
    arm_matched = np.max(np.abs(np.subtract(arm, near['arm_native_degrees']))) <= .8
    membership = observe(donor, reference) if arm_matched else None
    agreement = None
    if membership is not None:
        width = -membership['witness_in_shelf_m'][0]
        pose = (tank_mount(anchor) @ np.asarray(near['tank_optical_from_donor_optical'])
                @ np.asarray(membership['depth_from_shelf']))
        estimated = np.asarray(goal_from_shelf(pose, width))
        offset = original['shadow_replay']['lateral_offset_m']
        estimated[:2] += offset * np.array([-math.sin(estimated[2]), math.cos(estimated[2])])
        agreement = {'position_m': math.dist(estimated[:2], original['pose'][:2]),
                     'heading_deg': abs(math.degrees(wrap(estimated[2] - original['pose'][2]))),
                     'shelf_width_difference_m': abs(width - near['verified_width_m'])}
    scans_match = all(row['within_start_tolerance'] for row in positions)
    shelf_matches = (agreement is not None and agreement['position_m'] < .015
                     and agreement['heading_deg'] < 3 and agreement['shelf_width_difference_m'] < .010)
    return {'tank_start_confirmed': scans_match, 'rosmaster_near_preset_confirmed': bool(arm_matched),
            'rosmaster_shelf_confirmed': shelf_matches, 'tank_start_estimates': positions,
            'goal_agreement': agreement, 'motion_commands_sent': 0, 'permits_dispatch': False}


def main():
    near, reference, anchor, original = load_reference()
    health = tank_health()
    if health.get('armed') is not False or health.get('hardware_open') is not False:
        raise ValueError('Tank must be disarmed before checking the start placement')
    with ThreadPoolExecutor(2) as pool:
        donor = pool.submit(read_donor, near['arm_native_degrees'])
        scan1 = read_resume_scan()
        scan2 = read_resume_scan(scan1['meta']['streams']['scan']['source_timestamp_ns'])
        packet, arm = donor.result()
    result = score(anchor, original, (scan1, scan2), packet, arm, near, reference)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
