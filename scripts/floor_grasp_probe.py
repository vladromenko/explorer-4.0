"""Paired offline floor-cube diagnosis. Only the initial joint pose varies between scenes."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from explorer4.paths import DATA
from explorer4.sim.factory import EXPERTS, make
from explorer4.study_day import write_atomic

PROFILE = 'rosmaster_floor_pick_sim'
STUDY = DATA/'runs/floor-cube-pair-20261121/grasp-diagnosis'
MODES = ('nominal', 'real_train_medoid')


def read_manifest():
    return json.loads((STUDY/'protocol.json').read_text())


def setup(env, plan, mode, seed):
    if env.manifest['xml_sha256'] != plan['model']:
        raise ValueError('Scene geometry differs from the completed comparison')
    center = np.array(plan['start_pose'][mode], float)
    if np.any(center < env.action_space.low) or np.any(center > env.action_space.high):
        raise ValueError('Start center outside model joint ranges')
    env.home_native = center
    obs, _ = env.reset(seed=seed)
    cube = env.data.body('task_cube').xpos.copy()
    # These are diagnostic ground truth only. Neither coordinates nor segmentation enter policy inputs.
    return obs, cube


def camera_pixels(env, renderer):
    renderer.enable_segmentation_rendering()
    renderer.update_scene(env.data, camera=env.camera_name)
    ids = renderer.render()
    return int(((ids[:,:,0] == env.model.geom('cube').id) & (ids[:,:,1] == int(mujoco.mjtObj.mjOBJ_GEOM))).sum())


def trial(env, seed, mode, plan, client=None, renderer=None, trace_path=None):
    obs, cube = setup(env, plan, mode, seed)
    initial_state = obs['state'].tolist()
    pixels = camera_pixels(env, renderer) if renderer is not None else None
    if client is None:
        expert = EXPERTS[PROFILE](env)
    else:
        client.request('reset')
    trace = []
    first_cmd = first_measured = None
    first_rise = first_held = None
    minimum = float('inf')
    max_rise = 0.
    min_at = None
    control = {'task':'pick up the cube', 'camera':env.camera}
    while True:
        action = expert.action() if client is None else client.action(obs, control)
        obs, _, done, truncated, info = env.step(action)
        pos = env.data.body('task_cube').xpos
        tip = env.data.site('gripperframe').xpos
        dist = float(np.linalg.norm(pos - tip))
        rise = float(pos[2] - cube[2])
        stamp = round(float(env.elapsed), 3)
        if dist < minimum:
            minimum, min_at = dist, stamp
        max_rise = max(max_rise, rise)
        if first_cmd is None and action[5] > 100:
            first_cmd = {'time_s':stamp,'distance_m':dist}
        if first_measured is None and obs['state'][5] > 100:
            first_measured = {'time_s':stamp,'distance_m':dist}
        if first_rise is None and rise >= .03:
            first_rise = stamp
        if first_held is None and info['held']:
            first_held = stamp
        if trace_path:
            trace.append([stamp, list(map(float, action)), obs['state'].tolist(), tip.tolist(), pos.tolist(),
                          bool(info['held']), bool(info['in_carry_pose'])])
        if done or truncated:
            break
    if trace_path:
        write_atomic(trace_path, '\n'.join(json.dumps(row) for row in trace) + '\n')
    return dict(seed=seed, start=mode, initial_state=initial_state, cube_xyz0=cube.tolist(),
                visible_cube_pixels_at_reset=pixels, outcome=info['outcome'], reason=info['termination_reason'],
                steps=env.steps, min_distance_m=minimum, min_distance_at_s=min_at, max_lift_m=max_rise,
                first_command_above_100=first_cmd, first_measured_above_100=first_measured,
                measured_above_100_at_start=initial_state[5] > 100, first_lift_3cm_s=first_rise,
                first_held_s=first_held)


def run(plan, work, seeds, client=None, tag='control'):
    work.mkdir(parents=True, exist_ok=True)
    env = make(PROFILE, images=client is not None)
    renderer = None
    results = []
    try:
        if client is None:
            renderer = mujoco.Renderer(env.model, height=480, width=640)
        for seed in seeds:
            sides = []
            for mode in MODES:
                trace = work/f'{mode}-{seed}.jsonl' if client is not None else None
                record = trial(env, seed, mode, plan, client, renderer, trace)
                sides.append(record)
            if not np.allclose(sides[0]['cube_xyz0'], sides[1]['cube_xyz0'], atol=1e-9, rtol=0):
                raise ValueError('Cube moved between paired initial placements')
            results.extend(sides)
            write_atomic(work/'progress.json', json.dumps({'paired_seeds':len(results)//2,'total':len(seeds),'trials':results}))
    finally:
        if renderer is not None:
            renderer.close()
        env.close()
    result = {'status':'completed','tag':tag,'domain':'sim','profile':PROFILE,'model_hash':plan['model'],
              'protocol_sha256':hashlib.sha256((STUDY/'protocol.json').read_bytes()).hexdigest(),
              'scene_seeds':seeds,'trials':results,'physical_skill_verified':False,
              'summary':{m:{'success':sum(r['outcome']=='success' for r in results if r['start']==m),
                            'scenes':len(seeds),
                            'visible_initial_scenes':sum(r['visible_cube_pixels_at_reset'] > 0 for r in results if r['start']==m) if client is None else None,
                            'held_scenes':sum(r['first_held_s'] is not None for r in results if r['start']==m),
                            'median_min_distance_cm':round(100*np.median([r['min_distance_m'] for r in results if r['start']==m]),2),
                            'median_max_lift_cm':round(100*np.median([r['max_lift_m'] for r in results if r['start']==m]),2)}
                         for m in MODES}}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job',type=Path)
    args = parser.parse_args()
    plan = read_manifest()
    if args.job:
        from explorer4.act_client import ACTClient
        cfg = json.loads(args.job.read_text())
        arm = cfg['diagnostic_arm']
        src = plan['models'][arm]
        if (arm not in ('T0','T1') or cfg['source_job'] != src['job'] or cfg['checkpoint'] != src['checkpoint'] or
                cfg['scene_seeds'] != plan['trace_seeds'] or cfg['expected_model_hash'] != plan['model'] or
                cfg['profile'] != PROFILE or cfg['diagnostic_protocol_sha256'] != hashlib.sha256((STUDY/'protocol.json').read_bytes()).hexdigest()):
            raise ValueError('Unexpected diagnostic configuration')
        bundle = Path(cfg['checkpoint'])
        with (bundle/'model.safetensors').open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest() != src['weights_sha256']:
                raise ValueError('Learned weights changed')
        work = DATA/'jobs'/args.job.stem
        client = ACTClient(bundle, work/'trace-inference.log', device='cuda')
        try:
            result = run(plan, work, cfg['scene_seeds'], client, arm)
        finally:
            client.close()
        result['weights_sha256'] = src['weights_sha256']
    else:
        work = STUDY/'control'
        result = run(plan, work, plan['control_seeds'])
    write_atomic(work/'result.json', json.dumps(result,indent=2))
    print(json.dumps(result['summary']), flush=True)


if __name__=='__main__':
    main()
