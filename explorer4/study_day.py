"""Time-bounded, restartable dispatcher for a frozen plan of native offline Explorer jobs."""
import argparse
import hashlib
import html
import json
import logging
import math
import re
import shutil
import statistics
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import catalog
from .jobs import Jobs, resumable_checkpoint
from .paths import DATA
from .resources import ResourceLease


def write_atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(content)
    temp.replace(path)


def read_plan(ident):
    if not re.fullmatch('[0-9a-f]{64}', ident):
        raise ValueError('Invalid study plan ID')
    raw = (DATA/'study-days'/f'{ident}.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != ident:
        raise ValueError('Study plan digest mismatch')
    plan = json.loads(raw)
    seen = set()
    for group in plan['groups']:
        if not set(group['needs']).issubset(seen):
            raise ValueError('Unresolved study dependency')
        for key in group['keys']:
            task = plan['tasks'][key]
            if task['kind'] not in {'train', 'simulation', 'validation'} or key in seen:
                raise ValueError('Invalid study task: ' + key)
            if task.get('source') and task['source'] not in group['needs']:
                raise ValueError('Missing source dependency: ' + key)
            if task['kind'] == 'simulation' and (not 1 <= len(task['seeds']) <= 1000 or
                    len(set(task['seeds'])) != len(task['seeds']) or any(type(s) != int or s < 0 for s in task['seeds'])):
                raise ValueError('Invalid scene list')
            seen.add(key)
    if seen != set(plan['tasks']):
        raise ValueError('Unscheduled study tasks')
    return plan


def measured_rate(rows, tasks):
    estimates = []
    for key, row in rows.items():
        if row['status'] != 'completed' or tasks[key]['kind'] != 'train':
            continue
        config = json.loads(row['config'])
        duration_file = DATA/'jobs'/row['id']/'trainer-b8.log'
        if duration_file.is_file():
            # Actual completed trainer wall time includes model setup and saving.
            start = DATA/'jobs'/(row['id']+'.json')
            if start.exists():
                duration = duration_file.stat().st_mtime - start.stat().st_mtime
                if 0.2 < duration / config['steps'] < 5:
                    estimates.append(duration / config['steps'])
    return statistics.median(estimates) if estimates else 0.85


def estimate(task, rate):
    if task['kind'] == 'train':
        return task['steps'] * rate * 1.06 + 120
    if task['kind'] == 'simulation':
        return 40 + len(task['seeds']) * 15
    return 120


def find_jobs(plan, ident, inventory):
    # The catalog is newest first. Reconcile a job even if the service stopped after INSERT.
    by_draft, by_key = {}, {}
    for row in inventory:
        cfg = json.loads(row['config'])
        if cfg.get('draft_id'):
            by_draft.setdefault(cfg['draft_id'], row)
        if cfg.get('study_plan') == ident:
            by_key.setdefault(cfg['study_task'], row)
    found = {}
    for key, task in plan['tasks'].items():
        row = by_draft.get(task.get('draft')) if task['kind'] == 'train' else by_key.get(key)
        if row:
            found[key] = row
    return found


def enqueue(api, ident, key, task, found):
    if task['kind'] == 'train':
        return api.start_prepared_training(task['draft'])
    source = found[task['source']]
    bundle = Path(source['checkpoint'])
    if source['status'] != 'completed' or not (bundle/'model.safetensors').is_file():
        raise ValueError('Source checkpoint unavailable')
    cfg = dict(study_plan=ident, study_task=key, source_job=source['id'], device='cuda',
               memory_limit_mib=8192, checkpoint=str(bundle), physical_deployment_authorized=False)
    if task['kind'] == 'simulation':
        cfg.update(kind='sim_evaluate', profile=task['profile'], expected_model_hash=task['physics'],
                   episodes=len(task['seeds']), scene_seeds=task['seeds'])
        if task.get('demo_efficiency'):
            from .sim_protocol import protocol
            from scripts.demo_efficiency.design import load
            design,_ = load(task['demo_efficiency'])
            if task['profile']!=design['simulation'] or task['seeds']!=design['pilot_seeds']:
                raise ValueError('Receiver-only evaluation differs from the matched comparison')
            if design.get('endpoint'):
                cfg['carry_ticks'] = design['ticks_per_synthetic_take']
            cfg.update(diagnostic='demo_efficiency_receiver', demo_efficiency=task['demo_efficiency'],
                       protocol=protocol(task['profile'],task['seeds'],task['geometry'],str(bundle)))
    else:
        step = task['step']
        checkpoints = bundle.parent.parent
        versions = [p for p in checkpoints.iterdir() if p.name.isdecimal() and int(p.name) == step]
        if len(versions) != 1 or not (versions[0]/'pretrained_model/model.safetensors').is_file():
            raise ValueError(f'No unique checkpoint at update {step}')
        cfg.update(kind='evaluate', partition='validation', checkpoint=str(versions[0]/'pretrained_model'))
    return api._insert(source['profile'], source['policy'], cfg)


def transient(row):
    if row['status'] == 'interrupted':
        return True
    if row['status'] != 'failed':
        return False
    log = DATA/'logs'/(row['id']+'.log')
    trainer_logs = sorted((DATA/'jobs'/row['id']).glob('trainer-*.log'))
    pieces = [str(row.get('error') or '')]
    for path in [log, *trainer_logs]:
        if path.is_file():
            with path.open('rb') as stream:
                stream.seek(max(0, path.stat().st_size - 10000))
                pieces.append(stream.read().decode(errors='replace'))
    why = ' '.join(pieces).lower()
    return any(s in why for s in ('out of memory', 'sigkill', 'oom', 'resource temporarily unavailable',
                                  'process exit=137', 'process exit=-9', 'timeout expired'))


def metrics(task, row):
    folder = DATA/'jobs'/row['id']
    if task['kind'] == 'simulation':
        result = json.loads((folder/'result.json').read_text())
        trials = result['trials']
        if result['status'] != 'completed' or [t['seed'] for t in trials] != task['seeds']:
            raise ValueError('Scene list mismatch in completed evaluation')
        return {'success': sum(t['outcome'] == 'success' for t in trials), 'trials': len(trials),
                'successful_seeds': [t['seed'] for t in trials if t['outcome'] == 'success']}
    report = json.loads((folder/'evaluation.json').read_text())
    episodes = report['datasets']
    if report['role'] != 'held_out_validation' or not episodes:
        raise ValueError('Expected held-out validation')
    channels = episodes[0]['channels']
    if any(e['channels'] != channels for e in episodes):
        raise ValueError('Validation channel mismatch')
    per_axis = [statistics.mean(v) for v in zip(*(e['mae_by_channel'] for e in episodes), strict=True)]
    if not all(math.isfinite(x) for x in per_axis):
        raise ValueError('Nonfinite validation error')
    return {'episodes': len(episodes), 'samples': sum(e['samples'] for e in episodes),
            'mean_episode_mae_degrees_by_channel': dict(zip(channels, per_axis, strict=True))}


def page(plan, summary):
    labels = {'completed':'готово','queued':'в очереди Explorer','running':'в работе',
              'waiting':'в плане','failed':'ошибка','interrupted':'прервано','cancelled':'отменено',
              'budget':'резерв, не помещается','dependency':'зависит от пропущенного этапа',
              'condition':'проверка уже пройдена','expired':'время вышло','blocked':'ошибка проверки'}
    items = []
    comparisons = []
    milestone = summary.get('evening', {})
    headline = ''
    if milestone:
        if milestone['complete']:
            headline = 'Основное сравнение завершено.'
        else:
            headline = f'К 18:00 МСК · завершено {milestone["completed_count"]} из {milestone["total"]} обязательных заданий.'
            if milestone['estimate']:
                headline += ' Расчётное завершение в ' + milestone['estimate'][11:16] + ' МСК.'
            if milestone['at_risk']:
                headline += ' Есть риск задержки.'
        headline = '<p><strong>' + html.escape(headline) + '</strong></p>'
        if milestone['complete']:
            headline += ('<p>Сравните ошибки T0 и T1 по суставам и парные исходы в симуляторе. '
                         'После выбора весов зафиксируйте версию для однократной проверки на s08.</p>')
    snapshots = ''.join(f'<a href="{html.escape(s)}">{html.escape(label)}</a> ' for label, s in summary.get('snapshots', {}).items())
    axes = dict(base_rotation='основание', shoulder='плечо', elbow='локоть', wrist_pitch='наклон кисти',
                wrist_roll='поворот кисти', gripper='клешня')
    for group in plan['groups']:
        pair = group['keys']
        if len(pair) == 2 and all(summary['tasks'][k]['status'] == 'completed' for k in pair):
            a, b = [summary['tasks'][k]['metrics'] for k in pair]
            label = html.escape(group['title'] + ' (' + ', '.join(pair) + ')')
            if 'successful_seeds' in a and 'successful_seeds' in b:
                left, right = set(a['successful_seeds']), set(b['successful_seeds'])
                comparisons.append(f'<li>{label}. Успех у обеих моделей на {len(left & right)} из {a["trials"]} сцен, '
                                   f'только у первой на {len(left - right)}, только у второй на {len(right - left)}.</li>')
            if 'mean_episode_mae_degrees_by_channel' in a and 'mean_episode_mae_degrees_by_channel' in b:
                left, right = [m['mean_episode_mae_degrees_by_channel'] for m in (a, b)]
                delta = ', '.join(f'{axes.get(k, html.escape(k))} {right[k]-left[k]:+.2f}°' for k in left)
                comparisons.append(f'<li>{label}. Разность ошибок второй и первой модели, {delta}. '
                                   'Отрицательное значение означает меньшую ошибку второй модели.</li>')
        for key in group['keys']:
            row = summary['tasks'][key]
            esc = html.escape
            name = esc(key)
            if row.get('job'):
                name = f'<a href="/jobs/{esc(row["job"])}">{name}</a>'
            m = row.get('metrics', {})
            numbers = ''
            if 'trials' in m:
                numbers = f'{m["success"]} / {m["trials"]} успешных захватов'
            elif 'mean_episode_mae_degrees_by_channel' in m:
                numbers = ', '.join(f'{axes.get(k, esc(k))} {v:.2f}°' for k, v in m['mean_episode_mae_degrees_by_channel'].items())
            status = esc(labels.get(row['status'], row['status']))
            live = row.get('progress', {})
            if 'step' in live:
                status += f' · {live["step"]} / {live["total"]}'
            items.append(f'<tr><td>{esc(group["title"])}</td><td>{name}</td><td>{status}</td><td>{numbers or esc(row.get("error", ""))}</td></tr>')
    return ('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            '<meta http-equiv="refresh" content="60"><title>Explorer · Дневная очередь</title>'
            '<style>body{font:16px system-ui;max-width:1100px;margin:2em auto;padding:0 1em;color:#172a35}'
            'table{border-collapse:collapse}th,td{padding:.6em;text-align:left;border-bottom:1px solid #ccd4d8}'
            'a{color:#126777}td:last-child{font-size:.9em}</style><h1>Захват кубика с пола</h1>'
            f'<p>{summary["as_of"]} · {plan["comparison"]}</p><p>{plan["limits"]}</p>'
            '<p>Таблица обновляется раз в минуту. Ошибка действия показана в градусах по каждому суставу. '
            'Для длинных пар доступны веса после 5 000 и 10 000 обновлений.</p>'
            + headline + ('<p>Сохранённые итоги · ' + snapshots + '</p>' if snapshots else '')
            + ('<h2>Завершённые сравнения</h2><ul>' + ''.join(comparisons) + '</ul>' if comparisons else '')
            + '<table><thead><tr><th>Этап</th><th>Задание</th><th>Состояние</th><th>Результат</th></tr></thead><tbody>'
            + ''.join(items) + '</tbody></table></html>')


def cycle(ident, plan, root, state, api, now):
    deadline = datetime.combine(date.fromisoformat(plan['day']) + timedelta(days=1), datetime.min.time(), now.tzinfo)
    seconds = (deadline - now).total_seconds()
    inventory = catalog.rows('jobs')
    found = find_jobs(plan, ident, inventory)
    tasks = plan['tasks']
    rate = measured_rate(found, tasks)
    # Only one logical study dispatcher holds the lock. UI jobs continue to use their native leases.
    occupied = any(r['status'] in ('queued', 'running') for r in inventory)
    enough_space = (shutil.disk_usage(DATA/'checkpoints').free > 8 * 2**30 and
                    shutil.disk_usage(DATA/'jobs').free > 2 * 2**30)
    ready = seconds > 0 and enough_space
    changed = False
    flags = {}
    for key, row in found.items():
        if row['status'] == 'completed' and key not in state['metrics'] and key not in state['errors']:
            try:
                state['metrics'][key] = metrics(tasks[key], row)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                state['errors'][key] = str(exc)
        stalled = row['status'] == 'failed' and (root/('watchdog-' + row['id'] + '.json')).exists()
        if (ready and not occupied and key not in state['retried'] and (stalled or transient(row))
                and estimate(tasks[key], rate) < seconds):
            state['retried'].append(key)
            write_atomic(root/'state.json', json.dumps(state))
            try:
                if tasks[key]['kind'] == 'train':
                    try:
                        resumable_checkpoint(row['id'])
                    except ValueError:
                        enqueue(api, ident, key, tasks[key], found)
                    else:
                        api.resume(row['id'])
                else:
                    enqueue(api, ident, key, tasks[key], found)
                changed = occupied = True
            except (OSError, ValueError, RuntimeError) as exc:
                state['errors'][key] = str(exc)

    for index, group in enumerate(plan['groups']):
        keys = group['keys']
        missing = [k for k in keys if k not in found and k not in state['errors']]
        if not missing:
            continue
        if seconds <= 0:
            flags.update(dict.fromkeys(missing, 'expired'))
            continue
        dependencies = group['needs']
        if any(k in state['errors'] or k in found and found[k]['status'] in ('failed', 'interrupted', 'cancelled')
               or flags.get(k) in ('dependency','condition','budget') for k in dependencies):
            flags.update(dict.fromkeys(missing, 'dependency'))
            continue
        if any(k not in state['metrics'] for k in dependencies):
            continue
        gate = group.get('if_imperfect')
        if gate and state['metrics'][gate]['success'] == state['metrics'][gate]['trials']:
            flags.update(dict.fromkeys(missing, 'condition'))
            continue
        admitted = index in state['admitted']
        if not admitted and sum(estimate(tasks[k], rate) for k in missing) > seconds:
            flags.update(dict.fromkeys(missing, 'budget'))
            continue
        if not ready or (occupied and not (group.get('prequeue') or admitted)):
            continue
        if not admitted:
            state['admitted'].append(index)
            write_atomic(root/'state.json', json.dumps(state))
        for key in missing:
            try:
                enqueue(api, ident, key, tasks[key], found)
                changed = occupied = True
            except (ValueError, OSError, RuntimeError) as exc:
                state['errors'][key] = str(exc)
                logging.exception('Study task preparation: %s', key)
    if changed:
        found = find_jobs(plan, ident, catalog.rows('jobs'))
    summary = {'as_of': now.isoformat(timespec='seconds'), 'deadline': deadline.isoformat(),
               'plan': ident, 'seconds_per_update': round(rate, 3), 'space_ready': enough_space, 'tasks': {}}
    for key in tasks:
        row = found.get(key, {})
        status = 'blocked' if key in state['errors'] else row.get('status', flags.get(key, 'waiting'))
        summary['tasks'][key] = {'status': status, 'job': row.get('id'), 'error': state['errors'].get(key) or row.get('error') or '',
                                 'metrics': state['metrics'].get(key, {})}
    report_root = DATA/'simlab/reports'
    if 'evening' in plan:
        from .study_monitor import progress, evening_progress
        observations = {k:progress(r, now.timestamp()) for k,r in found.items() if r['status']=='running' and tasks[k]['kind']=='train'}
        for key, obs in observations.items():
            summary['tasks'][key]['progress'] = obs
        actual = [obs['seconds_per_update'] for obs in observations.values() if 'seconds_per_update' in obs]
        forecast_rate = statistics.median(actual) if actual else rate
        summary['evening'] = evening_progress(plan, summary['tasks'], forecast_rate, now, observations, estimate)
        reports = {}
        for hour in plan['evening']['report_hours']:
            if now >= deadline - timedelta(hours=24-hour):
                reports[f'{hour}:00'] = f'study-{plan["day"]}-{hour:02d}.html'
        if summary['evening']['complete']:
            reports['Основное сравнение'] = f'study-{plan["day"]}-completed.html'
        summary['snapshots'] = reports
        for name in reports.values():
            if not (report_root/name).exists():
                write_atomic(report_root/name, page(plan, summary))
    write_atomic(root/'state.json', json.dumps(state, indent=2))
    write_atomic(root/'status.json', json.dumps(summary, ensure_ascii=False, indent=2))
    write_atomic(report_root/f'study-{plan["day"]}.html', page(plan, summary))
    if plan.get('efficiency_plan') and all(row['status'] == 'completed' for row in summary['tasks'].values()):
        return True
    # Report the final state of already-dispatched work even if it completes past midnight.
    return seconds <= 0 and not any(row['status'] in ('running','queued') for row in found.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--control', action='store_true')
    args = parser.parse_args()
    plan = read_plan(args.plan)
    if args.check:
        print(f'{len(plan["tasks"])} tasks, {len(plan["groups"])} groups')
        return
    if args.control:
        from .study_monitor import check_service
        check_service(args.plan, plan['day'], ZoneInfo(plan['timezone']), 'explorer3-study-' + plan['day'].replace('-', ''))
        return
    root = DATA/'runs'/('study-' + plan['day'])/args.plan
    root.mkdir(parents=True, exist_ok=True)
    tz = ZoneInfo(plan['timezone'])
    if datetime.now(tz).date() < date.fromisoformat(plan['day']):
        raise ValueError('Study starts on a future day')
    with ResourceLease('study-' + plan['day']):
        path = root/'state.json'
        state = json.loads(path.read_text()) if path.exists() else dict(metrics={}, errors={}, admitted=[], retried=[])
        api = Jobs(None)
        while not cycle(args.plan, plan, root, state, api, datetime.now(tz)):
            time.sleep(15)


if __name__ == '__main__':
    main()
