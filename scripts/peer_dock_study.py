"""Frozen, paired evaluation of RGB waypoint sharing in the shared MuJoCo room."""
import argparse
import fcntl
import hashlib
import json
import math
import shutil
from pathlib import Path

import cv2
import numpy as np
from scipy.stats import binomtest

from explorer4.paths import DATA, ROOT
from explorer4.peer_dock_config import MAX_AGE_S
from explorer4.sim.state_codec import dump, load

NAME = 'peer-observation-dock-v1'
ROOMS = ('workshop', 'storage', 'inspection')
SPLITS = {'calibration': list(range(847100, 847106)), 'test': list(range(848000, 848024))}
SOURCES = ('scripts/peer_dock_study.py', 'explorer4/sim/cooperation.py', 'explorer4/sim/peer_dock.py',
           'explorer4/sim/fleet.py', 'explorer4/sim/mobile.py', 'explorer4/simlab/perception.py',
           'explorer4/sim/room.py', 'explorer4/sim/tank_model.py', 'explorer4/sim/state_codec.py')


def write(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False))
    temp.replace(path)


def frozen(path, value):
    if path.exists() and json.loads(path.read_text()) != value:
        raise ValueError(f'Frozen input differs: {path}')
    if not path.exists():
        write(path, value)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def room_for(seed):
    return ROOMS[seed % len(ROOMS)]


def scene_inputs(world, folder, seed, before_donor=None):
    folder.mkdir(parents=True, exist_ok=True)
    world.output = folder
    world.reset(seed)
    frozen(folder/'start.json', {'seed':seed, 'room':world.scene,
        'world_model_sha256':world.world.manifest['xml_sha256'],
        'initial_state_sha256':dump(folder/'initial-state.json', world.initial)})
    before = world.camera('tank', 'recipient-before')
    # Freeze the decision BEFORE asking the donor or branching on a rollout outcome.
    decision = {'request':before['packet'] is None, 'local_packet':before['packet'],
                'local_image_sha256':digest(folder/'recipient-before.png'), 'time_s':before['simulation_time_s']}
    if before_donor is not None:
        decision['local_measurement'] = before['measurement']
    frozen(folder/'decision.json', decision)
    if before_donor is not None:
        before_donor(decision)
    observed = world.observe(save=True)
    donor = {'packet':observed['packet'], 'recipient_held':observed['recipient_held'],
             'after_donor_state_sha256':dump(folder/'after-donor.json', world.world.snapshot())}
    frozen(folder/'donor.json', donor)


def local_scan(world, local):
    """Active onboard comparison with the same three-second sensing budget as the donor."""
    if local is not None:
        return world.dock(local, save=False)
    for step in range(60):
        yaw = world.sensors.odometry[2]
        turn = float(np.clip(-2 * math.atan2(math.sin(yaw), math.cos(yaw)), -.5, .5))
        world.world.step({'tank':[0.,turn]})
        world.sensors.integrate(.05)
        if step % 4 == 3:
            packet = world.camera('tank', None)['packet']
            if packet is not None:
                return world.dock(packet, save=False)
    return world.dock(None, save=False)


def rollouts(world, folder, seed, shuffled, shuffled_seed):
    world.output = folder
    world.reset(seed)
    decision = json.loads((folder/'decision.json').read_text())
    donor = json.loads((folder/'donor.json').read_text())['packet']
    branches = {}
    branches['local_only'] = world.dock(decision['local_packet'], save=False)
    world.rewind()
    branches['local_scan'] = local_scan(world, decision['local_packet'])
    # All three transport controls branch at the exact same post-observation state.
    state = load(folder/'after-donor.json')
    for name, packet in [('always', donor), ('stale', {**donor, 'stamp_s':donor['stamp_s']-MAX_AGE_S-.25} if donor else None),
                         ('shuffled', shuffled)]:
        world.rewind()
        world.world.restore(state)
        world.received = donor
        world.stage = 'observed'
        branches[name] = world.dock(packet, save=name=='always')
    result = {'seed':seed,'room':world.scene,'initial':json.loads((folder/'start.json').read_text()),
              'decision':decision,'donor_packet':donor,'shuffled_packet_seed':shuffled_seed,
              'registered_true_goal_score_only':state['tasks']['tank']['env']['goal'].tolist(),
              'branches':branches}
    write(folder/'outcomes.json',result)
    print(f"{world.scene} {seed}: local={branches['local_only']['task']} peer={branches['always']['task']} "
          f"self_scan={branches['local_scan']['task']} shuffled={branches['shuffled']['task']}",flush=True)


def summarize(rows, protocol):
    count = sum(r['decision']['request'] for r in rows)
    order = protocol['random_assignment_order']
    random = set([s for s in order if any(r['seed']==s for r in rows)][:count])
    names = ('local_only','local_scan','always','selective','matched_random','stale','shuffled')
    stats = {k:{'successes':0,'calls':0,'scenes':len(rows),'elapsed_sim_s':[]} for k in names}
    gains = losses = 0
    for r in rows:
        outcomes = r['branches']
        r['policies'] = {}
        call = r['decision']['request']
        for k in names:
            ref = k
            if k in ('selective','matched_random'):
                ref = 'always' if (call if k=='selective' else r['seed'] in random) else 'local_only'
            success = outcomes[ref]['task']=='success'
            r['policies'][k] = {'branch':ref,'success':success}
            stats[k]['successes'] += int(success)
            stats[k]['calls'] += int(ref not in ('local_only','local_scan'))
            stats[k]['elapsed_sim_s'].append(outcomes[ref]['simulation_time_s'])
        a, b = [r['policies'][k]['success'] for k in ('selective','matched_random')]
        gains += a and not b
        losses += b and not a
    for col in stats.values():
        col['median_elapsed_sim_s'] = float(np.median(col.pop('elapsed_sim_s')))
    return {'conditions':stats, 'paired_vs_random':{'gains':gains, 'losses':losses,
        'n':len(rows),'exact_two_sided_p':binomtest(gains,gains+losses).pvalue if gains+losses else 1.}}


def evaluate(root, worlds, split, protocol):
    seeds = SPLITS[split]
    base = root/split
    for seed in seeds:
        folder = base/str(seed)
        if not (folder/'donor.json').exists():
            scene_inputs(worlds[room_for(seed)],folder,seed)
    # A precommitted cyclic permutation uses the actual packet produced in another scene.
    for i,seed in enumerate(seeds):
        folder = base/str(seed)
        if not (folder/'outcomes.json').exists():
            other = seeds[(i+1) % len(seeds)]
            packet = json.loads((base/str(other)/'donor.json').read_text())['packet']
            rollouts(worlds[room_for(seed)], folder, seed, packet, other)
    rows = [json.loads((base/str(s)/'outcomes.json').read_text()) for s in seeds]
    return rows, summarize(rows,protocol)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=DATA/'runs'/NAME)
    parser.add_argument('--public',type=Path,default=DATA/'simlab/reports'/NAME)
    args = parser.parse_args()
    root=args.output
    root.mkdir(parents=True,exist_ok=True)
    lock=(root/'.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (root/'result.json').is_file():
        result=json.loads((root/'result.json').read_text())
        if result['status'] == 'completed' and digest(root/'protocol.json') == result['protocol_sha256']:
            print(json.dumps(result['conditions'],indent=2))
            return
    from explorer4.sim.cooperation import CooperationWorld
    cv2.setNumThreads(1)
    protocol={'version':1,'domain':'MuJoCo','seeds':SPLITS,'layouts':list(ROOMS),
        'split_rule':'disjoint seed groups in the same three room presets; no held-out-layout claim',
        'decision':'Request peer only when the local RGB image yields no valid marker pose.',
        'controller':'Known wall heading, surveyed starting pad, measured marker position and integrated ideal body twist.',
        'allocation':'One independent fixed random ordering. Match the selective request count after the paired rollouts.',
        'random_assignment_order':np.random.default_rng(197312).permutation(SPLITS['calibration']+SPLITS['test']).tolist(),
        'shuffled':'Cyclic next scene in the listed split. Retain the actual peer payload including frame hash and time.',
        'stale':'Same donor pose with timestamp aged by one second. Freshness tolerance is 0.75 s.',
        'score':'Existing independent 8 cm / 0.15 rad stable for 0.5 s docking verifier.',
        'software_hashes':{name:digest(ROOT/name) for name in SOURCES},
        'weight_updates':0,'physical_robot_commands':0}
    frozen(root/'protocol.json',protocol)
    worlds={}
    try:
        for room in ROOMS:
            worlds[room]=CooperationWorld(root/'scratch'/room,847100,room)
        _, calibration = evaluate(root,worlds,'calibration',protocol)
        frozen(root/'calibration.json',calibration)
        rows, score = evaluate(root,worlds,'test',protocol)
        result={'status':'completed','domain':'simulation','scenes':len(rows),'protocol_sha256':digest(root/'protocol.json'),
                **score,'calibration':calibration,'weight_updates':0,'physical_robot_commands':0,
                'evidence':[],'by_room':{room:sum(r['policies']['selective']['success'] for r in rows if r['room']==room)
                                         for room in ROOMS}}
        public=args.public
        public.mkdir(parents=True,exist_ok=True)
        for row in rows:
            seed=str(row['seed'])
            folder=public/seed
            folder.mkdir(exist_ok=True)
            source=root/'test'/seed
            names=('recipient-before.png','donor-observation.png','recipient-final.png','world-final.png')
            for name in names:
                shutil.copy2(source/name,folder/name)
            write(folder/'outcomes.json',row)
            result['evidence'].append({'seed':row['seed'],'room':row['room'],'outcomes':seed+'/outcomes.json',
                'local_frame':seed+'/'+names[0],'donor_frame':seed+'/'+names[1],'final_frame':seed+'/'+names[2],
                'overview':seed+'/'+names[3]})
        shutil.copy2(root/'protocol.json',public/'protocol.json')
        write(root/'result.json',result)
        write(public/'result.json',result)
        print(json.dumps(score,indent=2),flush=True)
    finally:
        for world in worlds.values():
            world.close()
        lock.close()


if __name__ == '__main__':
    main()
