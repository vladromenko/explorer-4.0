"""Score an official LeRobot checkpoint on a new bank of cube scenarios."""

import argparse
import json
import math
from pathlib import Path

import numpy as np

from explorer4.act_client import ACTClient
from explorer4.profiles import profile
from explorer4.resources import ResourceLease
from explorer4.sim.factory import make
from explorer4.sim.floor_carry import FloorCarry
from explorer4.sim.skill_transfer import TransferVerifier
from explorer4.sim_protocol import bundle_identity, scene_revision, sha256_file

from .evaluate import save_json, sha_array
from .mobile_floor import drive
from .scenarios import DISTANCE, MAX_TICKS, OUT, PROFILE, scenarios, setup


def evaluation_cases():
    # Each distance band covers all three yaw bins and all three lateral bins.
    return [case for index, case in enumerate(scenarios(988800)) if index % 9 in (0, 4, 8)]


def run_case(client, scene, config):
    xy = scene['xy']
    yaw = scene['yaw_deg']
    base = None
    if scene['distance'] == 'outside':
        base = drive(scene)
        if base['reason'] != 'ready_for_arm':
            return {**scene, 'retained': False, 'reason': base['reason'], 'base': base}
        xy = base['cube_relative_xy_for_scene_transfer']
        yaw -= math.degrees(base['stopped_pose'][2])
    with make(PROFILE, images=False) as env:
        setup(env, scene, xy, yaw)
        initial = sha_array(np.asarray(env.data.qpos, dtype='<f8'))
        carry, safety = FloorCarry(env), TransferVerifier(env)
        env.physics_observer = safety
        reset = client.request('reset', seed=scene['seed'], confirm_seed=True)
        if reset.get('applied_seed') != scene['seed']:
            raise ValueError('Inference worker did not confirm the registered seed')
        for _ in range(MAX_TICKS):
            observation = {**env.observation(), 'rgb': env.render()}
            _, _, done, timeout, info = env.step(client.action(observation, config))
            carry.measure()
            if safety.forbidden_pairs or timeout or (done and info['outcome'] == 'failure'):
                break
        retained = env.steps == MAX_TICKS and carry.success and not safety.forbidden_pairs
        if safety.forbidden_pairs:
            reason = 'motion_guard'
        elif retained:
            reason = 'retained'
        elif any(sample[3] for sample in carry.samples):
            reason = 'bilateral_contact_without_terminal_retention'
        else:
            reason = 'no_bilateral_contact'
        return {**scene, 'retained': retained, 'reason': reason, 'base': base,
                'initial_qpos_sha256': initial, 'steps': env.steps,
                'forbidden_contacts': safety.report()['forbidden_contact_pairs'],
                'terminal_samples': carry.samples[-(env.fps + 1):]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkpoint', type=Path)
    parser.add_argument('name')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cuda')
    args = parser.parse_args()
    if not args.name.replace('-', '').isalnum():
        raise ValueError('Invalid report name')
    root = OUT / 'policy-evaluation' / args.name
    cases = evaluation_cases()
    bundle = bundle_identity(args.checkpoint)
    code = [Path(__file__).with_name(f'{name}.py') for name in ('scenario_policy', 'scenarios', 'mobile_floor')]
    protocol = {'cases': cases, 'checkpoint': bundle, 'arm_scene': scene_revision(PROFILE),
                'base_scene': scene_revision('rosmaster_dock_sim'),
                'code_sha256': {p.name: sha256_file(p) for p in code},
                'scope': 'Simulated closed-loop arm scoring. Distant targets first use the shared depth/ideal odometry base stage.'}
    with ResourceLease('compute'), ResourceLease('simulation_world'):
        registered = root / 'protocol.json'
        if registered.exists() and json.loads(registered.read_text()) != protocol:
            raise ValueError('Registered model, code or scenarios changed')
        save_json(registered, protocol)
        client = ACTClient(args.checkpoint, root / 'inference.log', device=args.device)
        try:
            if client.ready.get('checkpoint_bundle_sha256') != bundle['checkpoint_bundle_sha256']:
                raise ValueError('Worker loaded different checkpoint weights or processors')
            rows = []
            for case in cases:
                path = root / f"{case['seed']}.json"
                row = json.loads(path.read_text()) if path.exists() else run_case(client, case, profile(PROFILE))
                if not path.exists():
                    save_json(path, row)
                rows.append(row)
                print(case['seed'], case['distance'], row['reason'], flush=True)
        finally:
            client.close()
        summary = {band: [sum(r['retained'] for r in rows if r['distance'] == band),
                          sum(r['distance'] == band for r in rows)] for band in DISTANCE}
        save_json(root / 'result.json', {'cases': rows, 'retained_over_attempted': summary,
                                        'model': client.ready['policy_type'], 'physical_trials': 0})


if __name__ == '__main__':
    main()
