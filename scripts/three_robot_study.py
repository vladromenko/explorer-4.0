"""Paired three-robot docking demonstration. No training and no physical interfaces."""
import argparse
import fcntl
import json
import zipfile
from pathlib import Path

import cv2

from explorer4.paths import DATA, ROOT
from explorer4.cognitive.registry import cards
from explorer4.cognitive.three_robot_cards import ROLES
from explorer4.sim.state_codec import dump
from explorer4.sim.three_robot_dock import COLOURS, ThreeRobotDock, order_from_rgb
from scripts.peer_dock_study import digest, frozen, write

NAME = 'three-robot-dock-v1'
SCENES = [(868000,'workshop'),(868001,'storage'),(868002,'inspection'),(868003,'workshop')]
CONDITIONS = ('intact','missing_order','wrong_order','missing_pose','wrong_pose')
SOURCES = ('scripts/three_robot_study.py','explorer4/sim/three_robot_dock.py','explorer4/cognitive/three_robot_cards.py',
           'explorer4/sim/fleet.py','explorer4/sim/cooperation.py','explorer4/sim/peer_dock.py','explorer4/sim/mobile.py')


def scene(folder,seed,preset):
    folder.mkdir(parents=True,exist_ok=True)
    world=ThreeRobotDock(folder,seed,preset)
    try:
        world.overview('team-initial')
        initial_sha=dump(folder/'initial-state.json',world.initial)
        order=order_from_rgb(world.frame('so101','so101-order'))
        frozen(folder/'order.json',order)
        # On an absent input the live mission never acquires a donor frame.
        missing=world.drive(None,None)
        world.rewind()
        if order['station'] is None:
            return {'seed':seed,'room':preset,'outcome':'order_unavailable','order':order,
                    'initial_state_sha256':initial_sha,'conditions':{name:missing for name in CONDITIONS}}
        remote=world.observe_stations()
        observed=world.world.snapshot()
        observed_sha=dump(folder/'observation-state.json',observed)
        actual=world.measure(remote,order)
        other=next(k for k in COLOURS if k!=order['station'])
        wrong_order={**order,'station':other}
        alternate=world.measure(remote,wrong_order)
        # This fault retains the accepted identity and transposes only sensed coordinates.
        shifted={**actual,'target_xy_m':alternate['target_xy_m']} if actual and alternate else None
        cases={'intact':(order,actual), 'wrong_order':(wrong_order,alternate),
               'missing_pose':(order,None), 'wrong_pose':(order,shifted)}
        conditions={'missing_order':missing}
        for name,(message,pose) in cases.items():
            world.rewind()
            world.world.restore(observed)
            conditions[name]=world.drive(message,pose,record=name=='intact')
            conditions[name].update(received_order=message['station'],rosmaster_acted=True)
        conditions['missing_order'].update(received_order=None,rosmaster_acted=False)
        trace={'seed':seed,'room':preset,'outcome':'success' if conditions['intact']['success'] else 'failure',
               'initial_state_sha256':initial_sha,'after_rosmaster_sha256':observed_sha,
               'order':order,'requested_measurement':actual,'alternate_measurement':alternate,'conditions':conditions,
               'scorer_only':{'customer_station':world.required,'station_centres_xy_m':{k:v.tolist() for k,v in world.goals.items()}},
               'artifacts':{'so101':'so101-order.png','rosmaster':'rosmaster-stations.png','tank':'tank-final.png',
                            'before':'team-initial.png','after':'team-final.png'}}
        return trace
    finally:
        world.close()


def run(folder,scenes):
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        cv2.setNumThreads(1)
        if (folder/'result.json').is_file():
            saved=json.loads((folder/'result.json').read_text())
            previous=json.loads((folder/'protocol.json').read_text())
            if (saved['status']!='completed' or previous['scenes']!=[list(x) for x in scenes]
                    or saved['protocol_sha256']!=digest(folder/'protocol.json')
                    or any(row['trace_sha256']!=digest(folder/row['trace']) for row in saved['evidence'])):
                raise ValueError('Existing result and requested scenes differ')
            return saved
        registry=cards()
        selected={key:registry[key].version for key in ROLES}
        if any(registry[k].sim_admission!='available' or registry[k].real_admission!='blocked' for k in ROLES):
            raise ValueError('Three-robot mission requires its simulation-only registered roles')
        protocol={'version':1,'domain':'simulation','scenes':[list(x) for x in scenes],'conditions':list(CONDITIONS),
                  'method':'SO-101 RGB token colour; ROSMASTER RGB square corners, IPPE and surveyed camera frame; Tank body-twist odometry and existing geometric drive.',
                  'evaluator':'Independent stored customer request, 8 cm, 0.15 rad, stationary for 0.5 s.',
                  'skills':selected,'sources':{f:digest(ROOT/f) for f in SOURCES},'training':False,'hardware':False}
        frozen(folder/'protocol.json',protocol)
        if not (folder/'frozen-source.zip').exists():
            with zipfile.ZipFile(folder/'frozen-source.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
                for name in SOURCES:
                    archive.write(ROOT/name,name)
        rows=[]
        for seed,preset in scenes:
            dest=folder/str(seed)
            path=dest/'trace.json'
            if not path.exists():
                write(path,scene(dest,seed,preset))
            trace=json.loads(path.read_text())
            rows.append({'seed':seed,'room':preset,'trace':str(seed)+'/trace.json','trace_sha256':digest(path),
                         'success':{k:trace['conditions'][k]['success'] for k in CONDITIONS}})
            print(seed,rows[-1]['success'],flush=True)
        result={'status':'completed','domain':'simulation','scenes':len(rows),'protocol_sha256':digest(folder/'protocol.json'),
                'successes':{k:sum(r['success'][k] for r in rows) for k in CONDITIONS},'evidence':rows,
                'interpretation':'Finite three-role demonstration with engineered skills. No mobile manipulation or learned help selector evaluated.',
                'physical_commands':0,'weight_updates':0}
        write(folder/'result.json',result)
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=None)
    parser.add_argument('--room',choices=['workshop','storage','inspection'],default='workshop')
    parser.add_argument('--output',type=Path,default=DATA/'simlab/reports'/NAME)
    args=parser.parse_args()
    run(args.output,SCENES if args.seed is None else [(args.seed,args.room)])


if __name__=='__main__':
    main()
