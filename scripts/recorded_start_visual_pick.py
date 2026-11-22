"""Fit a torchvision ResNet-18 to simulated cube XY and test the learned target in MuJoCo."""
import argparse
import csv
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from explorer4.paths import DATA

PROFILE = 'rosmaster_floor_pick_recorded_start_sim'
RUN = DATA / 'runs/recorded-start-cube-20261121/night/visual-pick-v1'
PUBLIC = DATA / 'simlab/reports/recorded-start-night'
PROTOCOL = dict(profile=PROFILE, physics='0e44d9f93c8dd4b9a6452e009097b205209f509ebe0653dc78a339783e5925dc',
                training=[921000, 922023], validation=[923000, 923127], paired=[88500, 88519],
                fresh=[924000, 924019], seed=1000, image_hw=[120, 160],
                view_servo=[90,57,24,0,75,30], view_steps=20, epochs=30, batch=32,
                pretrained='torchvision ResNet18_Weights.IMAGENET1K_V1', selection='lowest validation mean XY error',
                controls=['predicted_xy', 'training_mean_xy'], labels='XY in metres at observation, simulated training and scoring only',
                task='Single RGB frame after commanded look pose; predict metric XY; vendor IK and fixed grasp sequence')
CENTER = np.array([.21, 0.], dtype=np.float32)
SCALE = .05


def seeds(split):
    first, last = PROTOCOL[split]
    return range(first, last + 1)


def save_json(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    tmp.replace(path)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def make_env():
    from explorer4.sim.factory import make
    env = make(PROFILE, images=False)
    if env.manifest['xml_sha256'] != PROTOCOL['physics']:
        raise ValueError('Simulator revision differs')
    return env


def observe(env, seed, trace=None):
    import cv2
    env.reset(seed=seed)
    if trace is not None:
        trace.append(env.data.qpos.tolist())
    for _ in range(PROTOCOL['view_steps']):
        _, _, done, timeout, _ = env.step(PROTOCOL['view_servo'])
        if trace is not None:
            trace.append(env.data.qpos.tolist())
        if done or timeout:
            raise RuntimeError('Unexpected end during camera positioning')
    h, w = PROTOCOL['image_hw']
    return cv2.resize(env.render(), (w,h), interpolation=cv2.INTER_AREA)


def capture():
    env = make_env()
    try:
        for split in ('training','validation'):
            folder = RUN / split
            folder.mkdir(exist_ok=True)
            # Chunked writes preserve completed simulator work on restart.
            group = list(seeds(split))
            for start in range(0,len(group),32):
                ids = group[start:start+32]
                path = folder / f'{ids[0]}.npz'
                if path.exists():
                    continue
                rgb, xy = [], []
                for seed in ids:
                    rgb.append(observe(env,seed))
                    xy.append(env.data.body('task_cube').xpos[:2].copy())
                tmp = path.with_suffix('.tmp.npz')
                np.savez(tmp, seeds=ids, rgb=rgb, xy=np.array(xy,dtype=np.float32))
                tmp.replace(path)
                print(split,ids[-1], flush=True)
    finally:
        env.close()


def load_data(split):
    import torch
    images, labels, ids = [], [], []
    for path in sorted((RUN/split).glob('*.npz')):
        with np.load(path) as data:
            ids.extend(data['seeds'].tolist())
            images.append(torch.from_numpy(data['rgb']))
            labels.append(torch.from_numpy((data['xy'] - CENTER) / SCALE))
    if ids != list(seeds(split)):
        raise ValueError('Incomplete split: '+split)
    return torch.cat(images), torch.cat(labels)


def build_model(pretrained):
    from torch import nn
    from torchvision.models import resnet18, ResNet18_Weights
    resnet = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1 if pretrained else None)
    return nn.Sequential(resnet.conv1,resnet.bn1,resnet.relu,resnet.maxpool,resnet.layer1,resnet.layer2,
                         nn.Conv2d(128,16,1),nn.ReLU(),nn.AdaptiveAvgPool2d((8,10)),nn.Flatten(),
                         nn.Linear(1280,128),nn.ReLU(),nn.Linear(128,2))


def normalize(images, device):
    import torch
    x = images.to(device).permute(0,3,1,2).float().div_(255)
    mean = torch.as_tensor([.485,.456,.406],device=device)[None,:,None,None]
    std = torch.as_tensor([.229,.224,.225],device=device)[None,:,None,None]
    return (x-mean)/std


def train():
    import torch
    import torchvision
    import transformers
    from transformers import Trainer, TrainingArguments
    from transformers.trainer_utils import get_last_checkpoint

    class SceneDataset(torch.utils.data.Dataset):
        def __init__(self, split):
            self.images, self.labels = load_data(split)

        def __len__(self):
            return len(self.labels)

        def __getitem__(self, idx):
            return dict(images=self.images[idx], labels=self.labels[idx])

    class LocalizationModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.network = build_model(True)

        def forward(self, images, labels=None):
            logits = self.network(normalize(images, images.device))
            loss = torch.nn.functional.smooth_l1_loss(logits, labels, beta=.12) if labels is not None else None
            return dict(loss=loss, logits=logits)

    def metrics(result):
        cm = np.linalg.norm(result.predictions-result.label_ids,axis=1)*SCALE*100
        return dict(mean_cm=float(cm.mean()),median_cm=float(np.median(cm)))

    torch.set_num_threads(2)
    transformers.set_seed(PROTOCOL['seed'])
    training = SceneDataset('training')
    model = LocalizationModel()
    optimizer = torch.optim.AdamW([dict(params=model.network[:6].parameters(),lr=.00015),
                                   dict(params=model.network[6:].parameters(),lr=.001)],weight_decay=.0001)
    folder = RUN/'trainer'
    folder.mkdir(exist_ok=True)
    args = TrainingArguments(output_dir=str(folder), num_train_epochs=PROTOCOL['epochs'],
                             per_device_train_batch_size=PROTOCOL['batch'], per_device_eval_batch_size=32,
                             seed=PROTOCOL['seed'], data_seed=PROTOCOL['seed'], lr_scheduler_type='constant',
                             eval_strategy='epoch', save_strategy='epoch', logging_strategy='epoch',
                             load_best_model_at_end=True, metric_for_best_model='mean_cm', greater_is_better=False,
                             save_total_limit=2, report_to='none', disable_tqdm=True)
    trainer = Trainer(model=model,args=args,train_dataset=training,eval_dataset=SceneDataset('validation'),
                      compute_metrics=metrics,optimizers=(optimizer,None))
    trainer.train(resume_from_checkpoint=get_last_checkpoint(str(folder)))
    torch.save(model.network.state_dict(),RUN/'weights.tmp')
    (RUN/'weights.tmp').replace(RUN/'weights.pt')
    base = Path(torch.hub.get_dir())/'checkpoints/resnet18-f37072fd.pth'
    log = [dict(epoch=row['epoch'],mean_cm=row['eval_mean_cm'],median_cm=row['eval_median_cm'])
           for row in trainer.state.log_history if 'eval_mean_cm' in row]
    save_json(RUN/'fit.json',dict(epochs=log,mean_xy=(training.labels.mean(0).numpy()*SCALE+CENTER).tolist(),
              trainer='transformers.Trainer',transformers=transformers.__version__,torch=str(torch.__version__),
              torchvision=str(torchvision.__version__),selected_checkpoint=trainer.state.best_model_checkpoint,
              base_weights_sha256=digest(base),weights_sha256=digest(RUN/'weights.pt')))


def execute(env, xy, trace=None):
    from explorer4.sim.vendor_rosmaster.arm_model import ArmModel
    arm = ArmModel(tcp_offset=float(env.model.site('gripperframe').pos[2]))
    command = env.observation()['state'].astype(float).copy()
    # Same offsets, stage durations, joint rate limits and carry posture as the fixed-cube expert.
    origin = env.elapsed
    stages = [(2.5,.10,30), (4.5,.004,30), (6.5,.004,150), (8.,.12,150), (float('inf'),None,150)]
    step_limit = np.array([45]*5+[120])*env.dt
    for end, offset, grip in stages:
        if offset is None:
            target = np.array([*env.cfg['carry_pose'],grip])
        else:
            solution,_ = arm.grasp_ik([*xy,.018+offset],env.observation()['state'])
            if solution is None:
                return dict(outcome='failure',reason='unreachable_target',steps=env.steps)
            target = np.r_[solution,grip]
        while env.elapsed - origin < end:
            command += np.clip(target-command,-step_limit,step_limit)
            _, _, done, timeout, info = env.step(command)
            if trace is not None:
                trace.append(env.data.qpos.tolist())
            if done or timeout:
                return dict(outcome=info['outcome'],reason=info['termination_reason'],steps=env.steps)
    raise RuntimeError('Missing episode outcome')


def evaluate():
    import torch
    torch.set_num_threads(2)
    fit = json.loads((RUN/'fit.json').read_text())
    if digest(RUN/'weights.pt') != fit['weights_sha256']:
        raise ValueError('Unexpected checkpoint')
    model = build_model(False).eval()
    model.load_state_dict(torch.load(RUN/'weights.pt',map_location='cpu',weights_only=True))
    env = make_env()
    try:
        historical = list(range(88300,88320))
        supplement = dict(seeds=historical,weights_sha256=fit['weights_sha256'],
                          purpose='Replay original pre/post ACT scenes using fixed visual weights')
        supplement_path = RUN/'historical-replay-plan.json'
        if supplement_path.exists() and json.loads(supplement_path.read_text()) != supplement:
            raise ValueError('Historical replay plan differs')
        save_json(supplement_path,supplement)
        blocks = dict(paired=seeds('paired'),fresh=seeds('fresh'),historical=historical)
        trials = []
        for block, scene_seeds in blocks.items():
            for seed in scene_seeds:
                for method in PROTOCOL['controls']:
                    path = RUN / f'{block}-{seed}-{method}.json'
                    if path.exists():
                        saved = json.loads(path.read_text())
                        if saved['weights_sha256'] != fit['weights_sha256']:
                            raise ValueError('Saved trial belongs to another checkpoint')
                        trials.append(saved)
                        continue
                    trace = [] if seed == seeds('fresh').start and method == 'predicted_xy' else None
                    rgb = observe(env,seed,trace)
                    if method == 'predicted_xy':
                        with torch.inference_mode():
                            output = model(normalize(torch.from_numpy(rgb[None]),'cpu'))
                        xy = output[0].numpy()*SCALE + CENTER
                    else:
                        xy = np.asarray(fit['mean_xy'])
                    # Ground truth is collected solely for the error metric. The controller receives xy.
                    truth = env.data.body('task_cube').xpos[:2].copy()
                    row = dict(block=block,seed=seed,method=method, predicted_xy=xy.tolist(),
                               weights_sha256=fit['weights_sha256'],
                               localization_error_cm=float(100*np.linalg.norm(xy-truth)), **execute(env,xy,trace))
                    if trace is not None:
                        save_json(RUN/'first-fresh-trace.json',dict(profile=PROFILE,seed=seed,fps=env.fps,
                            model=PROTOCOL['physics'],outcome=row['outcome'],qpos=trace,
                            checkpoint_sha256=fit['weights_sha256']))
                    save_json(path,row)
                    trials.append(row)
                    print(block,seed,method,row['outcome'],flush=True)
        groups = {}
        for block in blocks:
            groups[block] = {}
            for method in PROTOCOL['controls']:
                rows = [t for t in trials if t['block']==block and t['method']==method]
                groups[block][method] = dict(successes=sum(t['outcome']=='success' for t in rows),total=len(rows),
                       median_error_cm=float(np.median([t['localization_error_cm'] for t in rows])))
        report = dict(protocol=PROTOCOL,historical_replay=supplement,fit=fit,groups=groups,trials=trials,
                      script_sha256=digest(Path(__file__)),
                      simulator_inputs_for_policy=['front RGB after fixed observation motion'],
                      motion_controller_inputs=['estimated XY', 'joint positions', 'fixed cube size', 'elapsed time'])
        save_json(RUN/'result.json',report)
        save_json(PUBLIC/'visual-pick-v1.json',report)
    finally:
        env.close()


def publish():
    result = json.loads((RUN/'result.json').read_text())
    expected_weights = digest(RUN/'weights.pt')
    grouped = {}
    for t in result['trials']:
        row = grouped.setdefault(t['seed'], dict(block=t['block'],seed=t['seed']))
        if t['method'] in row or t['weights_sha256'] != expected_weights:
            raise ValueError('Duplicate trial or different weights')
        row[t['method']] = t['outcome']
    original = json.loads((RUN.parent/'control-comparison.json').read_text())
    if original['model_hash'] != PROTOCOL['physics'] or original['seeds'] != result['historical_replay']['seeds']:
        raise ValueError('Historical reference differs')
    for trial in original['paired_trials']:
        for source in ('before','after','control'):
            grouped[trial['seed']]['act_'+source] = trial[source]
    sources = []
    for variant in ('100','25','diffusion'):
        path = PUBLIC/f'improvement-confirmation-{variant}-trials.json'
        ref = json.loads(path.read_text())
        if (ref['status'] != 'completed' or ref['model']['xml_sha256'] != PROTOCOL['physics']
            or [t['seed'] for t in ref['trials']] != list(seeds('paired'))):
            raise ValueError('Invalid comparison: '+variant)
        for trial in ref['trials']:
            name = 'diffusion' if variant == 'diffusion' else 'act_'+variant
            grouped[trial['seed']][name] = trial['outcome']
        sources.append(path)
    table = RUN/'paired-scenes.csv'
    with table.open('w',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=['block','seed','predicted_xy','training_mean_xy',
            'act_before','act_after','act_control','act_100','act_25','diffusion'])
        writer.writeheader()
        writer.writerows(grouped[seed] for seed in sorted(grouped))
    (PUBLIC/'visual-pick-scenes.csv').write_bytes(table.read_bytes())
    archive = PUBLIC/'visual-pick-evidence.zip'
    tmp = archive.with_suffix('.tmp')
    with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in [Path(__file__),RUN/'weights.pt',RUN/'protocol.json',RUN/'historical-replay-plan.json',
                     RUN/'fit.json',RUN/'result.json',
                     RUN.parent/'control-comparison.json',table,*sources]:
            bundle.write(path,path.name)
        for path in [RUN/'trainer.log',RUN/'framing.json']:
            if path.is_file():
                bundle.write(path,path.name)
    tmp.replace(archive)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['capture','train','evaluate','publish'])
    stage = parser.parse_args().stage
    RUN.mkdir(parents=True,exist_ok=True)
    protocol_path = RUN/'protocol.json'
    if protocol_path.exists() and json.loads(protocol_path.read_text()) != PROTOCOL:
        raise RuntimeError('Frozen protocol changed')
    if not protocol_path.exists():
        save_json(protocol_path,PROTOCOL)
    {'capture':capture,'train':train,'evaluate':evaluate,'publish':publish}[stage]()
