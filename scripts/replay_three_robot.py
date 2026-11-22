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


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene',type=Path,default=DATA/'simlab/reports'/NAME/'868000')
    replay(parser.parse_args().scene)
