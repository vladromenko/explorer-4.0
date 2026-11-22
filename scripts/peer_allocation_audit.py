"""Post-hoc fixed-budget communication audit on committed, already observed scene outcomes."""
import argparse
import csv
import hashlib
import itertools
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import multivariate_hypergeom

EVIDENCE = Path(__file__).resolve().parents[1]/'docs/results/peer-camera-docking'
COSTS = (0., .10, .25, .50, 1.)
TIME_COST = .005


def archived_rows():
    cells=defaultdict(dict)
    with (EVIDENCE/'paired.csv').open() as stream:
        for record in csv.DictReader(stream):
            key=int(record['seed'])
            if record['method'] in cells[key]:
                raise ValueError('Repeated scene branch')
            cells[key][record['method']]=record
    v1={}
    for fallback in ('local_only','local_scan'):
        rows=[]
        for seed,methods in cells.items():
            local,peer=methods[fallback],methods['always']
            rows.append({'seed':seed,'room':local['room'],'layout':'open','local':int(local['success']),
                'peer':int(peer['success']),'local_s':float(local['terminal_time_s']),
                'peer_s':float(peer['terminal_time_s']),'ask':bool(int(methods['selective']['calls']))})
        v1['open_room_'+fallback]=rows
    development=json.loads((EVIDENCE/'screen-development.json').read_text())
    if development['phase']!='development_only' or development['test_outcomes_read']:
        raise ValueError('Only the published development block is admissible')
    v2=[]
    for row in development['rows']:
        # Layout is used only for post-hoc stratification. The rule sees only the local detector bit.
        v2.append({'seed':row['seed'],'room':row['room'],'layout':'screened' if row['seed']%2==0 else 'parked',
                   'local':row['local'],'peer':row['peer'],'local_s':row['local_time_s'],
                   'peer_s':row['peer_time_s'],'ask':row['x'][0]==0.})
    return {**v1,'screen_development_local_scan':v2}


def allocation_distribution(local,peer,calls):
    """All uniformly chosen subsets of a fixed size, with or without harmful calls."""
    diffs=peer-local
    populations=[int((diffs==i).sum()) for i in (1,-1,0)]
    possible=[]
    for gained,lost in itertools.product(range(min(calls,populations[0])+1),range(min(calls,populations[1])+1)):
        tied=calls-gained-lost
        if 0<=tied<=populations[2]:
            possible.append((gained,lost,tied))
    probabilities=np.atleast_1d(multivariate_hypergeom.pmf(possible,populations,calls))
    pmf=defaultdict(float)
    for (gained,lost,_),p in zip(possible,probabilities):
        pmf[int(local.sum())+gained-lost]+=float(p)
    if not np.isclose(sum(pmf.values()),1.):
        raise ValueError('Incomplete assignment distribution')
    return dict(sorted(pmf.items()))


def analyze(rows):
    n=len(rows)
    local=np.array([r['local'] for r in rows])
    peer=np.array([r['peer'] for r in rows])
    ask=np.array([r['ask'] for r in rows])
    local_s=np.array([r['local_s'] for r in rows])
    peer_s=np.array([r['peer_s'] for r in rows])
    selective=np.where(ask,peer,local)
    selective_s=np.where(ask,peer_s,local_s)
    calls=int(ask.sum())
    dist=allocation_distribution(local,peer,calls)
    expected_successes=sum(k*p for k,p in dist.items())
    expected_time=float(local_s.sum()+calls/n*(peer_s-local_s).sum())
    successes=int(selective.sum())
    time_extra=float((selective_s-local_s).sum())
    def utility(success,time,requested,cost):
        return (success-TIME_COST*time-cost*requested)/n
    cost_table=[]
    for cost in COSTS:
        cost_table.append({'cost_per_call':cost,'self':utility(int(local.sum()),float(local_s.sum()),0,cost),
            'always':utility(int(peer.sum()),float(peer_s.sum()),n,cost),
            'visibility_rule':utility(successes,float(selective_s.sum()),calls,cost),
            'uniform_mean':utility(expected_successes,expected_time,calls,cost)})
    def breakdown(name):
        groups=defaultdict(list)
        for row in rows:
            groups[row[name]].append(row)
        result={}
        for label,group in sorted(groups.items()):
            result[label]={'n':len(group),'local_successes':sum(r['local'] for r in group),
                           'peer_successes':sum(r['peer'] for r in group),
                           'rule_calls':sum(r['ask'] for r in group),
                           'rule_successes':sum(r['peer'] if r['ask'] else r['local'] for r in group)}
        return result
    return {'scenes':n,'calls':calls,'self_successes':int(local.sum()),'always_successes':int(peer.sum()),
            'rule_successes':successes,'onboard_only_scenes':int((~ask).sum()),
            'onboard_only_failures':int((1-local[~ask]).sum()),
            'requested_with_positive_endpoint_gain':int(((peer>local)&ask).sum()),
            'requested_with_zero_endpoint_gain':int(((peer==local)&ask).sum()),
            'requested_with_negative_endpoint_gain':int(((peer<local)&ask).sum()),
            'uniform_expected_successes':expected_successes,'uniform_success_distribution':dist,
            'uniform_fraction_at_least_as_successful':sum(v for k,v in dist.items() if k>=successes),
            'local_vs_rule_cost_break_even':(successes-int(local.sum())-TIME_COST*time_extra)/calls if calls else None,
            'mean_utility':cost_table,'by_room':breakdown('room'),'by_layout':breakdown('layout')}


def report():
    blocks=archived_rows()
    names=('paired.csv','screen-development.json')
    return {'analysis':'Post-hoc comparison of the fixed visibility rule against all equally likely calls at its observed budget.',
            'inputs_sha256':{f:hashlib.sha256((EVIDENCE/f).read_bytes()).hexdigest() for f in names},
            'cost_per_sim_second':TIME_COST,
            'scope':'Conditional finite-scene distribution. Development scenarios were deliberately balanced. No population or conformal guarantee.',
            'fit_performed':False,'simulator_reruns':0,'sealed_selector_scenes_read':0,
            'blocks':{name:analyze(rows) for name,rows in blocks.items()}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=EVIDENCE/'allocation-audit.json')
    args=parser.parse_args()
    args.output.write_text(json.dumps(report(),allow_nan=False,indent=2)+'\n')
