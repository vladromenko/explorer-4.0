"""Prepare grouped splits then invoke the pinned official trainer, never a replacement loop."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from .paths import DATA,ROOT,offline_environment
from .profiles import profile, TRAINING
from .datasets import grouped_split, load_plan


split_episodes = grouped_split

def combine(episodes: list[dict], destination: Path, name: str):
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.datasets.dataset_tools import merge_datasets
    sources=[LeRobotDataset('local/'+episode['id'],root=episode['dataset'],video_backend='pyav')
             for episode in episodes]
    # Upstream aggregation preserves the recorded MP4 files without a lossy re-encode.
    # Only the selected training sources contribute to the merged normalization statistics.
    return merge_datasets(sources,output_repo_id='local/'+name,output_dir=destination,
                          concatenate_videos=False,concatenate_data=False)


def loader_workers():
    """Video-decoding DataLoader workers. 0 (the default) decodes in the trainer process and made a
    16-sample ACT batch take ~1.5 s with an idle GPU; DATA/configs/training.json may raise it (max 6)."""
    try:
        from .paths import DATA
        value=json.loads((DATA/'configs/training.json').read_text()).get('num_workers',0)
    except (OSError,ValueError):
        return 0
    return value if type(value) is int and 0<=value<=6 else 0


def train_command(dataset: Path, output: Path, policy='act',steps=50,batch=8,seed=1000,device='cuda',initial_checkpoint=None):
    args=[sys.executable,'-m','lerobot.scripts.lerobot_train',f'--dataset.repo_id=local/{dataset.name}',
          f'--dataset.root={dataset}','--dataset.video_backend=pyav','--dataset.use_imagenet_stats=false',
          f'--policy.type={policy}',f'--policy.device={device}','--policy.push_to_hub=false',
          '--wandb.enable=false',f'--output_dir={output}',f'--steps={steps}',f'--batch_size={batch}',
          f'--num_workers={loader_workers()}','--persistent_workers=false',f'--seed={seed}','--env_eval_freq=0',
          '--log_freq=10',f'--save_freq={min(steps,5000)}']
    info_path=dataset/'meta/info.json'
    if info_path.exists() and 'observation.environment_state' in json.loads(info_path.read_text())['features'] and not initial_checkpoint:
        normalization='MIN_MAX' if policy=='diffusion' else 'MEAN_STD'
        args.append('--policy.normalization_mapping='+json.dumps({
            'VISUAL':'MEAN_STD','STATE':normalization,'ACTION':normalization,'ENV':normalization}))
    if initial_checkpoint:
        args.remove(f'--policy.type={policy}')
        args.append(f'--policy.path={initial_checkpoint}')
    if policy=='smolvla':
        from .policy_catalog import smolvla_paths
        base,vlm=smolvla_paths()
        if not initial_checkpoint:args.remove('--policy.type=smolvla')
        info=json.loads((dataset/'meta/info.json').read_text())
        if 'observation.environment_state' in info['features']:
            raise ValueError('SmolVLA recipe cannot silently discard depth/lidar environment_state')
        features={}
        for key,value in info['features'].items():
            if key=='observation.state':
                features[key]={'type':'STATE','shape':value['shape']}
            elif key.startswith('observation.images.'):
                shape=value['shape']
                features[key]={'type':'VISUAL','shape':[shape[2],shape[0],shape[1]]}
        if not initial_checkpoint:args.append(f'--policy.path={base}')
        args.extend([f'--policy.vlm_model_name={vlm}',
                     '--policy.input_features='+json.dumps(features),
                     '--policy.output_features='+json.dumps({'action':{'type':'ACTION','shape':info['features']['action']['shape']}})])
    return args


def evaluation_command(checkpoint, roots, destination, role, device='cuda'):
    return [sys.executable, '-m', 'explorer4.evaluation', '--checkpoint', str(checkpoint),
            '--output', str(destination), '--role', role, '--device', device] + [v for root in roots for v in ('--dataset', str(root))]


def bind_test_checkpoint(source_dir, checkpoint):
    from . import fleet_config
    from .sim_protocol import bundle_identity
    identity = bundle_identity(checkpoint)
    path = source_dir/'frozen-test-checkpoint.json'
    binding = {'checkpoint':str(Path(checkpoint).resolve()), 'sha256':identity['checkpoint_sha256'],
               'checkpoint_bundle_sha256':identity['checkpoint_bundle_sha256']}
    with fleet_config.locked():
        if path.exists():
            old = json.loads(path.read_text())
            if (old['sha256'] != binding['sha256'] or
                    (old.get('checkpoint_bundle_sha256') and old['checkpoint_bundle_sha256'] != binding['checkpoint_bundle_sha256']) or
                    (not old.get('checkpoint_bundle_sha256') and Path(old['checkpoint']).resolve() != Path(checkpoint).resolve())):
                raise ValueError('Test already bound to a different checkpoint or its processors')
            return 'bundle' if old.get('checkpoint_bundle_sha256') else 'legacy_weights_only'
        fleet_config.atomic_write(path,binding)
    return 'bundle'


def run_job(path: Path):
    cfg = json.loads(path.read_text())
    work = DATA/'jobs'/path.stem
    work.mkdir(exist_ok=True)
    if cfg.get('kind') == 'simlab_pipeline':
        from scripts.simlab_pipeline import run_managed
        run_managed(cfg,work)
        return
    if cfg.get('kind') == 'three_robot_docking':
        public = DATA/'simlab/reports/three-robot-dock-v1/jobs'/work.name
        subprocess.run([str(ROOT/'.venv-sim/bin/python'),'-m','scripts.three_robot_study',
                        '--output',str(public),'--seed',str(int(cfg['seed'])),'--room',cfg['scene']],
                       cwd=ROOT,env={**offline_environment(),'MUJOCO_GL':'egl'},check=True,timeout=300)
        (work/'result.json').write_bytes((public/'result.json').read_bytes())
        return
    if cfg.get('kind') == 'workspace_study':
        from .study_queue import execute
        from .peer_primary_recovery import has_fit, partial_confirmation
        from .peer_confirmation import primary_saved
        attached = 'peer_confirmation' in cfg
        if not (attached and primary_saved(cfg, work)):
            if has_fit(cfg):
                subprocess.run([str(ROOT/'.venv-sim/bin/python'), '-m', 'explorer4.peer_primary_recovery',
                                work.name], cwd=ROOT, env={**offline_environment(), 'MUJOCO_GL':'egl'}, check=True)
            else:
                execute(cfg, work)
        if attached:
            command = (['explorer4.peer_primary_recovery', work.name, '--confirmation'] if partial_confirmation(cfg)
                       else ['explorer4.peer_confirmation', 'resume', work.name])
            if cfg.get('peer_frame_repair'):
                command = ['explorer4.peer_camera_recovery', 'run', work.name]
            subprocess.run([str(ROOT/'.venv-sim/bin/python'), '-m', *command], cwd=ROOT,
                           env={**offline_environment(), 'MUJOCO_GL':'egl', 'OMP_NUM_THREADS':'1'}, check=True)
        return
    if cfg.get('kind')=='noise_demonstrations':
        subprocess.run([str(ROOT/'.venv-sim/bin/python'),'-m','explorer4.noise_demonstrations',str(path),str(work)],
            cwd=ROOT,env={**offline_environment(),'MUJOCO_GL':'egl'},check=True,timeout=1200)
        return
    if cfg.get('kind')=='cognitive_order':
        from .cognitive.real_execution import propose_order
        propose_order(cfg,work)
        return
    if cfg.get('kind')=='cognitive_tracking':
        subprocess.run([str(ROOT/'.venv-sim/bin/python'),'-m','explorer4.cognitive.tracking',str(path),str(work)],
            cwd=ROOT,env={**offline_environment(),'YOLO_AUTOINSTALL':'false'},check=True,timeout=30)
        return
    if cfg.get('kind')=='cognitive_observation':
        from .cognitive.observation_job import execute
        execute(cfg,work)
        return
    if cfg.get('kind')=='cognitive_simulation':
        from .cognitive.run import execute
        execute(cfg,work)
        return
    if cfg.get('kind')=='rosmaster_identification':
        from .rosmaster_preparation import load_identification
        from .sim.rosmaster_sysid import identify,simulator_values
        plan=load_identification(cfg['plan_id'])
        result=identify(plan['entries'],plan['profile'],holdout_fraction=plan['holdout_fraction'])
        result.update(plan_id=cfg['plan_id'],simulator_values=simulator_values(result),training_started=False,
            physical_robot_access=False,applied_to_simulator=False)
        (work/'result.json').write_text(json.dumps(result,indent=2))
        return
    if cfg.get('kind')=='branch_gain_train':
        from .gain_model import fit_plan
        fit_plan(cfg['plan_id'],work)
        return
    if cfg.get('kind')=='fleet_execution':
        subprocess.run([str(ROOT/'.venv-sim/bin/python'),'-m','explorer4.sim.fleet_run',str(path),str(work)],
                       check=True,env={**offline_environment(),'MUJOCO_GL':'egl'})
        return
    if cfg.get('kind')=='sim_correction_import':
        from .sim.import_episode import ingest
        result=ingest(cfg['spool'],review=cfg['review'])
        (work/'result.json').write_text(json.dumps({**result,'training_started':False,'review':cfg['review']},indent=2))
        return
    if cfg.get('kind')=='sim_branches':
        subprocess.run([str(ROOT/'.venv-sim/bin/python'),'-m','explorer4.sim.branching',str(path),str(work)],
                       check=True,env={**offline_environment(),'MUJOCO_GL':'egl'})
        return
    if cfg.get('kind')=='vision':
        interpreter=ROOT/('.venv-sim/bin/python' if cfg['method']=='yoloe' else '.venv/bin/python')
        subprocess.run([str(interpreter),'-m','explorer4.perception',cfg['image'],str(work),
            '--method',cfg['method'],'--prompt',cfg['prompt'],'--device',cfg['device']],
            check=True,env={**offline_environment(),'YOLO_AUTOINSTALL':'false'})
        return
    if cfg.get('kind')=='support_calibration':
        from .act_support import prepare
        prepare(cfg['source_job'],work)
        return
    if cfg.get('kind') == 'sim_align':
        if not cfg.get('plan_id'):
            raise ValueError('Для подстройки нужен замороженный план реальных показов. Выберите его в панели.')
        result = subprocess.run([str(ROOT/'.venv-sim/bin/python'), str(ROOT/'scripts/sim_align.py'), '--plan-id', cfg['plan_id'], '--apply'],
                                cwd=ROOT, env={**offline_environment(), 'MUJOCO_GL': 'egl'}, capture_output=True, text=True, timeout=600)
        (work/'alignment.json').write_text(result.stdout or json.dumps({'error': result.stderr[-2000:]}))
        if result.returncode:
            raise RuntimeError('Подстройка сцены не выполнена: ' + result.stderr[-300:])
        report = json.loads(result.stdout[result.stdout.index('{'):])
        # demonstrations of the (re)aligned scenes for co-training; report what was really obtained
        import random
        from . import catalog as _catalog
        def successes(name):
            return sum(1 for e in _catalog.rows('episodes') if e['profile'] == name and e['outcome'] == 'success')
        demos = {}
        for block in (b for b in ('so101_handover','rosmaster_floor_pick') if report.get(b,{}).get('measured')):
            name = block+'_sim'
            before = successes(name)
            start = random.randint(20000, 900000)
            proc = subprocess.run([str(ROOT/'.venv-sim/bin/python'), '-m', 'explorer4.sim.collect', '--start', str(start),
                                   '--count', str(cfg.get('demos', 70)), '--profile', name], cwd=ROOT,
                                  env={**offline_environment(), 'MUJOCO_GL': 'egl'}, capture_output=True, text=True, timeout=4 * 3600)
            demos[name] = {'scene_from': 'measured' if 'measured' in report.get(block, {}) else 'instructions (not enough real demonstrations)',
                           'kept': report.get(block, {}).get('kept'), 'seeds': [start, start + cfg.get('demos', 70)],
                           'attempts': cfg.get('demos', 70), 'successful_demonstrations': successes(name) - before,
                           'process_error': proc.stderr[-500:] if proc.returncode else None}
        (work/'result.json').write_text(json.dumps({'alignment': report, 'demonstrations': demos}, ensure_ascii=False, indent=1))
        return
    if cfg.get('kind') == 'help_experiment':
        subprocess.run([sys.executable, str(ROOT/'scripts/swarm_help_experiment.py'), '--rooms', str(cfg.get('rooms', 30)),
                        '--out', str(work)], cwd=ROOT, env=offline_environment(), check=True, timeout=48 * 3600)
        runs = sorted(p for p in work.iterdir() if p.is_dir())
        (work/'result.json').write_text((runs[-1]/'summary.json').read_text() if runs else '{}')
        return
    if cfg.get('kind') == 'deploy_gate':
        from .deploy_gate import run
        run(cfg['source_job'], work, development_plan_id=cfg.get('development_plan_id'))
        return
    if cfg.get('kind') == 'sim_evaluate':
        if cfg.get('diagnostic') == 'floor_grasp_start_pose':
            subprocess.run([str(ROOT/'.venv-sim/bin/python'), str(ROOT/'scripts/floor_grasp_probe.py'),
                            '--job', str(path)], check=True, timeout=1800,
                           env={**offline_environment(), 'MUJOCO_GL':'egl'})
            return
        seed_args = ['--seeds', *map(str, cfg['scene_seeds'])] if 'scene_seeds' in cfg else []
        action_steps = ['--act-action-steps',str(cfg['act_action_steps'])] if 'act_action_steps' in cfg else []
        improvement = cfg.get('diagnostic') == 'recorded_start_improvement_20261122'
        record_floor = improvement or cfg.get('diagnostic') in {
            'recorded_start_adaptation', 'recorded_start_control', 'recorded_start_transfer'}
        subprocess.run([str(ROOT/'.venv-sim/bin/python'),'-m','explorer4.sim.evaluate',cfg['checkpoint'],
            str(work/'result.json'),'--profile',cfg['profile'],'--count',str(cfg['episodes']),'--device',cfg.get('device','cuda')]+seed_args+
            (['--expected-model-sha256',cfg['expected_model_hash']] if cfg.get('expected_model_hash') else [])+
            (['--queue-config',str(path)] if cfg.get('protocol') else [])+
            (['--record-floor'] if record_floor else [])+
            action_steps+(['--seed-policy-per-scene'] if improvement else []),
            check=True,env={**offline_environment(),'MUJOCO_GL':'egl'})
        return
    if cfg.get('kind') == 'sim_ppo':
        subprocess.run([str(ROOT/'.venv-sim/bin/python'),'-m','explorer4.sim.ppo','--job',str(path)],
                       check=True,env=offline_environment())
        return
    if cfg.get('kind') == 'benchmark':
        from .benchmark import run
        run(cfg['source_job'],work/'result.json')
        return
    if cfg.get('kind') == 'research':
        from .research import analyze
        analyze(work)
        return
    if cfg.get('kind') == 'evaluate':
        source = DATA/'jobs'/cfg['source_job']
        split = json.loads((source/'split.json').read_text())
        partition=cfg.get('partition','validation')
        if partition=='test':
            if not split['test']:raise ValueError('Smoke не содержит независимого test')
            test_binding=bind_test_checkpoint(source,cfg['checkpoint'])
        selected = split[partition] or split['train']
        role = 'held_out_'+partition if split[partition] else 'training_data_diagnostic_not_generalization'
        subprocess.run(evaluation_command(cfg['checkpoint'], [e['dataset'] for e in selected], work/'evaluation.json', role, cfg.get('device','cuda')),
                       env=offline_environment(), check=True)
        (work/'result.json').write_text(json.dumps({'checkpoint': cfg['checkpoint'], 'evaluation': str(work/'evaluation.json'),
                      'test_binding':test_binding if partition=='test' else None,'physical_skill_verified':False}))
        return
    profile(cfg['profile'])
    if cfg.get('draft_id'):
        from .training_drafts import load
        reviewed=load(cfg['draft_id'])
        for key in ('profile','policy','plan_id','steps','batch_size','seed','train_seed','split_seed','device','initial_checkpoint','initial_checkpoint_sha256','diffusion_floor_recipe','vision_initializer','floor_development_gate','smolvla_development'):
            if cfg.get(key)!=reviewed.get(key):raise ValueError('Job differs from the reviewed training draft: '+key)
    if cfg.get('smolvla_development'):
        from .smolvla_development import verify_before_train
        if not cfg.get('draft_id'):
            raise ValueError('The SmolVLA pilot requires its reviewed draft')
        verify_before_train(cfg)
    if cfg.get('floor_development_gate') and (not cfg.get('draft_id') or
            cfg.get('checkpoint_interval') != reviewed.get('checkpoint_interval') or cfg.get('checkpoint_interval') != 1000):
        raise ValueError('A checkpoint gate requires a reviewed simulation draft with 1000-step saves')
    plan = {}
    if cfg.get('plan_id'):
        plan = load_plan(cfg['plan_id'])
        splits = plan['splits']
        if cfg.get('floor_development_gate') and cfg['floor_development_gate']['expected_geometry_sha256'] != plan['sim_model_hash']:
            raise ValueError('The reviewed gate and dataset use different simulated geometry')
    else:
        splits = json.loads((work/'split.json').read_text()) if (work/'split.json').exists() else (
            {'train': cfg['episodes'], 'validation': [], 'test': []} if cfg['smoke'] else split_episodes(cfg['episodes'], cfg['seed']))
    split_path = work/'split.json'
    if split_path.exists() and json.loads(split_path.read_text()) != splits:
        raise ValueError('Frozen split differs from previous run')
    split_path.write_text(json.dumps(splits, indent=2))
    if not (work/'train').exists():
        combine(splits['train'], work/'train', cfg['profile'])
    steps = TRAINING[cfg['policy']].get('smoke_steps', 50) if cfg['smoke'] else TRAINING[cfg['policy']].get('steps', 100000)
    if cfg.get('steps') is not None:
        steps=int(cfg['steps'])
    resume = cfg.get('resume_checkpoint')
    if resume and cfg.get('initial_checkpoint') and cfg.get('resume_of_existing_job')!=path.stem:
        raise ValueError('Fine-tuning and optimizer resume are different jobs')
    initial = cfg.get('initial_checkpoint')
    if cfg.get('vision_initializer') and not resume:
        from .wrist_pretraining import initialize, recipe
        if cfg['vision_initializer'] != recipe() or cfg['policy'] != 'act' or not cfg['profile'].startswith('so101_') or initial:
            raise ValueError('Incompatible external initialization')
        initial = initialize(work/'train',work/'wrist-encoder-initialization',cfg['seed'])
    if resume:
        saved = json.loads((Path(resume)/'train_config.json').read_text())
        batches = (saved['batch_size'],)
    else:
        recipe=TRAINING[cfg['policy']]
        batches = (int(cfg['batch_size']),) if cfg.get('batch_size') else tuple([int(recipe.get('batch_size',8))]+[int(b) for b in recipe.get('oom_batch_fallback',(4,2,1))])
    done = False
    for batch in batches:
        if not done:
            output = DATA/'checkpoints'/f'{path.stem}-b{batch}'
            command = ([sys.executable, '-m', 'lerobot.scripts.lerobot_train',
                        f'--config_path={resume}/train_config.json', '--resume=true'] if resume else
                       train_command(work/'train', output, cfg['policy'], steps, batch, cfg['seed'],cfg.get('device','cuda'),initial))
            if not resume and cfg.get('diffusion_floor_recipe'):
                if cfg['policy'] != 'diffusion' or cfg.get('initial_checkpoint'):
                    raise ValueError('Floor cube diffusion recipe requires a new diffusion policy')
                command.extend(['--policy.resize_shape=[240,320]', '--policy.crop_ratio=1.0',
                                '--policy.noise_scheduler_type=DDIM', '--policy.num_inference_steps=16',
                                '--policy.horizon=32', '--policy.n_action_steps=10',
                                '--policy.drop_n_last_frames=21', '--policy.down_dims=[128,256,512]'])
            if not resume and (profile(cfg['profile']).get('domain') == 'sim' or cfg.get('checkpoint_interval') is not None):
                # Long runs need optimizer checkpoints before the final step. The
                # checkpoint volume is external; raw recordings remain on DATA.
                interval = int(cfg.get('checkpoint_interval', 1000))
                if interval < 1:
                    raise ValueError('Checkpoint interval must be positive')
                command = [a if not a.startswith('--save_freq=') else f'--save_freq={min(steps, interval)}' for a in command]
            (work/f'command-b{batch}.json').write_text(json.dumps(command, indent=2))
            log_path = work/f'trainer-b{batch}.log'
            development = None
            with log_path.open('a') as log:
                if cfg.get('floor_development_gate'):
                    from .floor_development_gate import run as run_gate
                    development = run_gate(work,output,cfg,batch,command,resume,log)
                    returncode = 0
                else:
                    returncode = subprocess.run(command, env=offline_environment(), stdout=log, stderr=subprocess.STDOUT).returncode
            if returncode == 0:
                done = True
                checkpoint = (development['selected_checkpoint'] if development else str(output/'checkpoints/last/pretrained_model'))
                if checkpoint:
                    if cfg.get('smolvla_development'):
                        from .smolvla_development import verify_processors
                        verify_processors(Path(checkpoint), work/'train', cfg['smolvla_development'])
                    subprocess.run([sys.executable, '-m', 'explorer4.reload_check', str(checkpoint), str(work/'train'),cfg.get('device','cuda')],
                                   env=offline_environment(), check=True)
                    if splits['validation']:
                        subprocess.run(evaluation_command(checkpoint, [e['dataset'] for e in splits['validation']],
                                       work/'evaluation.json', 'held_out_validation', cfg.get('device','cuda')), env=offline_environment(), check=True)
                result = {'checkpoint':checkpoint, 'effective_batch':batch, 'seed': cfg['seed'], 'smoke': cfg['smoke'],
                    'steps':steps, 'train_seed':cfg['seed'], 'split_seed':plan.get('split_seed',plan.get('seed')), 'plan_id':cfg.get('plan_id'), 'physical_skill_verified':False,'test_used':False,
                    'domain':profile(cfg['profile']).get('domain','real'),'initial_checkpoint':cfg.get('initial_checkpoint'),
                    'resume_checkpoint':resume,'draft_id':cfg.get('draft_id'),'mixture':cfg.get('mixture'),
                    'normalization':cfg.get('normalization','train_only'),'training_started':True,
                    'checkpoint_selection':'development_task_endpoint' if development else 'last_checkpoint',
                    'last_checkpoint':development['last_checkpoint'] if development else checkpoint}
                if development:
                    result.update(steps=development['last_step'],requested_steps=steps,training_result=development['status'],
                                  selected_step=development['selected_step'],last_checkpoint=development['last_checkpoint'],
                                  selected_checkpoint=checkpoint,development_gate=str(work/'development-gate/status.json'))
                if cfg.get('smolvla_development'):
                    from .smolvla_development import score
                    result['development_report'] = score(cfg, work, Path(checkpoint))
                temporary = work/'result.tmp'
                temporary.write_text(json.dumps(result))
                temporary.replace(work/'result.json')
            elif resume or 'out of memory' not in log_path.read_text().lower() or batch == 1:
                raise RuntimeError(f'Trainer failed: {log_path}')
    if not done:raise RuntimeError('Обучение не завершилось в разрешённом размере batch; см. журнал задания')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', type=Path, required=True)
    run_job(parser.parse_args().job)
