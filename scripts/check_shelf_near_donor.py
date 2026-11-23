"""Check whether the documented, reachable ROSMASTER near preset still sees the shelf."""

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from explorer4.navigation import wrap
from explorer4.peer_dock_real import write_json
from explorer4.peer_dock_shelf import goal_from_shelf, observe
from explorer4.peer_shelf_run import EVIDENCE, REFERENCE, shelf_calibration, tank_mount

from .peer_dock_markerless_pair import load_packet


def packets(group):
    recorded = json.loads((group / 'result.json').read_text())
    for index, row in enumerate(recorded['rows']):
        packet = load_packet(group / f'{index:02}.npz', 'rosmaster')
        if hashlib.sha256(packet['payload']).hexdigest() != row['input_sha256']:
            raise ValueError('The ROSMASTER joint sample and camera frame were not captured together')
        yield packet, row['arm_native_degrees']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('calibration_capture', type=Path)
    parser.add_argument('held_out_capture', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    reference, _ = shelf_calibration()
    anchor_dir = EVIDENCE / '8b89d84f817e444ca26aea0965df1f05'
    anchor = load_packet(anchor_dir / 'tank.npz', 'tank')
    anchor['mount_source'] = json.loads((anchor_dir / 'tank-mount.json').read_text())
    tank_view = observe(anchor, reference['tank'])
    tank_camera_from_shelf = np.asarray(tank_view['depth_from_shelf'])
    tank_base = tank_mount(anchor)
    local = goal_from_shelf(tank_base @ tank_camera_from_shelf, -tank_view['witness_in_shelf_m'][0])
    near_raw = (REFERENCE / 'near-donor-reference.json').read_bytes()
    near = json.loads(near_raw)
    first, first_arm = next(packets(args.calibration_capture))
    calibration = observe(first, near)
    donor_view = np.asarray(calibration['depth_from_shelf'])
    tank_camera_from_donor = tank_camera_from_shelf @ np.linalg.inv(donor_view)
    reference_width = -calibration['witness_in_shelf_m'][0]
    if abs(reference_width + tank_view['witness_in_shelf_m'][0]) > .010:
        raise ValueError('The two robots identified different shelf widths')
    tested = []
    for packet, arm in packets(args.held_out_capture):
        if np.max(np.abs(np.subtract(first_arm, arm))) > .8:
            raise ValueError('The camera arm moved between near-pose exposures')
        view = observe(packet, near)
        width = -view['witness_in_shelf_m'][0]
        relative = tank_base @ tank_camera_from_donor @ np.asarray(view['depth_from_shelf'])
        inferred = goal_from_shelf(relative, width)
        tested.append({'depth_stamp_ns': packet['meta']['streams']['depth']['source_timestamp_ns'],
                       'goal_error_m': math.dist(local[:2], inferred[:2]),
                       'heading_error_deg': abs(math.degrees(wrap(local[2] - inferred[2]))),
                       'width_difference_m': abs(width - reference_width)})
    if not tested or len({r['depth_stamp_ns'] for r in tested}) != len(tested):
        raise ValueError('Held-out depth exposures must be distinct')
    report = {'scope': 'Archived RGB-D at one fixed chassis placement and near arm preset. One calibration exposure and a later set of held-out frames. No physical commands.',
              'current_pose_recheck_before_dispatch': True,
              'arm_native_degrees': first_arm, 'near_reference_sha256': hashlib.sha256(near_raw).hexdigest(),
              'tank_optical_from_donor_optical': tank_camera_from_donor.tolist(), 'verified_width_m': reference_width,
              'max_goal_error_m': max(r['goal_error_m'] for r in tested),
              'max_heading_error_deg': max(r['heading_error_deg'] for r in tested), 'frames': tested}
    args.output.parent.mkdir(exist_ok=True, parents=True)
    write_json(args.output, report)
    print(len(tested), report['max_goal_error_m'], report['max_heading_error_deg'], flush=True)


if __name__ == '__main__':
    main()
