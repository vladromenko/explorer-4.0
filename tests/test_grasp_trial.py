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
    monkeypatch.setattr(grasp_admission,"prewarm_field",lambda:None)
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


def test_late_measurement_reconciles_saved_capture_after_restart(tmp_path, monkeypatch):
    import json
    from explorer4 import catalog

    plan, op, session, written = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(grasp_trial, "VERDICT_WAIT_S", 0)
    monkeypatch.setattr(grasp_trial, "DATA", tmp_path)
    monkeypatch.setattr(catalog, "DATA", tmp_path)
    monkeypatch.setattr(catalog, "prepare", lambda: None)
    catalog.initialize()
    grasp_trial.start(plan, "user", 0, session, op, "fixture", True)
    session.thread.join(8)
    record = grasp_trial.result(plan["id"])
    assert record["pending_at_capture_close"] and record["success"] is None
    assert record["sequence_completed"] and record["stop_acknowledged_by_agent"] and not op.lease
    label, hardware = written[0]
    assert label == "awaiting_measurement" and hardware["independent_endpoint"] is None

    # Receive the human measurement before the capture reaches the catalogue.
    measured = grasp_trial.observe_outcome(plan["id"], op, "held", 61., 1.1, "fixture ruler")
    assert measured["success"]
    episode = record["episodes"][0]
    root = tmp_path / "datasets/rosmaster_pick_place" / episode
    root.mkdir(parents=True)
    raw = json.dumps(dict(domain="real", command_source="policy", outcome=label, hardware=hardware))
    (root / "provenance.json").write_text(raw)
    catalog.add_episode(dict(id=episode, profile="rosmaster_pick_place", dataset=str(root), episode_index=0,
                             session="fixture", scene="fixture", category="rollout", outcome=label, frames=3))
    grasp_trial.recover_observed_outcomes()
    grasp_trial.recover_observed_outcomes()
    assert catalog.rows("episodes")[0]["outcome"] == "success"
    assert (root / "provenance.json").read_text() == raw


def test_late_stop_while_saving_preserves_completed_physical_verdict(tmp_path, monkeypatch):
    plan, op, session, written = fixture(tmp_path, monkeypatch)
    in_save, resume = threading.Event(), threading.Event()
    def pause_before_writer():
        in_save.set()
        assert resume.wait(4)
        return {}
    monkeypatch.setattr(rs, "agent_code_hashes", pause_before_writer)
    grasp_trial.start(plan, "user", 0, session, op, "fixture", True)
    until = time.monotonic() + 4
    while session.status()["phase"] != "awaiting_grasp_verdict" and time.monotonic() < until:
        time.sleep(.01)
    scored = grasp_trial.observe_outcome(plan["id"], op, "held", 61., 1.2, "ruler")
    try:
        assert scored["success"] and in_save.wait(4)
        session.mark_emergency()
        assert not session.finish("aborted", emergency=True)
    finally:
        resume.set()
    session.thread.join(4)
    audit = grasp_trial.result(plan["id"])
    assert audit["success"] and audit["rollout_outcome_at_save"] == written[0][0] == "success"
    assert not written[0][1]["emergency_intervention"] and not audit["emergency"]


def test_late_verdict_acquires_operator_before_fleet(tmp_path, monkeypatch):
    from contextlib import contextmanager
    plan, op, _, _ = fixture(tmp_path, monkeypatch)
    grasp_trial.amend(plan["id"], finished_at=time.time(), sequence_completed=True, stop_acknowledged_by_agent=True)
    held = []
    @contextmanager
    def operator_lock():
        held.append("operator")
        try:
            yield
        finally:
            held.remove("operator")
    @contextmanager
    def fleet_lock():
        assert held == ["operator"]
        yield
    op.lock = operator_lock()
    monkeypatch.setattr(grasp_trial.fleet_config, "locked", fleet_lock)
    assert grasp_trial.observe_outcome(plan["id"], op, "held", 61., 1.2, "ruler")["success"]


def test_restart_indexes_only_a_complete_bound_orphaned_capture(tmp_path, monkeypatch):
    import av
    import json
    import pyarrow as pa
    import pyarrow.parquet as pq
    from explorer4 import catalog

    monkeypatch.setattr(grasp_trial, "RESULTS", tmp_path / "trials")
    monkeypatch.setattr(grasp_trial, "DATA", tmp_path)
    monkeypatch.setattr(grasp_trial.fleet_config, "locked", nullcontext)
    monkeypatch.setattr(catalog, "DATA", tmp_path)
    monkeypatch.setattr(catalog, "prepare", lambda: None)
    catalog.initialize()
    ident, episode, command = "1"*32, "2"*32, "3"*32
    plan = {"id": ident, "kind":"conditioned_grasp"}
    grasp_trial.amend(ident, plan_id=ident, episodes=[episode], scene="pad", frames=3,
                      finished_at=time.time(), sequence_completed=True, stop_acknowledged_by_agent=True,
                      pending_at_capture_close=True, success=None)
    root = tmp_path / "datasets/rosmaster_pick_place" / episode
    for folder in ("meta/episodes/chunk-000", "data/chunk-000", "videos/observation.images.front/chunk-000"):
        (root / folder).mkdir(parents=True)
    raw = {"category":"rollout","synthetic":False,"domain":"real","command_source":"policy",
           "scene_id":"pad", "session_id":"fixture", "closed_at":time.time(), "outcome":"awaiting_measurement",
           "hardware":{"trial_plan":plan,"trial_id":command,"conditioned_grasp_result":"/api/rosmaster/grasp-trial/"+ident}}
    (root / "provenance.json").write_text(json.dumps(raw))
    (root / "meta/info.json").write_text(json.dumps({"total_frames":3,"total_episodes":1}))
    pq.write_table(pa.table({"episode_index":[0],"length":[3],"dataset_from_index":[0],"dataset_to_index":[3]}),
                   root / "meta/episodes/chunk-000/file-000.parquet")
    (root / "meta/stats.json").write_text(json.dumps({name:{} for name in ("observation.state","action","observation.images.front")}))
    pq.write_table(pa.table({"task_index":[0]}), root / "meta/tasks.parquet")
    pq.write_table(pa.table({"episode_index":[0,0,0], "frame_index":[0,1,2],
                             "observation.state":[[0.] * 6] * 3, "action":[[0.] * 6] * 3}),
                   root / "data/chunk-000/file-000.parquet")
    rows = [{"frame_index":i,"episode_id":episode,"trial_id":command,"command_source":"policy"} for i in range(3)]
    sidecar = root / "research.jsonl"
    def save(rows):
        sidecar.write_text("".join(json.dumps(row)+"\n" for row in rows))
    save(rows)
    grasp_trial.recover_observed_outcomes()
    assert catalog.rows("episodes") == []  # No final video.
    with av.open(str(root / "videos/observation.images.front/chunk-000/file-000.mp4"), "w") as video:
        stream = video.add_stream("mpeg4", rate=20)
        stream.width = stream.height = 16
        stream.pix_fmt = "yuv420p"
        for index in range(3):
            frame = av.VideoFrame.from_ndarray(np.full((16,16,3), index, np.uint8), format="rgb24")
            video.mux(stream.encode(frame))
        video.mux(stream.encode(None))
    save([{**r,"trial_id":"wrong"} for r in rows])
    grasp_trial.recover_observed_outcomes()
    assert catalog.rows("episodes") == []  # Same video and frame count, different physical command trial.
    save(rows)
    grasp_trial.recover_observed_outcomes()
    [entry] = catalog.rows("episodes")
    assert (entry["id"],entry["outcome"],entry["frames"]) == (episode,"awaiting_measurement",3)
    assert grasp_trial.observe_outcome(ident, Operator(), "held", 61., 1.1, "ruler")["success"]
    grasp_trial.recover_observed_outcomes()
    [entry] = catalog.rows("episodes")
    assert entry["outcome"] == "success" and entry["created"] == raw["closed_at"]
    assert json.loads((root / "provenance.json").read_text()) == raw
