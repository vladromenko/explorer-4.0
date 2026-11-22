"""Exercise the physical trial entry point without a serial port, HTTP endpoint or camera."""
from contextlib import nullcontext
import copy
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from explorer4 import grasp_admission, grasp_trial, rosmaster_control as rc, rosmaster_session as rs, trials


def inputs():
    return {"arm": [0.] * 3, "drive": [0.] * 3, "grip": 0.}


class Operator:
    INPUT_HOLD_S = .25
    def __init__(self):
        self.generation=0
        self.owner=self.lease=self.error=None
        self.status={}
        self.lock=threading.RLock()
        self.commands=[]
        self.armed=0
        self.heartbeat=True

    @property
    def inputs(self):
        return {"user": (time.monotonic() if self.heartbeat else 0., inputs())}

    def enable(self, owner, profile, mode, visible, source, expected_generation):
        assert (profile,mode,visible,source)==("rosmaster_pick_place","joint",True,"policy")
        assert expected_generation==self.generation
        self.owner,self.lease=owner,"lease"
        self.status={"profile":profile,"source":source}
        self.armed+=1

    def set_direct(self, action):
        if action is not None:
            assert set(action)=={"arm"} and len(action["arm"])==6
            self.commands.append(action)

    def stop(self, reason):
        self.error=reason
        self.owner=self.lease=None
        self.generation+=1


def fixture(tmp_path,monkeypatch):
    from explorer4 import data_safety, grasp_reference
    plan={"id":"a"*32,"session":"b"*32,"kind":"conditioned_grasp","profile":"rosmaster_pick_place",
          "method":"rbf","approval_sha256":"f"*64,"max_duration_s":22.}
    monkeypatch.setattr(grasp_trial,"RESULTS",tmp_path/"results")
    monkeypatch.setattr(grasp_trial.fleet_config,"locked",nullcontext)
    monkeypatch.setattr(trials.local_work,"require_hardware_mode",lambda _:None)
    monkeypatch.setattr(data_safety,"require_space",lambda:None)
    monkeypatch.setattr(grasp_reference,"prepare_recording",lambda _:None)
    monkeypatch.setattr(rc,"ensure_agent",lambda:True)
    monkeypatch.setattr(rc,"request",lambda path: {"hardware_open":True} if path=="/health" else pytest.fail(path))
    claimed=[]
    monkeypatch.setattr(grasp_admission,"claim",lambda p:claimed.append(p["id"]))
    def gate(p):
        if p["id"] in claimed:
            raise PermissionError("already claimed")
    monkeypatch.setattr(grasp_admission,"require",gate)
    monkeypatch.setattr(grasp_admission,"prewarm",lambda:None)
    monkeypatch.setattr(grasp_admission,"preflight",lambda p,s:True)
    class Client:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def close(self):pass
    monkeypatch.setattr(rs,"agent_client",Client)
    monkeypatch.setattr(rs,"ClockMap",lambda _: SimpleNamespace(probe=lambda *args:{}))
    monkeypatch.setattr(rs,"ResourceLease",lambda _:nullcontext())
    monkeypatch.setattr(rs.catalog,"event",lambda *args:None)
    operator=Operator()
    session=rs.RosmasterSession(operator)
    rgb=np.zeros((480,640,3),np.uint8)
    monkeypatch.setattr(session,"sample",lambda *_:{"arm_measured":[90.]*6,"arm_target":[90.]*6,"rgb":rgb,"observation_ns":time.monotonic_ns(),"camera_ns":time.monotonic_ns()})
    monkeypatch.setattr(session,"frame",lambda *args:{"command_source":"policy","observation.state":[90.]*6})
    class Policy:
        def __init__(self,plan):self.n=0
        def next_sample(self,sample):
            if self.n==3:raise StopIteration
            self.n+=1
            return [90.]*6
        def reset(self):pass
    monkeypatch.setattr(grasp_admission,"LiveGrasp",Policy)
    written=[]
    class Writer:
        def __init__(self,name,series,scene,category):
            assert category=="rollout" and name=="rosmaster_pick_place"
            self.id="fixture"
        def add(self,frame):assert frame["command_source"]=="policy"
        def finish(self,outcome,provenance):written.append((outcome,copy.deepcopy(provenance)))
    monkeypatch.setattr(rs,"EpisodeWriter",Writer)
    return plan,operator,session,written


def test_operator_click_to_frozen_rollout_with_independent_endpoint(tmp_path,monkeypatch):
    plan,op,session,written=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):
        grasp_trial.start(plan,"user",0,session,op,"fixture",False)
    assert not op.armed
    grasp_trial.start(plan,"user",0,session,op,"fixture",True)
    end=time.monotonic()+8
    while time.monotonic()<end and session.status()["phase"]!="awaiting_grasp_verdict":
        time.sleep(.02)
    assert session.status()["phase"]=="awaiting_grasp_verdict",session.status()
    assert not op.lease and len(op.commands)==3
    before=grasp_trial.result(plan["id"])
    assert before["success"] is None and before["sequence_completed"] and before["stop_acknowledged_by_agent"]
    with pytest.raises(ValueError):
        session.finish("success")
    scored=grasp_trial.observe_outcome(plan["id"],op,"held",62.,1.5,"video frame and ruler")
    session.thread.join(3)
    assert scored["success"] and written[0][0]=="success" and written[0][1]["source"]=="policy"
    with pytest.raises(ValueError,match="уже"):
        grasp_trial.observe_outcome(plan["id"],op,"held",80.,2.,"second report")
    with pytest.raises(PermissionError):
        grasp_trial.start(plan,"user",op.generation,session,op,"second",True)


def test_stop_during_preflight_and_refusal_never_arm(tmp_path,monkeypatch):
    plan,op,session,_=fixture(tmp_path,monkeypatch)
    def stop_before_claim(*args):op.stop("STOP")
    monkeypatch.setattr(grasp_admission,"preflight",stop_before_claim)
    with pytest.raises(PermissionError,match="STOP"):
        grasp_trial.start(plan,"user",0,session,op,"fixture",True)
    assert op.armed==0 and not op.commands and not grasp_trial.result(plan["id"])
    op.heartbeat=False
    with pytest.raises(InterruptedError,match="heartbeat"):
        grasp_trial.start(plan,"user",op.generation,session,op,"fixture",True)


@pytest.mark.parametrize("visible,lift,hold",[("unobservable",None,None),("failed",None,None),("held",50.,2.),("held",60.,.8)])
def test_sequence_and_controller_completion_cannot_self_score(tmp_path,monkeypatch,visible,lift,hold):
    plan,op,_,_=fixture(tmp_path,monkeypatch)
    grasp_trial.amend(plan["id"],finished_at=time.time(),sequence_completed=True,stop_acknowledged_by_agent=True)
    assert not grasp_trial.observe_outcome(plan["id"],op,visible,lift,hold,"operator")["success"]
