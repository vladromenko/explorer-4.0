"""Render a recorded three-robot order and verify every Tank command against its original digest."""
import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np

from explorer4.paths import DATA
from explorer4.sim.state_codec import load
from explorer4.sim.three_robot_dock import ThreeRobotDock, order_from_rgb
from scripts.peer_dock_study import digest, write
from scripts.replay_peer_dock import panel
from scripts.three_robot_study import NAME


def replay(folder):
    trace=json.loads((folder/'trace.json').read_text())
    expected=trace['conditions']['intact']
    if not expected['success']:
        raise ValueError('The selected intact trial did not complete its order')
    so=cv2.imread(str(folder/'so101-order.png'))[:,:,::-1]
    ros=cv2.imread(str(folder/'rosmaster-stations.png'))[:,:,::-1]
    order=order_from_rgb(so)
    if order!=trace['order']:
        raise ValueError('SO-101 order differs from the saved camera frame')
    with tempfile.TemporaryDirectory(dir=folder) as tmp:
        scratch=Path(tmp)
        world=ThreeRobotDock(scratch,trace['seed'],trace['room'])
        try:
            world.world.restore(load(folder/'observation-state.json'))
            packet=world.measure(ros,order)
            if packet!=expected['consumed']:
                raise ValueError('ROSMASTER result differs from the saved camera and kinematic state')
            writer=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','rawvideo','-pix_fmt','rgb24',
                    '-s','960x282','-r','8','-i','pipe:0','-an','-c:v','libx264','-threads','1',
                    '-pix_fmt','yuv420p','-movflags','+faststart',str(scratch/'replay.mp4')],stdin=subprocess.PIPE)
            tank=world.world.views['tank']
            commands=[]
            def capture():
                view=world.world.render()
                tiles=np.hstack([panel(so,'SO-101 | original order token'),panel(ros,'ROSMASTER | original station view'),
                                 panel(view,'Tank | shared-world motion')])
                footer=np.full((32,960,3),27,dtype=np.uint8)
                label=f"Seed {trace['seed']} | order {order['station']} | Tank command {len(commands)} | t = {world.world.data.time:.2f} s"
                cv2.putText(footer,label,(8,20),cv2.FONT_HERSHEY_SIMPLEX,.52,(230,230,230),1,cv2.LINE_AA)
                writer.stdin.write(np.vstack([tiles,footer]).tobytes())
            try:
                capture()
                while not tank.done:
                    action=world.sensors.action(packet)
                    world.world.step({'tank':action})
                    world.sensors.integrate(tank.env.dt)
                    commands.append(action)
                    if len(commands)%3==0:capture()
                capture()
            finally:
                writer.stdin.close()
                status=writer.wait()
            command_sha=hashlib.sha256(np.asarray(commands,dtype='<f8').tobytes()).hexdigest()
            if (status or command_sha!=expected['commands_sha256'] or len(commands)!=expected['actions']
                    or tank.env.info()['distance_m']!=expected['distance_to_ordered_dock_m']):
                raise ValueError('Replay failed the original action and terminal state check')
            os.replace(scratch/'replay.mp4',folder/'replay.mp4')
            write(folder/'replay.json',{'order':order['station'],'actions':len(commands),'commands_sha256':command_sha,
                  'source_trace_sha256':digest(folder/'trace.json'),'video_sha256':digest(folder/'replay.mp4')})
        finally:
            world.close()


def verify_endpoints(folder):
    """Replay the two distinct commanded paths and independently recompute both terminal distances."""
    trace=json.loads((folder/'trace.json').read_text())
    state=load(folder/'observation-state.json')
    records={}
    with tempfile.TemporaryDirectory() as temp:
        world=ThreeRobotDock(Path(temp),trace['seed'],trace['room'])
        try:
            observed=order_from_rgb(cv2.imread(str(folder/'so101-order.png'))[:,:,::-1])
            donor=cv2.imread(str(folder/'rosmaster-stations.png'))[:,:,::-1]
            required=trace['scorer_only']['customer_station']
            goals=trace['scorer_only']['station_centres_xy_m']
            if observed!=trace['order'] or observed['station']!=required:
                raise ValueError('Source order differs from the scorer')
            for condition in ('intact','wrong_order'):
                world.rewind()
                world.world.restore(state)
                previous=trace['conditions'][condition]
                message={**observed,'station':previous['received_order']}
                pose=world.measure(donor,message)
                if pose!=previous['consumed']:
                    raise ValueError('Original camera does not reproduce the delivered pose')
                current=world.drive(message,pose)
                xy=world.world.views['tank'].env.data.qpos[:2].copy()
                distances={k:float(np.linalg.norm(xy-np.asarray(goal))) for k,goal in goals.items()}
                expected=(distances[required]<.08 and abs(current['yaw_error_rad'])<.15
                          and current['stable_s']>=.5 and world.world.views['tank'].env.info()['stationary'])
                if (current['commands_sha256']!=previous['commands_sha256'] or expected!=previous['success']
                        or abs(distances[required]-previous['distance_to_ordered_dock_m'])>1e-9):
                    raise ValueError('Independent terminal pose or original commands differ')
                records[condition]={'terminal_xy_m':xy.tolist(),'distance_by_station_m':distances,
                                    'confirmed':bool(expected),'commands_sha256':current['commands_sha256']}
            if trace['conditions']['wrong_pose']['commands_sha256']!=records['wrong_order']['commands_sha256']:
                raise ValueError('Swapped positions should have the same physical transcript')
            if any(trace['conditions'][k]['actions']!=0 for k in ('missing_order','missing_pose')):
                raise ValueError('Robots acted without an observation')
        finally:
            world.close()
    return {'seed':trace['seed'],'room':trace['room'],'order':required,'trace_sha256':digest(folder/'trace.json'),
            'so101_frame_sha256':trace['order']['frame_sha256'],
            'rosmaster_frame_sha256':trace['requested_measurement']['source_frame_sha256'],
            'ordered_xy_m':goals[required],'endpoints':records}



if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene',type=Path,default=DATA/'simlab/reports'/NAME/'868000')
    parser.add_argument('--verify-endpoints',action='store_true')
    args=parser.parse_args()
    if args.verify_endpoints:
        print(json.dumps(verify_endpoints(args.scene),indent=2))
    else:
        replay(args.scene)
