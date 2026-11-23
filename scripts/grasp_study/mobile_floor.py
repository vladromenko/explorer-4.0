"""Sequential depth-guided base and arm evaluation for initially distant cubes."""

import json
import math
from pathlib import Path

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from explorer4.floor_cube_localization import top_surface
from explorer4.resources import ResourceLease
from explorer4.sim.factory import make
from explorer4.sim.mobile import DockExpert
from explorer4.sim.vendor_rosmaster.arm_model import ArmModel
from explorer4.sim_protocol import scene_revision, sha256_file

from .depth_floor_recovery import SIZE, capture
from .evaluate import save_json
from .scenarios import LOOK, OUT, evaluate_scenario, oriented_top, scenarios


SCAN_LOOKS = ((90., 130., 1., 5., 90., 31.), (90., 130., 1., 25., 90., 31.))
SCAN_BOUNDS = ((.155, .65), (-.18, .18))
STOP_DISTANCE = .195


def transform(data, body):
    result = np.eye(4)
    result[:3, :3] = data.xmat[body].reshape(3, 3)
    result[:3, 3] = data.xpos[body]
    return result


def set_scene(base, scenario):
    """Use a cube collider on the existing force-driven mobile model."""
    m, d = base.model, base.data
    target = m.body('target').id
    cube = m.geom('target_board').id
    m.body_pos[target] = [*scenario['xy'], SIZE / 2 + .002]
    turn = math.radians(scenario['yaw_deg']) / 2
    m.body_quat[target] = [math.cos(turn), 0., 0., math.sin(turn)]
    m.geom_size[cube, :3] = SIZE / 2
    centre = m.geom('target_center').id
    m.geom_size[centre] = [.0001, .0001, .0001]
    m.geom_rgba[centre, 3] = m.geom_rgba[m.geom('dock_zone').id, 3] = 0.
    mujoco.mj_setConst(m, mujoco.MjData(m))
    mujoco.mj_forward(m, d)
    return cube


def point_camera(base, look):
    m, d = base.model, base.data
    camera = m.camera(base.camera_name).id
    world_from_base = transform(d, m.body('base').id)
    parent_from_base = np.linalg.inv(transform(d, m.cam_bodyid[camera])) @ world_from_base
    base_from_camera = ArmModel().camera_pose(look)
    optical_from_mujoco = np.diag([1., -1., -1., 1.])
    mount = parent_from_base @ base_from_camera @ optical_from_mujoco
    m.cam_pos[camera] = mount[:3, 3]
    m.cam_quat[camera] = Rotation.from_matrix(mount[:3, :3]).as_quat()[[3, 0, 1, 2]]
    mujoco.mj_forward(m, d)


def acquire(base, renderer):
    depth, intrinsics, world_from_optical = capture(base, renderer)
    world_from_base = transform(base.data, base.model.body('base').id)
    base_from_optical = np.linalg.inv(world_from_base) @ world_from_optical
    points = top_surface(depth, intrinsics, base_from_optical, SIZE, SCAN_BOUNDS)
    local = oriented_top(points)
    if local is None:
        return None
    return (world_from_base @ [*local, 0., 1.])[:2]


def drive(scenario):
    with make('rosmaster_dock_sim', images=False) as base:
        base.reset(seed=scenario['seed'], options={'variation': 'varied'})
        cube = set_scene(base, scenario)
        camera = mujoco.Renderer(base.model, height=240, width=320)
        camera.enable_depth_rendering()
        try:
            target = None
            for look in SCAN_LOOKS:
                point_camera(base, look)
                target = acquire(base, camera)
                if target is not None:
                    break
            if target is None:
                return {'reason': 'far_cube_unobserved'}
            base.goal = np.r_[target - [STOP_DISTANCE, 0.], 0.]
            controller = DockExpert(base)
            for _ in range(220):
                request = controller.action()
                request[:2] = np.clip(request[:2], -.10, .10)
                _, _, done, timeout, _ = base.step(request)
                if any(cube in (c.geom1, c.geom2) for c in base.data.contact):
                    return {'reason': 'base_contact', 'ticks': base.steps}
                if done or timeout:
                    break
            point_camera(base, LOOK)
            measured = acquire(base, camera)
        finally:
            camera.close()
        world_from_base = transform(base.data, base.model.body('base').id)
        relative = np.linalg.inv(world_from_base) @ [*scenario['xy'], 0., 1.]
        speed = float(np.linalg.norm(base.body_velocity()))
        if measured is None:
            reason = 'no_fresh_view_after_stop'
        elif speed >= .035:
            reason = 'base_did_not_settle'
        elif not (.17 <= relative[0] <= .25 and abs(relative[1]) <= .05):
            reason = 'base_did_not_stop_in_reach'
        else:
            reason = 'ready_for_arm'
        return {'reason': reason, 'ticks': base.steps, 'base_speed': speed, 'acquisition_look': list(look),
                'first_estimate_world_xy': target.tolist(),
                'end_estimate_world_xy': None if measured is None else measured.tolist(),
                'stopped_pose': base.data.qpos.tolist(), 'cube_relative_xy_for_scene_transfer': relative[:2].tolist()}


def scenario_result(scene):
    report = drive(scene)
    arm = None
    if report['reason'] == 'ready_for_arm':
        adjusted = {**scene, 'distance': 'after_approach',
                    'xy': report['cube_relative_xy_for_scene_transfer'],
                    'yaw_deg': scene['yaw_deg'] - math.degrees(report['stopped_pose'][2])}
        arm = evaluate_scenario(adjusted, 'depth')
    return {'scenario': scene, 'base': report, 'arm': arm, 'retained': bool(arm and arm['retained'])}


def main():
    cases = [row for row in scenarios(988200) if row['distance'] == 'outside']
    root = OUT / 'mobile-development-v2'
    protocol = {'scenarios': cases, 'scan_looks': [list(p) for p in SCAN_LOOKS],
                'stopped_reacquisition_look': list(LOOK), 'stop_distance_m': STOP_DISTANCE,
                'comparison': 'Same distant scenes as the original stationary-arm and privileged sequential teacher.',
                'scope': 'Simulated registered depth, ideal base odometry, two sequential physics models. No shared whole-body dynamics.',
                'mobile_scene_revision': scene_revision('rosmaster_dock_sim'),
                'code_sha256': sha256_file(Path(__file__)),
                'arm_evaluator_sha256': sha256_file(Path(__file__).with_name('scenarios.py'))}
    with ResourceLease('simulation_world'):
        registered = root / 'protocol.json'
        if registered.exists() and json.loads(registered.read_text()) != protocol:
            raise ValueError('Existing protocol differs')
        save_json(registered, protocol)
        results = []
        for case in cases:
            path = root / f"{case['seed']}.json"
            row = json.loads(path.read_text()) if path.exists() else scenario_result(case)
            if not path.exists():
                save_json(path, row)
            results.append(row)
            print(case['seed'], row['base']['reason'], None if row['arm'] is None else row['arm']['reason'], flush=True)
        save_json(root / 'result.json', {'cases': results, 'retained': sum(r['retained'] for r in results),
                                        'attempts': len(cases)})


if __name__ == '__main__':
    main()
