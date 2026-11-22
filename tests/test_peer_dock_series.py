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
    class FakePool:
        def __init__(self, max_workers):
            self.max_workers = max_workers

        def submit(self, function, robot, directory, index, fleet):
            assert function is series.observe_one
            observed.append(robot)
            future = concurrent.futures.Future()
            future.set_result((None, {"reason": "board hidden", "source_robot": robot}))
            return future

        def shutdown(self, *, wait, cancel_futures):
            assert not wait and cancel_futures

    monkeypatch.setattr(series.concurrent.futures, "ThreadPoolExecutor", FakePool)
    finished=[]
    monkeypatch.setattr(series,'terminal',lambda ident,result:finished.append(result))
    fleet=SimpleNamespace(pose_frame=lambda *a:([0.,0.,1.],time.time(),'map'),scan=lambda _:np.array([[1.,.2]]))
    spec=json.loads(series.CONFIG.read_text())
    if mode == "sequential":
        spec = {**spec, "donor_budget_s": 3.}
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
    assert finished[0]['peer_requests'] == int(mode == 'selective')


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


def valid_capture(robot, clock):
    future = concurrent.futures.Future()
    future.set_result(({"map_frame_id": "map", "source_robot": robot},
                       {"source_robot": robot, "valid": True, "expires_monotonic_s": clock[0] + .5}))
    return future


def fake_driver(goal, fleet):
    return SimpleNamespace(active=True, episode=None, command=lambda _: (.04, .01),
                           cancel=lambda reason: None, status=lambda: {"source_robot": goal["source_robot"]})


def test_sequential_discards_late_local_and_holds_during_one_donor_request(tmp_path, monkeypatch):
    task, clock, observed, finished = make_attempt(tmp_path, monkeypatch, "sequential")
    monkeypatch.setattr(series.field, "operator_drive", fake_driver)
    assert task.command(None)[1] != 0
    assert observed == ["tank", "tank"]
    late_local = concurrent.futures.Future()
    late_local.set_running_or_notify_cancel()
    task.future = late_local

    clock[0] += 3.
    assert task.command(None) == [0., 0.]
    assert task.phase == "hold_for_peer" and task.peer_requests == 0
    late_local.set_result(valid_capture("tank", clock).result())
    clock[0] += .05
    assert task.command(None) == [0., 0.] and observed[-1] == "rosmaster"
    clock[0] += .05
    assert task.command(None) == [0., 0.]
    assert observed == ["tank", "tank", "rosmaster", "rosmaster"]
    task.future = valid_capture("rosmaster", clock)
    assert task.command(None) == [.04, .01]
    task.cancel()
    row, = finished
    assert [event["phase"] for event in row["phase_events"]] == [
        "initial", "local_scan", "hold_for_peer", "peer", "docking", "finished"]
    assert row["phase_events"][2] == {"phase": "hold_for_peer", "at_s": 3., "discarded_capture": "002-tank"}
    assert row["phase_events"][3]["at_s"] == pytest.approx(3.05)
    assert row["peer_requests"] == 1 and row["consumed_goal"]["source_robot"] == "rosmaster"
    assert [e["source_robot"] for e in row["observations"] if e.get("valid")] == ["rosmaster"]


def test_sequential_local_recovery_does_not_call_peer(tmp_path, monkeypatch):
    task, clock, observed, finished = make_attempt(tmp_path, monkeypatch, "sequential")
    monkeypatch.setattr(series.field, "operator_drive", fake_driver)
    assert task.command(None)[1] != 0
    clock[0] += 2.9
    task.future = valid_capture("tank", clock)
    assert task.command(None) == [.04, .01]
    clock[0] += .3
    assert task.command(None) == [.04, .01]
    task.cancel()
    assert observed == ["tank", "tank"]
    assert finished[0]["peer_requests"] == 0 and finished[0]["consumed_goal"]["source_robot"] == "tank"


@pytest.mark.parametrize("ending", ["stop_at_handoff", "donor_timeout", "controller_error"])
def test_sequential_counts_only_issued_requests_even_on_stop_or_error(tmp_path, monkeypatch, ending):
    task, clock, observed, finished = make_attempt(tmp_path, monkeypatch, "sequential")
    task.command(None)
    clock[0] += 3.
    assert task.command(None) == [0., 0.]
    if ending == "stop_at_handoff":
        task.cancel()
    else:
        clock[0] += .1
        assert task.command(None) == [0., 0.]
        if ending == "donor_timeout":
            task.future = valid_capture("rosmaster", clock)
            clock[0] += 2.9
        else:
            def unavailable(robot):
                raise OSError("lost fixture scan")
            task.fleet.scan = unavailable
        assert task.command(None) == [0., 0.]
    row, = finished
    assert row["peer_requests"] == int(ending != "stop_at_handoff")
    assert row["consumed_goal"] is None
    assert row["reason"] == {"stop_at_handoff": "operator_stop", "donor_timeout": "no_measurement_before_deadline",
                             "controller_error": "controller_error"}[ending]
    assert row["phase_events"][-1]["reason"] == row["reason"]


def test_unknown_physical_condition_cannot_submit_an_observation(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="Unknown physical docking condition"):
        make_attempt(tmp_path, monkeypatch, "misspelled")
    assert not (tmp_path / "trial").exists()


def test_stop_persists_request_even_if_drive_trace_fails_to_close(tmp_path, monkeypatch):
    task, clock, observed, finished = make_attempt(tmp_path, monkeypatch, "sequential")
    monkeypatch.setattr(series.field, "operator_drive", fake_driver)
    task.command(None)
    clock[0] += 3.
    task.command(None)
    clock[0] += .1
    task.command(None)
    task.future = valid_capture("rosmaster", clock)
    task.command(None)

    def failed_cancel(reason):
        raise OSError("drive trace storage failed")

    task.driver.cancel = failed_cancel
    task.cancel()
    row, = finished
    assert row["reason"] == "operator_stop" and row["peer_requests"] == 1
    assert row["controller_endpoint"]["error"] == "drive trace storage failed"
    assert row["consumed_goal"]["source_robot"] == "rosmaster"
