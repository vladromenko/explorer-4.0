"""Fresh-process LeRobot policy evaluation on actual MuJoCo dynamics and unseen seeds."""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path
import numpy as np
from .factory import make
from explorer4.profiles import profile as profile_config


from explorer4.act_client import ACTClient
from explorer4.sim_protocol import protocol, model_identity


def evaluate(checkpoint,output,seeds,profile='so101_pick_place_sim',expected_model=None,device='cuda',record_floor=False,
             seed_policy_per_scene=False, expected_protocol=None):
    seeds=list(seeds)
    if record_floor and profile not in {'rosmaster_floor_pick_recorded_start_sim','rosmaster_floor_pick_sim'}:
        raise ValueError('Floor diagnostics require a floor-pick scene')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    env=make(profile,images=True)
    if expected_model is not None and env.manifest['xml_sha256']!=expected_model:
        env.close()
        raise ValueError('Физика сцены изменилась после записи обучающего набора. Нужны новые показы; перенос между моделями требует отдельного эксперимента')
    cfg=profile_config(profile)
    manifest=protocol(profile,seeds,model_identity(env.manifest),checkpoint)
    if expected_protocol is not None and manifest != expected_protocol:
        env.close()
        raise ValueError('Queued geometry, scene, ordered seeds or model bundle changed')
    weights_sha256=manifest['checkpoint_sha256']
    client=None
    trials=[];latencies=[]
    try:
        client=ACTClient(checkpoint,output.with_suffix('.inference.log'),device=device)
        if client.ready.get('checkpoint_bundle_sha256') != manifest['checkpoint_bundle_sha256']:
            raise ValueError('Inference worker loaded a different checkpoint bundle')
        requested=os.environ.get('EXPLORER_N_ACTION_STEPS')
        if requested is not None and client.ready.get('n_action_steps')!=int(requested):
            raise RuntimeError('Policy worker did not apply the requested execution horizon')
        for seed in seeds:
            obs,_=env.reset(seed=seed)
            initial_digest=hashlib.sha256(np.asarray(env.data.qpos, dtype='<f8').tobytes()).hexdigest()
            client.request('reset', **({'seed':seed} if seed_policy_per_scene else {}))
            # per-episode task text (knowledge-gap profiles carry the object's measured size)
            episode_cfg={**cfg,'task':getattr(env,'task_text',None) or cfg['task']}
            if record_floor:
                initial_state=obs['state'].tolist()
                cube_start=env.data.body('task_cube').xpos.copy()
                min_distance=float('inf');max_lift=0.;ever_held=False
                frames=[env.data.qpos.tolist()]
            done=False
            while not done:
                started=time.monotonic();action=client.action(obs,episode_cfg);latencies.append(time.monotonic()-started)
                obs,reward,terminated,truncated,info=env.step(action)
                if record_floor:
                    cube=env.data.body('task_cube').xpos
                    min_distance=min(min_distance,float(np.linalg.norm(env.data.site('gripperframe').xpos-cube)))
                    max_lift=max(max_lift,float(cube[2]-cube_start[2]))
                    ever_held |= bool(info['held'])
                    if frames is not None:frames.append(env.data.qpos.tolist())
                done=terminated or truncated
            trials.append({'seed':seed,'outcome':info['outcome'],'reason':info['termination_reason'],
                           'steps':env.steps,'sim_seconds':env.elapsed,'initial_qpos_sha256':initial_digest})
            if record_floor:
                trials[-1].update(initial_state=initial_state,cube_xyz0=cube_start.tolist(),
                                  min_tip_cube_cm=100*min_distance,max_lift_cm=100*max_lift,ever_held=ever_held)
                if frames is not None:
                    trace=output.with_name(f'floor-trial-{seed}.json')
                    temporary=trace.with_suffix('.tmp')
                    temporary.write_text(json.dumps(dict(profile=profile,seed=seed,fps=env.fps,
                        model=env.manifest['xml_sha256'],outcome=info['outcome'],qpos=frames,
                        checkpoint_sha256=weights_sha256)))
                    temporary.replace(trace)
                    if seed==seeds[0]:
                        alias=output.with_name('first-floor-trial.json')
                        alias_temp=alias.with_suffix('.tmp');alias_temp.write_text(trace.read_text());alias_temp.replace(alias)
            output.write_text(json.dumps({'status':'running','trials':trials},indent=2))
    finally:
        if client is not None:client.close()
        env.close()
    if protocol(profile,seeds,model_identity(env.manifest),checkpoint) != manifest:
        raise ValueError('Policy or scene changed during evaluation')
    result={'protocol':manifest,'profile':profile,'status':'completed','domain':'sim','policy':client.ready['policy_type'],'checkpoint':str(checkpoint),
            'checkpoint_sha256':weights_sha256,'n_action_steps':client.ready.get('n_action_steps'),
            'policy_seed_per_scene':seed_policy_per_scene,
            'model':env.manifest,'new_process_reload':True,'privileged_input':False,'trials':trials,
            'success_fraction':sum(t['outcome']=='success' for t in trials)/len(trials),
            'sensor_to_action_seconds_p50_p95_max':np.percentile(latencies,[50,95,100]).tolist(),
            'physical_skill_verified':False}
    output.write_text(json.dumps(result,indent=2));print(json.dumps(result))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('checkpoint',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--start',type=int,default=10000);parser.add_argument('--count',type=int,default=3)
    parser.add_argument('--seeds', type=int, nargs='+', help='Explicit scene seeds, in evaluation order')
    parser.add_argument('--profile',default='so101_pick_place_sim')
    parser.add_argument('--expected-model-sha256')
    parser.add_argument('--queue-config',type=Path)
    parser.add_argument('--record-floor',action='store_true')
    parser.add_argument('--act-action-steps',type=int)
    parser.add_argument('--seed-policy-per-scene',action='store_true')
    args = parser.parse_args()
    seeds = args.seeds if args.seeds is not None else range(args.start, args.start + args.count)
    if not 1 <= len(seeds) <= 10000 or len(set(seeds)) != len(seeds) or any(s < 0 for s in seeds):
        parser.error('Expected a non-empty list of distinct, non-negative scene seeds (at most 10000)')
    if args.act_action_steps is not None:
        config=json.loads((args.checkpoint/'config.json').read_text())
        if config['type']!='act' or not 1<=args.act_action_steps<=config['chunk_size']:
            parser.error('Execution override must be within the ACT prediction horizon')
        if config.get('temporal_ensemble_coeff') is not None:
            parser.error('Execution horizon comparison requires ACT without temporal ensembling')
        os.environ['EXPLORER_N_ACTION_STEPS']=str(args.act_action_steps)
    evaluate(args.checkpoint, args.output, seeds, args.profile, args.expected_model_sha256,
             record_floor=args.record_floor, seed_policy_per_scene=args.seed_policy_per_scene,
             expected_protocol=json.loads(args.queue_config.read_text())['protocol'] if args.queue_config else None)
