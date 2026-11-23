"""Stratified cube poses and a composeable move-then-grasp teacher in MuJoCo."""

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import math
from multiprocessing import get_context
from pathlib import Path

import cv2
import mujoco
import numpy as np

from explorer4.conditioned_grasp import SLEW_DEGREES_PER_SECOND
from explorer4.floor_cube_localization import top_surface
from explorer4.paths import DATA, ROOT
from explorer4.resources import ResourceLease
from explorer4.sim.capture import SimCapture
from explorer4.sim.factory import make
from explorer4.sim.floor_carry import FloorCarry
from explorer4.sim.mobile import DockExpert
from explorer4.sim.skill_transfer import TransferVerifier
from explorer4.sim_protocol import scene_revision, sha256_file

from .depth_floor_recovery import PROFILE, SIZE, capture
from .evaluate import ik_targets, save_json, sha_array


DISTANCE = {'near': (.176, .192), 'middle': (.199, .219), 'edge': (.226, .246), 'outside': (.29, .46)}
Y = (-.043, 0., .043)
YAW = (-34., 0., 34.)
LOOK = (90.8, 93.46, 2.05, 4.86, 90., 31.)
LOOK_TICKS = 55
MAX_TICKS = 360
OUT = DATA / 'simlab/reports/varied-floor-cube-v1'


def scenarios(first_seed):
    rows = []
    for band, limits in DISTANCE.items():
        for i, y in enumerate(Y):
            for j, yaw in enumerate(YAW):
                seed = first_seed + len(rows)
                rng = np.random.default_rng(seed)
                rows.append({'seed': seed, 'distance': band, 'xy': [float(rng.uniform(*limits)), y],
                             'yaw_deg': yaw, 'start': 'raised' if (i + j) % 2 else 'recording'})
    return rows


def relocate_base(world_xy, seed):
    """Use the existing force-driven mobile model and privileged DockExpert labels."""
    with make('rosmaster_dock_sim', images=False) as base:
        base.reset(seed=seed, options={'variation': 'varied'})
        target = base.model.body('target').id
        cube = base.model.geom('target_board').id
        base.model.body_pos[target] = [*world_xy, SIZE / 2 + .002]
        base.model.geom_size[cube, :3] = SIZE / 2
        base.model.geom_size[base.model.geom('target_center').id] = [.0001, .0001, .0001]
        mujoco.mj_setConst(base.model, mujoco.MjData(base.model))
        mujoco.mj_forward(base.model, base.data)
        start = base.data.qpos.copy()
        base.goal = np.r_[np.asarray(world_xy) - [.197, 0.], 0.]
        controller = DockExpert(base)
        stuck = False
        for _ in range(220):
            request = controller.action()
            request[:2] = np.clip(request[:2], -.10, .10)
            _, _, done, timeout, info = base.step(request)
            if any(cube in (c.geom1, c.geom2) for c in base.data.contact):
                stuck = True
                break
            if done or timeout:
                break
        x, y, angle = base.data.qpos
        rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
        relative = (np.asarray(world_xy) - [x, y]) @ rotation
        speed = float(np.linalg.norm(base.body_velocity()))
        report = {'initial_pose': start.tolist(), 'stopped_pose': base.data.qpos.tolist(),
                  'ticks': base.steps, 'base_speed': speed, 'contact': stuck,
                  'stopped_in_reach': bool(not stuck and speed < .035 and .17 <= relative[0] <= .25
                                            and abs(relative[1]) <= .05)}
        return relative, math.degrees(angle), report


def setup(env, scenario, xy, yaw):
    env.reset(seed=scenario['seed'])
    if scenario['start'] == 'raised':
        env.data.qpos[:6] = env.to_radians([90, 90, 90, 90, 90, 31])
        env.data.qpos[6:11] = env.data.qpos[5] * np.array([1, 1, -1, -1, 1])
        env.data.ctrl[:] = env.data.qpos[:6]
        env.filtered = env.pending = env.data.ctrl.copy()
    i = int(env.model.joint('cube_free').qposadr[0])
    env.data.qpos[i:i + 2] = xy
    turn = math.radians(yaw) / 2
    env.data.qpos[i + 3:i + 7] = [math.cos(turn), 0., 0., math.sin(turn)]
    env.episode_parameters['scenario'] = scenario
    env.episode_parameters['cube_in_arm_frame_at_reset'] = [*map(float, xy), yaw]
    mujoco.mj_forward(env.model, env.data)


def oriented_top(points):
    if len(points) < 100:
        return None
    center, sides, _ = cv2.minAreaRect(np.asarray(points, dtype=np.float32))
    if not all(.82 * SIZE <= length <= 1.16 * SIZE for length in sides):
        return None
    return np.asarray(center)


def evaluate_scenario(scenario, method, record=False):
    xy = scenario['xy']
    yaw = scenario['yaw_deg']
    base = None
    if scenario['distance'] == 'outside':
        if method != 'teacher':
            return {**scenario, 'method': method, 'reason': 'requires_mobile_perception', 'retained': False}
        xy, angle, base = relocate_base(xy, scenario['seed'])
        yaw -= angle
        if not base['stopped_in_reach']:
            return {**scenario, 'method': method, 'reason': 'base_did_not_stop_in_reach', 'base': base, 'retained': False}
    with make(PROFILE, images=False) as env:
        setup(env, scenario, xy, yaw)
        initial = sha_array(np.asarray(env.data.qpos, dtype='<f8'))
        recorder = SimCapture(env, scenario['seed'], 'scripted_expert') if record else None
        carry, safety = FloorCarry(env), TransferVerifier(env)
        env.physics_observer = safety
        command = env.observation()['state'].astype(float)
        slew = SLEW_DEGREES_PER_SECOND * env.dt

        def step(target):
            command[:] += np.clip(np.asarray(target) - command, -slew, slew)
            if recorder:
                recorder.add(env, command)
            _, _, done, timeout, info = env.step(command)
            carry.measure()
            return not timeout and not (done and info['outcome'] == 'failure') and not safety.forbidden_pairs

        measured = None
        reason = 'look_motion_guard'
        if all(step(LOOK) for _ in range(LOOK_TICKS)):
            if method == 'teacher':
                measured = env.data.body('task_cube').xpos[:2].copy()
            else:
                renderer = mujoco.Renderer(env.model, height=240, width=320)
                try:
                    renderer.enable_depth_rendering()
                    depth, camera, transform = capture(env, renderer)
                    bounds = tuple(env.cfg[k] for k in ('object_x_m', 'object_y_m'))
                    measured = oriented_top(top_surface(depth, camera, transform, SIZE, bounds))
                finally:
                    renderer.close()
            reason = 'unobserved_cube' if measured is None else 'unreachable_target'
            if measured is not None:
                for target in ik_targets(env, measured):
                    if not step(target):
                        reason = 'motion_guard'
                        break
                    if env.steps == MAX_TICKS:
                        reason = 'retained' if carry.success else 'terminal_hold_not_verified'
                        break
        retained = reason == 'retained'
        trace = {'initial_qpos_sha256': initial, 'steps': env.steps, 'retained': retained, 'reason': reason,
                 'method': method, 'measured_xy': None if measured is None else measured.tolist(),
                 'forbidden_contacts': safety.report()['forbidden_contact_pairs'], 'base': base}
        if recorder:
            trace['spool'] = str(recorder.finish('success' if retained else 'failure', reason))
        return {**scenario, **trace}


def work(job):
    path, scenario, method, record = job
    result = evaluate_scenario(scenario, method, record)
    save_json(path, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['development', 'training'], default='development')
    parser.add_argument('--record', action='store_true')
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    if args.record and args.split != 'training':
        raise ValueError('Only the separate training split can export demonstrations')
    output = OUT / args.split
    cases = scenarios(988200 if args.split == 'development' else 988400)
    methods = ('teacher',) if args.split == 'training' else ('teacher', 'depth')
    protocol = {'scenarios': cases, 'methods': methods, 'exports_demonstrations': args.record,
                'source_sha256': sha256_file(Path(__file__)), 'scene_revision': scene_revision(PROFILE),
                'look': LOOK, 'endpoint': 'Bilateral contact, >50 mm lift and carry pose for final second',
                'scope': 'Simulated stationary arm, plus sequential base/arm teacher using privileged coordinates.'}
    protocol = json.loads(json.dumps(protocol))
    registered = output / 'protocol.json'
    with ResourceLease('simulation_world'):
        if registered.exists() and json.loads(registered.read_text()) != protocol:
            raise ValueError('The scenario protocol has already been registered with different settings')
        save_json(registered, protocol)
        paths = {output / method / f"{case['seed']}.json": (case, method) for case in cases for method in methods}
        pending = [(path, *values, args.record) for path, values in paths.items() if not path.exists()]
        if pending:
            with ProcessPoolExecutor(max_workers=args.workers, mp_context=get_context('spawn')) as workers:
                for row in workers.map(work, pending):
                    print(row['method'], row['seed'], row['distance'], row['reason'], flush=True)
        results = [json.loads(path.read_text()) for path in paths]
        scores = {method: {band: [sum(r['retained'] for r in results if r['method'] == method and r['distance'] == band),
                                  sum(r['method'] == method and r['distance'] == band for r in results)]
                           for band in DISTANCE} for method in methods}
        save_json(output / 'result.json', {'results': results, 'scores_retained_over_all': scores})
        print(scores, flush=True)


if __name__ == '__main__':
    main()
