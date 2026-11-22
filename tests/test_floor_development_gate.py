"""Gate orchestration with a publishing trainer double and synthetic evaluator receipts."""

import io
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from explorer4 import floor_development_gate as gate
from explorer4 import training_drafts

GEOMETRY = "a" * 64
STEPS = 10000


def with_starts(profile, policy, steps, geometry):
    rows = [
        {
            "seed": s,
            "initial_qpos_sha256": f"{s:064x}",
            "initial_rgb_sha256": f"{s * 2:064x}",
            "initial_parameters_sha256": f"{s * 3:064x}",
            "reference_png_sha256": f"{s * 4:064x}",
        }
        for s in gate.SEEDS
    ]
    return {**gate.recipe(profile, policy, steps, geometry), "starts": rows}


def publish(output, policy, step):
    root = output / "checkpoints" / f"{step:06}"
    model, state = root / "pretrained_model", root / "training_state"
    gate.write(
        model / "train_config.json",
        {
            "policy": {"type": policy},
            "steps": STEPS,
            "batch_size": 8,
            "output_dir": str(output),
            "scheduler": {"name": "cosine"},
        },
    )
    gate.write(model / "config.json", {"type": policy})
    (model / "model.safetensors").write_bytes(f"test weights {step}".encode())
    for role in ["pre", "post"]:
        gate.write(model / f"policy_{role}processor.json", {"steps": []})
    gate.write(state / "training_step.json", {"step": step, "num_processes": 1, "batch_size": 8})
    for filename in [
        "optimizer_param_groups.json",
        "rng_state.safetensors",
        "optimizer_state.safetensors",
        "scheduler_state.json",
    ]:
        (state / filename).write_bytes(b"test state")
    link = root.parent / "last"
    link.unlink(missing_ok=True)
    link.symlink_to(root.name)
    return model


def make_run(tmp_path, monkeypatch, policy, signals):
    work, output = tmp_path / "job", tmp_path / "checkpoints/job-b8"
    recipe = with_starts(gate.PROFILE, policy, STEPS, GEOMETRY)
    config = {
        "profile": gate.PROFILE,
        "policy": policy,
        "domain": "sim",
        "steps": STEPS,
        "device": "cpu",
        "draft_id": "d" * 64,
        "floor_development_gate": recipe,
    }
    stages, attempts = [], []

    def trainer(command, stop, log):
        assert command[:3] == [sys.executable, "-m", "lerobot.scripts.lerobot_train"]
        if not stages:
            assert "--steps=10000" in command
        else:
            previous = stages[-1]
            assert command[3:] == [
                f"--config_path={output}/checkpoints/{previous:06}/pretrained_model/train_config.json",
                "--resume=true",
            ]
        stage = stop or STEPS
        publish(output, policy, stage)
        stages.append(stage)

    def evaluator(args, **kwargs):
        model, raw = map(Path, args[3:5])
        assert args[args.index("--device") + 1] == "cpu"
        assert list(map(int, args[args.index("--seeds") + 1 : args.index("--record-floor")])) == list(
            gate.SEEDS
        )
        step = int(model.parent.name)
        attempts.append(step)
        identity = gate.bundle_identity(model)
        rows = []
        for index, seed in enumerate(gate.SEEDS):
            score = signals[step]
            if score is None:
                return subprocess.CompletedProcess(args, 8)
            held = index < score
            rows.append(
                {
                    "seed": seed,
                    "steps": 1,
                    "policy_seed": seed,
                    "outcome": "failure",
                    "ever_held": held,
                    "max_lift_cm": 1.0 if held else 0.999,
                    **recipe["starts"][index],
                    "reference_rgb_sha256": recipe["starts"][index]["initial_rgb_sha256"],
                    "rgb_channels": 921600,
                    "rgb_max_level_error": 0,
                    "rgb_different_channels": 0,
                }
            )
            gate.write(
                raw.parent / f"floor-trial-{seed}.json",
                {
                    "seed": seed,
                    "model": GEOMETRY,
                    "profile": gate.PROFILE,
                    "outcome": "failure",
                    "fps": 20,
                    "qpos": [[0], [1]],
                    "checkpoint_sha256": identity["checkpoint_sha256"],
                },
            )
        gate.write(
            raw,
            {
                "status": "completed",
                "domain": "sim",
                "profile": gate.PROFILE,
                "policy": policy,
                "privileged_input": False,
                "new_process_reload": True,
                "policy_seed_per_scene": True,
                "checkpoint": str(model),
                "protocol": {
                    **identity,
                    "scene_revision": recipe["scene_revision"],
                    "xml_sha256": GEOMETRY,
                    "scene_seeds": list(gate.SEEDS),
                },
                "trials": rows,
            },
        )
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(gate, "train_stage", trainer)
    monkeypatch.setattr(gate, "run_evaluator", evaluator)

    def run(resume=None):
        command = [sys.executable, "-m", "lerobot.scripts.lerobot_train", "--steps=10000"]
        return gate.run(work, output, config, 8, command, resume, io.StringIO())

    return run, stages, attempts, work, output


def test_publication_hook_returns_control_before_the_next_native_update(monkeypatch, tmp_path):
    # No torch import or optimizer: exercise the exact adapter with a native-shaped module.
    package = ModuleType("lerobot.scripts")
    trainer = ModuleType("lerobot_train")
    trainer.__file__ = str(tmp_path / "fake_native.py")
    Path(trainer.__file__).write_text("# simulated published source")
    monkeypatch.setattr(gate, "TRAINER_SHA256", gate.sha256_file(trainer.__file__))
    events = []

    def original(path):
        events.append(("saved", path.name))

    trainer.update_last_checkpoint = original

    def main():
        assert sys.argv == ["lerobot-train", "--steps=10000"]
        trainer.update_last_checkpoint(Path("000500"))
        trainer.update_last_checkpoint(Path("001000"))
        pytest.fail("The optimizer should have yielded at the 1000-step publication")

    trainer.main = main
    package.lerobot_train = trainer
    monkeypatch.setitem(sys.modules, "lerobot.scripts", package)
    argv = sys.argv
    assert gate.native_until(1000, ["--steps=10000"]) == gate.PUBLISHED
    assert events == [("saved", "000500"), ("saved", "001000")]
    assert sys.argv is argv and trainer.update_last_checkpoint is original


def test_stops_after_two_negative_blocks_and_keeps_optimizer_resume(tmp_path, monkeypatch):
    run, stages, attempts, work, _output = make_run(tmp_path, monkeypatch, "act", {1000: 0, 3000: 0})
    result = run()
    assert stages == attempts == [1000, 3000]
    assert result["status"] == "stopped_no_grasp_signal" and result["selected_checkpoint"] is None
    assert result["last_step"] == 3000 and result["requested_steps"] == 10000 and not result["test_used"]
    assert int(Path(result["last_checkpoint"]).parent.name) == 3000
    assert gate.read(work / "development-gate/status.json") == result
    assert all(len(list(Path(c["replays"]).glob("floor-trial-*.json"))) == 8 for c in result["checks"])


def test_technical_retry_resumes_native_state_then_selects_earlier_than_latest(tmp_path, monkeypatch):
    signals = {1000: 1, 3000: None, STEPS: 0}
    run, stages, attempts, work, output = make_run(tmp_path, monkeypatch, "diffusion", signals)
    with pytest.raises(RuntimeError, match="unavailable"):
        run()
    status = gate.read(work / "development-gate/status.json")
    assert status["status"] == "technical_error" and len(status["checks"]) == 1
    assert stages == [1000, 3000] and attempts == [1000, 3000, 3000]
    signals[3000] = 2
    result = run(status["last_checkpoint"])
    assert stages == [1000, 3000, STEPS] and attempts == [1000, 3000, 3000, 3000, STEPS]
    assert result["status"] == "completed" and result["selected_step"] == 3000 and result["last_step"] == STEPS
    assert (
        result["selected_checkpoint_sha256"]
        == gate.bundle_identity(Path(result["selected_checkpoint"]))["checkpoint_sha256"]
    )
    assert len(list((work / "development-gate/3000").glob("attempt-*/technical-error.json"))) == 2
    (output / "checkpoints/003000/training_state/rng_state.safetensors").unlink()
    with pytest.raises(ValueError, match="incomplete optimizer"):
        gate.checkpoint_at(output, 3000, STEPS, "diffusion", 8)


def test_only_explicit_fresh_floor_drafts_pin_disjoint_development_scenes(tmp_path, monkeypatch):
    monkeypatch.setattr(training_drafts, "DATA", tmp_path)
    monkeypatch.setattr(gate, "freeze_recipe", with_starts)
    splits = {
        role: [{"id": str(seed), "scene": f"{gate.PROFILE}-seed-{seed}-{GEOMETRY}", "frames": 5}]
        for role, seed in zip(("train", "validation", "test"), [11, 12, 13])
    }
    plan = {"profile": gate.PROFILE, "sim_model_hash": GEOMETRY, "splits": splits, "domain": "sim"}
    monkeypatch.setattr(training_drafts.datasets, "freeze", lambda *a, **kw: ("a" * 64, plan))

    def prepare(**opts):
        return training_drafts.prepare(
            gate.PROFILE, "act", ["11", "12", "13"], steps=STEPS, batch=8, seed=1000, device="cpu", **opts
        )[1]

    assert "floor_development_gate" not in prepare()
    draft = prepare(floor_development=True)
    assert draft["checkpoint_interval"] == 1000 and draft["floor_development_gate"]["ordered_seeds"] == list(
        gate.SEEDS
    )
    assert draft["preparation_only"] and not (tmp_path / "jobs").exists()
    with pytest.raises(ValueError, match="fresh long"):
        prepare(floor_development=True, source={"id": "previous"})
    splits["train"][0]["scene"] = f"{gate.PROFILE}-seed-{gate.SEEDS[2]}-{GEOMETRY}"
    with pytest.raises(ValueError, match="independent"):
        prepare(floor_development=True)


@pytest.mark.parametrize("selected", [None, "003000"])
def test_jobs_entrypoint_publishes_only_the_selected_model(tmp_path, monkeypatch, selected):
    from explorer4 import training

    name = "8" * 32
    work = tmp_path / "jobs" / name
    (work / "train").mkdir(parents=True)
    output = tmp_path / "checkpoints" / (name + "-b8")
    latest = output / "checkpoints" / ("010000" if selected else "003000") / "pretrained_model"
    chosen = output / "checkpoints" / selected / "pretrained_model" if selected else None
    splits = {role: [{"id": role, "dataset": role}] for role in ("train", "validation", "test")}
    config = {
        "draft_id": "d" * 64,
        "domain": "sim",
        "smoke": False,
        "profile": gate.PROFILE,
        "plan_id": "a" * 64,
        "policy": "act",
        "steps": STEPS,
        "batch_size": 8,
        "seed": 1000,
        "device": "cpu",
        "checkpoint_interval": 1000,
        "floor_development_gate": gate.recipe(gate.PROFILE, "act", STEPS, GEOMETRY),
    }
    job = tmp_path / "jobs" / (name + ".json")
    gate.write(job, config)
    monkeypatch.setattr(training, "DATA", tmp_path)
    monkeypatch.setattr(training_drafts, "load", lambda ident: config)
    monkeypatch.setattr(training, "load_plan", lambda ident: {"splits": splits, "sim_model_hash": GEOMETRY})
    commands = []

    def native_double(work, expected_output, cfg, batch, command, resume, log):
        assert output == expected_output and resume is None and batch == 8
        assert "--steps=10000" in command and "--save_freq=1000" in command
        return {
            "status": "completed" if chosen else "stopped_no_grasp_signal",
            "selected_checkpoint": str(chosen) if chosen else None,
            "last_checkpoint": str(latest),
            "last_step": STEPS if chosen else 3000,
            "selected_step": 3000 if chosen else None,
        }

    monkeypatch.setattr(gate, "run", native_double)
    monkeypatch.setattr(training.subprocess, "run", lambda args, **kwargs: commands.append(args))
    training.run_job(job)
    result = gate.read(work / "result.json")
    assert result["requested_steps"] == STEPS and result["steps"] == (STEPS if chosen else 3000)
    assert result["last_checkpoint"] == str(latest)
    assert result["checkpoint"] == result["selected_checkpoint"] == (str(chosen) if chosen else None)
    assert not result["test_used"]
    if chosen:
        assert len(commands) == 2 and all(str(chosen) in command for command in commands)
        assert "held_out_validation" in commands[1] and "test" not in commands[1]
    else:
        assert not commands


def test_crash_after_intermediate_publication_recovers_once(tmp_path, monkeypatch):
    run, stages, _attempts, _work, output = make_run(tmp_path, monkeypatch, "act", {1000: 0, 3000: 0})
    publish_expected = gate.train_stage
    crashed = []

    def trainer(command, stop, log):
        if stop == 3000 and not crashed:
            publish(output, "act", 2000)
            stages.append(2000)
            crashed.append(True)
            raise gate.NativeStageInterrupted("simulated child exit")
        return publish_expected(command, stop, log)

    monkeypatch.setattr(gate, "train_stage", trainer)
    result = run()
    assert stages == [1000, 2000, 3000] and result["last_step"] == 3000
    assert result["trainer_recoveries"] == [
        {"target_step": 3000, "saved_step": 2000, "error": "simulated child exit"}
    ]


def test_rejects_scene_changes_even_when_the_initial_pose_matches():
    import numpy as np

    from explorer4.sim.seeded_start import compare_rgb

    reference = np.zeros((480, 640, 3), dtype=np.uint8)
    image = reference.copy()
    image.flat[0] = 1
    assert compare_rgb(image, reference) == (1, 1)
    image.flat[0] = 2
    with pytest.raises(ValueError, match="Development RGB changed"):
        compare_rgb(image, reference)
    image.flat[:10] = 1
    with pytest.raises(ValueError, match="Development RGB changed"):
        compare_rgb(image, reference)
