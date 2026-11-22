"""Freeze a controlled screen study and measure development scenes without fitting a model."""
import argparse
import fcntl
import json
import shutil
import zipfile
from pathlib import Path

import numpy as np

from explorer4.paths import DATA, ROOT
from explorer4.peer_request_policy import read, local_features
from scripts import peer_dock_study as study

NAME = 'peer-screen-dock-v2'
SPLITS = {'train': ('workshop_screen', list(range(861000, 861016))),
          'calibration': ('storage_screen', list(range(862000, 862008))),
          'test': ('inspection_screen', list(range(863000, 863016)))}
SOURCES = (*study.SOURCES, 'explorer4/peer_dock_config.py', 'explorer4/sim/peer_screens.py',
           'explorer4/peer_request_policy.py', 'scripts/peer_screen_evidence.py')
CALL_COST = .10
TIME_COST = .005


def protocol():
    return {'version':2, 'splits':{k:{'room':r,'seeds':s} for k,(r,s) in SPLITS.items()},
            'random_order':np.random.default_rng(452).permutation(SPLITS['test'][1]).tolist(),
            'development':'Workshop trains. Storage selects one threshold. Inspection opens only after fit.',
            'scene':'Opaque contact-enabled screen on a bracket. Alternating sheltered and parked across each room. Targets and starting angles vary independently.',
            'local_comparator':'Use the initial camera pose if available, otherwise rotate on the pad for at most 3 s, then drive only from a valid measured pose.',
            'primary':'Independent stable docking; compare learned and matched-random with identical numbers of requests and active local fallback.',
            'utility':'I(success) - 0.10 * peer_calls - 0.005 * total_simulated_seconds',
            'call_cost':CALL_COST, 'per_second_cost':TIME_COST, 'subjects':'simulated Tank + ROSMASTER',
            'software_hashes':{f:study.digest(ROOT/f) for f in SOURCES}}


def capture_source(root, frozen):
    archive = root/'frozen-source.zip'
    if not archive.exists():
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as out:
            for name, expected in frozen['software_hashes'].items():
                if expected != study.digest(ROOT/name):
                    raise ValueError('Source changed during preparation: ' + name)
                out.write(ROOT/name, name)


def development(root, public):
    from explorer4.sim.cooperation import CooperationWorld
    root.mkdir(parents=True, exist_ok=True)
    frozen = protocol()
    study.frozen(root/'protocol.json', frozen)
    capture_source(root, frozen)
    rows = []
    for split in ('train', 'calibration'):
        room, seeds = SPLITS[split]
        world = CooperationWorld(root/'scratch'/room, seeds[0], room)
        try:
            for seed in seeds:
                folder = root/split/str(seed)
                path = folder/'outcomes.json'
                if not path.exists():
                    # Snapshot local data before the donor and retain both original PNGs.
                    if not (folder/'donor.json').exists():
                        study.scene_inputs(world, folder, seed, before_donor=lambda d: None)
                    world.output = folder
                    world.reset(seed)
                    initial = read(folder/'decision.json')
                    local = world.local_scan(initial['local_packet'], save=True)
                    world.rewind()
                    world.world.restore(study.load(folder/'after-donor.json'))
                    donor = read(folder/'donor.json')['packet']
                    world.received = donor
                    peer = world.dock(donor, save=False)
                    study.frozen(path, {'seed':seed,'room':room,'local_scan':local,'always':peer,
                                        'initial_sha256':study.digest(folder/'initial-state.json')})
                d = read(folder/'decision.json')
                a = read(path)
                rows.append({'split':split,'room':room,'seed':seed,
                             'x':local_features(d['local_packet'], d['local_measurement']),
                             'image_sha256':d['local_image_sha256'],
                             'local':int(a['local_scan']['task']=='success'),
                             'peer':int(a['always']['task']=='success'),
                             'local_time_s':a['local_scan']['simulation_time_s'],
                             'peer_time_s':a['always']['simulation_time_s'],
                             'outcomes_sha256':study.digest(path)})
                print(f"{split} {seed}: active={rows[-1]['local']} peer={rows[-1]['peer']}",flush=True)
        finally:
            world.close()
    final = {'status':'completed','phase':'development_only','protocol_sha256':study.digest(root/'protocol.json'),
             'rows':rows,'test_outcomes_read':False,'weight_updates':0,'physical_robot_commands':0}
    study.frozen(root/'development.json', final)
    public.mkdir(parents=True, exist_ok=True)
    for name in ('protocol.json','development.json','frozen-source.zip'):
        shutil.copy2(root/name, public/name)
    for row in rows:
        src = root/row['split']/str(row['seed'])
        dest = public/str(row['seed'])
        dest.mkdir(exist_ok=True)
        for name in ('recipient-before.png','local-scan-last.png','recipient-final.png','donor-observation.png',
                     'world-observation.png','decision.json','donor.json','outcomes.json'):
            if (src/name).is_file():
                shutil.copy2(src/name, dest/name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=DATA/'runs'/NAME)
    parser.add_argument('--public',type=Path,default=DATA/'simlab/reports'/NAME)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    with (args.output/'.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (args.output/'development.json').exists():
            print('Development outcomes already frozen.')
            return
        development(args.output, args.public)


if __name__ == '__main__':
    main()
