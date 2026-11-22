"""Compare saved ACT traces with an oracle-geometry teacher on the same scenes."""
import json
import statistics
import sys
from pathlib import Path

import mujoco
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from explorer4.paths import DATA
from explorer4.recorded_start_followup import NIGHT, PUBLIC, read, write
from explorer4.sim.factory import EXPERTS, make

PROFILE = 'rosmaster_floor_pick_recorded_start_sim'


def grasp_geometry(env, positions):
    data = mujoco.MjData(env.model)
    tip = data.site('gripperframe').xpos
    cube = data.body('task_cube').xpos
    distances, horizontal_errors, heights, open_flags = [], [], [], []
    for qpos in positions:
        data.qpos[:] = qpos
        mujoco.mj_kinematics(env.model, data)
        offset = tip - cube
        distances.append(float(np.linalg.norm(offset)))
        horizontal_errors.append(float(np.linalg.norm(offset[:2])))
        heights.append(float(cube[2]))
        open_flags.append(bool(qpos[5] > .5*env.manifest['gripper_closed_rad']))
    close = next((i for i in range(1,len(open_flags)) if open_flags[i-1] and not open_flags[i]), None)
    return dict(first_observed_closure=close,
                first_closure_tip_to_cube_cm=100*distances[close] if close is not None else None,
                first_closure_horizontal_error_cm=100*horizontal_errors[close] if close is not None else None,
                closest_tip_to_cube_cm=100*min(distances),
                peak_lift_cm=100*(max(heights)-heights[0]))


def teacher_trial(env, seed):
    env.reset(seed=seed)
    expert = EXPERTS[PROFILE](env)
    positions = [env.data.qpos.copy()]
    while True:
        _, _, terminated, truncated, info = env.step(expert.action())
        positions.append(env.data.qpos.copy())
        if terminated or truncated:
            break
    return dict(outcome=info['outcome'], reason=info['termination_reason'], steps=env.steps,
                **grasp_geometry(env, positions))


def metrics(trials):
    errors = [t['first_closure_horizontal_error_cm'] for t in trials
              if t['first_closure_horizontal_error_cm'] is not None]
    return dict(trials=len(trials), successes=sum(t['outcome']=='success' for t in trials),
                observed_closures=len(errors),
                median_horizontal_error_cm=statistics.median(errors) if errors else None,
                low_lift_under_1cm=sum(t['peak_lift_cm']<1 for t in trials))


def main():
    state = read(NIGHT/'improvement-state.json')
    normal = state['jobs']['confirmation-100']['id']
    selected = state['jobs']['confirmation-25']['id']
    sources = {key: DATA/'jobs'/ident for key,ident in [('act_100',normal),('act_25',selected)]}
    records = {key:read(path/'result.json') for key,path in sources.items()}
    plan = read(NIGHT/'improvement-plan.json')
    seeds = plan['confirmation_seeds']
    for key, result in records.items():
        if (result['status']!='completed' or result['checkpoint_sha256']!=plan['source_weights_sha256']
            or result['n_action_steps']!=int(key.split('_')[1]) or [t['seed'] for t in result['trials']]!=seeds):
            raise ValueError(f'Unexpected completed result: {key}')
    env = make(PROFILE, images=False)
    paired = []
    try:
        if env.manifest['xml_sha256'] != plan['model_sha256']:
            raise ValueError('Different simulator physics')
        for i,seed in enumerate(seeds):
            row = dict(seed=seed, teacher_oracle=teacher_trial(env,seed))
            for key,root in sources.items():
                original = records[key]['trials'][i]
                trace = read(root/f'floor-trial-{seed}.json')
                if (trace['seed']!=seed or trace['model']!=plan['model_sha256']
                    or trace['checkpoint_sha256']!=plan['source_weights_sha256']
                    or len(trace['qpos'])!=original['steps']+1 or trace['outcome']!=original['outcome']):
                    raise ValueError(f'Unexpected trace: {key}, {seed}')
                row[key] = dict(outcome=original['outcome'], reason=original['reason'],
                                **grasp_geometry(env, trace['qpos']))
            paired.append(row)
            print(seed, {key:value['outcome'] for key,value in row.items() if key!='seed'}, flush=True)
    finally:
        env.close()
    groups = {key:metrics([row[key] for row in paired]) for key in ('teacher_oracle',*sources)}
    groups['act_25_failures'] = metrics([row['act_25'] for row in paired if row['act_25']['outcome']=='failure'])
    groups['act_25_successes'] = metrics([row['act_25'] for row in paired if row['act_25']['outcome']=='success'])
    value = dict(model_sha256=plan['model_sha256'], source_checkpoint_sha256=plan['source_weights_sha256'],
                 teacher_inputs='Privileged ground truth cube position at reset; no RGB localization',
                 closure_metric='First observed closure after opening, using the simulator gripper threshold; '
                                'distances from gripperframe to cube centre',
                 groups=groups, paired_trials=paired)
    write(NIGHT/'grasp-diagnosis.json', value)
    write(PUBLIC/'grasp-diagnosis.json', value)
    print(json.dumps(groups, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
