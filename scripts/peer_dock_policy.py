"""Prepare, explicitly fit, or evaluate a peer-request selector against active onboard sensing."""
import argparse
import fcntl
import json
from pathlib import Path

import numpy as np

from explorer4.paths import DATA, ROOT
from explorer4.peer_request_policy import FEATURES, checksum, local_features, read, score
from scripts import peer_dock_study as study
from scripts import peer_screen_evidence as screen

POLICY = 'peer-observation-policy-v2'
EXECUTION = (*screen.SOURCES, 'scripts/peer_dock_policy.py', 'explorer4/cognitive/run.py',
             'explorer4/cognitive/registry.py', 'explorer4/cognitive/protocol.py', 'explorer4/cognitive/schemas.py')


def prepare(root, source):
    evidence = read(source/'development.json')
    protocol = read(source/'protocol.json')
    if evidence['status'] != 'completed' or evidence['protocol_sha256'] != study.digest(source/'protocol.json'):
        raise ValueError('Development outcomes must match their frozen protocol')
    if any(study.digest(ROOT/name) != sha for name, sha in protocol['software_hashes'].items()):
        raise ValueError('Development simulator differs from the current simulator')
    splits = protocol['splits']
    rows = evidence['rows']
    train = set(splits['train']['seeds'])
    calibration = set(splits['calibration']['seeds'])
    test = set(splits['test']['seeds'])
    if train & calibration or (train | calibration) & test or {r['seed'] for r in rows} != train | calibration:
        raise ValueError('Expected disjoint train, calibration and sealed test data')
    for r in rows:
        folder = source/r['split']/str(r['seed'])
        if (r['seed'] not in splits[r['split']]['seeds'] or
                r['outcomes_sha256'] != study.digest(folder/'outcomes.json') or
                r['image_sha256'] != study.digest(folder/'recipient-before.png')):
            raise ValueError('Development row differs from its source')
    plan = {'version':2, 'task':'Incremental utility of a fresh peer observation versus active onboard scanning.',
            'rows':rows, 'features':list(FEATURES), 'train_room':splits['train']['room'],
            'calibration_room':splits['calibration']['room'], 'test_room':splits['test']['room'],
            'test_seeds':splits['test']['seeds'], 'random_order':protocol['random_order'], 'ridge_alpha':1.,
            'call_cost':protocol['call_cost'],'per_second_cost':protocol['per_second_cost'],
            'source_protocol_sha256':evidence['protocol_sha256'],
            'execution_hashes':{name:study.digest(ROOT/name) for name in EXECUTION},
            'limitations':'Controlled screen coating, registered start and wall axis, ideal odometry. Room presets share fixtures.',
            'fit_started':False}
    study.frozen(root/'plan.json', plan)
    return plan


def verify_plan(root):
    plan = read(root/'plan.json')
    if any(study.digest(ROOT/name) != sha for name, sha in plan['execution_hashes'].items()):
        raise ValueError('Execution source differs from the frozen plan')
    return plan


def gain(plan, row):
    return (row['peer'] - row['local'] - plan['call_cost'] -
            plan['per_second_cost'] * (row['peer_time_s'] - row['local_time_s']))


def fit(root):
    """This explicitly selected stage alone may update selector weights."""
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    plan = verify_plan(root)
    train = [r for r in plan['rows'] if r['split'] == 'train']
    calibration = [r for r in plan['rows'] if r['split'] == 'calibration']
    x = np.array([r['x'] for r in train])
    y = np.array([gain(plan, r) for r in train])
    scaler = StandardScaler().fit(x)
    ridge = Ridge(alpha=plan['ridge_alpha']).fit(scaler.transform(x), y)
    artifact = {'schema':'peer_request_ridge_v2', 'features':list(FEATURES), 'plan_sha256':checksum(plan),
                'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist(),
                'coef':ridge.coef_.tolist(),'intercept':float(ridge.intercept_)}
    calibration_scores = [score(artifact,r['x']) for r in calibration]
    candidates = [min(calibration_scores), *[float(np.nextafter(s,np.inf)) for s in sorted(set(calibration_scores))]]
    def benefit(threshold):
        calls = [s >= threshold for s in calibration_scores]
        return sum(gain(plan,r) for c,r in zip(calls,calibration) if c), -sum(calls)
    threshold = max(candidates, key=benefit)
    artifact['threshold'] = threshold
    study.frozen(root/'model.json', artifact)
    study.frozen(root/'fit.json', {'train_scenes':len(train),'calibration_scenes':len(calibration),
                 'model_sha256':checksum(artifact),'calibration_incremental_utility_sum':benefit(threshold)[0],
                 'training_gain_constant':bool(np.ptp(y)<1e-12),'threshold':threshold,
                 'test_results_read':False,'motor_weights_updated':False})


def freeze_prediction(folder, seed, model, decision):
    features = local_features(decision['local_packet'], decision['local_measurement'])
    prediction = score(model, features)
    record = {'seed':seed,'model_sha256':checksum(model),'score':prediction,'features':features,
              'request':prediction>=model['threshold'],'image_sha256':decision['local_image_sha256'],
              'time_s':decision['time_s']}
    study.frozen(folder/'model-decision.json',record)


def evaluation_summary(rows, plan):
    from scipy.stats import binomtest
    count = sum(r['model_decision']['request'] for r in rows)
    random_seeds = set(plan['random_order'][:count])
    methods = ('local_only','local_scan','always','learned','matched_random','visibility_rule','stale','shuffled')
    stats = {k:{'successes':0,'calls':0,'scenes':len(rows),'times':[],'total_utility':0.} for k in methods}
    gains = losses = 0
    for r in rows:
        choices = {'learned':r['model_decision']['request'], 'matched_random':r['seed'] in random_seeds,
                   'visibility_rule':r['decision']['local_packet'] is None}
        outcomes = {}
        for k in methods:
            branch = ('always' if choices[k] else 'local_scan') if k in choices else k
            outcome = r['branches'][branch]
            success = int(outcome['task'] == 'success')
            call = int(branch not in ('local_only','local_scan'))
            seconds = outcome['simulation_time_s']
            s = stats[k]
            s['successes'] += success
            s['calls'] += call
            s['times'].append(seconds)
            s['total_utility'] += success - plan['call_cost']*call - plan['per_second_cost']*seconds
            outcomes[k] = {'branch':branch,'success':success}
        r['policies'] = outcomes
        gains += int(outcomes['learned']['success'] > outcomes['matched_random']['success'])
        losses += int(outcomes['learned']['success'] < outcomes['matched_random']['success'])
    for s in stats.values():
        s['median_elapsed_sim_s'] = float(np.median(s.pop('times')))
    return {'conditions':stats,'paired_vs_random':{'gains':gains,'losses':losses,
            'exact_two_sided_p':binomtest(gains,gains+losses).pvalue if gains+losses else 1.}}


def evaluate(root):
    plan = verify_plan(root)
    model = read(root/'model.json')
    if model['plan_sha256'] != checksum(plan) or checksum(model) != read(root/'fit.json')['model_sha256']:
        raise ValueError('Model provenance differs from frozen plan')
    from explorer4.sim.cooperation import CooperationWorld
    seeds = plan['test_seeds']
    world = CooperationWorld(root/'scratch',seeds[0],plan['test_room'])
    try:
        for seed in seeds:
            folder = root/'test'/str(seed)
            if (folder/'donor.json').exists():
                if not (folder/'model-decision.json').exists():
                    raise ValueError('Missing pre-request decision in an already observed scene')
                freeze_prediction(folder, seed, model, read(folder/'decision.json'))
            else:
                study.scene_inputs(world, folder, seed, before_donor=lambda d:freeze_prediction(folder,seed,model,d))
        rows = []
        for i, seed in enumerate(seeds):
            folder = root/'test'/str(seed)
            if not (folder/'outcomes.json').exists():
                other = seeds[(i+1) % len(seeds)]
                wrong = read(root/'test'/str(other)/'donor.json')['packet']
                study.rollouts(world,folder,seed,wrong,other)
            row = read(folder/'outcomes.json')
            row['model_decision'] = read(folder/'model-decision.json')
            rows.append(row)
        summary = evaluation_summary(rows,plan)
        for row in rows:
            study.frozen(root/'test'/str(row['seed'])/'policy-comparison.json',row['policies'])
        study.frozen(root/'evaluation.json',{'status':'completed','model_sha256':checksum(model),
                     'test_room':plan['test_room'],'test_seeds':seeds,'scenes':len(seeds),**summary,
                     'fit_on_test':False,'physical_robot_commands':0})
    finally:
        world.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=('prepare','fit','evaluate'))
    parser.add_argument('--output',type=Path,default=DATA/'runs'/POLICY)
    parser.add_argument('--source',type=Path,default=DATA/'runs'/screen.NAME)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    with (args.output/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.stage == 'prepare':
            plan = prepare(args.output,args.source)
            print(f'Prepared {len(plan["rows"])} development scenes; fit was not started.')
        elif args.stage == 'fit':
            fit(args.output)
        else:
            evaluate(args.output)


if __name__ == '__main__':
    main()
