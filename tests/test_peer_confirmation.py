"""Guard the held queue, saved primary results and paired estimator without opening test worlds."""
import json
import sqlite3

import pytest

from explorer4 import peer_confirmation as confirmation


@pytest.fixture
def job_db(monkeypatch, tmp_path):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""CREATE TABLE jobs(id TEXT, status TEXT, config TEXT);
        CREATE TABLE training_starts(job_id TEXT, not_before REAL);""")
    cfg = {"kind": "workspace_study", "track": "peer_learning", "study_plan": "original-plan"}
    db.execute("INSERT INTO jobs VALUES(?,?,?)", ("job", "queued", json.dumps(cfg)))
    db.commit()
    monkeypatch.setattr(confirmation.catalog, "connect", lambda: db)
    monkeypatch.setattr(confirmation, "REPORTS", tmp_path)
    monkeypatch.setattr(confirmation, "protocol", lambda ident,cfg: {"id": ident, "plan": cfg["study_plan"]})
    yield db, cfg
    db.close()


def test_attaches_only_digest_while_held(job_db):
    db, cfg = job_db
    key = confirmation.attach("job")
    assert confirmation.attach("job") == key
    row, updated = confirmation.job(db, "job")
    assert updated == {**cfg, "peer_confirmation": key}
    assert row["status"] == "queued" and row["not_before"] is None
    assert confirmation.digest(confirmation.directory(key) / "protocol.json") == key
    with pytest.raises(ValueError, match="Held"):
        confirmation.confirm("job")
    db.execute("INSERT INTO training_starts VALUES(?,?)", ("job", 100.))
    db.commit()
    with pytest.raises(ValueError, match="unscheduled"):
        confirmation.attach("job")


def test_restore_primary_only_if_job_and_public_evidence_match(job_db, tmp_path):
    _, cfg = job_db
    root = confirmation.primary(cfg)
    work = tmp_path / "job"
    evaluation = {"status": "completed", "scenes": 2, "model_sha256": "test-model"}
    result = {**evaluation, "track": "peer_learning", "study_plan": cfg["study_plan"]}
    assert not confirmation.primary_saved(cfg, work)
    for path, value in ((root/"result.json",result), (work/"result.json",result), (root/"evaluation.json",evaluation)):
        confirmation.study_queue.write_json(path,value)
    assert confirmation.primary_saved(cfg, work)
    stamp = (root / "result.json").stat().st_mtime_ns
    (work / "result.json").unlink()
    assert confirmation.primary_saved(cfg, work)
    assert (root / "result.json").stat().st_mtime_ns == stamp
    confirmation.study_queue.write_json(work/"result.json",{**result, "scenes":1})
    with pytest.raises(ValueError, match="disagree"):
        confirmation.primary_saved(cfg, work)


def test_paired_time_includes_extra_sensing_and_cost():
    costs = {"call_cost": .1, "per_second_cost": .005}
    verifier = {"task":"success", "source":"fixed_outcome_verifier", "raw_environment_outcome":"success",
                "stationary":True, "distance_m":.02, "yaw_error_rad":.02, "stable_s":.55, "actions_sent":100}
    local = confirmation.measure({**verifier, "simulation_time_s":5.}, 0, costs)
    immediate = confirmation.measure({**verifier, "simulation_time_s":8.}, 1, costs)
    seq = confirmation.measure({**verifier, "simulation_time_s":11.}, 1, costs)
    summary = confirmation.summarize([{"methods":{"learned":local, "local_scan":local,
                                                "immediate_peer":immediate, "sequential":seq}}])
    assert (local["decision_frames"],immediate["decision_frames"],seq["decision_frames"]) == (1,2,17)
    assert summary["paired"]["learned_minus_sequential"]["mean_delta_seconds"] == -6.
    assert summary["paired"]["learned_minus_sequential"]["mean_delta_utility"] == pytest.approx(.13)
    with pytest.raises(ValueError, match="endpoint"):
        confirmation.measure({**verifier, "simulation_time_s":11., "distance_m":.09}, 1, costs)


@pytest.mark.parametrize("attached", [False, True])
def test_normal_worker_orders_primary_before_optional_confirmation(tmp_path,monkeypatch,attached):
    from explorer4 import training
    cfg = {"kind":"workspace_study", "track":"peer_learning", "study_plan":"fixture"}
    if attached:
        cfg["peer_confirmation"] = "a"*64
    path = tmp_path / "job-input.json"
    path.write_text(json.dumps(cfg))
    (tmp_path/"jobs").mkdir()
    monkeypatch.setattr(training, "DATA", tmp_path)
    steps = []
    monkeypatch.setattr(confirmation.study_queue, "execute", lambda cfg, work: steps.append(("primary",work.name)))
    def consume(argv, **options):
        assert options["check"] and argv[2:5] == ["explorer4.peer_confirmation", "resume", path.stem]
        steps.append(("confirmation",path.stem))
    monkeypatch.setattr(training.subprocess, "run", consume)
    training.run_job(path)
    assert steps == [("primary",path.stem)] + ([("confirmation",path.stem)] if attached else [])
