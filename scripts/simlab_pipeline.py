"""Run the existing SimLab trainer, frozen evaluation and videos with one compute lease."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from explorer4.paths import DATA, offline_environment  # noqa: E402

TITLES = {'check':'проверочный прогон','full':'полное обучение','clone':'клонирование учителя','eval':'оценка и видео'}
PROFILES = {'tank':'tank_dock_sim','rosmaster':'rosmaster_dock_sim','so101':'so101_pick_place_sim'}


def selection(robot,kind,policy=None):
    """Validate the managed recipe and freeze the selected evaluation input."""
    if not isinstance(robot,str) or robot not in PROFILES or not isinstance(kind,str) or kind not in TITLES:
        raise ValueError('Неизвестная машина или действие SimLab')
    allowed = {'clone','eval'} if robot=='so101' else {'check','full','eval'}
    if kind not in allowed:
        raise ValueError('Такая задача не поддерживается для этой машины')
    if kind!='eval':
        if policy is not None:
            raise ValueError('Входная политика применяется при оценке')
        return {}
    if not isinstance(policy,(str,Path)) or not str(policy):
        raise ValueError('Для оценки выберите сохранённую политику SimLab')
    base=(DATA/'simlab/policies').resolve()
    folder=Path(policy).resolve()
    if folder.parent!=base or not folder.is_dir():
        raise ValueError('Политика должна быть каталогом в SimLab')
    for filename in ('policy.json','policy.npz'):
        if not (folder/filename).is_file() or (folder/filename).resolve().parent!=folder:
            raise ValueError('Отсутствует файл политики SimLab')
    from explorer4.simlab.artifact import Policy
    artifact=Policy(folder)
    if artifact.robot!=robot:
        raise ValueError('Политика относится к другой машине')
    for output in (folder/'videos',folder/'eval-0.5.json',folder/'eval-1.0.json'):
        if output.is_symlink():
            raise ValueError('Результаты оценки должны находиться в каталоге политики')
    return {'policy':str(folder),'weights_sha256':artifact.info['weights_sha256'],
            'policy_manifest_sha256':hashlib.sha256((folder/'policy.json').read_bytes()).hexdigest()}


def step(title,args,python):
    print(json.dumps({'stage':title,'at':time.time()},ensure_ascii=False),flush=True)
    subprocess.run([str(python),'-u',*args],cwd=ROOT,env={**offline_environment(),'PYTHONPATH':str(ROOT),'MUJOCO_GL':'egl'},check=True)


def run_pipeline(robot,kind,name,*,policy=None,log=None,job_id=None,python=sys.executable):
    """The caller owns compute for the entire pipeline, including evaluation and encoding."""
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,120}',name):
        raise ValueError('Недопустимое имя результата SimLab')
    active=DATA/'simlab/active.json'
    active.parent.mkdir(parents=True,exist_ok=True)
    current={'pid':os.getpid(),'robot':robot,'kind':kind,'name':name,'log':str(log) if log else None,
             'started':time.time(),'job_id':job_id}
    temporary=active.with_suffix('.tmp')
    temporary.write_text(json.dumps(current,ensure_ascii=False))
    temporary.replace(active)
    folder=Path(policy) if policy else DATA/'simlab/policies'/name
    try:
        if kind in ('check','full'):
            minutes='10' if kind=='check' else '240'
            step('обучение',['scripts/simlab_train.py',robot,'--minutes',minutes,'--steps','4000000000','--name',name],python)
        elif kind=='clone':
            step('клонирование учителя и оценка',['scripts/simlab_arm_bc.py','--name',name],python)
        if robot!='so101':
            for curriculum in ('0.5','1.0'):
                step(f'оценка в MuJoCo (сложность {curriculum})',['scripts/simlab_eval.py',str(folder),'--curriculum',curriculum,'--episodes','100'],python)
        step('видео',['scripts/simlab_video.py',str(folder),'--episodes','4'],python)
        info=json.loads((folder/'policy.json').read_text())
        videos=folder/'videos/index.json'
        video_record=json.loads(videos.read_text())
        print(json.dumps({'stage':'готово','at':time.time()},ensure_ascii=False),flush=True)
        return {'simlab_action':kind,'robot':robot,'policy_dir':str(folder),'weights_sha256':info['weights_sha256'],
                'videos':video_record,'video_index':str(videos),'evaluations':[str(f) for f in sorted(folder.glob('eval*.json'))]}
    finally:
        try:
            if json.loads(active.read_text()).get('pid')==os.getpid():
                active.unlink()
        except (OSError,ValueError):
            pass


def run_managed(cfg,work):
    """Called from the Jobs worker which owns the exclusive compute lease."""
    from explorer4 import catalog
    with catalog.connect() as db:
        job=db.execute('SELECT config,status FROM jobs WHERE id=?',(work.name,)).fetchone()
    if not job or job['status']!='running' or json.loads(job['config'])!=cfg:
        raise ValueError('Запуск SimLab требует активного задания из очереди')
    # The parent owns the lock across all subprocesses. Confirm it without taking a second flock.
    lock=DATA/'locks/compute.lock'
    st=lock.stat()
    owner=lock.read_text().strip()
    key=f'{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}'
    held=any(line.split()[1:6]==['FLOCK','ADVISORY','WRITE',owner,key]
             for line in Path('/proc/locks').read_text().splitlines())
    if not held:
        raise RuntimeError('Воркер Jobs не удерживает вычислительный ресурс')
    selected=selection(cfg['robot'],cfg['simlab_action'],cfg.get('policy'))
    if any(cfg.get(key)!=selected.get(key) for key in ('weights_sha256','policy_manifest_sha256')):
        raise ValueError('Политика изменилась после постановки в очередь')
    name=f"{cfg['robot']}_{'bc' if cfg['robot']=='so101' else 'dock'}_{cfg['simlab_action']}_{work.name}"
    result=run_pipeline(cfg['robot'],cfg['simlab_action'],name,policy=selected.get('policy'),
                        log=DATA/'logs'/f'{work.name}.log',job_id=work.name,python=ROOT/'.venv-sim/bin/python')
    (work/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('robot',choices=list(PROFILES))
    parser.add_argument('kind',choices=list(TITLES))
    parser.add_argument('--policy')
    parser.add_argument('--name')
    parser.add_argument('--log')
    args=parser.parse_args()
    from explorer4.resources import ResourceLease
    stamp=time.strftime('%m%d_%H%M%S')
    name=args.name or (f'so101_bc_{stamp}' if args.robot=='so101' else f'{args.robot}_dock_{args.kind}_{stamp}')
    with ResourceLease('compute'):
        run_pipeline(args.robot,args.kind,name,policy=args.policy,log=args.log)


if __name__=='__main__':
    main()
