#!/usr/bin/env python3
"""Deploy own inert services, with backups and rollback; never acquire hardware."""
import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path
import shlex
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from explorer4.paths import ROOT,DATA
from agents.tank.limits import DEFAULTS, load as effective_limits
from scripts.build_staging_bundles import build
from scripts.install_tank_bundle import LEGACY as PERMISSION_FILES

HEALTH_FILES = ('agent.py', 'native_driver.py', 'native_client.py', 'limits.py', 'motor_link.py',
                'motion_permission.py', 'sensors.py')
PREVIOUS_PERMISSION_SHA = 'b7c34ba88d19c487fd3e388754af76c26be2a0eadec15289673c0fb042a2b22c'


HOST_STAGE='/home/pi/explorer3-recording-r2-staging'
STAGE='/home/ubuntu/explorer3-recording-r2-staging'
REMOTE='/home/ubuntu/explorer3'
SERVICES=('explorer3-tank-agent.service','explorer3-tank-sensors@0.service','explorer3-tank-sensors@1.service')


def ssh(*args,timeout=40):
    return subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5','tank',shlex.join(args)],capture_output=True,text=True,timeout=timeout,check=True).stdout


def docker(*args):return ssh('docker','exec','-u','ubuntu','MentorPi',*args)


def health():
    import httpx
    cfg=json.loads((DATA/'configs/tank-agent.json').read_text())
    with httpx.Client(headers={'X-Explorer-Token':cfg['token']},trust_env=False,timeout=3) as client:
        response=client.get(f"http://{cfg['host']}:{cfg['port']}/health");response.raise_for_status();return response.json()


def source_hash(name):
    return hashlib.sha256((ROOT / 'agents/tank' / name).read_bytes()).hexdigest()


def read_policy():
    # Return operator limits and hashes of permission markers. Never transmit their contents.
    program = """import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
caps = root / 'configs/tank-limits.json'
names = sys.argv[2:]
print(json.dumps({'limits_hex': caps.read_bytes().hex() if caps.exists() else None,
                  'permission_sha256': {n: hashlib.sha256((root/n).read_bytes()).hexdigest()
                                        if (root/n).exists() else None for n in names}}))"""
    return json.loads(docker('python3', '-c', program, REMOTE, *PERMISSION_FILES))


def require_inert(status):
    if status.get('armed') is not False or status.get('hardware_open') is not False:
        raise ValueError('Tank must report both disarmed and its motor hardware closed')


def preflight(status, raw):
    require_inert(status)
    with tempfile.TemporaryDirectory() as work:
        if raw is not None:
            stored = json.loads(raw)
            if not isinstance(stored, dict) or stored.get('version') != 2:
                raise ValueError('Onboard limit format requires explicit migration. Version 1 has different stop and sensor semantics; preserve the file and compare its active limits before updating.')
            for name, value in stored.items():
                if name not in DEFAULTS:
                    raise ValueError('Unknown onboard operator setting: '+name)
                default = DEFAULTS[name]
                if type(value) is not type(default) and not (type(default) is float and type(value) is int):
                    raise ValueError('Unsupported onboard operator setting: '+name)
                if isinstance(default, dict):
                    if set(value) != set(default) or any(type(x) not in (float, int) or not math.isfinite(x) or x < 0 for x in value.values()):
                        raise ValueError('Invalid onboard velocity or acceleration group: '+name)
                elif type(value) in (float, int) and (not math.isfinite(value) or value < 0):
                    raise ValueError('Invalid onboard operator setting: '+name)
            folder = Path(work) / 'configs'
            folder.mkdir()
            (folder/'tank-limits.json').write_bytes(raw)
        expected = effective_limits(Path(work))
        if raw is not None and any(type(v) is int and type(DEFAULTS[k]) is float and expected[k] != v
                                   for k,v in stored.items()):
            raise ValueError('Candidate loader would ignore an integer-valued operator override')
    if status.get('limits') != expected:
        raise ValueError('Candidate effective limits differ from the running operator limits. Preserve current configuration and reconcile explicitly before deployment.')
    if (status.get('software') or {}).get('motion_permission.py') not in {
        PREVIOUS_PERMISSION_SHA, source_hash('motion_permission.py')}:
        raise ValueError('Existing onboard permission implementation is unrecognized; explicit migration required')
    return {'effective_limits':expected,'operator_config_sha256': hashlib.sha256(raw).hexdigest() if raw is not None else None}


def configuration_bytes(snapshot):
    return bytes.fromhex(snapshot['limits_hex']) if snapshot['limits_hex'] is not None else None


def verify_installation(actual, expected, before, after):
    require_inert(actual)
    if before != after:
        raise ValueError('Onboard settings or permission markers changed during deployment')
    if actual.get('limits') != expected['effective_limits']:
        raise ValueError('Published limits differ from the preflight operator limits')
    if actual.get('software') != {name:source_hash(name) for name in HEALTH_FILES}:
        raise ValueError('Runtime source inventory differs from the full expected Tank build')


def deploy():
    current=health()
    require_inert(current)
    before = read_policy()
    expected = preflight(current, configuration_bytes(before))
    out=DATA/'validation/recording-r2/staging';build(DATA,out)
    ssh('mkdir','-p',HOST_STAGE);docker('mkdir','-p',STAGE)
    for source,name in ((out/'tank-staging.tar','bundle.tar'),(ROOT/'scripts/install_tank_bundle.py','installer.py')):
        subprocess.run(['scp','-q',str(source),'tank:'+HOST_STAGE+'/'+name],check=True,timeout=30)
        ssh('docker','cp',HOST_STAGE+'/'+name,'MentorPi:'+STAGE+'/'+name)
    docker('tar','-xf',STAGE+'/bundle.tar','-C',STAGE)
    stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
    host_helper='/home/pi/explorer3/control/handoff.py'
    host_backup=host_helper+'.before-recording-'+stamp
    ssh('sudo','-n','cp','-p',host_helper,host_backup)
    archive=None
    original_services={unit:ssh('systemctl','show',unit,'-p','ActiveState','--value').strip()=='active' for unit in SERVICES}
    report={'created_at':time.time(),'services_before':original_services,'host_backup':host_backup,'physical_commands':0,'preflight':expected}
    try:
        # Recheck immediately before changing code; no /session, /command or handoff call.
        current=health()
        if read_policy() != before or preflight(current, configuration_bytes(before)) != expected:
            raise ValueError('Onboard operator state changed before installation')
        installed=json.loads(docker('python3',STAGE+'/installer.py','--stage',STAGE))
        archive=installed['archive'];report['archive']=archive
        ssh('docker','cp','MentorPi:'+STAGE+'/payload/handoff.py',HOST_STAGE+'/handoff.py')
        ssh('sudo','-n','install','-m','755',HOST_STAGE+'/handoff.py',host_helper)
        for unit in SERVICES:
            if original_services[unit]:ssh('sudo','-n','systemctl','restart',unit)
        deadline=time.monotonic()+20;actual=None
        while time.monotonic()<deadline and actual is None:
            try:actual=health()
            except Exception:time.sleep(.5)
        if actual is None:raise RuntimeError('Updated agent did not become healthy')
        verify_installation(actual, expected, before, read_policy())
        remote=ssh('sha256sum',host_helper).split()[0]
        if remote!=hashlib.sha256((ROOT/'agents/tank/handoff.py').read_bytes()).hexdigest():raise RuntimeError('Host helper hash mismatch')
        report.update(status='installed_verified_inert',health=actual)
    except Exception as exc:
        report.update(status='failed',error=str(exc))
        if archive:
            docker('python3',STAGE+'/installer.py','--rollback',archive)
            ssh('sudo','-n','cp','-p',host_backup,host_helper)
            for unit in SERVICES:
                if original_services[unit]:ssh('sudo','-n','systemctl','restart',unit)
            report['status']='rolled_back'
        (DATA/'validation/recording-r2/deployment.json').write_text(json.dumps(report,indent=2))
        raise
    (DATA/'validation/recording-r2/deployment.json').write_text(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--apply',action='store_true')
    action.add_argument('--preflight-health',type=Path, help='Offline checks using a saved GET /health JSON')
    stored=parser.add_mutually_exclusive_group()
    stored.add_argument('--limits-file',type=Path, help='Exact file captured on the robot')
    stored.add_argument('--no-limits-file',action='store_true', help='The operator configuration was verified absent')
    args=parser.parse_args()
    if args.preflight_health:
        if not args.limits_file and not args.no_limits_file:
            parser.error('Supply the saved --limits-file or verified --no-limits-file')
        status=json.loads(args.preflight_health.read_bytes())
        try:
            result=preflight(status.get('health',status),args.limits_file.read_bytes() if args.limits_file else None)
        except (ValueError, TypeError) as error:
            parser.exit(2, 'Offline preflight refused: '+str(error)+'\n')
        print(json.dumps(result,indent=2))
    else:
        if args.limits_file or args.no_limits_file:
            parser.error('--apply reads and preserves operator settings from the robot')
        report=deploy()
        print(json.dumps({k:report[k] for k in ('status','archive','host_backup','physical_commands')},indent=2))
