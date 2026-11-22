from types import SimpleNamespace

from explorer4 import catalog, training_schedule as schedule
from explorer4.jobs import Jobs


def test_training_waits_for_its_own_release_after_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "DATA", tmp_path)
    catalog.initialize()
    engine = Jobs(SimpleNamespace(owner=None, maintenance=False))
    fitted = engine._insert("so101_pick_place", "act", {"kind": "train"})
    field = engine._insert("tank_dock_sim", "peer", {"kind": "cognitive_simulation"})
    later = engine._insert("tank_dock_sim", "ppo", {"kind": "simlab_pipeline"})
    observed = []

    def record_only(job):
        observed.append(job["id"])
        with catalog.connect() as db:
            db.execute("UPDATE jobs SET status='completed' WHERE id=?", (job["id"],))

    monkeypatch.setattr(engine, "_run", record_only)
    monkeypatch.setattr(schedule.time, "time", lambda: 100.0)
    assert schedule.set_start([fitted], 250.0) == 1
    engine.tick()
    engine.thread.join()
    assert observed == [field]
    catalog.initialize()
    engine.tick()
    assert observed == [field]
    monkeypatch.setattr(schedule.time, "time", lambda: 260.0)
    engine.tick()
    engine.thread.join()
    assert observed == [field, fitted]
    assert [r["id"] for r in schedule.queue()] == [later]
    schedule.set_start([later], 270.0)
    schedule.set_start([later], None)
    monkeypatch.setattr(schedule.time, "time", lambda: 275.0)
    engine.tick()
    assert observed == [field, fitted]


def test_withdraw_before_claim_never_launches(tmp_path, monkeypatch):
    from explorer4 import jobs, resources

    monkeypatch.setattr(catalog, "DATA", tmp_path)
    monkeypatch.setattr(jobs, "DATA", tmp_path)
    monkeypatch.setattr(resources, "DATA", tmp_path)
    for part in ("jobs", "logs"):
        (tmp_path / part).mkdir()
    catalog.initialize()
    engine = Jobs(SimpleNamespace(owner=None, maintenance=False))
    ident = engine._insert("example", "act", {"kind": "train", "device": "cpu"})
    schedule.set_start([ident], 0.0)
    old_snapshot = engine.get(ident)
    schedule.set_start([ident], None)

    def forbidden(*args, **kwargs):
        raise AssertionError("A held training job attempted to spawn a process")

    monkeypatch.setattr(jobs.subprocess, "Popen", forbidden)
    engine._run(old_snapshot)
    assert engine.get(ident)["status"] == "queued"
    assert schedule.queue()[0]["not_before"] is None


def test_cancel_and_resume_cannot_reuse_an_old_start(tmp_path, monkeypatch):
    from explorer4 import study_queue

    monkeypatch.setattr(catalog, "DATA", tmp_path)
    monkeypatch.setattr(study_queue, "verify", lambda plan: {})
    catalog.initialize()
    engine = Jobs(SimpleNamespace(owner=None, maintenance=False))
    ident = engine._insert(
        "example", "act", {"kind": "workspace_study", "study_plan": "test"}
    )
    schedule.set_start([ident], 0.0)
    engine.cancel(ident)
    with catalog.connect() as db:
        assert ident not in schedule.permits(db)
        # Reproduce an older installation's leftover authorization on a cancelled job.
        db.execute("INSERT INTO training_starts VALUES(?,0)", (ident,))
    engine.resume(ident)
    assert schedule.queue()[0]["not_before"] is None
