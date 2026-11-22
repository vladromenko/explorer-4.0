"""Development-only MuJoCo gates at published checkpoints of native LeRobot floor-pick training."""

import argparse
import json
import math
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

from .paths import ROOT, offline_environment
from .sim_protocol import bundle_identity, scene_revision, sha256_file

PROFILE = "rosmaster_floor_pick_recorded_start_sim"
SEEDS = tuple(range(957300, 957308))
BOUNDARIES = (1000, 3000)
PUBLISHED = 75
# The adapter relies on the single-process publication point of upstream LeRobot v0.6.1.
TRAINER_SHA256 = "059bda054bbb188d4a40d0a32941aa4d9ac59252a37d67a258e685a0a6d063ec"


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    os.replace(tmp, path)


def recipe(profile, policy, steps, model_sha):
    if (
        profile != PROFILE
        or policy not in ("act", "diffusion")
        or type(steps) is not int
        or steps <= BOUNDARIES[-1]
        or not isinstance(model_sha, str)
        or not re.fullmatch(r"[0-9a-f]{64}", model_sha)
    ):
        raise ValueError("Проверка захвата требует нового длинного ACT или Diffusion в сцене записанной позы")
    return {
        "version": 1,
        "profile": PROFILE,
        "policy": policy,
        "ordered_seeds": list(SEEDS),
        "partition": "development",
        "checkpoints": list(BOUNDARIES),
        "expected_geometry_sha256": model_sha,
        "scene_revision": scene_revision(PROFILE),
        "native_trainer_sha256": TRAINER_SHA256,
        "evaluator_sha256": sha256_file(ROOT / "explorer4/sim/evaluate.py"),
        "seed_probe_sha256": sha256_file(ROOT / "explorer4/sim/seeded_start.py"),
        "inference_worker_sha256": sha256_file(ROOT / "explorer4/sim/policy_worker.py"),
        "lift_cm": 1.0,
        "early_stop": "No held object or 1 cm lift in both completed 1000 and 3000 evaluations.",
        "selection": "Most task completions, then holds, then 1 cm lifts; earliest step on a tie.",
    }


def validate_starts(rows):
    keys = ("initial_qpos_sha256", "initial_rgb_sha256", "initial_parameters_sha256", "reference_png_sha256")
    if [r.get("seed") for r in rows] != list(SEEDS):
        raise ValueError("Unexpected seeds in frozen development starts")
    for key in keys:
        digests = {r.get(key, "") for r in rows}
        if len(digests) != len(SEEDS) or any(not re.fullmatch(r"[a-f0-9]{64}", d) for d in digests):
            raise ValueError("Expected distinct physical starts, appearance and dynamics")


def freeze_recipe(profile, policy, steps, model_sha):
    gate = recipe(profile, policy, steps, model_sha)
    proc = subprocess.run(
        [str(ROOT / ".venv-sim/bin/python"), "-m", "explorer4.sim.seeded_start"],
        cwd=ROOT,
        env={**offline_environment(), "MUJOCO_GL": "egl"},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode:
        raise ValueError(f"Development seed verification failed: {proc.stderr[-500:]}")
    receipt = json.loads(proc.stdout.splitlines()[-1])
    if receipt["xml_sha256"] != model_sha:
        raise ValueError("Development scene does not match selected recordings")
    validate_starts(receipt["rows"])
    return {**gate, "starts": receipt["rows"]}


def validate_split(plan):
    """SimCapture embeds the source seed and geometry in each episode's scene ID."""
    for episodes in plan["splits"].values():
        for episode in episodes:
            scene = re.fullmatch(rf"{PROFILE}-seed-(\d+)-([0-9a-f]{{64}})", episode.get("scene", ""))
            if not scene or scene[2] != plan["sim_model_hash"] or int(scene[1]) in SEEDS:
                raise ValueError("Unable to establish independent development seeds for this dataset")


def checkpoint_at(output, step, steps, policy, batch):
    # LeRobot pads checkpoint names against the full requested step count.
    root = output / "checkpoints" / str(step).zfill(max(6, len(str(steps))))
    model = root / "pretrained_model"
    state = root / "training_state"
    config = read(model / "train_config.json")
    saved = read(state / "training_step.json")
    if (
        saved.get("num_processes") != 1
        or saved.get("batch_size") != batch
        or config["steps"] != steps
        or config["policy"]["type"] != policy
        or config["batch_size"] != batch
        or Path(config["output_dir"]).resolve() != output.resolve()
        or saved["step"] != step
    ):
        raise ValueError("Checkpoint step, recipe or output directory changed")
    required = ["optimizer_state.safetensors", "optimizer_param_groups.json", "rng_state.safetensors"]
    if config.get("scheduler") is not None:
        required.append("scheduler_state.json")
    if any(not (state / f).is_file() or not (state / f).stat().st_size for f in required):
        raise ValueError("Checkpoint has incomplete optimizer, RNG or scheduler state")
    return model


def native_until(step, argv):
    """Single-process adapter at LeRobot's post-save hook, after its original last link is published."""
    if int(os.environ.get("WORLD_SIZE", "1")) != 1:
        raise ValueError("Development-boundary exit requires single-process training")
    from lerobot.scripts import lerobot_train

    if sha256_file(lerobot_train.__file__) != TRAINER_SHA256:
        raise ValueError(
            "The installed native trainer changed; verify its checkpoint publication hook before training"
        )
    previous = lerobot_train.update_last_checkpoint

    class PublishedBoundary(Exception):
        pass

    def after_publication(path):
        value = previous(path)
        if int(Path(path).name) == step:
            raise PublishedBoundary
        return value

    lerobot_train.update_last_checkpoint = after_publication
    original_argv = sys.argv
    sys.argv = ["lerobot-train", *argv]
    try:
        lerobot_train.main()
    except PublishedBoundary:
        return PUBLISHED
    finally:
        sys.argv = original_argv
        lerobot_train.update_last_checkpoint = previous
    return 0


def summarize(result, gate, model, identity, starts):
    rows = result.get("trials", [])
    protocol = result.get("protocol", {})
    if (
        result.get("status") != "completed"
        or result.get("profile") != PROFILE
        or result.get("policy") != gate["policy"]
        or result.get("domain") != "sim"
        or result.get("privileged_input") is not False
        or result.get("new_process_reload") is not True
        or result.get("policy_seed_per_scene") is not True
        or Path(result.get("checkpoint", "")).resolve() != model.resolve()
        or protocol.get("xml_sha256") != gate["expected_geometry_sha256"]
        or protocol.get("scene_revision") != gate["scene_revision"]
        or protocol.get("scene_seeds") != gate["ordered_seeds"]
        or any(protocol.get(k) != v for k, v in identity.items())
        or [r.get("policy_seed") for r in rows] != gate["ordered_seeds"]
        or [r.get("seed") for r in rows] != gate["ordered_seeds"]
    ):
        raise ValueError("Development rollout does not match the frozen policy, scene and seeds")
    for row, expected in zip(rows, gate["starts"], strict=True):
        if (
            any(
                row.get(k) != expected[k]
                for k in ("initial_qpos_sha256", "initial_parameters_sha256", "reference_png_sha256")
            )
            or row.get("reference_rgb_sha256") != expected["initial_rgb_sha256"]
            or not re.fullmatch(r"[0-9a-f]{64}", row.get("initial_rgb_sha256", ""))
            or row["rgb_channels"] <= 0
            or not 0 <= row["rgb_max_level_error"] <= 1
            or not 0 <= row["rgb_different_channels"] <= row["rgb_channels"] * 0.00001
        ):
            raise ValueError("Development camera or physical start differs from the verified reference")
    fingerprints = [r["initial_qpos_sha256"] for r in rows]
    if any(not isinstance(s, str) or len(s) != 64 for s in fingerprints) or (starts and starts != fingerprints):
        raise ValueError("Paired development starts differ")
    for r in rows:
        if (
            r.get("outcome") not in {"success", "failure"}
            or type(r.get("ever_held")) is not bool
            or type(r["max_lift_cm"]) not in (float, int)
            or not math.isfinite(r["max_lift_cm"])
            or r["max_lift_cm"] < 0
        ):
            raise ValueError("Incomplete physical outcome or lift measurement")
    return {
        "scenes": len(rows),
        "task_successes": sum(r["outcome"] == "success" for r in rows),
        "holds": sum(r["ever_held"] for r in rows),
        "lifts": sum(r["max_lift_cm"] >= gate["lift_cm"] for r in rows),
        "max_lift_cm": max(r["max_lift_cm"] for r in rows),
        "initial_qpos_sha256": fingerprints,
        "checkpoint": str(model),
        **{k: v for k, v in identity.items() if k != "processors"},
    }


def run_evaluator(args, *, env, log):
    # The Jobs cgroup owns this child and its policy worker. Use a dedicated process
    # group so a renderer stall can terminate just this evaluation before retrying.
    with subprocess.Popen(
        args, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
    ) as child:
        try:
            child.wait(timeout=3600)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            raise TimeoutError("Development simulation exceeded its one-hour deadline") from None
        return subprocess.CompletedProcess(args, child.returncode)


def checked_summary(result, gate, model, bundle, starts, replays):
    summary = summarize(result, gate, model, bundle, starts)
    for row in result["trials"]:
        trace = read(replays / f"floor-trial-{row['seed']}.json")
        if (
            trace.get("seed") != row["seed"]
            or trace.get("profile") != PROFILE
            or trace.get("outcome") != row["outcome"]
            or not (trace.get("fps", 0) > 0)
            or trace.get("checkpoint_sha256") != bundle["checkpoint_sha256"]
            or trace.get("model") != gate["expected_geometry_sha256"]
            or len(trace.get("qpos", [])) != row["steps"] + 1
        ):
            raise ValueError("Incomplete or mismatched replay")
    return {**summary, "replays": str(replays)}


def evaluate_gate(folder, gate, model, device, starts, log):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "evaluation.json"
    bundle = bundle_identity(model)
    if target.is_file():
        try:
            result = read(target)
            replays = Path(result["replays"])
            if replays.parent != folder:
                raise ValueError("Replay folder is outside its gate")
            return checked_summary(result, gate, model, bundle, starts, replays)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # Keep a damaged cached receipt for diagnosis before replaying the same saved model.
            invalid = folder / f"rejected-{len(list(folder.glob('rejected-*.json'))) + 1:03}.json"
            target.rename(invalid)
            print(f"Rechecking {model}: cached evaluation rejected: {exc}", file=log, flush=True)
    for attempt in range(2):
        # Preserve incomplete or failed evidence on an explicit retry of this job.
        path = folder / f"attempt-{len(list(folder.glob('attempt-*'))) + 1:03}"
        path.mkdir()
        raw = path / "evaluation.json"
        write(path / "starts.json", gate["starts"])
        args = [
            str(ROOT / ".venv-sim/bin/python"),
            "-m",
            "explorer4.sim.evaluate",
            str(model),
            str(raw),
            "--profile",
            PROFILE,
            "--seeds",
            *map(str, gate["ordered_seeds"]),
            "--record-floor",
            "--seed-policy-per-scene",
            "--device",
            device,
            "--development-starts",
            str(path / "starts.json"),
            "--expected-model-sha256",
            gate["expected_geometry_sha256"],
        ]
        print(" ".join(args), file=log, flush=True)
        try:
            env = {**offline_environment(), "MUJOCO_GL": "egl"}
            env.pop("EXPLORER_N_ACTION_STEPS", None)
            with (path / "rollout.log").open("w") as out:
                proc = run_evaluator(args, env=env, log=out)
            if proc.returncode:
                raise RuntimeError(f"Simulator exited {proc.returncode}")
            result = read(raw)
            summary = checked_summary(result, gate, model, bundle, starts, path)
            result["replays"] = str(path)
            write(target, result)
            return summary
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            write(path / "technical-error.json", {"error": str(exc)})
            if attempt == 1:
                raise RuntimeError(
                    "Development gate unavailable; resume from the saved optimizer checkpoint"
                ) from exc


class NativeStageInterrupted(RuntimeError):
    """A native child ended before its expected publication or final exit."""


def resume_command(model):
    return [
        sys.executable,
        "-m",
        "lerobot.scripts.lerobot_train",
        f"--config_path={model}/train_config.json",
        "--resume=true",
    ]


def train_stage(command, stop, log):
    args = command
    if stop is not None:
        if command[:3] != [sys.executable, "-m", "lerobot.scripts.lerobot_train"]:
            raise ValueError("Unexpected native trainer")
        args = [
            sys.executable,
            "-m",
            "explorer4.floor_development_gate",
            "--until-published",
            str(stop),
            "--",
            *command[3:],
        ]
    print(" ".join(args), file=log, flush=True)
    code = subprocess.run(
        args, cwd=ROOT, env=offline_environment(), stdout=log, stderr=subprocess.STDOUT, check=False
    ).returncode
    if code != (PUBLISHED if stop is not None else 0):
        raise NativeStageInterrupted(f"Native trainer exited {code} before expected boundary {stop}")


def run(work, output, cfg, batch, command, resume, log):
    gate = cfg["floor_development_gate"]
    if (
        not cfg.get("draft_id")
        or cfg.get("domain") != "sim"
        or cfg.get("initial_checkpoint")
        or cfg.get("smoke")
        or {key: value for key, value in gate.items() if key != "starts"}
        != recipe(cfg["profile"], cfg["policy"], cfg["steps"], gate["expected_geometry_sha256"])
    ):
        raise ValueError("Gate applies only to its reviewed raw-policy draft")
    validate_starts(gate["starts"])
    folder = work / "development-gate"
    status_file = folder / "status.json"
    steps = cfg["steps"]
    state = {
        "status": "preparing",
        "gate": gate,
        "draft_id": cfg["draft_id"],
        "requested_steps": steps,
        "last_step": 0,
        "last_checkpoint": None,
        "selected_step": None,
        "selected_checkpoint": None,
        "checks": [],
        "trainer_recoveries": [],
        "test_used": False,
        "physical_commands": 0,
    }
    previous_checks = {}
    if status_file.exists():
        previous = read(status_file)
        state["trainer_recoveries"] = previous.get("trainer_recoveries", [])
        previous_checks = {row["step"]: row["checkpoint_bundle_sha256"] for row in previous["checks"]}
        if (
            previous["gate"] != gate
            or previous["draft_id"] != cfg["draft_id"]
            or previous["requested_steps"] != steps
        ):
            raise ValueError("Prior gate belongs to another training plan")
    starts = None
    current = Path(resume).resolve() if resume else None
    completed = int(current.parent.name) if current else 0
    if current and current != checkpoint_at(output, completed, steps, cfg["policy"], batch).resolve():
        raise ValueError("Resume checkpoint is outside this training job")
    write(status_file, state)
    try:
        for step in [*gate["checkpoints"], steps]:
            if completed < step:
                state.update(status="training", target_step=step)
                write(status_file, state)
                if current:
                    command = resume_command(current)
                stop = None if step == steps else step
                try:
                    train_stage(command, stop, log)
                except NativeStageInterrupted as exc:
                    # Retry once only after new, fully published optimizer progress.
                    link = output / "checkpoints/last"
                    if not link.is_symlink() or not link.resolve().name.isdecimal():
                        raise
                    recovered = int(link.resolve().name)
                    if not completed < recovered <= step:
                        raise
                    saved = checkpoint_at(output, recovered, steps, cfg["policy"], batch).resolve()
                    if saved.parent != link.resolve():
                        raise ValueError("Published recovery path is outside this job") from exc
                    state["trainer_recoveries"].append(
                        {"target_step": step, "saved_step": recovered, "error": str(exc)}
                    )
                    state.update(last_step=recovered, last_checkpoint=str(saved))
                    write(status_file, state)
                    print(f"Recovering from published step {recovered} after {exc}", file=log, flush=True)
                    if recovered < step:
                        train_stage(resume_command(saved), stop, log)
                current = checkpoint_at(output, step, steps, cfg["policy"], batch).resolve()
                if (output / "checkpoints/last").resolve() != current.parent:
                    raise ValueError("Native trainer did not publish the expected last checkpoint")
                completed = step
            model = checkpoint_at(output, step, steps, cfg["policy"], batch).resolve()
            state.update(
                status="evaluating", target_step=step, last_step=completed, last_checkpoint=str(current)
            )
            write(status_file, state)
            summary = evaluate_gate(folder / str(step), gate, model, cfg["device"], starts, log)
            if step in previous_checks and previous_checks[step] != summary["checkpoint_bundle_sha256"]:
                raise ValueError("Published weights or processor assets changed after their earlier evaluation")
            starts = summary.pop("initial_qpos_sha256")
            state["checks"].append(
                {"step": step, "result": str(folder / str(step) / "evaluation.json"), **summary}
            )
            print(
                f"Development {step}: {summary['holds']} holds, {summary['lifts']} lifts, {summary['task_successes']} successes of {summary['scenes']}",
                file=log,
                flush=True,
            )
            if step == gate["checkpoints"][-1] and all(c["holds"] == c["lifts"] == 0 for c in state["checks"]):
                state.update(status="stopped_no_grasp_signal", reason=gate["early_stop"])
                break
        else:
            best = max(state["checks"], key=lambda c: (c["task_successes"], c["holds"], c["lifts"], -c["step"]))
            state.update(
                status="completed",
                selected_step=best["step"],
                selected_checkpoint=best["checkpoint"],
                selected_checkpoint_sha256=best["checkpoint_sha256"],
                reason=gate["selection"],
            )
    except Exception as exc:
        state.update(status="technical_error", reason=str(exc))
        write(status_file, state)
        raise
    write(status_file, state)
    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--until-published", type=int, required=True)
    parser.add_argument("trainer_arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.until_published not in BOUNDARIES or args.trainer_arguments[:1] != ["--"]:
        parser.error("Unsupported checkpoint boundary")
    sys.exit(native_until(args.until_published, args.trainer_arguments[1:]))
