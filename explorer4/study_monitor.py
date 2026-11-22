"""Progress and independent heartbeat checks for an already-authorized local study."""
import json
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from .paths import DATA


def progress(job, now):
    folder = DATA/'jobs'/job['id']
    logs = sorted(folder.glob('trainer-*.log'), key=lambda p: p.stat().st_mtime)
    stamp = DATA/'jobs'/(job['id']+'.json')
    touched = [p.stat().st_mtime for p in [stamp, *logs, DATA/'logs'/(job['id']+'.log')] if p.is_file()]
    observation = {'quiet_seconds': max(0, round(now - max(touched))) if touched else None}
    if logs:
        log = logs[-1]
        with log.open('rb') as stream:
            stream.seek(max(0, log.stat().st_size - 32768))
            tail = stream.read().decode(errors='replace')
        entries = re.findall(r'(\d+)/(\d+)\s*\[([\d:]+)[<,]', tail)
        if entries:
            done, total = map(int, entries[-1][:2])
            elapsed = 0
            for field in entries[-1][2].split(':'):
                elapsed = elapsed * 60 + int(field)
            observation.update(step=done, total=total)
            # Discard startup transients. Use recent achieved step rates on resumed runs.
            rates = re.findall(r'(\d+\.\d+)step/s', tail)
            if done >= 250 and len(rates) >= 5:
                from statistics import median
                hz = median(float(r) for r in rates[-15:])
                if .2 < hz < 5:
                    observation['seconds_per_update'] = 1 / hz
            elif done >= 250 and 0.2 < elapsed / done < 5:
                observation['seconds_per_update'] = elapsed / done
    return observation


def evening_progress(plan, rows, rate, now, observations, estimate):
    milestone = plan['evening']
    required = milestone['required']
    missing, issues = [], []
    seconds = 0
    for key in required:
        task = plan['tasks'][key]
        item = rows[key]
        if item['status'] == 'completed' and item['metrics']:
            continue
        missing.append(key)
        if item['status'] in ('failed','blocked','cancelled','interrupted','dependency','expired','budget'):
            issues.append(key)
        live = observations.get(key, {})
        if live.get('quiet_seconds', 0) and live['quiet_seconds'] > 1200:
            issues.append(key)
        if 'step' in live:
            seconds += max(0, live['total']-live['step']) * live.get('seconds_per_update', rate) + 120
        else:
            seconds += estimate(task, rate)
    target = now.replace(hour=milestone['target_hour'], minute=0, second=0, microsecond=0)
    eta = now + timedelta(seconds=round(seconds))
    return dict(complete=not missing, completed_count=len(required)-len(missing), total=len(required),
                issues=sorted(set(issues)), missing=missing, target=target.isoformat(timespec='minutes'),
                estimate=eta.isoformat(timespec='minutes') if missing and not issues else None,
                at_risk=bool(missing) and (bool(issues) or eta > target))


def check_service(ident, day, tz, unit):
    from .study_day import read_plan, write_atomic
    from . import catalog
    from .compute_process import unit_name
    plan = read_plan(ident)
    if plan['day'] != day or datetime.now(tz).date().isoformat() != day:
        return
    if unit != 'explorer3-study-' + day.replace('-', ''):
        raise ValueError('Unexpected study service')
    root = DATA/'runs'/('study-' + day)/ident
    root.mkdir(parents=True, exist_ok=True)
    sysctl = ['systemctl', '--user']
    subprocess.run([*sysctl, 'start', 'explorer3-ui.service'], check=True, timeout=20)
    status_file = root/'status.json'
    now = time.time()
    if not status_file.exists() or now - status_file.stat().st_mtime > 240:
        subprocess.run([*sysctl, 'restart', unit+'.service'], check=True, timeout=25)
    else:
        subprocess.run([*sysctl, 'start', unit+'.service'], check=True, timeout=20)
    if not status_file.exists():
        return
    status = json.loads(status_file.read_text())
    rows = {r['id']:r for r in catalog.rows('jobs')}
    old_file = root/'control.json'
    old = json.loads(old_file.read_text()) if old_file.is_file() else {}
    checked = {'as_of': datetime.now(tz).isoformat(timespec='seconds'), 'running': {}}
    for key, item in status['tasks'].items():
        row = rows.get(item['job'])
        if not row or row['status'] != 'running' or plan['tasks'][key]['kind'] != 'train':
            continue
        sample = progress(row, now)
        scope = unit_name(row['id'])
        result = subprocess.run([*sysctl, 'show', scope, '-p', 'ActiveState', '-p', 'CPUUsageNSec'],
                                check=False, timeout=15, text=True, capture_output=True)
        props = dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
        cpu = props.get('CPUUsageNSec', '')
        sample.update(job=row['id'], sampled=now, cpu_ns=int(cpu) if cpu.isdecimal() else None)
        before = old.get('running', {}).get(key, {})
        marker = root/('watchdog-' + row['id'] + '.json')
        # Require both prolonged silence and negligible CPU across distinct timer invocations.
        # Never touch a different job, a busy worker, or a manual cancellation.
        if (sample['quiet_seconds'] is not None and sample['quiet_seconds'] > 2400 and
                before.get('job') == row['id'] and before.get('quiet_seconds', 0) > 2100 and
                now-before.get('sampled', now) >= 120 and props.get('ActiveState') == 'active' and
                sample['cpu_ns'] is not None and before.get('cpu_ns') is not None and
                0 <= sample['cpu_ns'] - before['cpu_ns'] < 200000000 and not marker.exists()):
            write_atomic(marker, json.dumps({'study': ident, 'job': row['id'], 'step': sample.get('step'),
                                             'reason':'No progress for 40 minutes, CPU inactive on successive checks'}))
            subprocess.run([*sysctl, 'stop', scope], check=True, timeout=40)
            sample['recovery_requested'] = True
        checked['running'][key] = sample
    write_atomic(old_file, json.dumps(checked, indent=2))
