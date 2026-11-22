"""Render a saved peer-assisted approach and verify the original command sequence."""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np

from explorer4.paths import DATA
from explorer4.sim.cooperation import CooperationWorld
from explorer4.sim.state_codec import load
from scripts.peer_dock_study import NAME, digest, write


def panel(rgb, title):
    panel=np.full((250,320,3),27,dtype=np.uint8)
    h=round(rgb.shape[0]*320/rgb.shape[1])
    display=cv2.resize(rgb,(320,h),interpolation=cv2.INTER_AREA)
    top=(240-h)//2
    panel[top:top+h]=display
    cv2.rectangle(panel,(0,0),(319,22),(27,27,27),-1)
    cv2.putText(panel,title,(7,16),cv2.FONT_HERSHEY_SIMPLEX,.45,(242,242,242),1,cv2.LINE_AA)
    return panel


def replay(source,seed,output,split='test'):
    folder=source/split/str(seed)
    row=json.loads((folder/'outcomes.json').read_text())
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        scratch=Path(tmp)
        world=CooperationWorld(scratch,seed,row['room'])
        try:
            world.world.restore(load(folder/'after-donor.json'))
            donor=cv2.imread(str(folder/'donor-observation.png'))[:,:,::-1]
            packet=world.sensors.packet('rosmaster',donor)
            original=json.loads((folder/'donor.json').read_text())['packet']
            if (packet is None or packet['frame_sha256']!=original['frame_sha256']
                    or not np.allclose(packet['target_xy_m'],original['target_xy_m'],atol=1e-10,rtol=0)):
                raise ValueError('Stored image and kinematic state do not reproduce the donor measurement')
            world.received=original
            source_frame=cv2.imread(str(folder/'recipient-before.png'))[:,:,::-1]
            encoder=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','rawvideo','-pix_fmt','rgb24',
                '-s','960x282','-r','8','-i','pipe:0','-an','-c:v','libx264','-threads','1',
                '-pix_fmt','yuv420p','-movflags','+faststart',str(scratch/'replay.mp4')],stdin=subprocess.PIPE)
            try:
                def frame(tick,sim):
                    panels=np.hstack([panel(source_frame,'Tank | before request'),panel(donor,'ROSMASTER | returned observation'),
                                      panel(sim.render(),'Shared room | replay')])
                    footer=np.full((32,960,3),27,dtype=np.uint8)
                    text=f'Paired scene {seed} | command {tick} | sim time {sim.data.time:.2f} s | ArUco 7'
                    cv2.putText(footer,text,(9,21),cv2.FONT_HERSHEY_SIMPLEX,.53,(230,230,230),1,cv2.LINE_AA)
                    encoder.stdin.write(np.vstack([panels,footer]).tobytes())
                frame(0,world.world)
                def sample(tick,sim):
                    if tick % 3==0: frame(tick,sim)
                result=world.dock(original,save=False,on_tick=sample)
                frame(result['actions_sent'],world.world)
            finally:
                encoder.stdin.close()
                status=encoder.wait()
            if status:
                raise RuntimeError('Video encoding failed')
            expected=row.get('branches',row)['always']
            for key in ('task','commands_sha256','actions_sent','distance_m','yaw_error_rad'):
                if result[key]!=expected[key]:
                    raise ValueError('Replay differs at '+key)
            os.replace(scratch/'replay.mp4',output)
            write(output.with_suffix('.json'),{'seed':seed,'condition':'always','task':result['task'],
                  'frame_sha256':original['frame_sha256'],'commands_sha256':result['commands_sha256'],
                  'actions_sent':result['actions_sent'],'original_outcome_sha256':digest(folder/'outcomes.json'),
                  'video_sha256':digest(output),'video':output.name})
        finally:
            world.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=DATA/'runs'/NAME)
    parser.add_argument('--seed',type=int,default=848000)
    parser.add_argument('--split',choices=['test','train','calibration'],default='test')
    parser.add_argument('--output',type=Path,default=None)
    args=parser.parse_args()
    video=args.output or DATA/'simlab/reports'/args.source.name/f'replay-{args.seed}.mp4'
    replay(args.source,args.seed,video,args.split)
    print(video)


if __name__=='__main__':
    main()
