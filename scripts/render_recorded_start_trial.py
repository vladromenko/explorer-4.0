"""Render a captured MuJoCo trajectory; this performs no additional policy trial."""
import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def webm(source,destination):
    import av
    temporary=destination.with_name(destination.stem+'.tmp.webm')
    with av.open(str(source)) as incoming,av.open(str(temporary),mode='w',format='webm') as outgoing:
        original=incoming.streams.video[0];rate=original.average_rate or Fraction(5,1)
        stream=outgoing.add_stream('libvpx-vp9',rate=rate)
        stream.width=original.codec_context.width;stream.height=original.codec_context.height
        stream.pix_fmt='yuv420p';stream.bit_rate=0
        stream.options={'crf':'34','deadline':'realtime','cpu-used':'5','row-mt':'1','threads':'1'}
        count=0
        for count,frame in enumerate(incoming.decode(video=0),start=1):
            frame.pts=count-1;frame.time_base=Fraction(1,1)/rate
            for packet in stream.encode(frame):outgoing.mux(packet)
        for packet in stream.encode():outgoing.mux(packet)
    temporary.replace(destination)
    return dict(frames=count,codec='vp9',file=str(destination))


def render(source,destination):
    import cv2
    import av
    import mujoco
    import numpy as np
    from explorer4.sim.factory import make
    trace=json.loads(source.read_text())
    if trace['profile']!='rosmaster_floor_pick_recorded_start_sim':
        raise ValueError('Only the recorded-start floor scene is supported')
    env=make(trace['profile'],images=False)
    renderer=None;container=None
    temporary=destination.with_name(destination.stem+'.tmp.mp4')
    destination.parent.mkdir(parents=True,exist_ok=True)
    try:
        if env.manifest['xml_sha256']!=trace['model']:raise ValueError('Replay physics differ')
        env.reset(seed=trace['seed'])
        renderer=mujoco.Renderer(env.model,height=360,width=480)
        camera=mujoco.MjvCamera();camera.type=mujoco.mjtCamera.mjCAMERA_FREE
        camera.lookat[:]=[.02,0,.15];camera.distance=.85;camera.azimuth=135;camera.elevation=-25
        container=av.open(str(temporary),mode='w',format='mp4',options={'movflags':'+faststart'})
        stride=4
        stream=container.add_stream('libx264',rate=Fraction(str(trace['fps']))/stride)
        stream.width=960;stream.height=360;stream.pix_fmt='yuv420p'
        stream.options={'preset':'fast','crf':'23','threads':'1'}
        for i,qpos in enumerate(trace['qpos']):
            if i%stride and i!=len(trace['qpos'])-1:continue
            values=np.asarray(qpos,dtype=float)
            if values.shape!=env.data.qpos.shape or not np.isfinite(values).all():
                raise ValueError('Invalid captured state')
            env.data.qpos[:]=values;mujoco.mj_forward(env.model,env.data)
            renderer.update_scene(env.data,camera=camera);overview=renderer.render().copy()
            renderer.update_scene(env.data,camera=env.camera_name);wrist=renderer.render().copy()
            frame=np.concatenate([overview,wrist],axis=1)
            cv2.rectangle(frame,(0,0),(960,37),(12,20,28),-1)
            text=f'Seed {trace["seed"]} | recorded policy trial | {i/trace["fps"]:.2f} s | final outcome: {trace["outcome"]}'
            cv2.putText(frame,text,(12,25),cv2.FONT_HERSHEY_SIMPLEX,.5,(235,245,250),1,cv2.LINE_AA)
            for packet in stream.encode(av.VideoFrame.from_ndarray(frame,format='rgb24')):
                container.mux(packet)
            if i==0:cv2.imwrite(str(destination.with_suffix('.png')),cv2.cvtColor(frame,cv2.COLOR_RGB2BGR))
        for packet in stream.encode():container.mux(packet)
        container.close();container=None
        temporary.replace(destination)
        metadata={k:trace[k] for k in ('profile','seed','fps','model','outcome','checkpoint_sha256')}
        metadata.update(source_frames=len(trace['qpos']),render_stride=stride,
                        source_trace=str(source),additional_policy_trials=0)
        destination.with_suffix('.json').write_text(json.dumps(metadata,indent=2))
        webm(destination,destination.with_suffix('.webm'))
        return metadata
    finally:
        if container is not None:container.close()
        if renderer is not None:renderer.close()
        env.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('destination',type=Path)
    parser.add_argument('--webm-only',action='store_true')
    args=parser.parse_args();print(json.dumps(webm(args.source,args.destination) if args.webm_only else render(args.source,args.destination)))
