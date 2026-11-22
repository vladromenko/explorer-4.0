"""Fit conditional joint trajectories to existing demonstrations and replay them in MuJoCo."""
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import RBFInterpolator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from explorer4.paths import DATA
from scripts import recorded_start_visual_pick as visual

ROOT = DATA / 'runs/article-closeout-20261122/learned-trajectories'
PUBLIC = DATA / 'simlab/reports/article-20261122'
SOURCE = 'a3487bcecce548a3869bde3bb16e2a1d'
VISION = 'a2967027c4a87e7d91f819aee9a15d581a2d80630ee80d9b53ea145bec4d08d8'
SIZES = [5, 11, 20, 32]
ARMS = [f'rgb_{n}' for n in SIZES] + ['mean_32', 'rgb_ik']
HORIZON = 220


def read(path):
    return json.loads(path.read_text())


def prepare():
    ROOT.mkdir(parents=True, exist_ok=True)
    split = read(DATA / 'jobs' / SOURCE / 'split.json')
    examples = sorted(split['train'], key=lambda row: row['id'])
    order = np.random.default_rng(1000).permutation(len(examples))
    examples = [examples[i] for i in order]
    expected_counts = [32, 4, 4]
    if [len(split[part]) for part in ('train', 'validation', 'test')] != expected_counts:
        raise ValueError('Unexpected original split')
    if set(row['id'] for row in examples) & {r['id'] for role in ('validation','test') for r in split[role]}:
        raise ValueError('Overlapping split')
    protocol = dict(source=SOURCE, train_ids=[r['id'] for r in examples], nested_sizes=SIZES,
                    heldout_seeds=list(range(926000,926060)), physics=visual.PROTOCOL['physics'],
                    vision_sha256=VISION, arms=ARMS, control_horizon=HORIZON,
                    method='SciPy thin-plate spline, linear polynomial, smoothing 0.005 after XY scaling by 0.05 m. Predict all six action channels over time. Last command held; 45/120 deg/s command slew.',
                    vision='Frozen ResNet-18 trained earlier on 1024 separately labelled simulated images. Mean control uses the mean XY of the 32 training scenes.',
                    scope='Simulated motor demonstration budget, one nested order, frozen shared perception; no physical demonstration saving inferred.')
    path = ROOT / 'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('Protocol changed')
    visual.save_json(path, protocol)
    env = visual.make_env()
    xy, action = [], []
    try:
        for row in examples:
            p = Path(row['dataset'])
            hardware = read(p/'provenance.json')['hardware']
            obs, _ = env.reset(seed=hardware['seed'])
            records = [json.loads(line) for line in (p/'research.jsonl').read_text().splitlines()]
            if len(records)!=row['frames'] or not np.allclose(obs['state'],records[0]['observation.state'],atol=1e-4):
                raise ValueError('Inconsistent demonstration')
            sequence = np.array([r['action'] for r in records])
            action.append(sequence[np.minimum(np.arange(HORIZON),len(sequence)-1)])
            xy.append(env.data.body('task_cube').xpos[:2].copy())
    finally:
        env.close()
    path = ROOT/'motor.npz'
    if path.exists():
        with np.load(path) as old:
            if not np.array_equal(old['xy'],xy) or not np.array_equal(old['action'],action):
                raise ValueError('Changed motor targets')
    else:
        np.savez(path, xy=xy,action=action)
    return protocol


def execute(env, trajectory):
    current = env.observation()['state'].astype(float)
    step_limit = np.array([45]*5+[120])*env.dt
    step = 0
    while True:
        target = trajectory[min(step,len(trajectory)-1)]
        current += np.clip(target-current,-step_limit,step_limit)
        _,_,done,timeout,info = env.step(current)
        if done or timeout:
            return dict(outcome=info['outcome'],reason=info['termination_reason'],steps=env.steps)
        step += 1


def run(protocol):
    import torch
    torch.set_num_threads(1)
    net = visual.build_model(False).eval()
    if visual.digest(visual.RUN/'weights.pt') != VISION:
        raise ValueError('Different visual model')
    net.load_state_dict(torch.load(visual.RUN/'weights.pt', map_location='cpu',weights_only=True))
    with np.load(ROOT/'motor.npz') as bundle:
        xy, action = bundle['xy'], bundle['action']
    models = {n:RBFInterpolator(xy[:n]/.05,action[:n],smoothing=.005,kernel='thin_plate_spline') for n in SIZES}
    motor_sha = visual.digest(ROOT/'motor.npz')
    env = visual.make_env()
    try:
        for seed in protocol['heldout_seeds']:
            path = ROOT/f'{seed}.json'
            if path.is_file():
                row = read(path)
                if row['motor_sha256']!=motor_sha or row['vision_sha256']!=VISION or list(row['arms'])!=ARMS:
                    raise ValueError('Inconsistent saved trial')
                continue
            results = {}
            rgb = visual.observe(env,seed)
            snapshot = env.snapshot()
            pixels = hashlib.sha256(rgb.tobytes()).hexdigest()
            with torch.inference_mode():
                pred = net(visual.normalize(torch.from_numpy(rgb[None]),'cpu'))[0].numpy()*visual.SCALE+visual.CENTER
            truth = env.data.body('task_cube').xpos[:2].copy()
            for arm in ARMS:
                env.restore(snapshot)
                if not np.array_equal(env.snapshot()['physics'],snapshot['physics']):
                    raise ValueError('Paired physics state changed')
                if arm=='rgb_ik':
                    result = visual.execute(env,pred)
                else:
                    n = int(arm.split('_')[1])
                    goal = xy.mean(0) if arm=='mean_32' else pred
                    result = execute(env, models[n](goal[None]/.05)[0])
                results[arm] = result
            visual.save_json(path,dict(seed=seed,motor_sha256=motor_sha,vision_sha256=VISION,observed_frame_sha256=pixels,
                predicted_xy=pred.tolist(),cube_xy_for_scoring=truth.tolist(),arms=results))
            print(seed, [r['outcome'] for r in results.values()],flush=True)
    finally:
        env.close()


def report(protocol):
    from scipy.stats import binomtest
    rows = [read(ROOT/f'{s}.json') for s in protocol['heldout_seeds']]
    wins = {arm:sum(r['arms'][arm]['outcome']=='success' for r in rows) for arm in ARMS}
    a,b = 'rgb_32','mean_32'
    def gained(x,y):
        return sum(r['arms'][x]['outcome']=='success' and r['arms'][y]['outcome']!='success' for r in rows)
    gain, loss = gained(a,b), gained(b,a)
    summary = dict(protocol=protocol,weights_sha256=visual.digest(ROOT/'motor.npz'),successes=wins,total=len(rows),
        paired_rgb32_vs_mean32=dict(gains=gain,losses=loss,exact_p=binomtest(gain,gain+loss).pvalue if gain+loss else 1.),
        rows=rows)
    visual.save_json(PUBLIC/'learned-motor-results.json',summary)
    path = PUBLIC/'learned-motor-scenes.csv'
    with path.open('w') as stream:
        writer = csv.writer(stream);writer.writerow(['seed',*ARMS])
        for row in rows:
            writer.writerow([row['seed'],*(row['arms'][a]['outcome'] for a in ARMS)])
    print(wins, flush=True)


if __name__=='__main__':
    protocol=prepare()
    run(protocol)
    report(protocol)
