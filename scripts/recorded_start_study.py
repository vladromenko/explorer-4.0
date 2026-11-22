"""Offline cube ACT adaptation using a scene initialized from five accepted real training demos."""
import argparse
import hashlib
import html
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from explorer4.paths import DATA, offline_environment
from explorer4.profiles import profile
from explorer4.study_day import write_atomic

NAME = 'rosmaster_floor_pick_recorded_start_sim'
RUN = DATA/'runs/recorded-start-cube-20261121'
CONTROL = DATA/'runs/floor-cube-pair-20261121/grasp-diagnosis'
PARENT = 'f441472964e54783b037b4abf216a67e'
DEADLINE = datetime(2026,11,22,tzinfo=ZoneInfo('Europe/Moscow')).timestamp()
SCENES = range(88200, 88248)
EVALUATION = list(range(88300,88320))


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))


def setup():
    from explorer4.jobs import Jobs
    from explorer4.datasets import load_plan
    parent = Jobs(None).get(PARENT)
    cfg = json.loads(parent['config'])
    old = load_plan(cfg['plan_id'], verify=False)
    target = profile(NAME)
    for key in ('channels','state_channels','units','state_units','image_shape','fps','camera'):
        if target.get(key) != old['profile_contract'].get(key):
            raise ValueError('Different physical interface: '+key)
    used = {read(Path(e['dataset'])/'provenance.json')['hardware']['seed'] for rows in old['splits'].values() for e in rows}
    probe = read(CONTROL/'protocol.json')
    if used.intersection(set(SCENES) | set(EVALUATION)) or set(SCENES).intersection(EVALUATION):
        raise ValueError('Seed overlap')
    if (parent['status'] != 'completed' or cfg['steps'] != 30000 or target['start_center_deg'] != probe['start_pose']['real_train_medoid']
        or old['sim_model_hash'] != probe['model'] or probe['medoid_episode'] != target['start_source_episode']
        or probe['real_plan'] != target['start_source_real_plan']):
        raise ValueError('Unexpected recorded start or source model')
    base = dict(profile=NAME, parent=PARENT, parent_plan=cfg['plan_id'], physics=old['sim_model_hash'],
                start_center_deg=target['start_center_deg'], real_training_episode=probe['medoid_episode'],
                planned_successful_demos=40, candidate_seeds=list(SCENES), evaluation_seeds=EVALUATION,
                primary_steps=10000, fallback_steps=8000, batch_size=8, seed=1000,
                method='Simulation-only adaptation of v4 ACT with fresh optimizer and train-only normalization. Before/after on same fresh scenes; this does not isolate the effect of the starting pose from additional training.',
                profile_contract_sha256=hashlib.sha256(json.dumps(target, sort_keys=True).encode()).hexdigest())
    path = RUN/'protocol.json'
    if path.exists() and read(path) != base:
        raise ValueError('Existing study protocol differs')
    write(path, base)
    return base


def capture(seed):
    from explorer4.sim.capture import SimCapture
    from explorer4.sim.factory import make, EXPERTS
    protocol = read(RUN/'protocol.json')
    env = make(NAME)
    try:
        env.reset(seed=seed)
        if env.manifest['xml_sha256'] != protocol['physics'] or env.home_native.tolist() != protocol['start_center_deg']:
            raise ValueError('Scene changed')
        teacher = EXPERTS[NAME](env)
        cap = SimCapture(env, seed, 'scripted_expert', spool_parent=DATA/'checkpoints/sim-staging')
        cap.meta.update(session=f'floor-cube-recorded-start-{seed}', controller={'name':'native_position_lag','lag_s':env.lag_s,'delay_frames':1},
                        start_center_deg=protocol['start_center_deg'], realized_start_deg=env.observation()['state'].tolist(),
                        start_source_episode=protocol['real_training_episode'], task=profile(NAME)['task'])
        while True:
            a = teacher.action()
            cap.add(env, a)
            _,_,done,truncated,info = env.step(a)
            if done or truncated:
                break
        root = cap.finish(info['outcome'], info['termination_reason'])
        write(RUN/'scenes'/f'{seed}.json', dict(seed=seed, outcome=info['outcome'], frames=cap.count, spool=str(root)))
    finally:
        env.close()


def import_scene(record):
    from explorer4 import catalog
    from explorer4.sim.import_episode import ingest
    from explorer4.validation import validate
    spool = Path(record['spool'])
    receipt = spool/'imported.json'
    existing = [e for e in catalog.rows('episodes') if e['session']==f'floor-cube-recorded-start-{record["seed"]}' and e['profile']==NAME]
    if len(existing)>1:
        raise ValueError('Duplicate simulation recording')
    if existing and not receipt.exists():
        hw = read(Path(existing[0]['dataset'])/'provenance.json')['hardware']
        if hw['lineage'] != spool.name:
            raise ValueError('Different capture for this seed')
        write(receipt, validate(existing[0]['id'], domain='sim'))
    result = ingest(spool)
    if result['readback']!='PASS' or result['frames'] != record['frames'] or result['domain']!='sim':
        raise ValueError('Simulation import failed readback')
    record['episode'] = result['episode_id']
    record['readback'] = result['readback']
    write(RUN/'scenes'/f'{record["seed"]}.json', record)


def native_eval(api, stage, source, protocol):
    from explorer4 import catalog
    for j in catalog.rows('jobs'):
        c = json.loads(j['config'])
        if c.get('recorded_start_evaluation') == stage and c.get('source_job') == source['id'] and c.get('profile') == NAME:
            return j['id']
    cfg = dict(kind='sim_evaluate',profile=NAME,source_job=source['id'],checkpoint=source['checkpoint'],device='cuda',
               episodes=len(EVALUATION),scene_seeds=EVALUATION,expected_model_hash=protocol['physics'],memory_limit_mib=8192,
               diagnostic='recorded_start_adaptation',recorded_start_evaluation=stage,physical_deployment_authorized=False)
    return api._insert(NAME,'act',cfg)


def report(state, stage):
    from explorer4.jobs import Jobs
    from explorer4.study_monitor import progress
    state['stage']=stage
    state['updated']=datetime.now(ZoneInfo('Europe/Moscow')).isoformat(timespec='seconds')
    write(RUN/'state.json', state)
    lines=[]
    for key,title in [('before','Исходные веса · 20 сцен'),('train','Дообучение ACT'),('after','Новые веса · те же 20 сцен')]:
        if key not in state:continue
        j=Jobs(None).get(state[key])
        labels={'running':'идёт','completed':'готово','queued':'в очереди','failed':'ошибка','interrupted':'прервано','cancelled':'отменено'}
        details=labels.get(j['status'],j['status'])
        if key=='train' and j['status']=='running':
            live=progress(j,time.time())
            if 'step' in live:details+=f' · {live["step"]} / {live["total"]}'
        if key != 'train' and j['status']=='completed':
            trials=read(DATA/'jobs'/j['id']/'result.json')['trials']
            if [t['seed'] for t in trials]!=EVALUATION:raise ValueError('Evaluation seed mismatch')
            details+=f' · захватов {sum(t["outcome"]=="success" for t in trials)} из {len(trials)}'
        lines.append(f'<li><a href="/jobs/{j["id"]}">{title}</a> · {html.escape(details)}</li>')
    body=('<!doctype html><html lang="ru"><meta charset="utf-8"><meta http-equiv="refresh" content="45">'
          '<meta name="viewport" content="width=device-width,initial-scale=1"><title>ACT из записанной стартовой позы</title>'
          '<style>body{font:17px system-ui;max-width:740px;margin:3rem auto;padding:0 1rem;color:#172a35}li{margin:.6rem 0}a{color:#126777}</style>'
          '<h1>Обучение захвату кубика из записанной позы</h1>'
          f'<p>{state["updated"][:16].replace("T"," ")} МСК · {html.escape(stage)}</p>'
          f'<p>Успешных показов симулятора с проверенным видео: {state.get("successes",0)} из 40. '
          f'Попыток обработано: {state.get("attempts",0)}.</p>'
          '<p>Стартовую позу руки взяли из пяти реальных обучающих записей. Кубик, камера и физика контакта соответствуют исходной сцене. '
          'Эталон показывает захват, а ACT получает изображение и положения суставов. План — 10 000 обновлений. '
          'Результат сравнения — доля захватов до и после обучения на одних и тех же 20 новых сценах.</p><ul>'+''.join(lines)+'</ul>')
    write_atomic(DATA/'simlab/reports/recorded-start-training-2026-11-21.html',body)


def drive():
    from explorer4 import catalog,training_drafts
    from explorer4.jobs import Jobs
    from explorer4.resources import ResourceLease
    with ResourceLease('recorded-start-adaptation-20261121'):
        p=setup();api=Jobs(None);source=api.get(PARENT)
        state=read(RUN/'state.json') if (RUN/'state.json').exists() else {}
        records=[]
        if time.time()<DEADLINE and 'before' not in state:
            state['before']=native_eval(api,'before',source,p)
        report(state,'Сбор показов MuJoCo')
        for seed in SCENES:
            if sum(r['outcome']=='success' for r in records)>=40:break
            marker=RUN/'scenes'/f'{seed}.json'
            if not marker.exists():
                if time.time()>=DEADLINE:
                    report(state,'Дневное время сбора истекло');return
                if not os.path.ismount(DATA/'checkpoints') or shutil.disk_usage(DATA/'checkpoints').free<6*2**30 or shutil.disk_usage(DATA/'jobs').free<3*2**30:
                    raise RuntimeError('Insufficient storage for collection')
                child('capture',seed)
            record=read(marker)
            if not record.get('episode'):
                child('import',seed);record=read(marker)
            records.append(record)
            state.update(attempts=len(records),successes=sum(r['outcome']=='success' for r in records))
            report(state,'Сбор показов MuJoCo')
        good=[r['episode'] for r in records if r['outcome']=='success']
        if len(good)!=40:
            report(state,'Сбор окончен, 40 успешных показов не набраны');return
        if 'draft' not in state:
            steps=p['primary_steps']
            _,cfg=training_drafts.prepare(NAME,'act',good,steps=steps,batch=8,seed=1000,device='cuda')
            cfg.update(source_job=PARENT,source_plan_id=p['parent_plan'],initial_checkpoint=source['checkpoint'],
                       initial_checkpoint_sha256=training_drafts.checkpoint_hash(source['checkpoint']),checkpoint_interval=1000,
                       mode='simulation_adaptation_new_optimizer',physical_deployment_authorized=False,
                       sampling='New recorded-start simulated train frames only',study='recorded_start_cube_20261121')
            state.update(draft=training_drafts.save_content(DATA/'training-drafts',cfg),steps=steps,splits=cfg['split_counts'])
            report(state,'Данные проверены, план обучения сохранён')
        matches=[j for j in catalog.rows('jobs') if json.loads(j['config']).get('draft_id')==state['draft']]
        state['train']=matches[0]['id'] if matches else api.start_prepared_training(state['draft'])
        while True:
            row=api.get(state['train'])
            report(state,'Обучение на новых показах')
            if row['status']=='completed':break
            if row['status'] in ('failed','cancelled','interrupted'):
                report(state,'Обучение остановлено · '+str(row.get('error') or row['status']));return
            time.sleep(30)
        if 'after' not in state:state['after']=native_eval(api,'after',row,p)
        while True:
            outcomes=[api.get(state[k])['status'] for k in ('before','after')]
            if all(s=='completed' for s in outcomes):
                report(state,'Сравнение завершено');return
            if any(s in ('failed','cancelled','interrupted') for s in outcomes):
                report(state,'Проверка в симуляторе остановлена');return
            report(state,'Проверка на новых сценах');time.sleep(25)


def child(mode,seed):
    py=ROOT/('.venv-sim/bin/python' if mode=='capture' else '.venv/bin/python')
    env={**offline_environment(),'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1',
         'LP_NUM_THREADS':'1','GALLIUM_DRIVER':'llvmpipe','MUJOCO_GL':'egl','MUJOCO_EGL_DEVICE_ID':'2',
         '__EGL_VENDOR_LIBRARY_FILENAMES':'/usr/share/glvnd/egl_vendor.d/50_mesa.json'}
    with (RUN/f'{seed}-{mode}.log').open('a') as log:
        subprocess.run([str(py),str(Path(__file__).resolve()),mode,str(seed)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['drive','capture','import'])
    parser.add_argument('seed',type=int,nargs='?')
    a=parser.parse_args()
    if a.mode=='drive':drive()
    elif a.seed not in SCENES:raise ValueError('Seed outside frozen collection')
    elif a.mode=='capture':capture(a.seed)
    else:import_scene(read(RUN/'scenes'/f'{a.seed}.json'))
