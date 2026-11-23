"""Replay paired camera conditions and score the physical pilot with optical geometry."""

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from explorer4 import navigation
from explorer4.paths import DATA, ROOT
from explorer4.peer_dock_real import write_json
from explorer4.peer_dock_shelf import goal_from_shelf, observe
from explorer4.peer_shelf_endpoint import estimate, starting_alignment
from explorer4.peer_shelf_run import EVIDENCE, REFERENCE, shelf_calibration, tank_mount, visible_shelf
from explorer4.sensors import decode_packet

from .peer_dock_shelf import replay_stopped_scan


def load_packet(path, robot):
    raw = path.read_bytes()
    packet = decode_packet(raw)
    meta = packet['meta']
    if meta['robot'] != robot or meta.get('read_only') is not True or meta.get('motion_commands_sent') != 0:
        raise ValueError(f'Invalid passive {robot} evidence')
    return packet


def compare(tank, donor, reference, calibration, *, mask_right):
    image = tank['arrays']['rgb']
    if mask_right:
        image = image.copy()
        first_column = int(min(pt[0] for pt in reference['tank']['lines']['right']) - 50)
        image[:, first_column:] = 0
    input_to_local = {**tank, 'arrays': {**tank['arrays'], 'rgb': image}}
    base_from_depth = tank_mount(tank)
    local_error = None
    try:
        measured = observe(input_to_local, reference['tank'])
        width = -measured['witness_in_shelf_m'][0]
        if abs(width - calibration['width_m']['tank']) > .010:
            raise ValueError('Local shelf width changed')
        goal = goal_from_shelf(base_from_depth @ np.asarray(measured['depth_from_shelf']), width)
    except ValueError as exc:
        goal = None
        local_error = str(exc)
    local = route(tank, goal, 'tank', 0)
    if goal is None:
        shelf, width = visible_shelf(donor, reference, calibration)
        base_from_donor = base_from_depth @ np.asarray(calibration['optical_from_donor'])
        goal = goal_from_shelf(base_from_donor @ shelf, width)
        selective = route(tank, goal, 'rosmaster', 1)
    else:
        selective = local
    return {'condition': 'right_edge_masked_in_rgb' if mask_right else 'unchanged_rgb',
            'local_abstention_reason': local_error, 'local_only': local, 'selective_help': selective}


def route(tank, goal, chosen, requests):
    if goal is None:
        return {'result': 'abstained', 'goal_source': None, 'requests': requests}
    replay = replay_stopped_scan(tank, goal, lateral_m=.10)
    eligible = (replay['state'] == 'arrived' and replay['minimum_scan_return_clearance_m'] >= .25
                and replay['reverse_steps'] == 0)
    return {'result': 'offline_arrived' if eligible else 'replay_rejected', 'goal_source': chosen,
            'requests': requests, 'replay': replay}


def endpoint_score(anchor_directory, stop_directory, reference):
    initial = json.loads((anchor_directory / 'result.json').read_text())
    anchor = load_packet(anchor_directory / 'tank.npz', 'tank')
    endpoint = load_packet(stop_directory / 'post-stop.npz', 'tank')
    if hashlib.sha256(anchor['payload']).hexdigest() != initial['packets']['tank']:
        raise ValueError('The initial Tank packet differs from the pilot receipt')
    source = json.loads((anchor_directory / 'tank-mount.json').read_text())
    anchor['mount_source'] = endpoint['mount_source'] = source
    terminal_reference = json.loads((REFERENCE / 'endpoint-reference.json').read_text())
    result = estimate(anchor, endpoint, reference['tank'], terminal_reference)
    position = math.dist(result['pose_xy_yaw'][:2], initial['pose'][:2])
    yaw = abs(navigation.wrap(result['pose_xy_yaw'][2] - initial['pose'][2]))
    result.update(position_error_m=position, heading_error_deg=math.degrees(yaw),
                  within_pilot_tolerance=position <= .045 and yaw <= .15,
                  input_sha256=[hashlib.sha256(packet['payload']).hexdigest() for packet in (anchor, endpoint)],
                  target_pose=initial['pose'],
                  scope='One stopped physical frame with retrospective natural shelf line annotations. Uses RGB-D and the same mounting model, no lidar pose or control output.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--endpoint', action='store_true')
    args = parser.parse_args()
    reference, calibration = shelf_calibration()
    rows = []
    for index in range(4):
        tank = load_packet(args.archive / f'paired-{index}-tank.npz', 'tank')
        donor = load_packet(args.archive / f'paired-{index}-rosmaster.npz', 'rosmaster')
        stamps = [p['meta']['streams']['depth']['source_timestamp_ns'] for p in (tank, donor)]
        for masked in (False, True):
            rows.append({'pair': index, 'depth_source_stamps_ns': stamps,
                         'inputs_sha256': [hashlib.sha256(p['payload']).hexdigest() for p in (tank, donor)],
                         **compare(tank, donor, reference, calibration, mask_right=masked)})
    if any(len({rows[i]['depth_source_stamps_ns'][camera] for i in range(0, len(rows), 2)}) != 4
           for camera in range(2)):
        raise ValueError('Duplicate recording in paired replay')
    summary = {}
    for condition in {row['condition'] for row in rows}:
        group = [row for row in rows if row['condition'] == condition]
        summary[condition] = {method: {'offline_arrivals': sum(row[method]['result'] == 'offline_arrived' for row in group),
                                       'requests': sum(row[method]['requests'] for row in group),
                                       'attempts': len(group)} for method in ('local_only', 'selective_help')}
    report = {'scope': 'Archived physical observations at a fixed placement. Visibility degradation is a software mask and execution is static-scan simulation.',
              'physical_paired_attempts': 0, 'summary': summary, 'rows': rows,
              'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if args.endpoint:
        start = EVIDENCE / '8b89d84f817e444ca26aea0965df1f05'
        end = EVIDENCE / '3dee5c5cfc4a4eb9b204ea3bacff0c6c'
        report['physical_pilot_optical_endpoint'] = endpoint_score(start, end, reference)
        anchor = load_packet(start / 'tank.npz', 'tank')
        report['start_alignment'] = [starting_alignment(anchor, load_packet(args.archive / f'paired-{i}-tank.npz', 'tank'))
                                     for i in range(4)]
        report['pilot_endpoint_against_start'] = starting_alignment(anchor, load_packet(end / 'post-stop.npz', 'tank'))
    args.output.parent.mkdir(exist_ok=True, parents=True)
    write_json(args.output, report)
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}), flush=True)


if __name__ == '__main__':
    main()
