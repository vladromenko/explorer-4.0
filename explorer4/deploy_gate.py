"""Evidence for a limited physical trial. A passing replay is not a physical success."""
import json
import time
from pathlib import Path

import numpy as np

from . import catalog, datasets
from .paths import DATA, ROOT
from .profiles import profile
from .sim_protocol import bundle_identity, model_identity, probe_geometry, scene_revision

GATES = DATA / 'gates'


def thresholds():
    return json.loads((ROOT / 'configs/deploy-gate.json').read_text())


def real_profile_of(name):
    cfg = profile(name)
    return cfg.get('real_profile', name) if cfg.get('domain') == 'sim' else name


def evaluation_scene(job):
    name = job['profile']
    if profile(name).get('domain') == 'sim':
        return name
    return {**datasets.SIM_FOR_REAL, 'tank_dock': 'tank_dock_sim', 'rosmaster_dock': 'rosmaster_dock_sim'}.get(name)


def scope_for(job):
    scene = evaluation_scene(job)
    real = real_profile_of(job['profile'])
    cfg = profile(real)
    start = None
    alignment = json.loads((ROOT/'configs/sim-alignment.json').read_text())
    if scene in ('rosmaster_floor_pick_sim','rosmaster_floor_pick_recorded_start_sim'):
        c = alignment['rosmaster_floor_pick']
        start = {'center':profile(scene).get('start_center_deg',c['start_pose']), 'tolerance':c['start_noise_deg']+1.}
    elif scene == 'so101_handover_sim':
        c = alignment['so101_handover']
        start = {'center':c['rest_pose'],'tolerance':c['rest_noise_deg']+1.}
    return {'start_pose':start, 'real_profile': real, 'scene': scene, 'instruction': profile(scene)['task'] if scene else cfg['task'],
            'robot': cfg['robot'], 'action_kind': 'body_velocity' if 'yaw_velocity' in cfg['channels'] else 'absolute_joint_target',
            'channels': cfg['channels'], 'units': cfg['units']}


def development_selection(job, scope, development_plan_id=None):
    """Use only declared development IDs. Join train/test and ancestor lineage by ID, session and scene."""
    config = json.loads(job['config'])
    selected = development_plan_id or (config.get('plan_id') if profile(job['profile']).get('domain') != 'sim' else None)
    if not selected:
        raise ValueError('Select a frozen real development plan; unassigned recordings and test data stay reserved')
    plans, visited = {}, set()
    pending = [job]
    while pending:
        current = pending.pop()
        if current['id'] in visited:
            continue
        visited.add(current['id'])
        cfg = json.loads(current['config'])
        ident = cfg.get('plan_id')
        if not ident:
            raise ValueError('Training lineage has no frozen split')
        plans[ident] = datasets.load_plan(ident, verify=False)
        if cfg.get('initial_checkpoint') or cfg.get('resume_checkpoint'):
            source_id = cfg.get('source_job')
            source_path = Path(cfg.get('resume_checkpoint') or cfg['initial_checkpoint']).resolve()
            ancestor = next((j for j in catalog.rows('jobs') if j['id'] != current['id'] and j.get('checkpoint') and
                             (j['id'] == source_id if source_id else Path(j['checkpoint']).resolve() == source_path)), None)
            if not ancestor:
                raise ValueError('Unresolved parent checkpoint lineage')
            pending.append(ancestor)
    reserved_seeds = set(range(10000,10020))
    for source in plans.values():
        for e in source['splits']['train']:
            if e['profile'] == scope['scene']:
                meta = json.loads((Path(e['dataset'])/'provenance.json').read_text())
                seed = meta.get('hardware',{}).get('seed')
                if type(seed) is not int or seed in reserved_seeds:
                    raise ValueError('Cannot establish independence of the standard scene seeds from training')
    plan = plans.get(selected) or datasets.load_plan(selected, verify=False)
    if plan['domain'] != 'real' or plan['profile'] != scope['real_profile'] or plan.get('smoke'):
        raise ValueError('Development plan must contain real recordings for this robot and physical profile')
    plans[selected] = plan
    candidates = {e['id']:e for e in plan['splits']['validation']}
    blocked = set()
    records = dict(candidates)
    for source in plans.values():
        for role in ('train', 'test'):
            for e in source['splits'][role]:
                blocked.add(e['id'])
                start_source = None
                if profile(e['profile']).get('domain')=='sim':
                    archived=json.loads((Path(e['dataset'])/'provenance.json').read_text())
                    start_source=archived.get('hardware',{}).get('start_source_episode')
                if start_source:
                    blocked.add(start_source)
                    e = {**e, 'lineage_sources':[*e.get('lineage_sources',[]),start_source]}
                records[e['id']] = e
        for entry in source['splits']['validation']:
            records.setdefault(entry['id'], entry)
    groups = datasets.connected_groups(records.values())
    current = {e['id']: e for e in catalog.rows('episodes')}
    held, rejected = [], {}
    for group in groups:
        conflict = any(e['id'] in blocked for e in group)
        for e in group:
            ident = e['id']
            if ident not in candidates:
                continue
            if conflict:
                rejected[ident] = 'linked to training or reserved test'
                continue
            meta = json.loads((Path(e['dataset']) / 'provenance.json').read_text())
            task = meta.get('hardware', {}).get('collection', {}).get('instruction') or meta.get('profile', {}).get('task')
            entry = current.get(ident, {})
            if (meta.get('domain', 'real') != 'real' or meta.get('synthetic') is not False or
                meta.get('command_source') != 'human' or meta.get('hardware', {}).get('pipeline_check') or
                entry.get('excluded', True) or entry.get('outcome') != 'success' or
                entry.get('category') not in ('demonstration','correction') or task != scope['instruction']):
                rejected[ident] = 'task, physical source, or operator inclusion differs'
                continue
            if datasets.fingerprint(e['dataset']) != e['sha256']:
                raise ValueError('Development recording has changed: ' + ident)
            held.append(e)
    return held, {'development_plan_id':selected, 'partition':'validation', 'episodes':[e['id'] for e in held],
                  'excluded':rejected, 'training_plan_ids':sorted(plans), 'test_frames_read':0}


def check_contract(core, real, job_id, recorded_contract=None):
    cfg = profile(real)
    problems = []
    camera = 'observation.images.' + cfg['camera']
    h,w,c = cfg.get('image_shape', [480,640,3])
    channels = cfg['channels']
    state_names = cfg.get('state_channels',channels)
    environment = cfg.get('environment_channels') or []
    expected = {'observation.state':[len(state_names)], camera:[c,h,w]}
    if environment:
        expected['observation.environment_state'] = [len(environment)]
    actual = core.cfg.input_features
    for key,shape in expected.items():
        if key not in actual or list(actual[key].shape) != shape:
            problems.append(f'{key}: expected {shape}')
    for key in actual.keys() - expected.keys():
        if not (getattr(core, 'type', None) == 'smolvla' and key in {'observation.images.camera1','observation.images.camera2','observation.images.camera3'}):
            problems.append('unavailable input '+key)
    action = core.cfg.output_features.get('action')
    if action is None or list(action.shape) != [len(channels)]:
        problems.append('action width/order unavailable')
    info = DATA/'jobs'/job_id/'train/meta/info.json'
    if not info.exists():
        problems.append('training feature metadata missing')
    else:
        data = json.loads(info.read_text())
        features = data['features']
        named = {'action':channels, 'observation.state':state_names}
        if environment:
            named['observation.environment_state'] = environment
        for key,names in named.items():
            if features.get(key,{}).get('names') != names:
                problems.append(key+' channel order differs')
        if features.get(camera,{}).get('shape') != [h,w,c] or data.get('fps') != cfg['fps']:
            problems.append('camera size or recording rate differs')
    if recorded_contract is None:
        problems.append('missing frozen training units and sensor contract')
    else:
        from .transfer_preparation import contract
        a,b = contract(recorded_contract),contract(cfg)
        for k in a.keys()-{'task'}:
            if a[k] != b[k]:
                problems.append('frozen contract differs: '+k)
        if (recorded_contract.get('environment_channels') or []) != environment:
            problems.append('environment channel order differs')
    return {'status':'fail' if problems else 'pass', 'message':'; '.join(problems) or 'Camera, state, action, units, environment and FPS match'}


def replay_real(core, episodes, real, limits):
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    cfg = profile(real)
    camera = 'observation.images.'+cfg['camera']
    mobile = 'yaw_velocity' in cfg['channels']
    errors, jumps, latency = [], [], []
    for episode in episodes:
        root = Path(episode['dataset'])
        ds = LeRobotDataset('local/'+root.name, root=root, video_backend='pyav')
        for i in np.linspace(0,len(ds)-1,min(len(ds),limits['frames_per_episode'])).astype(int):
            frame = ds[int(i)]
            rgb = (frame[camera].permute(1,2,0).numpy()*255).round().astype('uint8')
            state = frame['observation.state'].numpy()
            target = frame['action'].numpy()
            env = frame.get('observation.environment_state')
            if state.shape != (len(cfg.get('state_channels',cfg['channels'])),) or target.shape != (len(cfg['channels']),):
                raise ValueError('Unexpected recorded state or action shape')
            core.reset()
            start = time.monotonic()
            action = np.asarray(core.act(state,{cfg['camera']:rgb},frame.get('task') or cfg['task'],env))
            latency.append(time.monotonic()-start)
            if action.shape != target.shape or not np.isfinite([action,target]).all() or not np.isfinite(state).all():
                raise ValueError('Invalid predicted or recorded action/state')
            errors.append(np.abs(action-target))
            # Both base profiles put the previous commanded velocities last. Arm states are joint readbacks.
            reference = state[-len(target):] if mobile else state
            jumps.append(np.abs(action-reference))
    return np.asarray(errors),np.asarray(jumps),np.asarray(latency)


def replay_checks(core, episodes, real, limits):
    cfg = profile(real)
    errors,jumps,latency = replay_real(core,episodes,real,limits)
    if not len(errors):
        raise ValueError('No synchronized development frames')
    if 'yaw_velocity' in cfg['channels']:
        maximum = np.array([limits['velocity_mae'][u] for u in cfg['units']])
        jump_limits = [limits['velocity_first_step_p95'][u] for u in cfg['units']]
    else:
        maximum = [limits['joint_mae_deg']]*(len(cfg['channels'])-1)+[limits['gripper_mae']]
        jump_limits = [limits['first_step_jump_deg_p95']]*(len(cfg['channels'])-1)+[limits['gripper_first_step_p95']]
    # Report by native axis. An average over axes could hide a failed gripper or lateral control.
    mean = errors.mean(axis=0)
    p95 = np.percentile(jumps,95,axis=0)
    steps = getattr(core.cfg,'n_action_steps',1) or 1
    # Physical trials call the same synchronous runtime on every control tick. A chunk cannot hide a slow replan.
    budget = limits['latency_budget_fraction']/cfg['fps']
    elapsed = float(np.percentile(latency,95))
    return {'real_holdout':{'status':'pass' if np.all(mean<=maximum) else 'fail','episodes':len(episodes),
                'frames':len(errors),'channels':cfg['channels'],'units':cfg['units'],'mae':mean.tolist(),
                'limits':list(maximum),'message':'Mean absolute imitation error per native action channel'},
            'first_step':{'status':'pass' if np.all(p95<=jump_limits) else 'fail','p95':p95.tolist(),
                'limits':jump_limits,'message':'95th percentile fresh command change per native channel'},
            'latency':{'status':'pass' if elapsed<=budget else 'fail','replan_s_p95':elapsed,'budget_s':budget,
                'n_action_steps':steps,'message':'Synchronous replan time vs. one physical control tick'}}


def is_standard_sim_evaluation(job, source_job):
    cfg = json.loads(job['config'])
    return cfg.get('kind') == 'sim_evaluate' and cfg.get('source_job') == source_job and not cfg.get('diagnostic')


def mujoco_result(job_id, *, identity=None):
    jobs = catalog.rows('jobs')
    source = next((j for j in jobs if j['id']==job_id), None)
    if not source or not source.get('checkpoint'):
        return None
    scene = evaluation_scene(source)
    revision = scene_revision(scene) if scene else None
    for job in sorted((j for j in jobs if j['status']=='completed' and is_standard_sim_evaluation(j,job_id)),
                      key=lambda j:j['created'], reverse=True):
        cfg = json.loads(job['config'])
        manifest = cfg.get('protocol')
        if not manifest or manifest.get('version') != 2 or manifest.get('scene') != scene or manifest.get('scene_revision') != revision:
            continue
        if identity is None:
            identity = bundle_identity(source['checkpoint'])
        if any(manifest.get(k)!=v for k,v in identity.items()):
            continue
        path = DATA/'jobs'/job['id']/'result.json'
        if not path.is_file():
            continue
        r = json.loads(path.read_text())
        trials = r.get('trials',[])
        seeds = cfg.get('scene_seeds')
        count = 3 if json.loads(source['config']).get('smoke') else 20
        if (r.get('status')!='completed' or r.get('domain')!='sim' or r.get('protocol')!=manifest or
            cfg.get('profile')!=scene or r.get('profile')!=scene or manifest.get('task')!=profile(scene)['task'] or
            not manifest.get('xml_sha256') or manifest['xml_sha256']!=cfg.get('expected_model_hash') or
            manifest['xml_sha256']!=r.get('model',{}).get('xml_sha256') or
            model_identity(r['model'])['model_manifest_sha256']!=manifest.get('model_manifest_sha256') or
            r.get('checkpoint_sha256')!=identity['checkpoint_sha256'] or
            r.get('n_action_steps')!=manifest.get('n_action_steps') or cfg.get('act_action_steps') is not None or
            r.get('privileged_input') is not False or r.get('new_process_reload') is not True or
            seeds!=list(range(10000,10000+count)) or seeds!=manifest.get('scene_seeds') or
            [t.get('seed') for t in trials]!=seeds or any(not t.get('initial_qpos_sha256') or t.get('outcome') not in ('success','failure','timeout','aborted') for t in trials) or
            r.get('success_fraction')!=sum(t['outcome']=='success' for t in trials)/len(seeds)):
            continue
        return {**r,'job':job['id']}
    return None


def blocked(message):
    return {'status':'blocked','message':str(message)}


def run(job_id,out_dir=None,*,development_plan_id=None):
    from .policy_runtime import PolicyCore
    job = next(j for j in catalog.rows('jobs') if j['id']==job_id)
    if job['status']!='completed' or not job['checkpoint']:
        raise ValueError('A completed training checkpoint is required')
    limits, scope = thresholds(),scope_for(job)
    real, lineage = scope['real_profile'],{}
    checks, identity = {},{}
    try:
        identity = bundle_identity(job['checkpoint'])
        checks['bundle'] = {'status':'pass','message':'Weights, configuration and both processor pipelines hashed'}
        core = PolicyCore(job['checkpoint'],'cuda')
        cfg = json.loads(job['config'])
        frozen = datasets.load_plan(cfg['plan_id'],verify=False)['profile_contract'] if cfg.get('plan_id') else None
        checks['contract'] = check_contract(core,real,job_id,frozen)
        if not frozen or not scope['scene'] or frozen['task']!=scope['instruction'] or profile(scope['scene']).get('task_template'):
            checks['scope'] = blocked('Training instruction and executable fixed physical task must match the evaluated scene')
        else:
            checks['scope'] = {'status':'pass','message':scope['instruction']}
        held,lineage = development_selection(job,scope,development_plan_id)
        if len(held)<limits['min_real_holdout_episodes']:
            raise ValueError(f"{len(held)} eligible development episodes; {limits['min_real_holdout_episodes']} required")
        if checks['contract']['status']!='pass' or checks['scope']['status']!='pass':
            raise ValueError('Physical or task contract incomplete')
        checks.update(replay_checks(core,held,real,limits))
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, ImportError) as error:
        for name in ('bundle','contract','scope','real_holdout','first_step','latency'):
            checks.setdefault(name,blocked(error))
    sim = mujoco_result(job_id,identity=identity) if identity else None
    if sim:
        n,s = len(sim['trials']),sim['success_fraction']
        checks['mujoco'] = {'status':'pass' if n>=limits['mujoco_min_episodes'] and s>=limits['mujoco_min_success'] else 'fail',
                            'episodes':n,'success':s,'job':sim['job'],'scene':sim['profile'],
                            'message':f"Closed-loop success {s:.0%} over {n} matched scenes"}
    else:
        checks['mujoco'] = blocked('No matching standard evaluation with frozen seeds, weights, processors and scene revision')
    if identity and bundle_identity(job['checkpoint']) != identity:
        checks['bundle'] = blocked('Checkpoint bundle changed while checking')
    ready = all(c['status']=='pass' for c in checks.values())
    report = {'version':2,'job':job_id,'checkpoint':job['checkpoint'],**identity,'scope':scope,'development':lineage,
              'sim_protocol':sim['protocol'] if sim else None,'trained_on':job['profile'],'robot_task':real,
              'policy':job['policy'],'checked_at':time.time(),'verdict':'ready' if ready else 'blocked',
              'meaning':'Eligible for a limited physical trial' if ready else '; '.join(
                  f'{name}: {check["message"]}' for name,check in checks.items() if check['status']!='pass'),
              'checks':checks,'thresholds':limits,'motor_commands_sent':0}
    GATES.mkdir(parents=True,exist_ok=True)
    paths = [GATES/f'{job_id}.json'] + ([Path(out_dir)/'result.json'] if out_dir else [])
    for path in paths:
        temp = path.with_suffix('.'+str(time.time_ns())+'.tmp')
        temp.write_text(json.dumps(report,indent=2,ensure_ascii=False))
        temp.replace(path)
    return report


def latest(job_id):
    path = GATES / f'{job_id}.json'
    if not path.exists():
        return None
    r = json.loads(path.read_text())
    if r.get('verdict')=='ready':
        p = r.get('sim_protocol') or {}
        if (r.get('version')!=2 or not p.get('scene') or p.get('scene_revision')!=scene_revision(p['scene']) or
            r.get('thresholds')!=thresholds() or not r.get('development',{}).get('episodes')):
            return {**r,'verdict':'blocked','meaning':'Evidence is stale or predates scoped development and scene checks'}
    return r


def require(plan):
    report = latest(plan['source_id'])
    if not report:
        raise PermissionError('Модель не проверена: запустите «Допуск к роботу»')
    if report['verdict']!='ready':
        raise PermissionError(report['meaning'])
    scope = report['scope']
    if plan.get('start_pose')!=scope.get('start_pose'):
        raise PermissionError('Start pose differs from the evaluated scene')
    if plan.get('profile')!=scope['real_profile'] or plan.get('instruction')!=scope['instruction']:
        raise PermissionError('Physical robot profile or instruction differs from the checked task')
    frozen=report['sim_protocol']
    current_geometry=probe_geometry(frozen['scene'])
    if any(frozen.get(k)!=v for k,v in current_geometry.items()):
        raise PermissionError('MuJoCo geometry changed after the evaluated trial')
    if bundle_identity(plan['checkpoint'])['checkpoint_bundle_sha256']!=report['checkpoint_bundle_sha256']:
        raise PermissionError('Веса или процессоры изменились после проверки')
    return report
