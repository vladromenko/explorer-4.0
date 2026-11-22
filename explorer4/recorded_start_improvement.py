"""One fixed follow-up for ACT execution and the Diffusion Policy recipe."""
import hashlib
import html
import json
import statistics
from pathlib import Path

from . import catalog, training_drafts
from .policy_catalog import validate_recipe
from .recorded_start_followup import NIGHT, PUBLIC, read, write
from .paths import DATA

SOURCE = 'a3487bcecce548a3869bde3bb16e2a1d'
HORIZONS = (100, 25, 10)
DEVELOPMENT_SEEDS = tuple(range(88400, 88412))
CONFIRMATION_SEEDS = tuple(range(88500, 88520))
STUDY = 'recorded_start_improvement_20261122'


def weights_hash(checkpoint):
    with (Path(checkpoint)/'model.safetensors').open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(api):
    path = NIGHT/'improvement-plan.json'
    source = api.get(SOURCE)
    if source['status'] != 'completed' or source['policy'] != 'act':
        raise ValueError('The completed primary ACT is required')
    config = json.loads(source['config'])
    model = read(NIGHT.parent/'protocol.json')['physics']
    if path.exists():
        plan = read(path)
        if (plan['source_weights_sha256'] != weights_hash(source['checkpoint'])
            or plan['data_plan_id'] != config['plan_id'] or plan['model_sha256'] != model):
            raise ValueError('Improvement source differs from the frozen plan')
        return plan

    wanted = set(DEVELOPMENT_SEEDS + CONFIRMATION_SEEDS)
    for row in catalog.rows('jobs'):
        scenes = json.loads(row['config']).get('scene_seeds') or ()
        if wanted.intersection(scenes):
            raise ValueError('Improvement scenes overlap an existing job')
    from .datasets import load_plan
    split = load_plan(config['plan_id'])
    for entries in split['splits'].values():
        for episode in entries:
            if read(Path(episode['dataset'])/'provenance.json')['hardware']['seed'] in wanted:
                raise ValueError('Improvement scenes overlap a demonstration')
    validate_recipe('diffusion', source['profile'])
    base = dict(config)
    for field in ('draft_id', 'resume_checkpoint', 'resume_of_existing_job', 'source_job',
                  'source_plan_id', 'source_smoke', 'source_sim_model_hash', 'recovery_of'):
        base.pop(field, None)
    base.update(policy='diffusion', batch_size=4, initial_checkpoint=None,
                initial_checkpoint_sha256=None, preparation_only=True, training_started=False,
                training_requested=False, study=STUDY, mode='new_training', checkpoint_interval=1000,
                diffusion_floor_recipe=True)
    smoke = training_drafts.save_content(DATA/'training-drafts', dict(base, steps=50, smoke=True))
    train = training_drafts.save_content(DATA/'training-drafts', dict(base, steps=10000, smoke=False))
    plan = dict(source=SOURCE, source_weights_sha256=weights_hash(source['checkpoint']),
                profile=source['profile'], model_sha256=model, data_plan_id=config['plan_id'],
                dependency='Existing control and real-data transfer comparisons have finished',
                horizons=list(HORIZONS), development_seeds=list(DEVELOPMENT_SEEDS),
                confirmation_seeds=list(CONFIRMATION_SEEDS), diffusion={'smoke_draft':smoke,
                    'training_draft':train, 'smoke_updates':50, 'updates':10000, 'batch_size':4,
                    'training_seed':config['seed'], 'checkpoint_interval':1000,
                    'resize_hw':[240,320], 'crop':False, 'sampler':'DDIM', 'denoising_steps':16,
                    'prediction_steps':32, 'action_steps':10, 'down_dims':[128,256,512]},
                selection='Most completed grasps on development scenes; ties prefer the original or longer execution horizon',
                metrics=['successful grasps', 'failure reasons', 'ever held', 'lift', 'distance to cube', 'latency'],
                next_data_experiment='If missed grasps persist, collect expert recovery from policy-induced offsets '
                                     'on new training scenes; keep a matched clean-data control and a fresh evaluation.',
                scope='MuJoCo only; comparison of complete recipes with different batch sizes; no physical access')
    write(path, plan)
    return plan


def evaluation_job(api, plan, stage, source, seeds, horizon=None):
    config = dict(kind='sim_evaluate', profile=plan['profile'], source_job=source['id'],
                  checkpoint=source['checkpoint'], device='cuda', memory_limit_mib=8192,
                  episodes=len(seeds), scene_seeds=seeds, expected_model_hash=plan['model_sha256'],
                  diagnostic=STUDY, improvement_stage=stage, physical_deployment_authorized=False)
    if horizon is not None:
        config['act_action_steps'] = horizon
    return api._insert(plan['profile'], source['policy'], config)


def summarize(result, plan, source, seeds, horizon):
    trials = result['trials']
    expected_weights = plan['source_weights_sha256'] if source['id'] == SOURCE else weights_hash(source['checkpoint'])
    if (result['status'] != 'completed' or result['domain'] != 'sim'
        or result['policy'] != source['policy'] or result['model']['xml_sha256'] != plan['model_sha256']
        or result['checkpoint_sha256'] != expected_weights or not result['policy_seed_per_scene']
        or [trial['seed'] for trial in trials] != seeds
        or any(trial['outcome'] not in ('success', 'failure') for trial in trials)
        or result['n_action_steps'] != (horizon if horizon is not None else plan['diffusion']['action_steps'])):
        raise ValueError('Improvement evaluation differs from its fixed protocol')
    has_floor_metrics = all({'ever_held', 'max_lift_cm', 'min_tip_cube_cm'} <= t.keys() for t in trials)
    return dict(successes=sum(t['outcome'] == 'success' for t in trials), total=len(trials),
                successful_seeds=[t['seed'] for t in trials if t['outcome'] == 'success'],
                floor_metrics_recorded=has_floor_metrics,
                holds=sum(t['ever_held'] for t in trials) if has_floor_metrics else None,
                median_lift_cm=statistics.median(t['max_lift_cm'] for t in trials) if has_floor_metrics else None,
                median_min_tip_cube_cm=(statistics.median(t['min_tip_cube_cm'] for t in trials)
                                        if has_floor_metrics else None),
                latency_seconds=result['sensor_to_action_seconds_p50_p95_max'],
                weights_sha256=result['checkpoint_sha256'], n_action_steps=result['n_action_steps'])


def advance(api, plan, recover, shared_state, *, ready):
    state_path = NIGHT/'improvement-state.json'
    state = read(state_path) if state_path.exists() else {}
    jobs = state.setdefault('jobs', {})
    scores = state.setdefault('scores', {})

    def job(stage, submit, match, *, technical=False):
        if 'error' in jobs.get(stage, {}):
            return None
        ident = jobs.get(stage, {}).get('id')
        if ident is None:
            existing = next((row for row in catalog.rows('jobs') if match(json.loads(row['config']))), None)
            ident = existing['id'] if existing else submit()
        row = api.get(ident)
        if row['status'] in {'failed','interrupted','cancelled'} and not technical:
            try:
                row = recover(api, ident, shared_state)
            except (ValueError, RuntimeError) as error:
                jobs[stage] = dict(id=ident, status=row['status'], error=str(error))
                return None
        jobs[stage] = dict(id=row['id'], status=row['status'])
        if row['status'] in {'failed','interrupted','cancelled'}:
            jobs[stage]['error'] = row.get('error') or 'Technical run stopped'
        return row if row['status'] == 'completed' else None

    def evaluation(stage, source, seeds, horizon=None):
        if stage in scores:
            return True
        row = job(stage, lambda: evaluation_job(api, plan, stage, source, seeds, horizon),
                  lambda c: c.get('diagnostic') == STUDY and c.get('improvement_stage') == stage)
        if row is None:
            return False
        result = read(DATA/'jobs'/row['id']/'result.json')
        scores[stage] = summarize(result, plan, source, seeds, horizon)
        write(PUBLIC/f'improvement-{stage}-trials.json', result)
        return True

    def train(stage, draft, *, technical=False):
        return job(stage, lambda: api.start_prepared_training(draft),
                   lambda c: c.get('draft_id') == draft, technical=technical)

    def run_stages():
        source = api.get(SOURCE)
        for horizon in plan['horizons']:
            if not evaluation(f'development-{horizon}', source, plan['development_seeds'], horizon):
                return
        chosen = max(plan['horizons'], key=lambda n: scores[f'development-{n}']['successes'])
        state['chosen_act_horizon'] = chosen
        for horizon in dict.fromkeys((plan['horizons'][0], chosen)):
            if not evaluation(f'confirmation-{horizon}', source, plan['confirmation_seeds'], horizon):
                return
        smoke = train('diffusion-smoke', plan['diffusion']['smoke_draft'], technical=True)
        if smoke is None:
            return
        diffusion = train('diffusion-training', plan['diffusion']['training_draft'])
        if diffusion is not None and evaluation('confirmation-diffusion', diffusion, plan['confirmation_seeds']):
            baseline = set(scores[f'confirmation-{plan["horizons"][0]}']['successful_seeds'])
            state['paired_confirmation'] = {}
            for stage in dict.fromkeys((f'confirmation-{chosen}', 'confirmation-diffusion')):
                successes = set(scores[stage]['successful_seeds'])
                state['paired_confirmation'][stage] = dict(improved=sorted(successes-baseline),
                                                          regressed=sorted(baseline-successes))
            state['completed'] = True

    if ready and not state.get('completed') and not any('error' in value for value in jobs.values()):
        run_stages()
    state['status'] = ('completed' if state.get('completed') else 'stopped' if any('error' in item for item in jobs.values())
                       else 'running' if ready else 'waiting_for_previous_comparisons')
    write(state_path, state)
    write(PUBLIC/'improvement-plan.json', plan)
    write(PUBLIC/'improvement-results.json', state)
    return state['status'] in {'completed','stopped'}


def report():
    path = NIGHT/'improvement-state.json'
    if not path.exists():
        return ''
    state = read(path)
    status = {'completed':'Серия завершена', 'stopped':'Серия остановилась на технической ошибке',
              'running':'Серия выполняется', 'waiting_for_previous_comparisons':'Ожидает текущие сравнения'}[state['status']]
    title = '<h2>Как улучшить захват</h2>'
    details = ('<p>Проверяем частоту пересчёта ACT на 12 диагностических сценах. '
               'На следующих 20 сценах сравниваем выбранную частоту с исходной и с Diffusion Policy. '
               'Diffusion проходит проверку на 50 обновлениях перед полным обучением на прежних 32 показах.</p>')
    rows = []
    labels = {'diffusion-smoke':'Diffusion Policy · проверка запуска',
              'diffusion-training':'Diffusion Policy · обучение',
              'confirmation-diffusion':'Diffusion Policy · проверка на новых сценах'}
    statuses = {'completed':'завершено', 'queued':'в очереди', 'running':'выполняется',
                'failed':'ошибка', 'interrupted':'прервано', 'cancelled':'отменено'}
    for stage, item in state['jobs'].items():
        group, _, variant = stage.partition('-')
        phase = 'диагностика' if group == 'development' else 'проверка на новых сценах'
        label = labels.get(stage, f'ACT · {variant} команд · {phase}')
        score = state['scores'].get(stage)
        status_text = f'{score["successes"]}/{score["total"]}' if score else statuses.get(item['status'], item['status'])
        rows.append(f'<li><a href="/jobs/{item["id"]}">{html.escape(label)}</a> · {html.escape(status_text)}</li>')
    links = ('<p><a href="recorded-start-night/improvement-plan.json">План и условия проверки</a> · '
             '<a href="recorded-start-night/improvement-results.json">Результаты и журналы заданий</a></p>')
    return title + f'<p>{status}</p>' + details + links + ('<ul>'+''.join(rows)+'</ul>' if rows else '')
