"""Paired real protocol is immutable; only post-STOP independent measurements can score it."""
import concurrent.futures
import json
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from explorer4 import peer_dock_series as series


def fake_control(stopped=True):
    event=threading.Event()
    if stopped:event.set()
    return SimpleNamespace(lock=threading.RLock(),owner=None if stopped else 'owner',stop_event=event,last_stop_reason='Operator STOP')


def test_counterbalance_independent_score_no_overwrite(tmp_path,monkeypatch):
    from contextlib import nullcontext
    monkeypatch.setattr(series,'SERIES',tmp_path/'series.json')
    monkeypatch.setattr(series.fleet_config,'locked',nullcontext)
    s=series.prepare()
    assert len(s['protocol']['order'])==8 and s['attempts']==[]
    assert s['protocol']['order']==series.prepare()['protocol']['order']
    for i in range(0,8,2):
        a,b=s['protocol']['order'][i:i+2]
        assert a[0]==b[0] and {a[1],b[1]}=={'local_scan','selective'}
    row={'id':'attempt','condition':'selective','runtime':{'reason':'arrived','observations':[{'valid':True}]}}
    s['attempts'].append(row);series.field.write_json(series.SERIES,s)
    with pytest.raises(ValueError,match='замер'):
        series.next_slot(s)
    with pytest.raises(ValueError,match='STOP'):
        series.score(fake_control(False),'attempt',0.,0.,0.,True,False,'tape')
    assert not series.score(fake_control(),'attempt',.10,.0,0.,True,False,'measured 100 mm')['success']
    with pytest.raises(ValueError,match='уже'):
        series.score(fake_control(),'attempt',0.,0.,0.,True,False,'changed')
    assert series.report()['outcomes']['selective']['independent_successes']==0


def make_attempt(tmp_path,monkeypatch,mode):
    monkeypatch.setattr(series,'SERIES',tmp_path/'series.json')
    clock=[10.]
    monkeypatch.setattr(series,'time',SimpleNamespace(monotonic=lambda:clock[0],time=time.time))
    observed=[]
    def snapshot(self,robot):
        observed.append(robot)
        self.future=concurrent.futures.Future()
        self.future.set_result((None,{'reason':'board hidden','robot':robot}))
    monkeypatch.setattr(series.PairedAttempt,'submit',snapshot)
    finished=[]
    monkeypatch.setattr(series,'terminal',lambda ident,result:finished.append(result))
    fleet=SimpleNamespace(pose_frame=lambda *a:([0.,0.,1.],time.time(),'map'),scan=lambda _:np.array([[1.,.2]]))
    spec=json.loads(series.CONFIG.read_text())
    task=series.PairedAttempt('trial',mode,spec,{'tank':{'outward_deg':180.,'map_frame_id':'map'}},fleet)
    return task,clock,observed,finished


@pytest.mark.parametrize('mode,source,turn',[('selective','rosmaster',False),('local_scan','tank',True)])
def test_equal_sensing_budget_and_no_peer_in_local_control(tmp_path,monkeypatch,mode,source,turn):
    task,clock,observed,finished=make_attempt(tmp_path,monkeypatch,mode)
    v,w=task.command(None)
    assert v==0 and (abs(w)>0)==turn and abs(w)<=.5
    assert observed==['tank',source]
    clock[0]+=3.01
    assert task.command(None)==[0.,0.]
    assert not task.active and finished[0]['reason']=='no_measurement_before_deadline'


def test_search_refuses_close_obstacle_and_stop_cancels(tmp_path,monkeypatch):
    task,clock,observed,finished=make_attempt(tmp_path,monkeypatch,'local_scan')
    task.fleet.scan=lambda _:np.array([[.05,.12]])
    assert task.command(None)==[0.,0.] and not task.active
    task.cancel('STOP')
    assert len(finished)==1 and finished[0]['reason']=='unsafe_local_turn_clearance'


@pytest.mark.parametrize('reason,expected',[('blocked',True),('operator_stop',False)])
def test_independently_measured_endpoint_does_not_require_controller_arrival(tmp_path,monkeypatch,reason,expected):
    from contextlib import nullcontext
    monkeypatch.setattr(series,'SERIES',tmp_path/'series.json')
    monkeypatch.setattr(series.fleet_config,'locked',nullcontext)
    s=series.prepare()
    s['attempts'].append({'id':'run','condition':'local_scan','runtime':{'reason':reason,'observations':[{'valid':True}]}})
    series.field.write_json(series.SERIES,s)
    endpoint=series.score(fake_control(),'run',.01,0.,1.,True,False,'independent floor measurement')
    assert endpoint['success'] is expected and endpoint['independent_geometry_pass']
