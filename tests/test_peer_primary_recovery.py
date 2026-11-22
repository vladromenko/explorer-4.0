"""Interrupt the real capture sequence with a synthetic camera, without fitting or opening a test room."""

import hashlib
import json
from pathlib import Path

import pytest

from explorer4 import peer_primary_recovery as recovery, training
from scripts import peer_dock_policy as policy, peer_dock_study as study


class CameraFixture:
    def __init__(self, directory, seed, room):
        self.world = self
        self.scene = room
        self.output = directory
        self.number = 0
        self.manifest = {"xml_sha256": "fixture"}
        self.colour = b"original pixels"
        self.observations = []

    def reset(self, seed):
        self.number += 1
        self.initial = {"task_id": self.number, "seed": seed}

    def snapshot(self):
        return self.initial

    def restore(self, snapshot):
        self.number = snapshot["task_id"]
        self.initial = snapshot

    def camera(self, robot, label):
        (self.output / (label + ".png")).write_bytes(self.colour)
        return {
            "packet": None,
            "simulation_time_s": 0.0,
            "measurement": {"screen_fraction": 0.2},
        }

    def observe(self, save):
        self.observations.append(self.initial["seed"])
        self.camera("rosmaster", "donor-observation")
        (self.output / "world-observation.png").write_bytes(b"overview")
        return {"packet": None, "recipient_held": True}

    def close(self):
        pass


@pytest.fixture
def prefix(tmp_path):
    plan = {"test_seeds": [1, 2, 3], "test_room": "fixture"}
    model = {
        "mean": [0.0] * 5,
        "scale": [1.0] * 5,
        "coef": [0.0] * 5,
        "intercept": 0.1,
        "threshold": 0.5,
    }
    world = CameraFixture(tmp_path, 1, "fixture")
    for seed in (1, 2):
        folder = tmp_path / "test" / str(seed)

        def stop_before_donor(decision):
            policy.freeze_prediction(folder, seed, model, decision)
            if seed == 2:
                raise InterruptedError

        try:
            study.scene_inputs(world, folder, seed, before_donor=stop_before_donor)
        except InterruptedError:
            pass
    return tmp_path, plan, model


def digest_files(root):
    return {
        p: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def test_resume_preserves_prefix_and_refuses_changed_first_image(prefix):
    root, plan, model = prefix
    original = digest_files(root / "test")
    world = CameraFixture(root, 1, "fixture")
    world.colour = b"changed camera pixels"
    with pytest.raises(ValueError, match="recipient-before.png"):
        recovery.recover_scenes(root, plan, model, lambda *a: world)
    assert not world.observations
    assert digest_files(root / "test") == original

    world.colour = b"original pixels"
    recovery.recover_scenes(root, plan, model, lambda *a: world)
    assert [2, 3] == world.observations
    after = digest_files(root / "test")
    assert all(after[p] == signature for p, signature in original.items())
    for seed in plan["test_seeds"]:
        assert recovery.read(root / "test" / str(seed) / "start.json")["seed"] == seed
    recovery.recover_scenes(
        root,
        plan,
        model,
        lambda *args: pytest.fail("All original inputs already exist"),
    )
    assert digest_files(root / "test") == after


def test_resume_protects_torn_rollout_and_skips_committed_endpoint(prefix, monkeypatch):
    root, plan, model = prefix
    recovery.recover_scenes(root, plan, model, CameraFixture)
    saved = root / "test/1"
    partial = root / "test/2"
    (saved / "outcomes.json").write_text('{"task":"fixed synthetic result"}')
    (partial / "world-final.png").write_bytes(b"registered final frame")
    logs = []

    def rollout(world, stage, seed, packet, other):
        logs.append((seed, other))
        for name in recovery.ROLLOUT:
            (stage / name).write_bytes(b"new")

    monkeypatch.setattr(study, "rollouts", rollout)
    original = digest_files(root / "test")
    with pytest.raises(ValueError, match="world-final.png"):
        recovery.recover_scenes(root, plan, model, CameraFixture)
    assert logs == [(2, 3)]
    assert digest_files(root / "test") == original


def test_worker_skips_fit_with_saved_receipt(tmp_path, monkeypatch):
    cfg = {"kind": "workspace_study", "track": "peer_learning", "study_plan": "fixture"}
    monkeypatch.setattr(recovery, "primary", lambda c: tmp_path / "public")
    monkeypatch.setattr(training, "DATA", tmp_path)
    monkeypatch.setattr(
        recovery.study_queue,
        "execute",
        lambda *args: pytest.fail("Refitting is forbidden"),
    )
    (tmp_path / "jobs").mkdir()
    root = recovery.primary(cfg)
    (root / "test").mkdir(parents=True)
    with pytest.raises(ValueError, match="without a published fit"):
        recovery.has_fit(cfg)
    for filename in ("fit.json", "model.json"):
        (root / filename).write_text("{}")
    path = tmp_path / "fixture-job.json"
    path.write_text(json.dumps(cfg))
    cmd = []
    monkeypatch.setattr(
        training.subprocess, "run", lambda args, **kwargs: cmd.append(args[2:])
    )
    training.run_job(path)
    assert cmd == [["explorer4.peer_primary_recovery", path.stem]]


def test_partial_supplement_preserves_original_frames_and_skips_finished_rows(tmp_path):
    before = b"primary recipient pixels"
    spec = {
        "scenes": [
            {"seed": 1, "initial_rgb_sha256": hashlib.sha256(before).hexdigest()},
            {"seed": 2, "initial_rgb_sha256": hashlib.sha256(before).hexdigest()},
        ]
    }
    (tmp_path / "protocol.json").write_text("{}")
    for seed in (1, 2):
        (tmp_path / str(seed)).mkdir()
        (tmp_path / str(seed) / "initial.png").write_bytes(before)
    (tmp_path / "1/result.json").write_text("{}")
    original = digest_files(tmp_path)
    seen = []

    def run(spec, out, split):
        for scene in spec["scenes"]:
            folder = out / str(scene["seed"])
            if (folder / "result.json").exists():
                continue
            folder.mkdir(exist_ok=True)
            seen.append(scene["seed"])
            (folder / "initial.png").write_bytes(replay)
            (folder / "result.json").write_text("{}")

    replay = b"wrong"
    with pytest.raises(ValueError, match="original primary camera"):
        recovery.preserve_confirmation(run, spec, tmp_path, "test")
    assert digest_files(tmp_path) == original
    replay = before
    recovery.preserve_confirmation(run, spec, tmp_path, "test")
    assert seen == [2, 2]
    after = digest_files(tmp_path)
    assert all(after[p] == marker for p, marker in original.items())
    assert (tmp_path / "2/result.json").is_file()


def test_completed_evaluation_restores_results_without_fitting_or_opening_worlds(
    tmp_path, monkeypatch
):
    cfg = {"kind": "workspace_study", "track": "peer_learning", "study_plan": "fixture"}
    root = tmp_path / "simlab/reports/workspace/fixture/peer_learning"
    root.mkdir(parents=True)
    work = tmp_path / "jobs/fixture-job"
    plan = {"test_seeds": [42], "test_room": "temporary"}
    model = {"plan_sha256": recovery.checksum(plan), "threshold": 0.45}
    fit = {
        "model_sha256": recovery.checksum(model),
        "threshold": 0.5,
        "test_results_read": False,
        "motor_weights_updated": False,
    }
    evaluation = {
        "status": "completed",
        "model_sha256": recovery.checksum(model),
        "test_seeds": [42],
        "fit_on_test": False,
    }
    for name, data in (
        ("plan", plan),
        ("model", model),
        ("fit", fit),
        ("evaluation", evaluation),
    ):
        (root / (name + ".json")).write_text(json.dumps(data))
    monkeypatch.setattr(recovery, "DATA", tmp_path)
    monkeypatch.setattr(recovery, "primary", lambda c: root)
    monkeypatch.setattr(recovery.study_queue, "verify", lambda key: {})
    monkeypatch.setattr(
        policy, "verify_plan", lambda folder: recovery.read(folder / "plan.json")
    )
    monkeypatch.setattr(policy, "prepare", lambda dest, source: plan)
    monkeypatch.setattr(policy, "fit", lambda *a: pytest.fail("No fit on retry"))
    monkeypatch.setattr(
        policy,
        "evaluate",
        lambda *a: pytest.fail("No rerunning the completed evaluation"),
    )
    with pytest.raises(ValueError, match="threshold"):
        recovery.resume(cfg, work)
    assert not (work / "result.json").exists()
    fit["threshold"] = model["threshold"]
    (root / "fit.json").write_text(json.dumps(fit))
    before = digest_files(root)
    recovery.resume(cfg, work)
    after = digest_files(root)
    assert all(after[p] == signature for p, signature in before.items())
    assert recovery.read(work / "result.json") == recovery.read(root / "result.json")
