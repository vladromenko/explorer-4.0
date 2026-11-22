"""Publish paired 2-D room outcomes from the original E1 archive. This process is read-only on experiment inputs."""
import argparse
import csv
import hashlib
import html
import io
import itertools
import json
import math
import os
import statistics
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

from .paths import DATA, ROOT

ARCHIVE = DATA/'runs/article-closeout-20261122/e1/20261122-093612'
PUBLIC = DATA/'simlab/reports/room-study-e1'
CHECKOUT = ROOT.parent/'explorer-3.0'
SOURCE_REVISION = '251f1c5721897e0b0f69c1608821aa51d428e983'
SOURCE_TREE = f'https://github.com/vladromenko/explorer-4.0/tree/{SOURCE_REVISION}'
UNITS = ('explorer3-article-e1-20261122.service','explorer4-frozen-rooms-20261122.service')
NAMES = {'K0':'Без информационной помощи','K1':'Поиск Tank','K2':'Измерение SO-101',
         'K3':'Вызов при нехватке сведений','K5':'Всегда вызывать обоих'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return json.loads(path.read_text())


def atomic(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',dir=path.parent,delete=False,encoding='utf8') as stream:
        stream.write(text)
        source=stream.name
    os.replace(source,path)


def history():
    env={**os.environ,'XDG_RUNTIME_DIR':f'/run/user/{os.getuid()}','LC_ALL':'C'}
    args=['journalctl','--user','--no-pager','--since','2026-11-22 09:00','-o','json']
    for unit in UNITS: args.extend(['-u',unit])
    log=subprocess.run(args,env=env,capture_output=True,text=True,timeout=8)
    events=[]
    for line in log.stdout.splitlines():
        entry=json.loads(line)
        message=entry.get('MESSAGE','')
        for unit in UNITS:
            action=next((s for s in ('Started','Stopped') if message.startswith(s+' '+unit)),None)
            if action:
                stamp=datetime.fromtimestamp(int(entry['__REALTIME_TIMESTAMP'])/1e6).astimezone().isoformat(timespec='seconds')
                events.append({'time':stamp,'action':action.lower(),'unit':unit})
    active=subprocess.run(['systemctl','--user','show',UNITS[1],'-p','ActiveState','--value'],
                          env=env,capture_output=True,text=True,timeout=5)
    return events,active.stdout.strip() or 'unknown'


PRIORS = ('none','where','how','both')
PRIOR_TITLES = {'none':'Нет исходных сведений', 'where':'Положение', 'how':'Размер', 'both':'Положение и размер'}
STRATA_FIELDS = ('prior','pairs','k3_only','k5_only','both_delivered','neither_delivered',
                 'tank_pairs','tank_k3','tank_k5','tank_delta_episodes',
                 'so101_pairs','so101_k3','so101_k5','so101_delta_episodes',
                 'time_pairs','median_paired_wall_s_k3_minus_k5','mean_paired_wall_s_k3_minus_k5')
DEFINITIONS = {
    'design':'Post-hoc descriptive K3 minus K5 comparisons within the same seed. Include a room only once all five frozen conditions have reported. Priors cycle deterministically in blocks of the four object types. No tests across the four strata.',
    'prior':'none seeds neither store; where inserts a simulator-truth object XY rounded to centimetres with 0.1 m uncertainty into map memory; how inserts simulated size rounded to millimetres and the derived grasp height in the knowledge store; both inserts both records.',
    'policies':'K3 and K5 use the same roster, geometric grasp baseline and rule-based coordinator. K3 uses the assessed gaps; K5 adds both location and grasp-property gaps.',
    'delivery':'Within the 600 s deadline, the mission reports done and truth.delivered contains the requested object after the common virtual SO-101 handoff. The grasp proxy depends on modelled object width.',
    'tank_searched':'Episode indicator: a search stage was logged and Tank was on the roster. It does not identify which camera found the object.',
    'so101_measured':'Episode indicator: a learn stage was logged after waiting for station practice. It may record a failed measurement; a search failure may exit before this stage is logged. It excludes the common handoff.',
    'knowledge_requests':'Length of the worker knowledge store at episode end, including any seeded how record. It is not the number of requests.',
    'recovery_requests':'Failure broker choices (agents.helps), including local retries and human escalation. It does not count the initial information helpers.',
    'denominators':'Delivery uses every complete five-condition room. Each helper count uses pairs with both boolean flags. Seconds use pairs with both mission clocks, including failed missions and timeouts capped at 600 s. Supervisor fallback clocks from worker errors are excluded. Delta episodes and delta seconds are K3 minus K5.',
    'clock':'Elapsed real wall seconds from the worker monotonic clock around the mission command and join; simulator steps, human labour, and successful-delivery-only times are different measures.',
}


def has_mission_clock(row):
    seconds = row.get('seconds')
    return (
        row['outcome'] != 'worker_error'
        and type(seconds) in (int, float)
        and math.isfinite(seconds)
        and 0 <= seconds <= row['deadline_s']
    )


def prior_strata(cells, conditions):
    seeds = sorted({seed for seed, _ in cells})
    complete_pairs = [
        (cells[seed, 'K3'], cells[seed, 'K5'])
        for seed in seeds
        if all((seed, condition) in cells for condition in conditions)
    ]
    results = []
    for prior in PRIORS:
        pairs = [(a, b) for a, b in complete_pairs if a['prior'] == prior]
        outcomes = [(a['delivered'], b['delivered']) for a, b in pairs]
        row = {
            'prior': prior,
            'pairs': len(pairs),
            'k3_only': outcomes.count((True, False)),
            'k5_only': outcomes.count((False, True)),
            'both_delivered': outcomes.count((True, True)),
            'neither_delivered': outcomes.count((False, False)),
        }
        for robot, field in [('tank', 'tank_searched'), ('so101', 'so101_measured')]:
            observed = [
                (a[field], b[field]) for a, b in pairs
                if isinstance(a.get(field), bool) and isinstance(b.get(field), bool)
            ]
            k3 = sum(a for a, _ in observed)
            k5 = sum(b for _, b in observed)
            row.update({
                f'{robot}_pairs': len(observed),
                f'{robot}_k3': k3,
                f'{robot}_k5': k5,
                f'{robot}_delta_episodes': k3 - k5,
            })
        times = [
            a['seconds'] - b['seconds'] for a, b in pairs
            if has_mission_clock(a) and has_mission_clock(b)
        ]
        row.update(
            time_pairs=len(times),
            median_paired_wall_s_k3_minus_k5=round(statistics.median(times), 2) if times else None,
            mean_paired_wall_s_k3_minus_k5=round(statistics.mean(times), 2) if times else None,
        )
        results.append(row)
    return results


def trace_agrees(row):
    if row['outcome'] == 'worker_error':
        return True  # The supervisor cannot supply the missing worker-stage measurements.
    stages = {stage['stage'] for stage in row['stages']}
    return (
        row['tank_searched'] == ('search' in stages and 'tank' in row['robots'])
        and row['so101_measured'] == ('learn' in stages)
        and row['knowledge_requests'] == len(row['knowledge'])
        and row['recovery_requests'] == row['agents']['helps']
        and row['delivered'] == (row['outcome'] == 'done' and row['object'] in row['truth']['delivered'])
    )


def track(archive=ARCHIVE,checkout=CHECKOUT):
    protocol=load(archive/'protocol.json')
    conditions=protocol['conditions']
    if (conditions!=list(NAMES) or protocol['priors']!=list(PRIORS) or protocol['rooms']!=96
            or protocol['start_seed']!=78600):
        raise ValueError('Unexpected E1 protocol')
    issues=[]
    for file,expected in protocol['sources'].items():
        path=checkout/file
        if not path.is_file() or sha(path.read_bytes())!=expected:
            issues.append('Source hash differs: '+file)
    content=(archive/'results.jsonl').read_bytes()
    end=content.rfind(b'\n')+1
    rows=[json.loads(line) for line in content[:end].splitlines()]
    cells={}
    missing_artifacts=[]
    for r in rows:
        seed=r['seed'];condition=r['condition'];ix=seed-protocol['start_seed']
        key=seed,condition
        if (key in cells or not 0<=ix<protocol['rooms'] or condition not in conditions
                or r['object']!=protocol['objects'][ix%len(protocol['objects'])]
                or r['prior']!=protocol['priors'][(ix//len(protocol['objects']))%len(protocol['priors'])]
                or type(r['delivered']) is not bool or r['deadline_s']!=protocol['deadline_s']):
            issues.append(f'Invalid or duplicate result: {key}')
            continue
        folder=(archive/r['artifact_dir']).resolve()
        if not folder.is_relative_to((archive/'episodes').resolve()):
            raise ValueError('Unexpected episode path')
        request=load(folder/'request.json')
        if any(request[k]!=r[k] for k in ('seed','condition','object','prior','deadline_s')):
            issues.append(f'Worker request differs: {key}')
        if (folder/'result.json').is_file():
            recorded=load(folder/'result.json')
            if recorded!={k:v for k,v in r.items() if k!='artifact_dir'}:
                issues.append(f'Worker result differs: {key}')
        else:
            missing_artifacts.append(f'{seed}-{condition}')
            if r['outcome']!='worker_error':
                issues.append(f'Missing worker result: {key}')
        if not trace_agrees(r):
            issues.append(f'Worker stage, store, recovery counter or delivery truth differs: {key}')
        cells[key]=r
    seeds=range(protocol['start_seed'],protocol['start_seed']+protocol['rooms'])
    summaries={}
    for c in conditions:
        retained=[r for (s,k),r in cells.items() if k==c]
        summaries[c]={'n':len(retained),'delivered':sum(r['delivered'] for r in retained),
                      'worker_errors':sum(r['outcome']=='worker_error' for r in retained),
                      'timeouts':sum(r['outcome']=='timeout' for r in retained)}
    pairs=[]
    for a,b in itertools.combinations(conditions,2):
        matched=[(cells[s,a],cells[s,b]) for s in seeds if (s,a) in cells and (s,b) in cells]
        if not matched:continue
        counts=[sum((u['delivered'],v['delivered'])==values for u,v in matched)
                for values in [(False,True),(True,False),(True,True),(False,False)]]
        delta=[v['seconds']-u['seconds'] for u,v in matched]
        pairs.append(dict(a=a,b=b,matched_rooms=len(matched),b_only=counts[0],a_only=counts[1],
                          both=counts[2],neither=counts[3],median_paired_seconds_b_minus_a=round(statistics.median(delta),2)))
    events,service=history()
    paused=load(archive.parent.parent/'pause-20261122.json')
    full=sum(all((s,c) in cells for c in conditions) for s in seeds)
    expected=protocol['rooms']*len(conditions)
    status='invalid' if issues else 'complete' if len(cells)==expected else 'running' if service=='active' else 'interrupted'
    snapshot={'status':status,'recorded_at':datetime.now().astimezone().isoformat(timespec='seconds'),
              'archive':archive.name,'protocol_sha256':sha((archive/'protocol.json').read_bytes()),
              'rows_sha256':sha(content[:end]),'complete_cells':len(cells),'planned_cells':expected,
              'complete_matched_rooms':full,'planned_rooms':protocol['rooms'],'seed_first':seeds.start,'seed_last':seeds.stop-1,
              'latest_cell':{k:rows[-1][k] for k in ('seed','condition','object','prior','outcome')} if rows else None,
              'verified_historical_sources':len(protocol['sources'])-sum(x.startswith('Source hash') for x in issues),
              'conditions':summaries,'pairs':pairs,'prior_strata':prior_strata(cells,conditions),
              'prior_strata_method':DEFINITIONS,'historical_source_revision':SOURCE_REVISION,
              'prior_strata_historical_sources':{'scripts/knowledge_gap_experiment.py':[32,122,150,171,249,300],
                  'explorer3/swarm.py':[439,463,472],'explorer3/swarm_sim.py':[243,313],'explorer3/fleet_agents.py':[257,296]},
              'service_state':service,'service_events':events,
              'recorded_stops':sum(e['action']=='stopped' for e in events),
              'owner_pause':{'time':paused['time'],'cells':paused['missions_saved']},
              'worker_errors_missing_result':missing_artifacts,'integrity_issues':issues}
    return snapshot,list(cells.values())


def csv_text(rows,fields):
    stream=io.StringIO()
    writer=csv.DictWriter(stream,fields,extrasaction='ignore',lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def table(headings,rows):
    esc=lambda x:html.escape(str(x))
    return ('<table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headings)+'</tr></thead><tbody>'
            +''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table>')


def publish():
    report,rows=track()
    slug='snapshots/'+report['rows_sha256'][:16]
    snapshot=PUBLIC/slug
    if not (snapshot/'cells.csv').is_file():
        atomic(snapshot/'pairs.csv',csv_text(report['pairs'],['a','b','matched_rooms','b_only','a_only','both','neither','median_paired_seconds_b_minus_a']))
        atomic(snapshot/'cells.csv',csv_text(rows,['seed','condition','object','prior','outcome','delivered','seconds','knowledge_requests',
                                                 'recovery_requests','tank_searched','so101_measured','collisions','artifact_dir']))
    strata_name='strata-v1/'+report['rows_sha256']+'.csv'
    if not (PUBLIC/strata_name).exists():
        atomic(PUBLIC/strata_name,csv_text(report['prior_strata'],STRATA_FIELDS))
    report.update(cells_csv=slug+'/cells.csv',pairs_csv=slug+'/pairs.csv',prior_strata_csv=strata_name)
    atomic(PUBLIC/'progress.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    if not (PUBLIC/'protocol.json').is_file():atomic(PUBLIC/'protocol.json',(ARCHIVE/'protocol.json').read_text())
    names={'complete':'Завершено','running':'Выполняется','interrupted':'Остановлено','invalid':'Ошибка проверки архива'}
    summary=table(['Условие','Доставки','Попытки','Тайм-ауты','Ошибки процесса'],[
        [k+' · '+NAMES[k],v['delivered'],v['n'],v['timeouts'],v['worker_errors']] for k,v in report['conditions'].items()])
    pairs=table(['A','B','Общих комнат','Только B','Только A','Оба','Ни один','Медиана B − A, с'],[
        [p[k] for k in ('a','b','matched_rooms','b_only','a_only','both','neither','median_paired_seconds_b_minus_a')] for p in report['pairs']])
    def uses(row,robot):
        n=row[robot+'_pairs']
        return f"{row[robot+'_k3']}/{row[robot+'_k5']} ({row[robot+'_delta_episodes']:+d}; n={n})" if n else '— (n=0)'
    strata=table(['Что известно ROSMASTER','Комнат','Только K3','Только K5','Оба','Ни один',
                  'Поиск Tank, K3/K5 (Δ; n)','Измерение SO-101, K3/K5 (Δ; n)','Медианная Δ времени, с (n)'],[
        [PRIOR_TITLES[r['prior']],r['pairs'],r['k3_only'],r['k5_only'],r['both_delivered'],r['neither_delivered'],
         uses(r,'tank'),uses(r,'so101'),f"{r['median_paired_wall_s_k3_minus_k5']:+.2f} ({r['time_pairs']})" if r['time_pairs'] else '— (0)']
        for r in report['prior_strata']])
    pauses=table(['Событие','Время','Служба'],[
        ['Запуск' if e['action']=='started' else 'Остановка',e['time'],e['unit']] for e in report['service_events']])
    errors=''.join('<li>'+html.escape(s)+'</li>' for s in report['integrity_issues'])
    page=f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Серия E1 · 96 комнат</title><style>body{{max-width:980px;margin:3em auto;padding:0 1em;font:16px/1.55 system-ui;color:#18292f}}
table{{border-collapse:collapse;width:100%;margin-bottom:1.5em}}td,th{{border-bottom:1px solid #cbd5da;padding:.35em;text-align:left}}
h1,h2{{line-height:1.16}}a{{color:#075f62}}section{{overflow-x:auto}}</style>
<a href="/workspace">Рабочая панель</a><h1>Взаимопомощь в 96 виртуальных комнатах</h1>
<p><strong>{names[report['status']]} · {report['complete_cells']} из 480 проверок.</strong> Все пять условий готовы для {report['complete_matched_rooms']} из 96 комнат.</p>
<p>Снимок архива {report['recorded_at']}. Диапазон сцен 78600–78695. Измеряются доставки в двумерной модели с заданной зависимостью захвата от ширины предмета. В финальной передаче участвует SO‑101 при каждом условии.</p>
<p><a href="{slug}/cells.csv">Результат по каждому запуску, CSV</a> · <a href="{slug}/pairs.csv">Парные сравнения, CSV</a> · <a href="progress.json">Статус, JSON</a> · <a href="protocol.json">Замороженный протокол</a></p>
<h2>Доставки по методам</h2><section>{summary}</section><h2>Сравнения в одной и той же комнате</h2>
<p>В строку входят только сцены, завершённые обоими методами. Столбцы с исходами показывают число доставок по каждому сочетанию.</p><section>{pairs}</section>
<h2>Помощь в зависимости от исходных знаний ROSMASTER</h2>
<p>Послепротокольное описание только комнат со всеми пятью условиями. K3 оценивает нехватку сведений, K5 запрашивает поиск и измерение при любых исходных знаниях. Положение и размер подставлены из состояния симулятора. Тип знаний меняется после каждой группы из четырёх предметов.</p>
<section>{strata}</section>
<p>Δ = K3 − K5. Помощник учитывается максимум один раз на эпизод. Для Tank нужен зарегистрированный этап поиска и присутствие в команде; для SO-101 — запись этапа измерения, включая неудачи. При раннем завершении поиска запись об измерении может отсутствовать. Кто именно нашёл предмет, эти флаги не устанавливают. Финальная передача SO-101 общая для всех условий.</p>
<p>Время — фактические секунды работы миссии, включая неудачи и тайм-ауты с отсечением на 600 с. Для каждого показателя указан свой парный знаменатель n. Экспериментальный счётчик знаний включает предварительно записанный размер, а счётчик восстановления включает повторные попытки самого робота. <a href="{strata_name}">Скачать четыре строки, CSV</a>.</p>
<h2>Журнал выполнения</h2><p>В журнале зафиксировано остановок: {report['recorded_stops']}. При записи паузы было сохранено {report['owner_pause']['cells']} ячейки.</p>
<section>{pauses}</section><p>Проверены версии {report['verified_historical_sources']} исходных файлов, условия, заказы и рабочие журналы завершённых ячеек. <a href="{SOURCE_TREE}">Исходная версия в репозитории Explorer 4</a>.</p><ul>{errors}</ul></html>'''
    atomic(PUBLIC/'index.html',page)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watch',action='store_true')
    args=parser.parse_args()
    while True:
        report=publish()
        print(report['status'],report['complete_cells'],report['complete_matched_rooms'],flush=True)
        if not args.watch or report['status'] in ('complete','invalid'):return
        time.sleep(180)


if __name__=='__main__':
    main()
