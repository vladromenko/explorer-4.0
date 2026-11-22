"""Dependent real-data pilot and historically matched simulation evidence, with no hardware access."""
import csv
import hashlib
import importlib.metadata
import io
import json
import shutil
import subprocess
import time
from pathlib import Path

from . import catalog, training_drafts
from .datasets import load_plan
from .jobs import Jobs
from .paths import DATA, ROOT
from .profiles import profile
from .study_day import write_atomic
from .study_monitor import progress
from .transfer_preparation import contract

NIGHT=DATA/'runs/recorded-start-cube-20261121/night'
PUBLIC=DATA/'simlab/reports/recorded-start-night'


def read(path):return json.loads(path.read_text())


def write(path,value):write_atomic(path,json.dumps(value,ensure_ascii=False,indent=2))


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def load():
    plan=read(NIGHT/'followup-queue.json')
    if digest(NIGHT/'queue.json')!=plan['parent_queue_sha256']:raise ValueError('Parent queue changed')
    environment=read(NIGHT/'followup-environment.json')
    alignment=read(ROOT/'configs/sim-alignment.json')['rosmaster_floor_pick']
    if environment['profile']!=profile('rosmaster_floor_pick_sim') or environment['alignment']!=alignment:
        raise ValueError('Historical comparison scene settings changed')
    for name,expected in environment['source_sha256'].items():
        if digest(ROOT/name)!=expected:raise ValueError('Historical simulation implementation changed: '+name)
    historical=Jobs(None).get(plan['predecessor']);cfg=json.loads(historical['config'])
    for key in ('plan_id','steps','batch_size','seed','split_counts'):
        expected=plan['real_plan'] if key=='plan_id' else plan[key]
        if cfg[key]!=expected:raise ValueError('Historical training differs: '+key)
    for block in plan['comparators']:
        path=DATA/'jobs'/block['historical_job']/'result.json'
        if digest(path)!=block['result_sha256']:raise ValueError('Historical evaluation changed')
    return plan


def prepare_transfer(plan):
    source=Jobs(None).get(plan['primary_source'])
    if source['status']!='completed':return None
    previous=training_drafts.load(plan['historical_draft'])
    real=load_plan(plan['real_plan']);source_cfg=json.loads(source['config'])
    simulated=load_plan(source_cfg['plan_id'])
    if simulated['domain']!='sim' or real['domain']!='real' or source['policy']!='act':
        raise ValueError('Unexpected transfer domains')
    if contract(simulated['profile_contract'])!=contract(real['profile_contract']):
        raise ValueError('Real/sim observation or action contract differs')
    weights=read(Path(source['checkpoint'])/'config.json')
    if (weights['type']!='act' or weights['input_features']['observation.state']['shape']!=[6]
        or weights['input_features']['observation.images.front']['shape']!=[3,480,640]
        or weights['output_features']['action']['shape']!=[6]):raise ValueError('Unexpected ACT interface')
    for key in ('study_day','study_task'):previous.pop(key,None)
    previous.update(initial_checkpoint=source['checkpoint'],
                    initial_checkpoint_sha256=training_drafts.checkpoint_hash(source['checkpoint']),
                    source_job=source['id'],source_plan_id=source_cfg['plan_id'],
                    source_sim_model_hash=simulated['sim_model_hash'],
                    checkpoint_interval=1000,study='recorded_start_real_pilot_20261122',
                    matched_predecessor=plan['predecessor'],physical_deployment_authorized=False,
                    checkpoint_selection='final step 10000; real test partition remains locked')
    for key in ('steps','batch_size','seed','split_counts'):
        if previous[key]!=plan[key]:raise ValueError('Transfer differs from matched budget')
    return training_drafts.save_content(DATA/'training-drafts',previous)


def enqueue_evaluation_once(plan,index,source):
    block=plan['comparators'][index];stage='transfer-'+str(block['scene_seeds'][0])
    cfg=dict(kind='sim_evaluate',profile=block['profile'],source_job=source['id'],checkpoint=source['checkpoint'],
             device='cuda',memory_limit_mib=8192,episodes=20,scene_seeds=block['scene_seeds'],
             expected_model_hash=block['expected_model_hash'],diagnostic='recorded_start_transfer',
             followup_plan_sha256=digest(NIGHT/'followup-queue.json'),followup_stage=stage,
             historical_comparator=block['historical_job'],physical_deployment_authorized=False)
    # Persisted identity and insertion share a transaction, including requests from a restarted driver.
    with catalog.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute("SELECT id FROM jobs WHERE json_extract(config,'$.followup_plan_sha256')=? AND json_extract(config,'$.followup_stage')=? ORDER BY created DESC LIMIT 1",
                       (cfg['followup_plan_sha256'],stage)).fetchone()
        if row:return row['id']
        import uuid
        ident=uuid.uuid4().hex
        db.execute('INSERT INTO jobs(id,profile,policy,status,config,created) VALUES(?,?,?,?,?,?)',
                   (ident,block['profile'],'act','queued',json.dumps(cfg),time.time()))
        return ident


def compare_block(block,new_row,source):
    old=read(DATA/'jobs'/block['historical_job']/'result.json')
    new=read(DATA/'jobs'/new_row['id']/'result.json')
    cfg=json.loads(new_row['config']);seeds=block['scene_seeds']
    for result in (old,new):
        if (result.get('status')!='completed' or result.get('domain')!='sim'
            or [t['seed'] for t in result['trials']]!=seeds
            or result['model']['xml_sha256']!=block['expected_model_hash']
            or any(t['outcome'] not in ('success','failure') for t in result['trials'])
            or result['success_fraction']!=sum(t['outcome']=='success' for t in result['trials'])/20):
            raise ValueError('Incomplete or mismatched historical scene comparison')
    if (cfg['source_job']!=source['id'] or cfg['scene_seeds']!=seeds or cfg['profile']!=block['profile']
        or new['checkpoint']!=source['checkpoint'] or not new['new_process_reload'] or new['privileged_input'] is not False
        or new['checkpoint_sha256']!=digest(Path(source['checkpoint'])/'model.safetensors')
        or old['checkpoint_sha256']!=block['weights_sha256']):raise ValueError('Wrong transfer weights or scenes')
    pairs=[dict(seed=a['seed'],before=a['outcome'],after=b['outcome'],before_reason=a['reason'],after_reason=b['reason'],
                after_ever_held=b.get('ever_held'),after_max_lift_cm=b.get('max_lift_cm')) for a,b in zip(old['trials'],new['trials'])]
    value=dict(historical_job=block['historical_job'],new_job=new_row['id'],source_job=source['id'],
               model_hash=block['expected_model_hash'],profile=block['profile'],scene_seeds=seeds,
               old_weights_sha256=old['checkpoint_sha256'],new_weights_sha256=new['checkpoint_sha256'],
               old_result_sha256=block['result_sha256'],new_result_sha256=digest(DATA/'jobs'/new_row['id']/'result.json'),
               before_successes=sum(p['before']=='success' for p in pairs),after_successes=sum(p['after']=='success' for p in pairs),
               total=20,paired_trials=pairs,physical_trials=False)
    write(NIGHT/f'transfer-comparison-{seeds[0]}.json',value)
    write(PUBLIC/f'transfer-comparison-{seeds[0]}.json',value)
    return value


def evidence_bundle(plan,state):
    destination=NIGHT/'article-evidence';destination.mkdir(exist_ok=True)
    old=Jobs(None).get(plan['predecessor']);new=Jobs(None).get(state['train'])
    a=read(DATA/'jobs'/old['id']/'split.json');b=read(DATA/'jobs'/new['id']/'split.json')
    result=read(DATA/'jobs'/new['id']/'result.json')
    final_step=read(Path(new['checkpoint']).parent/'training_state/training_step.json')['step']
    if a!=b or result['plan_id']!=plan['real_plan'] or final_step!=10000:
        raise ValueError('Final transfer split/checkpoint differs from the historical run')
    old_cfg=read(Path(old['checkpoint'])/'config.json');new_cfg=read(Path(new['checkpoint'])/'config.json')
    for value in (old_cfg,new_cfg):value.pop('pretrained_path',None)
    if old_cfg!=new_cfg:raise ValueError('Transfer architecture differs from historical architecture')
    main=read(NIGHT.parent/'state.json');night=read(NIGHT/'state.json')
    ids=[main['before'],main['train'],main['after'],night['control_train'],night['control_evaluation'],
         plan['predecessor'],state['train'],*state['evaluations'].values(),*[b['historical_job'] for b in plan['comparators']]]
    ids.extend(entry['job'] for entry in night.get('recovery_log',[]))
    artifacts=[]
    for ident in dict.fromkeys(ids):
        row=Jobs(None).get(ident);write(destination/'jobs'/ident/'catalog.json',row)
        for path in (DATA/'jobs'/ident).glob('*'):
            if path.is_file() and (path.suffix in ('.json','.log')):
                target=destination/'jobs'/ident/path.name;shutil.copy2(path,target)
        log=DATA/'logs'/(ident+'.log')
        if log.exists():shutil.copy2(log,destination/'jobs'/ident/'launcher.log')
    for path in NIGHT.glob('*queue*.json'):shutil.copy2(path,destination/path.name)
    for path in NIGHT.glob('*comparison*.json'):shutil.copy2(path,destination/path.name)
    for name in ('followup-environment.json','expected-scenes.json','human-pilot-audit.json',
                 'free-placement-pilot.json','followup-validation.json','chat-observations.jsonl','recording-window.json',
                 'state.json','followup-state.json','status.json'):
        path=NIGHT/name
        if path.exists():shutil.copy2(path,destination/path.name)
    if (NIGHT/'primary-diagnosis.json').exists():shutil.copy2(NIGHT/'primary-diagnosis.json',destination/'primary-diagnosis.json')
    for path in [ROOT/'explorer4/training.py',ROOT/'explorer4/jobs.py',ROOT/'explorer4/sim/evaluate.py',
                 ROOT/'explorer4/sim/aligned.py',ROOT/'explorer4/sim/factory.py',ROOT/'explorer4/sim/rosmaster_arm.py',
                 ROOT/'explorer4/sim/environment.py',ROOT/'explorer4/sim/policy_worker.py',
                 ROOT/'configs/sim-profiles.json',ROOT/'configs/sim-alignment.json',ROOT/'scripts/recorded_start_study.py',
                 ROOT/'scripts/recorded_start_night.py',Path(__file__)]:
        target=destination/'source'/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    versions={}
    for name in ('torch','torchvision','lerobot','numpy','pandas','av'):
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    versions['git_head']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    write(destination/'versions.json',versions)
    for path in sorted(destination.rglob('*')):
        if path.is_file():artifacts.append(dict(path=str(path.relative_to(destination)),sha256=digest(path),bytes=path.stat().st_size))
    comparisons=[read(NIGHT/f'transfer-comparison-{b["scene_seeds"][0]}.json') for b in plan['comparators']]
    pairs=[p for c in comparisons for p in c['paired_trials']]
    manifest=dict(created=time.time(),artifacts=artifacts,real_test_used_for_tuning=False,
                  transfer_train_job=state['train'],historical_train_job=plan['predecessor'],
                  real_split_counts=plan['split_counts'],comparisons=comparisons,
                  aggregate=dict(before_successes=sum(c['before_successes'] for c in comparisons),
                                 after_successes=sum(c['after_successes'] for c in comparisons),total=60,
                                 improved=sum(p['before']=='failure' and p['after']=='success' for p in pairs),
                                 regressed=sum(p['before']=='success' and p['after']=='failure' for p in pairs)),
                  scope='Offline initialization on five real human training demonstrations, followed by matched MuJoCo trials; no physical autonomous trial')
    write(destination/'manifest.json',manifest);write(PUBLIC/'article-evidence.json',manifest)
    output=io.StringIO();writer=csv.DictWriter(output,fieldnames=list(pairs[0]));writer.writeheader();writer.writerows(pairs)
    write_atomic(PUBLIC/'transfer-paired-scenes.csv',output.getvalue())
    archive=shutil.make_archive(str(NIGHT/'article-evidence'),'zip',destination)
    shutil.copy2(archive,PUBLIC/'article-evidence.zip')
    return manifest


def publish(plan,state):
    labels={'queued':'в очереди','running':'идёт','completed':'завершено','failed':'ошибка','interrupted':'прервано'}
    status='Ожидает обещанных 20+20 проверок'
    if state.get('train'):
        row=Jobs(None).get(state['train']);status='Перенос на 5 человеческих показов: '+labels.get(row['status'],row['status'])
        if row['status']=='running':
            live=progress(row,time.time())
            if 'step' in live:status+=f' · {live["step"]}/10000'
    if state.get('completed'):status='Перенос и все 60 сопоставимых проверок завершены'
    body='<h2>Перенос на человеческие показы</h2><p>'+status+'</p>'
    body+='<p>Пять человеческих учебных показов, прежнее разбиение 5/2/3, batch 8, seed 1000, 10 000 шагов. '
    body+='Три реальные тестовые записи закрыты для настройки. После обучения — три исторических блока MuJoCo по 20 сцен. Это симуляционные, а не физические автономные испытания.</p>'
    if state.get('train'):body+=f'<p><a href="/jobs/{state["train"]}">Журнал переноса</a></p>'
    body+='<ul>'
    for block in plan['comparators']:
        seed=block['scene_seeds'][0];ident=state.get('evaluations',{}).get(str(seed));path=NIGHT/f'transfer-comparison-{seed}.json'
        label=f'{seed}–{seed+19}: '
        if path.exists():
            result=read(path);label+=f'{result["before_successes"]}/20 → {result["after_successes"]}/20'
            body+=f'<li><a href="recorded-start-night/transfer-comparison-{seed}.json">{label}</a></li>'
        else:body+='<li>'+label+(labels.get(Jobs(None).get(ident)['status'],'ожидает') if ident else 'ожидает')+'</li>'
    body+='</ul><p><a href="recorded-start-night/followup-queue.json">План зависимостей продолжения</a> · '
    body+='<a href="recorded-start-night/followup-environment.json">Зафиксированные условия сравнения</a> · '
    body+='<a href="recorded-start-night/free-placement-pilot.json">Будущий пилот на обычном полу</a></p>'
    if state.get('completed'):
        body+='<p><a href="recorded-start-night/article-evidence.zip">Пакет доказательств для статьи (ZIP)</a> · '
        body+='<a href="recorded-start-night/article-evidence.json">Модели, версии и контрольные суммы</a> · '
        body+='<a href="recorded-start-night/transfer-paired-scenes.csv">Все 60 парных исходов (CSV)</a></p>'
    write_atomic(PUBLIC/'followup-fragment.html',body)
    write(PUBLIC/'followup-status.json',dict(summary=status,plan=plan,**state))


def advance(shared_state,api,recover,allow_launch=False):
    plan=load();path=NIGHT/'followup-state.json';state=read(path) if path.exists() else {}
    if state.get('completed'):publish(plan,state);return True
    if not state.get('draft'):
        draft=prepare_transfer(plan)
        if draft:state['draft']=draft
    if allow_launch and state.get('draft'):
        if not state.get('train'):
            matches=[j for j in catalog.rows('jobs') if json.loads(j['config']).get('draft_id')==state['draft']]
            state['train']=matches[0]['id'] if matches else api.start_prepared_training(state['draft'])
            write(path,state)
        source=recover(api,state['train'],shared_state)
        if source['status']=='completed':
            for index,block in enumerate(plan['comparators']):
                key=str(block['scene_seeds'][0]);ident=state.setdefault('evaluations',{}).get(key)
                if not ident:
                    state['evaluations'][key]=enqueue_evaluation_once(plan,index,source);write(path,state);break
                row=recover(api,ident,shared_state);state['evaluations'][key]=row['id']
                if row['status']!='completed':break
                if not (NIGHT/f'transfer-comparison-{key}.json').exists():compare_block(block,row,source)
            else:
                manifest=evidence_bundle(plan,state);state['completed']=time.time();state['aggregate']=manifest['aggregate']
    write(path,state);publish(plan,state)
    return bool(state.get('completed'))
