"""Fit a bounded grasp correction in MuJoCo and evaluate the frozen policy on matched starts."""

import argparse
from concurrent.futures import ProcessPoolExecutor
import fcntl
import hashlib
from itertools import product
import json
import sys
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from scipy.stats import binomtest

from explorer4.grasp_measured import TRIAL_TICKS, next_target
from explorer4.grasp_residual import corrected_plan
from scripts.grasp_study import admission_native as base
from scripts.grasp_study.admission_native_v3 import OUT as OLD
from scripts.grasp_study.coverage_design import frozen, read
from scripts.grasp_study.residual_inputs import OUT

CANDIDATES = list(product((0, -4, 4), (0, -1, 1)))
NAMES = ("retained", "strict", "joint_success")


class ResidualActions(base.SimulatedActions):
    def plan_for_xy(self, xy):
        return corrected_plan(self, xy, *self.correction)


def worker_init():
    global env, policy, settings
    cv2.setNumThreads(1)
    sys.path[:0] = [str(base.ROOT / "agents/rosmaster"), str(base.NATIVE)]
    # Pure vendor control methods use simulated feedback and an inert output.
    from types import SimpleNamespace
    sys.modules['serial'] = SimpleNamespace()
    env = base.environment()
    policy = ResidualActions(None, base.SOURCE, base.VISION, "rbf", None, localizer=True)
    with base.REFERENCE.open() as stream:
        settings = json.loads(next(stream))["control_limits"]["arm_settings"]


def rollout(row, rgb, correction):
    initial, _ = base.observe(env, row['seed'], render=False)
    if initial != row["initial"] or base.sha_array(env.snapshot()["physics"]) != row['look_physics_sha256']:
        raise ValueError("Initial simulation state changed")
    policy.reset()
    policy.correction = correction
    policy.calibration = row['camera']
    observation = base.make_observation(row, rgb)
    executor = base.mock_executor(env, settings)
    metrics = base.GraspMetrics(env, initial['cube'][2])
    cube_id = metrics.cube
    sides = metrics.jaw_side
    carry_ticks = strict_ticks = 0
    final = {}
    target = None
    reason = "field_sequence_complete"
    actions = hashlib.sha256()
    count = 0
    for tick in range(TRIAL_TICKS):
        try:
            target = next_target(policy, observation, tick, target)
            now = env.steps*env.dt
            executor.direct = (now, executor.validate_direct({'arm':target}))
            executor.direct_step(env.dt, now)
        except (ValueError, RuntimeError) as exc:
            reason = "native_or_policy_stop: " + str(exc)
            break
        native = executor.io.arm_command()
        actions.update(np.ascontiguousarray(native,dtype="<f8").tobytes())
        ob, _, done, timeout, info = env.step(native)
        count += 1
        jaws = set()
        for contact in env.data.contact:
            a,b = env.model.geom_bodyid[[contact.geom1,contact.geom2]]
            jaw = b if a == cube_id else a if b == cube_id else None
            if jaw in sides and contact.dist <= 0:
                jaws.add(sides[jaw])
        cube = env.data.body('task_cube').xpos
        height = float(cube[2] - env.object_half()[2])
        carried = height > 0.050 and info['in_carry_pose']
        carry_ticks = carry_ticks + 1 if carried and len(jaws)==2 else 0
        strict_ticks = strict_ticks + 1 if carried and info['held'] else 0
        if tick >= TRIAL_TICKS-20:
            for k,val in {'height_mm':height*1000, 'jaw_deg':float(ob['state'][5]),
                          'tip_distance_mm':float(1000*np.linalg.norm(env.data.site('gripperframe').xpos-cube))}.items():
                bounds=final.setdefault(k,[val,val])
                bounds[0],bounds[1]=min(bounds[0],val),max(bounds[1],val)
        if timeout or (done and info['termination_reason'] != 'held_in_carry_pose'):
            reason=info['termination_reason']
            break
    retained = count==TRIAL_TICKS and carry_ticks>=20
    strict = count==TRIAL_TICKS and strict_ticks>=20 and bool(info['success'])
    return dict(retained=retained,strict=strict,joint_success=retained and strict,executed_ticks=count,
                terminal_bilateral_carry_s=carry_ticks*env.dt,terminal_strict_carry_s=strict_ticks*env.dt,
                reason=reason,last_second_ranges=final,command_sha256=actions.hexdigest())


def evaluate(task):
    group, seed, correction, version = task
    source = OLD if group == 'diagnosis' else OUT/group
    entry = read(source/'candidates'/f'{seed}.json')
    row = entry['row']
    if entry['row_sha256'] != base.digest(row) or entry['protocol_sha256'] != base.file_hash(source/'protocol.json'):
        raise ValueError("Candidate identity changed")
    rgb = cv2.imread(str(source/'frames'/f'{seed}.png'))[:,:,::-1].copy()
    if base.sha_array(rgb) != row['rgb_sha256']:
        raise ValueError("Starting RGB changed")
    radial, roll = correction
    receipt = OUT / group / 'rollouts' / f'{seed}_{radial}_{roll}.json'
    identity = dict(seed=seed,correction=list(correction),source_sha256=version,
                    initial_sha256=row['look_physics_sha256'],rgb_sha256=row['rgb_sha256'])
    if receipt.exists():
        result = read(receipt)
        if any(result[k]!=v for k,v in identity.items()):
            raise ValueError("Rollout receipt differs from requested trial")
        return result
    row = {**identity,**rollout(row,rgb,correction)}
    if group == 'diagnosis' and correction==(0,0):
        original=read(OLD/'trials'/f'{seed}.json')['trial']
        if (row['strict']!=original['terminal_success'] or row['command_sha256']!=original['native_action_sha256']):
            raise ValueError("Base policy diverged from the archived native run")
    frozen(receipt,row)
    return row


def paired(results, baseline, candidate):
    old = {r['seed']:r for r in results if r['correction']==list(baseline)}
    new = {r['seed']:r for r in results if r['correction']==list(candidate)}
    if old.keys()!=new.keys():
        raise ValueError("Unmatched seed lists")
    counts={}
    for key in NAMES:
        gains = [s for s in old if new[s][key] and not old[s][key]]
        losses = [s for s in old if old[s][key] and not new[s][key]]
        counts[key] = dict(base=sum(r[key] for r in old.values()), fitted=sum(r[key] for r in new.values()),
                           gains=gains,losses=losses,
                           paired_exact_p=float(binomtest(len(gains),len(gains)+len(losses)).pvalue) if gains or losses else 1.)
    return dict(n=len(old),scores=counts,stops={str(k):sum(r['reason'].startswith("native_or_policy_stop") for r in results if r['correction']==list(k)) for k in (baseline,candidate)})


def study(workers):
    source_files = [Path(__file__), base.ROOT/'explorer4/grasp_residual.py', *[base.ROOT/n for n in base.SOURCE_FILES]]
    source_hashes = {str(p.relative_to(base.ROOT)):base.file_hash(p) for p in source_files}
    version = base.digest(source_hashes)
    frozen(OUT/'motor-protocol.json',dict(design_sha256=base.file_hash(OUT/'design.json'),implementation=source_hashes,
           independent_contact="Each final 20 Hz sample needs nonpositive contact distance between cube and each jaw's own link, original carry, and >50 mm height above support. Score retained, original strict and intersection separately.",
           rank="Maximum retained, then intersection, then minimum absolute normalized correction. Exact remaining ties follow registered candidate order.", candidates=[list(c) for c in CANDIDATES]))
    allocated=read(OUT/'train/selection.json')['selected']
    if len(allocated)!=16:
        raise ValueError("Insufficient preselected training starts")
    with ProcessPoolExecutor(workers,initializer=worker_init) as pool:
        def run(group,seeds,corrections):
            return list(pool.map(evaluate,((group,s,c,version) for s in seeds for c in corrections)))
        rows=run('train',allocated,CANDIDATES)
        scores=[]
        for c in CANDIDATES:
            outcomes=[r for r in rows if r['correction']==list(c)]
            scores.append(dict(correction=list(c),**{k:sum(r[k] for r in outcomes) for k in NAMES}))
        best=max(scores,key=lambda s:(s["retained"],s["joint_success"],-abs(s["correction"][0])/4-abs(s["correction"][1])))
        correction=tuple(best['correction'])
        frozen(OUT/'fit.json',dict(parameters=best,candidates=scores,training_seeds=allocated,source_sha256=version,
                                  training_rollout_sha256=base.digest(rows),motor_protocol_sha256=base.file_hash(OUT/'motor-protocol.json')))
        print('Fit frozen',best,flush=True)
        arms=list(dict.fromkeys([(0,0),correction]))
        original=run('diagnosis',read(OLD/'selection.json')['selected'],arms)
        held=read(OUT/'confirmation/selection.json')
        confirmation=run('confirmation',held['selected'],arms)
    result=dict(domain="MuJoCo",physical_trials=0,fit_sha256=base.file_hash(OUT/'fit.json'),
                source_sha256=source_hashes,training=scores,parameters=best['correction'],
                original_20=paired(original,(0,0),correction),fresh=paired(confirmation,(0,0),correction),
                fresh_screen=held,original_trials=original,fresh_trials=confirmation)
    frozen(OUT/'result.json',result)
    print(json.dumps({k:result[k] for k in ('parameters','original_20','fresh')}),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers',type=int,choices=range(1,7),default=4)
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'.fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        study(args.workers)
