"""Paired held-out SO-101 rollouts: identical policy and physics, four sources of cube position."""
import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import cv2
import mujoco
import numpy as np

from explorer4.paths import DATA,ROOT
from explorer4.simlab import contract
from explorer4.simlab.arm_warp import MAX_STEP
from explorer4.simlab.artifact import Policy
from explorer4.simlab.so101_rgb import (BOX,CAMERA,CAMERA_TO_BASE,FOV,K,POSITION,SIZE,
                                        CubeTracker,PickBelief,OverheadScene,simultaneous_jaw_contact)

MODES = ('legacy_noisy','overhead_rgb','exact_xyz','constant','rgb_pick_belief','constant_pick_belief')
DEFAULT_OUT = DATA/'simlab/reports/so101-overhead-rgb-v1'
POLICY = DATA/'simlab/policies/so101_bc_v1'


def save(path,value):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,indent=2,allow_nan=False))
    tmp.replace(path)


def sha(path):
    with Path(path).open('rb') as src:
        return hashlib.file_digest(src,'sha256').hexdigest()


def summary(records):
    return {'episodes':len(records),**{key:sum(bool(r[key]) for r in records) for key in
            ('success','contact_lift','released_after_contact_lift','terminal_box','terminal_released','terminal_stationary')}}


def episode(env,policy,tracker,renderer,seed,mode,rng,video):
    env.reset(seed=seed)
    policy.reset()
    tracker.reset()
    belief=PickBelief(env.model)
    command=env.data.ctrl[:6].copy()
    lo,hi=env.ranges[:,0],env.ranges[:,1]
    horizon=int(env.deadline_s*env.fps)
    frames,errors=[],[]
    visible_count=0
    lift=False
    released_after_lift=False
    max_z=0.
    initial=env.data.qpos.copy()
    initial_z=env.data.body('task_cube').xpos[2]
    for t in range(horizon):
        now=t/env.fps
        visible,age=1,0.
        rgb=None
        if mode in ('rgb_pick_belief','constant_pick_belief'):
            if mode=='rgb_pick_belief' and (belief.pick is None or video):
                renderer.update_scene(env.data,camera=CAMERA)
                rgb=renderer.render()
            cube,visible,age,optical=belief.observe(env.data.qpos[:6].copy(),rgb,constant=mode=='constant_pick_belief')
            visible_count+=optical
        elif mode=='overhead_rgb':
            renderer.update_scene(env.data,camera=CAMERA)
            rgb=renderer.render()
            cube,visible,age=tracker.measure(rgb,now)
        elif mode=='constant':
            cube=np.array([.24,-.06,.016])   # geometric midpoint, fixed before evaluation
        else:
            cube=env.data.body('task_cube').xpos.copy()
            if mode=='legacy_noisy':
                cube+=rng.normal(0,.005,3)     # original evaluation stream, RNG seed=1
        if mode=='overhead_rgb':
            visible_count+=visible
            if visible:
                errors.append(np.abs(cube-env.data.body('task_cube').xpos))
        obs=contract.build_arm(2*(env.data.qpos[:6]-lo)/(hi-lo)-1,env.data.qvel[:6],cube,visible,age,BOX,t/horizon)
        if (mode!='overhead_rgb' or tracker.last_at is not None) and (not mode.endswith('pick_belief') or belief.pick is not None):
            target=lo+(policy.act_target(obs)+1)/2*(hi-lo)
            command=command+np.clip(target-command,-MAX_STEP,MAX_STEP)
        _,_,done,timeout,info=env.step(env.from_radians(command))
        true_z=float(env.data.body('task_cube').xpos[2])
        max_z=max(max_z,true_z)
        lift=lift or (true_z-initial_z>.03 and simultaneous_jaw_contact(env))
        released_after_lift=released_after_lift or bool(lift and info['released'])
        if video and (t%2==0 or done or timeout):
            from explorer4.simlab.video import _caption
            renderer.update_scene(env.data,camera='overview')
            view=renderer.render().copy()
            inset=rgb.copy() if rgb is not None else view
            frame=np.hstack([view,inset])
            frames.append(_caption(frame,[f't={now:.1f}s',f'{mode}, measured {visible}' if mode=='overhead_rgb' else f'{mode} (RGB anchor + joint FK)',f'lift {int(lift)} box {int(info["inside_box"])}']))
        if done or timeout:
            break
    if frames:
        from explorer4.simlab.video import _write
        _write(video,frames+[frames[-1]]*10,15)
    result={'seed':seed,'steps':t+1,'initial_qpos_sha256':hashlib.sha256(initial.astype('<f8').tobytes()).hexdigest(),
            'success':info['outcome']=='success','terminal_box':info['inside_box'],'terminal_released':info['released'],
            'terminal_stationary':info['stationary'],'stable_s':info['stable_s'],'reason':info['termination_reason'],
            'contact_lift':bool(lift),'released_after_contact_lift':released_after_lift,'max_cube_height_m':max_z}
    if mode=='overhead_rgb':
        result.update(frames_visible=visible_count,observation_frames=t+1,
                      visible_mae_xyz_m=np.mean(errors,axis=0).tolist() if errors else None)
    if mode.endswith('pick_belief'):
        result.update(optical_measurement_frames=visible_count,anchor_xyz_m=None if belief.pick is None else belief.pick.tolist())
    return result


def worker(out,mode):
    cv2.setNumThreads(1)
    frozen=json.loads((out/'protocol.json').read_text())
    if sha(POLICY/'policy.npz')!=frozen['weights_sha256']:
        raise ValueError('Frozen actor has changed')
    policy=Policy(POLICY)
    env=OverheadScene()
    if not np.allclose(env.data.body('target_box').xpos,BOX):
        raise ValueError('Box fixture no longer matches the declared scene position')
    rng=np.random.default_rng(1)
    tracker=CubeTracker()
    renderer=mujoco.Renderer(env.model,SIZE,SIZE) if mode in ('overhead_rgb','rgb_pick_belief') else None
    path=out/f'{mode}.json'
    records=[]
    try:
        for seed in frozen['seeds']:
            video=out/f'{mode}-seed{seed}.mp4' if seed==frozen['seeds'][0] and mode in ('overhead_rgb','rgb_pick_belief') else None
            records.append(episode(env,policy,tracker,renderer,seed,mode,rng,video))
            save(path,{'status':'completed' if len(records)==len(frozen['seeds']) else 'running','method':mode,
                       'model':env.manifest,'records':records,'summary':summary(records)})
    finally:
        if renderer is not None:
            renderer.close()
        env.close()


def study(out,seeds):
    out.mkdir(parents=True,exist_ok=True)
    previous=json.loads((POLICY/'eval-cpu.json').read_text())
    files=[Path(__file__).resolve(),ROOT/'explorer4/simlab/so101_rgb.py',ROOT/'explorer4/simlab/perception.py',
           ROOT/'explorer4/sim/environment.py',ROOT/'explorer4/sim/models.py',ROOT/'explorer4/simlab/artifact.py',
           ROOT/'explorer4/simlab/contract.py',ROOT/'explorer4/simlab/arm_warp.py']
    protocol={'seeds':seeds,'modes':list(MODES),'robot':'so101','physics_engine':mujoco.__version__,
              'weights_sha256':sha(POLICY/'policy.npz'),'export_sha256':sha(POLICY/'policy.json'),
              'old_report_sha256':sha(POLICY/'eval-cpu.json'),'code':{str(p.relative_to(ROOT)):sha(p) for p in files},
              'cad_sensor':{'camera':CAMERA,'width':SIZE,'height':SIZE,'K':K.tolist(),'optical_to_base':CAMERA_TO_BASE.tolist(),
                            'fovy_deg':FOV,'known_cube_side_m':.032,'sampling':'30 Hz, rendered RGB only'},
              'box_in_base_m':BOX.tolist(),'box_source':'fixed scene fixture in the Menagerie task extension (not estimated)',
              'methods':{'overhead_rgb':'Orange colour component via OpenCV; top-down pinhole XY and depth from known cube edge; reject partial/non-square components. Before first detection hold initial command, on occlusion hold last measured xyz with visible=0 and saturated age. No depth, segmentation buffer, true target or contact enters policy.',
                         'legacy_noisy':'Original noisy true cube XYZ, Gaussian 5 mm on each axis; numpy Generator seed 1 consumed sequentially.',
                         'exact_xyz':'Simulator cube centre delivered directly, no noise. Oracle control.',
                         'rgb_pick_belief':'First unobstructed top-face colour centroid projected onto the surveyed tabletop. Then a distinct encoder adapter updates a possible grasp from known arm FK, gripper closure and distance; release holds the estimated drop location. The actor receives estimate-available instead of pixel-visible, actual RGB acquisition is recorded separately. No true cube coordinates or contact.',
                         'constant_pick_belief':'Same encoder/closure adapter, identical estimate-available input; fixed workspace midpoint replaces initial RGB.',
                         'constant':'Workspace midpoint [.24,-.06,.016] m throughout, visible=1, age=0.'},
              'success':'Original scorer: open separated gripper, stationary cube inside bin for at least 0.5 s',
              'contact_lift':'Cube rose >30 mm above initial centre while both fixed and moving jaw bodies contacted it at a 30 Hz observation',
              'scope':'Easy nominal fixture; static monocular calibration from camera design; no physical success claim',
              'development_seeds':[910000,910001],
              'primary_comparison':'rgb_pick_belief vs constant_pick_belief, exact two-sided McNemar test of discordant paired outcomes',
              'test_recordings_used':0,'weight_updates':0,'motor_commands_sent':0}
    manifest=out/'protocol.json'
    if manifest.exists() and json.loads(manifest.read_text())!=protocol:
        raise ValueError('Existing protocol differs. Use a separate output directory.')
    save(manifest,protocol)
    def launch(mode):
        with (out/f'{mode}.log').open('w') as log:
            subprocess.run([sys.executable,str(Path(__file__).resolve()),'--out',str(out),'--worker',mode],
                cwd=ROOT,env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MUJOCO_GL':'egl'},
                stdout=log,stderr=subprocess.STDOUT,check=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(launch,MODES))
    reports={mode:json.loads((out/f'{mode}.json').read_text()) for mode in MODES}
    pairs=list(zip(*(reports[m]['records'] for m in MODES),strict=True))
    for rows in pairs:
        if len({(r['seed'],r['initial_qpos_sha256']) for r in rows})!=1:
            raise ValueError('Scene ordering or initial configuration differs between conditions')
    old={r['seed']:r for r in previous['episodes']}
    current=reports['legacy_noisy']['records']
    exact_match=sum(r['seed'] in old and (r['success'],r['steps'])==(old[r['seed']]['outcome']=='success',old[r['seed']]['steps']) for r in current)
    comparison={}
    rgb=reports['overhead_rgb']['records']
    for mode in MODES:
        ref=reports[mode]['records']
        comparison[mode]={'rgb_only':sum(a['success'] and not b['success'] for a,b in zip(rgb,ref)),
                          'other_only':sum(b['success'] and not a['success'] for a,b in zip(rgb,ref))}
    from scipy.stats import binomtest
    camera=reports['rgb_pick_belief']['records']
    fixed=reports['constant_pick_belief']['records']
    gained=sum(a['success'] and not b['success'] for a,b in zip(camera,fixed))
    lost=sum(b['success'] and not a['success'] for a,b in zip(camera,fixed))
    primary={'rgb_only':gained,'constant_only':lost,'paired_success_difference':(gained-lost)/len(camera),
             'n':len(camera),'exact_two_sided_p':binomtest(gained,gained+lost,.5).pvalue if gained+lost else 1.}
    result={'status':'completed','primary_comparison':primary,'protocol_sha256':sha(manifest),'seeds':seeds,'same_initial_scene_every_pair':True,
            'summary':{m:reports[m]['summary'] for m in MODES},'paired_discordance':comparison,
            'legacy_outcome_and_step_match_count':exact_match,'physical_skill_verified':False,'motor_commands_sent':0}
    save(out/'result.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,default=DEFAULT_OUT)
    parser.add_argument('--start',type=int,default=200000)
    parser.add_argument('--count',type=int,default=50)
    parser.add_argument('--worker',choices=MODES)
    args=parser.parse_args()
    if args.worker:
        worker(args.out,args.worker)
    else:
        if args.count<1:
            parser.error('At least one seed required')
        study(args.out,list(range(args.start,args.start+args.count)))
