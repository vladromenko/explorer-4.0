"""Bounded offline follow-up: matched ACT control after the primary 20-scene evaluation."""
import argparse
import hashlib
import html
import json
import math
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from explorer4 import catalog, training_drafts
from explorer4.jobs import Jobs, resumable_checkpoint
from explorer4.paths import DATA, offline_environment
from explorer4.profiles import profile
from explorer4.resources import ResourceLease, ResourceBusy
from explorer4.study_day import write_atomic
from explorer4.study_monitor import progress

RUN = DATA/'runs/recorded-start-cube-20261121'
NIGHT = RUN/'night'
PUBLIC = DATA/'simlab/reports/recorded-start-night'
PRIMARY = 'a3487bcecce548a3869bde3bb16e2a1d'
BEFORE = 'e28f1a5345d044828aa8080a3706b08c'
ORIGINAL = '680354eb6c963ad0a4002dc4eda7d4e948992430214399c3c0e882be72d41f5e'
ADAPTED = '0c74772d2b41575bce0bd3490d97b08e024e7338f5ff8826d2e5adedc5d2a7fd'
SEEDS = list(range(88300,88320))


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    write_atomic(path,json.dumps(value,ensure_ascii=False,indent=2))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def now():
    return datetime.now(ZoneInfo('Europe/Moscow')).isoformat(timespec='seconds')


def prepare():
    protocol=read(RUN/'protocol.json')
    adapted=training_drafts.load(ADAPTED)
    control=training_drafts.load(ORIGINAL)
    for key in ('profile','plan_id','steps','batch_size','seed','device','split_counts','frames'):
        if adapted[key]!=control[key]:raise ValueError('Unmatched control: '+key)
    if (control['initial_checkpoint'] is not None or control['source_job'] is not None
        or control['steps']!=10000 or control['batch_size']!=8 or control['seed']!=1000
        or control['split_counts']!={'train':32,'validation':4,'test':4}
        or protocol['evaluation_seeds']!=SEEDS):raise ValueError('Unexpected control protocol')
    current_hash=hashlib.sha256(json.dumps(profile(control['profile']),sort_keys=True).encode()).hexdigest()
    if current_hash!=protocol['profile_contract_sha256']:raise ValueError('Recorded-start profile changed')
    control.update(checkpoint_interval=1000,physical_deployment_authorized=False,
                   study='recorded_start_cube_control_20261122')
    draft=training_drafts.save_content(DATA/'training-drafts',control)
    queue=dict(version=1,primary=PRIMARY,before=BEFORE,original_control_draft=ORIGINAL,
               adapted_draft=ADAPTED,control_draft=draft,plan_id=control['plan_id'],
               steps=10000,batch_size=8,seed=1000,checkpoint_interval=1000,
               evaluation_seeds=SEEDS,expected_model_hash=protocol['physics'],
               protocol_sha256=digest(RUN/'protocol.json'),
               sequence=['primary_train','primary_evaluation_20','idle_ui_update','control_train','control_evaluation_20'],
               maximum_recoveries_per_job=2,physical_robot_access=False,
               control_definition='No learned task checkpoint; standard ACT ImageNet ResNet18 initialization is retained',
               human_data_rule='Five accepted real demos are a technical pilot, not a labeled protocol five. No real verification recording enters training.')
    if (NIGHT/'queue.json').exists() and read(NIGHT/'queue.json')!=queue:
        raise ValueError('The frozen night queue differs')
    write(NIGHT/'queue.json',queue)
    return queue


def verify_evaluation(result, config, source, protocol):
    if (result.get('status')!='completed' or result.get('domain')!='sim'
        or result.get('policy')!='act' or not result.get('new_process_reload')
        or result.get('privileged_input') is not False
        or [t['seed'] for t in result['trials']]!=SEEDS
        or config.get('scene_seeds')!=SEEDS or config.get('episodes')!=20
        or config.get('source_job')!=source['id'] or result['checkpoint']!=source['checkpoint']
        or config.get('checkpoint')!=source['checkpoint']
        or config.get('expected_model_hash')!=protocol['physics']
        or result['model']['xml_sha256']!=protocol['physics']):
        raise ValueError('Evaluation does not match the frozen scene/weights protocol')
    if any(t['outcome'] not in ('success','failure') for t in result['trials']):
        raise ValueError('Unfinished trial')
    successes=sum(t['outcome']=='success' for t in result['trials'])
    if result['success_fraction']!=successes/20:
        raise ValueError('Outcome count differs from result summary')
    if digest(Path(source['checkpoint'])/'model.safetensors')!=result['checkpoint_sha256']:
        raise ValueError('Evaluated weights have changed')
    return successes


def comparison(state, control=False):
    target=NIGHT/('control-comparison.json' if control else 'primary-comparison.json')
    if target.exists():return read(target)
    api=Jobs(None);main=read(RUN/'state.json');protocol=read(RUN/'protocol.json')
    ids={'before':BEFORE,'after':main['after']}
    if control:ids['control']=state['control_evaluation']
    results={};summary={};models={}
    for key,ident in ids.items():
        row=api.get(ident);cfg=json.loads(row['config']);source=api.get(cfg['source_job'])
        if row['status']!='completed':raise ValueError('Evaluation is not completed')
        result=read(DATA/'jobs'/ident/'result.json')
        summary[key]=verify_evaluation(result,cfg,source,protocol)
        models[key]=dict(job=ident,source_job=source['id'],checkpoint=source['checkpoint'],
                         weights_sha256=result['checkpoint_sha256'],result_sha256=digest(DATA/'jobs'/ident/'result.json'))
        results[key]=result
        write(PUBLIC/(key+'-result.json'),result)
    if models['after']['source_job']!=PRIMARY:raise ValueError('Wrong adapted model')
    train=read(DATA/'jobs'/PRIMARY/'result.json')
    if train['steps']!=10000 or train['effective_batch']!=8 or train['seed']!=1000:
        raise ValueError('Incomplete primary training')
    queue=read(NIGHT/'queue.json')
    trained=[PRIMARY]+([state['control_train']] if control else [])
    for ident in trained:
        result=read(DATA/'jobs'/ident/'result.json')
        saved=Path(result['checkpoint']).parent/'training_state/training_step.json'
        if (result['steps']!=10000 or result['effective_batch']!=8 or result['seed']!=1000
            or result['plan_id']!=queue['plan_id'] or read(saved)['step']!=10000):
            raise ValueError('Training budget, split or final checkpoint mismatch')
    if control:
        if read(DATA/'jobs'/PRIMARY/'split.json')!=read(DATA/'jobs'/state['control_train']/'split.json'):
            raise ValueError('Control split differs from the primary split')
        configs=[read(Path(api.get(ident)['checkpoint'])/'config.json') for ident in trained]
        for cfg in configs:
            cfg.pop('pretrained_path',None)
        if configs[0]!=configs[1]:raise ValueError('ACT architecture or recipe differs between arms')
    expected=read(NIGHT/'expected-scenes.json')
    if expected['seeds']!=SEEDS or expected['model']!=protocol['physics']:
        raise ValueError('Independent reset inventory differs')
    for key,result in results.items():
        if key=='before':continue  # Historical baseline stored seed/order/model, without reset vectors.
        for trial,scene in zip(result['trials'],expected['scenes']):
            for field,tolerance in [('initial_state',1e-6),('cube_xyz0',1e-12)]:
                if len(trial[field])!=len(scene[field]) or any(abs(a-b)>tolerance for a,b in zip(trial[field],scene[field])):
                    raise ValueError('Initial scene state differs: '+str(trial['seed']))
    paired=[dict(seed=seed,**{key:result['trials'][i]['outcome'] for key,result in results.items()}) for i,seed in enumerate(SEEDS)]
    value=dict(completed=now(),seeds=SEEDS,successes=summary,total=20,models=models,
               paired_trials=paired,model_hash=protocol['physics'],protocol_sha256=digest(RUN/'protocol.json'),
               outcome_definition='Cube held in carry pose for configured stable interval; temporary grasp alone is diagnostic',
               physical_robot_access=False,baseline_reset_vectors_recorded=False,
               new_evaluation_reset_vectors_verified=True,expected_scenes_sha256=digest(NIGHT/'expected-scenes.json'))
    improved=sum(r['before']=='failure' and r['after']=='success' for r in paired)
    regressed=sum(r['before']=='success' and r['after']=='failure' for r in paired)
    discordant=improved+regressed
    value['paired_change']=dict(improved=improved,regressed=regressed,
        unchanged=20-discordant,gain_percentage_points=5*(summary['after']-summary['before']),
        exact_two_sided_mcnemar_p=min(1.,2*sum(math.comb(discordant,i) for i in range(min(improved,regressed)+1))/2**discordant) if discordant else 1.)
    value['temporary_holds']={key:sum(t.get('ever_held',False) for t in result['trials'])
                              if all('ever_held' in t for t in result['trials']) else None for key,result in results.items()}
    write(target,value);write(PUBLIC/target.name,value)
    print(json.dumps({'comparison':target.name,'successes':summary,'time':now()}),flush=True)
    return value


def recover(api, ident, state):
    row=api.get(ident)
    if row['status'] not in ('failed','interrupted','cancelled'):return row
    window_path=NIGHT/'recording-window.json'
    window=read(window_path) if window_path.exists() else {}
    if window.get('status')=='closed' and window.get('paused_job')==ident and not window.get('resumed_at'):
        api.resume(ident)
        window.update(resumed_at=now(),resume_job=ident);write(window_path,window)
        state.setdefault('recording_window_resumes',[]).append(dict(job=ident,saved_step=window.get('saved_step'),time=now()))
        write(NIGHT/'state.json',state)
        return api.get(ident)
    entry=dict(time=now(),job=ident,status=row['status'],error=row.get('error'))
    cfg=json.loads(row['config'])
    if cfg.get('kind')=='sim_evaluate':
        matches=[j for j in catalog.rows('jobs') if json.loads(j['config']).get('recovery_of')==ident]
        if matches:return api.get(matches[0]['id'])
    root=cfg.get('recovery_root',ident)
    count=state.setdefault('recoveries',{}).get(root,0)
    if count>=2:raise RuntimeError('Two recoveries exhausted for '+root)
    log=DATA/'logs'/(ident+'.log')
    if log.exists():entry['log_tail']=log.read_text(errors='replace')[-6000:]
    if cfg.get('kind','train')=='train':
        checkpoint=resumable_checkpoint(ident)
        entry['resume_checkpoint']=str(checkpoint)
        entry['saved_step']=read(checkpoint.parent/'training_state/training_step.json')['step']
        api.resume(ident)
        replacement=ident
    else:
        # Keep partial outputs under their original ID, rerun the same frozen scene list.
        cfg['recovery_of']=ident
        cfg['recovery_root']=root
        matches=[j for j in catalog.rows('jobs') if json.loads(j['config']).get('recovery_of')==ident]
        replacement=matches[0]['id'] if matches else api._insert(row['profile'],row['policy'],cfg)
    state['recoveries'][root]=count+1
    state.setdefault('recovery_log',[]).append(entry)
    write(NIGHT/'state.json',state)
    print(json.dumps(entry,ensure_ascii=False),flush=True)
    return api.get(replacement)


def idle_ui_update(state):
    marker=NIGHT/'ui-validated.json'
    if state.get('ui_updated') or not marker.exists():return
    approved=read(marker)
    if digest(ROOT/'explorer4/learn_pages.py')!=approved['learn_pages_sha256']:
        raise ValueError('UI source differs from the isolated browser verification')
    with ResourceLease('compute'):
        if any(j['status'] in ('running','queued') for j in catalog.rows('jobs')):
            raise ResourceBusy('UI update waits for the idle gap')
        # The compute lease prevents the UI worker claiming a new job during this restart.
        subprocess.run(['systemctl','--user','restart','explorer3-ui.service'],check=True,timeout=50)
        state['ui_updated']=now()
        write(NIGHT/'state.json',state)


def render_available(state):
    main=read(RUN/'state.json');api=Jobs(None)
    for tag,ident in [('after-seed-88300',main.get('after')),('control-seed-88300',state.get('control_evaluation'))]:
        if not ident or api.get(ident)['status']!='completed':continue
        source=DATA/'jobs'/ident/'first-floor-trial.json'
        destination=PUBLIC/(tag+'.mp4')
        if not source.exists() or destination.exists() or tag in state.get('video_attempts',[]):continue
        state.setdefault('video_attempts',[]).append(tag);write(NIGHT/'state.json',state)
        env={**offline_environment(),'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1',
             'MUJOCO_GL':'egl','MUJOCO_EGL_DEVICE_ID':'0',
             '__EGL_VENDOR_LIBRARY_FILENAMES':'/usr/share/glvnd/egl_vendor.d/10_nvidia.json'}
        try:
            with (NIGHT/(tag+'-render.log')).open('w') as log:
                subprocess.run([str(ROOT/'.venv-sim/bin/python'),str(ROOT/'scripts/render_recorded_start_trial.py'),
                                str(source),str(destination)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
        except (subprocess.SubprocessError,OSError) as exc:
            state.setdefault('video_errors',{})[tag]=str(exc)
        write(NIGHT/'state.json',state)


def report(state,queue):
    from explorer4.recorded_start_improvement import report as improvement_report
    api=Jobs(None);main=read(RUN/'state.json');items=[];cards=[]
    for key,title,ident in [('primary_train','Основной ACT · с предобучением',PRIMARY),
                            ('primary_evaluation','Основная проверка',main.get('after')),
                            ('control_train','Контроль ACT · без предобучения навыку',state.get('control_train')),
                            ('control_evaluation','Контроль · те же 20 сцен',state.get('control_evaluation'))]:
        if not ident:
            items.append(dict(stage=key,status='waiting_for_dependency'))
            cards.append(f'<li>{title}: ожидает предыдущего этапа</li>');continue
        row=api.get(ident);sample=progress(row,time.time()) if 'train' in key and row['status']=='running' else {}
        suffix=f' · {sample["step"]} / {sample["total"]}' if 'step' in sample else ''
        path=DATA/'jobs'/ident/'result.json'
        if 'evaluation' in key and path.exists():
            try:
                trials=read(path)['trials'];suffix=f' · {len(trials)}/20 попыток, успехов {sum(t["outcome"]=="success" for t in trials)}'
            except (ValueError,KeyError):pass
        items.append(dict(stage=key,job=ident,status=row['status'],**sample))
        label={'running':'идёт','completed':'завершено','queued':'в очереди'}.get(row['status'],row['status'])
        cards.append(f'<li><a href="/jobs/{ident}">{title}</a>: {html.escape(label+suffix)}</li>')
    stage_labels={'primary_train':'Основной ACT','primary_evaluation':'Основная проверка',
                  'control_train':'Контрольный ACT','control_evaluation':'Контрольная проверка'}
    summary='; '.join(stage_labels[x['stage']]+(f': шаг {x["step"]} / {x["total"]}' if 'step' in x else ': выполняется')
                      for x in items if x['status']=='running')
    if not summary:summary='Серия завершена' if state.get('completed') else 'Ожидание следующего этапа'
    if state.get('completed') and (PUBLIC/'followup-status.json').exists():
        summary=read(PUBLIC/'followup-status.json')['summary']
    if (NIGHT/'primary-comparison.json').exists():
        scores=read(NIGHT/'primary-comparison.json')['successes']
        summary=f'Основная серия: до {scores["before"]}/20 → после {scores["after"]}/20. '+summary
    window=read(NIGHT/'recording-window.json') if (NIGHT/'recording-window.json').exists() else {}
    if window.get('status') in ('requested','opening','open','closing'):
        summary={'requested':'Запрошено окно записи; ожидаем сохранение шага',
                 'opening':'Готовим окно записи после checkpoint',
                 'open':'Окно записи открыто; вычисления удержаны',
                 'closing':'Завершаем запись и возвращаем очередь'}[window['status']]
    status=dict(updated=now(),summary=summary,items=items,queue=queue,**state)
    write(NIGHT/'status.json',status);write(PUBLIC/'status.json',status);write(PUBLIC/'queue.json',queue)
    write(PUBLIC/'protocol.json',read(RUN/'protocol.json'))
    rows=''
    result_path=NIGHT/('control-comparison.json' if (NIGHT/'control-comparison.json').exists() else 'primary-comparison.json')
    if result_path.exists():
        result=read(result_path)
        headings={'before':'До','after':'После','control':'Контроль'}
        columns=[k for k in headings if k in result['successes']]
        rows='<h2>Одни и те же сцены</h2><p>'+html.escape(', '.join(f'{headings[k]}: {result["successes"][k]}/20' for k in columns))+'</p>'
        rows+='<table><tr><th>Seed</th>'+''.join('<th>'+headings[k]+'</th>' for k in columns)+'</tr>'
        for r in result['paired_trials']:
            rows+='<tr><td>'+str(r['seed'])+'</td>'+''.join('<td>'+('✓' if r[k]=='success' else '—')+'</td>' for k in columns)+'</tr>'
        rows+='</table><p><a href="recorded-start-night/'+result_path.name+'">Сверка сцен, результатов и SHA-256 весов (JSON)</a></p>'
    if (NIGHT/'primary-diagnosis.json').exists():
        diagnosis=read(NIGHT/'primary-diagnosis.json')
        rows+=('<h2>Ошибки основной серии</h2><p>Неудач по лимиту времени: '+str(diagnosis['deadline_failures'])+'. '
               'Из них подъём меньше 1 см: '+str(diagnosis['failures_lift_under_1cm'])+'. '
               'У неудачных попыток медианное минимальное расстояние от кончика захвата до центра кубика: '
               f'{diagnosis["failed_median_min_tip_cube_cm"]:.2f} см. '
               'Эти измерения показывают этап сбоя, но сами по себе не отделяют ошибку наведения от проблемы контакта.</p>'
               '<p><a href="recorded-start-night/primary-paired-scenes.csv">Все 20 исходов и измерения (CSV)</a> · '
               '<a href="recorded-start-night/primary-diagnosis.json">Диагностическая сводка</a></p>')
    videos=''
    for path in sorted(PUBLIC.glob('*.mp4')):
        title={'after-seed-88300':'После обучения · сцена 88300','control-seed-88300':'Контроль без предобучения навыку · сцена 88300',
               'visual-pick-924000':'Наведение по RGB · первая новая сцена 924000'}.get(path.stem,path.stem)
        alternative=path.with_suffix('.webm')
        sources=(f'<source src="recorded-start-night/{alternative.name}" type="video/webm">' if alternative.exists() else '')
        sources+=f'<source src="recorded-start-night/{path.name}" type="video/mp4">'
        videos+=f'<figure><figcaption>{html.escape(title)} · воспроизведение записанной попытки</figcaption><video controls preload="metadata">{sources}</video></figure>'
    followup=(PUBLIC/'followup-fragment.html').read_text() if (PUBLIC/'followup-fragment.html').exists() else ''
    visual=''
    if (PUBLIC/'visual-pick-v1.json').is_file():
        groups=read(PUBLIC/'visual-pick-v1.json')['groups']
        paired=groups['paired']['predicted_xy']
        fresh=groups['fresh']['predicted_xy']
        control=groups['fresh']['training_mean_xy']
        historical=groups['historical']['predicted_xy']
        visual=(f'<h2>Захват по изображению кубика</h2><p>Зрение ResNet-18 и кинематика ROSMASTER. '
                f'На исходных сценах 88300–88319 результат {historical["successes"]}/{historical["total"]}. '
                f'На тех же сценах, что у ACT и Diffusion Policy, робот поднял и удержал кубик '
                f'{paired["successes"]} раз из {paired["total"]}. '
                f'На новых сценах результат {fresh["successes"]}/{fresh["total"]}. '
                f'С той же траекторией обзора и наведением в среднюю точку обучающей выборки '
                f'результат {control["successes"]}/{control["total"]}.</p>'
                '<p>Для донастройки зрительной сети использовали по одному размеченному кадру из 1 024 сцен MuJoCo. '
                'Ещё 128 сцен использовали для выбора весов. При каждой попытке сеть оценивает координаты кубика '
                'по изображению с руки. Успех засчитывается после подъёма и удержания в транспортной позе.</p>'
                '<p><a href="recorded-start-night/visual-pick-v1.json">Исходы попыток, ошибки наведения и версия весов</a></p>')
        if (PUBLIC/'visual-pick-evidence.zip').is_file():
            visual+=('<p><a href="recorded-start-night/visual-pick-scenes.csv">Сравнение по сценам (CSV)</a> · '
                     '<a href="recorded-start-night/visual-pick-evidence.zip">Скачать веса, код и журналы</a></p>')
    paper=('<p><a href="article-20261122/index.html">Рукопись, результаты экспериментов и опись физических показов</a></p>'
           if (PUBLIC.parent/'article-20261122/index.html').is_file() else '')
    page=('<!doctype html><html lang="ru"><meta charset="utf-8"><meta http-equiv="refresh" content="45">'
          '<meta name="viewport" content="width=device-width,initial-scale=1"><title>ROSMASTER · захват кубика</title>'
          '<style>body{background:#101820;color:#e0e9ee;font:17px system-ui;max-width:960px;margin:2rem auto;padding:0 1rem}'
          'a{color:#6cd6bd}li{margin:.7rem 0}video{width:100%;max-width:800px}table{border-collapse:collapse}td,th{padding:6px 20px;border:1px solid #456}code{overflow-wrap:anywhere}</style>'
          '<h1>ROSMASTER · поднять кубик с пола</h1><p>'+html.escape(now())+' МСК</p><p>'+html.escape(summary)+'</p>'+paper+
          '<p>Вычисления идут на Homebrain, в MuJoCo. Физический ROSMASTER выключен. ACT: изображение камеры и суставы → действия. '
          '40 успешных показов симулятора, разбиение 32/4/4. Проверка: 20 самостоятельных попыток, seeds 88300–88319 в этом порядке.</p>'
          '<p><a href="/learn?tab=sim">Обучение</a> · <a href="recorded-start-training-2026-11-21.html">Основной отчёт</a> · '
          '<a href="/sim">PPO · отдельная задача перекладывания кубика</a></p><ul>'+''.join(cards)+'</ul>'
          '<p>Контроль: тот же план и 32 учебных эпизода, seed 1000, batch 8, 10 000 шагов, сохранения каждые 1000. '
          'Без весов освоенного навыка; стандартная инициализация зрительного ResNet18 от ImageNet сохранена. '
          'Выбор весов заранее фиксирован на последнем шаге, проверочные сцены не используются для подбора.</p>'+visual+rows+videos+followup+improvement_report()+
          '<h2>Протокол и материалы</h2><p><a href="recorded-start-night/queue.json">Замороженная очередь</a> · '
          '<a href="recorded-start-night/protocol.json">Исходный протокол</a> · <a href="recorded-start-night/status.json">Текущее состояние</a></p>'
          '<p><a href="recorded-start-night/human-pilot.html">Аудит человеческих показов и происхождения данных</a></p>'
          '<p>Пять принятых реальных показов — технический пилот, а не протокольное k=5. '
          'Человеческие учебные показы и реальные проверочные записи хранятся раздельно.</p></html>')
    write_atomic(DATA/'simlab/reports/recorded-start-night.html',page)


def drive():
    from explorer4.recorded_start_followup import advance
    from explorer4.recorded_start_improvement import advance as advance_improvement, prepare as prepare_improvement
    queue=prepare();api=Jobs(None)
    with ResourceLease('recorded-start-night-20261122'):
        state=read(NIGHT/'state.json') if (NIGHT/'state.json').exists() else {}
        improvement_plan=prepare_improvement(api) if (NIGHT/'improvement-plan.json').exists() else None
        while True:
            window=NIGHT/'recording-window.json'
            if window.exists() and read(window).get('status') in ('requested','opening','open','closing'):
                report(state,queue);time.sleep(15);continue
            primary=recover(api,PRIMARY,state)
            main=read(RUN/'state.json')
            if not main.get('after'):
                # Restart only the lightweight study driver if it exited after a trainer failure.
                subprocess.run(['systemctl','--user','start','explorer3-recorded-start-20261121.service'],check=True,timeout=20)
            if primary['status']=='completed' and main.get('after'):
                if api.get(main['after'])['status'] in ('failed','interrupted','cancelled'):
                    # Stop the old reporter before replacing its locally cached evaluation ID.
                    subprocess.run(['systemctl','--user','stop','explorer3-recorded-start-20261121.service'],check=True,timeout=20)
                    main=read(RUN/'state.json')
                after=recover(api,main['after'],state)
                if after['id']!=main['after']:
                    main['after']=after['id'];write(RUN/'state.json',main)
                    subprocess.run(['systemctl','--user','start','explorer3-recorded-start-20261121.service'],check=True,timeout=20)
                if after['status']=='completed':
                    comparison(state)
                    try:idle_ui_update(state)
                    except ResourceBusy:report(state,queue);time.sleep(15);continue
                    if 'control_train' not in state:
                        matches=[j for j in catalog.rows('jobs') if json.loads(j['config']).get('draft_id')==queue['control_draft']]
                        state['control_train']=matches[0]['id'] if matches else api.start_prepared_training(queue['control_draft'])
                        write(NIGHT/'state.json',state)
            if 'control_train' in state:
                control=recover(api,state['control_train'],state)
                if control['status']=='completed' and 'control_evaluation' not in state:
                    cfg=dict(kind='sim_evaluate',profile=control['profile'],source_job=control['id'],checkpoint=control['checkpoint'],
                             device='cuda',episodes=20,scene_seeds=SEEDS,expected_model_hash=queue['expected_model_hash'],
                             memory_limit_mib=8192,diagnostic='recorded_start_control',physical_deployment_authorized=False)
                    matches=[j for j in catalog.rows('jobs') if json.loads(j['config']).get('diagnostic')=='recorded_start_control'
                             and json.loads(j['config']).get('source_job')==control['id']]
                    state['control_evaluation']=matches[0]['id'] if matches else api._insert(control['profile'],'act',cfg)
                if 'control_evaluation' in state:
                    evaluation=recover(api,state['control_evaluation'],state)
                    state['control_evaluation']=evaluation['id']
                    if evaluation['status']=='completed':
                        comparison(state,control=True);state.setdefault('completed',now())
            followup_complete=advance(state,api,recover,allow_launch=bool(state.get('completed')))
            improvement_complete=(advance_improvement(api,improvement_plan,recover,state,ready=followup_complete)
                                  if improvement_plan else True)
            write(NIGHT/'state.json',state);report(state,queue)
            render_available(state)
            report(state,queue)
            if state.get('completed') and followup_complete and improvement_complete:return
            time.sleep(30)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','drive','report'])
    args=parser.parse_args()
    if args.mode=='drive':drive()
    else:
        queue=prepare();state=read(NIGHT/'state.json') if (NIGHT/'state.json').exists() else {}
        report(state,queue);print(json.dumps(queue,ensure_ascii=False,indent=2))
