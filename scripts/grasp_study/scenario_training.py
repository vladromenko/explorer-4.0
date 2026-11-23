"""Import admitted scenario demonstrations and register matched LeRobot runs."""

import argparse
import hashlib
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from types import SimpleNamespace

from explorer4 import catalog, datasets, training_drafts
from explorer4.jobs import Jobs
from explorer4.paths import DATA
from explorer4.peer_dock_real import write_json
from explorer4.sim.import_episode import ingest


DISTANCE = ('near', 'middle', 'edge', 'outside')
PROFILE = 'rosmaster_floor_pick_sim'
OUT = DATA / 'simlab/reports/varied-floor-cube-v1/training'


def load_corpus():
    protocol = json.loads((OUT / 'protocol.json').read_text())
    code = Path(__file__).with_name('scenarios.py').read_bytes()
    if protocol['exports_demonstrations'] is not True or protocol['source_sha256'] != hashlib.sha256(code).hexdigest():
        raise ValueError('The training split must export demonstrations')
    report = json.loads((OUT / 'result.json').read_text())
    rows = report['results']
    if len(rows) != len(protocol['scenarios']):
        raise ValueError('The registered scenario bank is incomplete')
    admitted = defaultdict(list)
    for row, expected in zip(rows, protocol['scenarios'], strict=True):
        if (row['method'] != 'teacher' or row['seed'] < 988400
                or any(row.get(k) != v for k, v in expected.items())):
            raise ValueError('Only the separate training scenario bank may enter this plan')
        if row['retained'] and row.get('spool'):
            admitted[row['distance']].append(row)
    if any(len(admitted[band]) < 4 for band in DISTANCE):
        raise ValueError('Each scenario group needs four admitted demonstrations before preparing weights')
    return admitted


def scenario_plan(admitted):
    roles = {}
    labels = {}
    for band in DISTANCE:
        items = sorted(admitted[band], key=lambda row: row['seed'])
        split = None
        for dev, test in combinations(items, 2):
            train = [row for row in items if row['seed'] not in {dev['seed'], test['seed']}]
            if ({row['xy'][1] for row in train} == {-.043, 0., .043}
                    and {row['yaw_deg'] for row in train} == {-34., 0., 34.}
                    and {row['start'] for row in train} == {'recording', 'raised'}):
                split = {dev['seed']: 'validation', test['seed']: 'test'}
                break
        if split is None:
            raise ValueError(f'{band}: training would lose a lateral position, rotation or starting posture')
        for row in items:
            recorded = ingest(row['spool'])
            ident = recorded['episode_id']
            if recorded['readback'] != 'PASS' or ident in roles:
                raise ValueError('Invalid or duplicate LeRobot recording in the scenario bank')
            roles[ident] = split.get(row['seed'], 'train')
            labels[ident] = {'seed': row['seed'], 'distance': row['distance'],
                             'yaw_deg': row['yaw_deg'], 'source': 'MuJoCo scripted teacher'}
    _, checked = datasets.freeze(PROFILE, False, seed=1000, selected_ids=roles, min_sim_episodes=16)
    entries = [item for split in checked['splits'].values() for item in split]
    partitions = {key: [] for key in ('train', 'validation', 'test')}
    for group in datasets.connected_groups(entries):
        assigned = {roles[item['id']] for item in group}
        if len(assigned) != 1:
            raise ValueError('Related scenario recordings would cross data partitions')
        partitions[assigned.pop()].extend(group)
    plan = {**checked, 'splits': partitions, 'scenario_labels': labels,
            'split_rule': 'Separate simulation seeds; each distance band contributes to all three roles.'}
    return training_drafts.save_content(DATA / 'plans', plan), partitions


def register(steps, queue):
    plan, split = scenario_plan(load_corpus())
    result = {'plan': plan, 'split_counts': {role: len(items) for role, items in split.items()},
              'joint_policy_only': True, 'steps': steps, 'batch': 8, 'seed': 1000, 'models': {}}
    existing = {json.loads(row['config']).get('draft_id'): row for row in catalog.rows('jobs')}
    jobs = Jobs(SimpleNamespace(owner=None, armed=False))
    for policy in ('act', 'diffusion'):
        ident, _ = training_drafts.prepare(PROFILE, policy, plan_id=plan, steps=steps, batch=8,
                                            device='cuda', train_seed=1000)
        job = existing.get(ident)
        result['models'][policy] = {'draft': ident, 'job': job['id'] if job else None}
        if queue and job is None:
            result['models'][policy]['job'] = jobs.start_prepared_training(ident)
    write_json(OUT / 'queue.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--steps', type=int, default=3000)
    parser.add_argument('--queue', action='store_true')
    args = parser.parse_args()
    catalog.initialize()
    print(json.dumps(register(args.steps, args.queue), indent=2), flush=True)


if __name__ == '__main__':
    main()
