"""Run the real ROSMASTER native arm guards against MuJoCo feedback, without a transport."""

import argparse
import json
import sys
import types
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path
from unittest.mock import patch

import numpy as np

from explorer4.conditioned_grasp import SLEW_DEGREES_PER_SECOND, file_hash
from explorer4.grasp_shadow import close_to_look_state
from explorer4.paths import DATA, ROOT
from scripts.grasp_study.evaluate import (
    GraspMetrics,
    OUTPUT,
    environment,
    observe,
    save_json,
    trajectory_targets,
)

NATIVE = DATA / "provenance/rosmaster-own-runtime-20261114/native"
METHODS = ("rbf", "act", "diffusion")
REFERENCE = DATA / "datasets/rosmaster_pick_place/d8187db7e725432596d90e9111ccb2d6/research.jsonl"


def mock_executor(env, settings):
    def reject_serial(*args, **kwargs):
        raise AssertionError("No hardware transport exists in this experiment")

    with (
        patch.dict(sys.modules, {"serial": types.SimpleNamespace(Serial=reject_serial)}),
        patch.object(sys, "path", [str(ROOT / "agents/rosmaster"), str(NATIVE), *sys.path]),
    ):
        from runtime import NativeIO, RelaxedArm, Runtime
        from cubebot.arm_model import ArmModel
    # Constructors acquire serial devices. Only the pure control methods are exercised.
    executor = object.__new__(Runtime)
    io = object.__new__(NativeIO)
    executor.io = io
    executor.cfg = io.cfg = {"manual_base": {}, "arm": settings}
    executor.profile = "rosmaster_pick_place"
    executor.model = ArmModel(settings["tcp_offset_m"])
    executor.core = types.SimpleNamespace(measured_arm=lambda age: env.observation()["state"].tolist())
    io.runtime = executor
    io._arm_cmd = io.measured_arm()
    io.arm = RelaxedArm(executor.model, io.arm_command)

    def zero_base(*v, manual):
        if any(v) or not manual:
            raise AssertionError("Unexpected chassis command")

    def simulated_arm(target, duration):
        if duration != 160 or not executor.model.within_limits(target):
            raise AssertionError("Unexpected native arm contract")

    io.drive = zero_base
    io._publish_arm = simulated_arm
    return executor


def simulate(env, plan, height, settings):
    executor = mock_executor(env, settings)
    metrics = GraspMetrics(env, height)
    command = env.observation()["state"].astype(float)
    if not close_to_look_state(command):
        raise RuntimeError("Saved simulator look differs from the physical observation contract")
    max_gap = np.zeros(6)
    max_tracking = np.zeros(6)
    ticks = 0
    for target in trajectory_targets(plan):
        now = env.steps * env.dt
        command += np.clip(
            target - command, -SLEW_DEGREES_PER_SECOND * env.dt, SLEW_DEGREES_PER_SECOND * env.dt
        )
        executor.direct = (now, executor.validate_direct({"arm": command.tolist()}))
        actual = np.array(executor.io.measured_arm())
        previous = np.array(executor.io.arm_command())
        max_tracking = np.maximum(max_tracking, np.abs(previous - actual))
        try:
            executor.direct_step(env.dt, now)
        except (ValueError, RuntimeError) as exc:
            reason = "native_guard: " + str(exc)
            break
        native = executor.io.arm_command()
        max_gap = np.maximum(max_gap, np.abs(command - native))
        _, _, done, timeout, info = env.step(native)
        ticks += 1
        metrics.measure(env, info)
        if done or timeout:
            reason = info["termination_reason"]
            break
    return {
        **metrics.result(reason, env.steps),
        "executed_control_steps": ticks,
        "max_requested_to_native_deg": max_gap.tolist(),
        "max_native_to_measured_deg": max_tracking.tolist(),
    }


def worker(seeds):
    with REFERENCE.open() as f:
        limits = json.loads(next(f))["control_limits"]
    settings = limits["arm_settings"]
    env = environment()
    report = json.loads((OUTPUT / "fresh/summary.json").read_text())
    with np.load(OUTPUT / "fresh/plans.npz") as plans:
        rows = []
        try:
            for seed in seeds:
                prior = next(row for row in report["trials"] if row["seed"] == seed)
                initial, _ = observe(env, seed, render=False)
                if initial != prior["initial"]:
                    raise ValueError("Initial simulation state no longer matches the registered scene")
                snapshot = env.snapshot()
                results = {}
                for method in METHODS:
                    env.restore(snapshot)
                    result = simulate(env, plans[f"{seed}_{method}"], initial["cube"][2], settings)
                    result["published_sim_outcome"] = prior["arms"][method]["outcome"]
                    results[method] = result
                rows.append({"seed": seed, "methods": results})
                print(seed, [results[k]["reason"] for k in METHODS], flush=True)
        finally:
            env.close()
    return rows


def run(workers, output):
    seeds = list(range(940200, 940220))
    with ProcessPoolExecutor(workers, mp_context=get_context("spawn")) as pool:
        groups = pool.map(worker, [seeds[i::workers] for i in range(workers)])
        rows = sorted((row for group in groups for row in group), key=lambda r: r["seed"])
    summary = {
        "domain": "MuJoCo with archived native ROSMASTER direct-arm control",
        "physical_trials": 0,
        "physical_transport": "absent",
        "optimizer_updates": 0,
        "methods": list(METHODS),
        "trials": rows,
        "source_sha256": {
            "native_executor": file_hash(ROOT / "agents/rosmaster/runtime.py"),
            "native_base_io": file_hash(NATIVE / "cubebot/robot_io.py"),
            "native_arm_model": file_hash(NATIVE / "cubebot/arm_model.py"),
            "paired_plans": file_hash(OUTPUT / "fresh/plans.npz"),
        },
        "native_limits": {
            "source": "recorded ROSMASTER development telemetry",
            "floor_margin_m": 0.012,
            "tcp_offset_m": 0.085,
            "frequency_hz": 20,
            "servo_slew_deg_s": 60,
            "native_limit_inset_deg": 1,
            "tracking_stop_deg": 12,
        },
        "successes": {m: sum(row["methods"][m]["outcome"] == "success" for row in rows) for m in METHODS},
        "native_stops": {
            m: sum(row["methods"][m]["reason"].startswith("native_guard:") for row in rows) for m in METHODS
        },
        "limitations": "Controlled physics mock with simulated servo feedback and unchanged native guard code. Physical camera calibration, controller tracking, latency and physical task outcome require measurements.",
    }
    save_json(output, summary)
    print(summary["successes"], summary["native_stops"], flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workers", type=int, choices=[1, 2, 3, 4], default=2)
    p.add_argument("--output", type=Path, default=OUTPUT / "native-execution.json")
    a = p.parse_args()
    run(a.workers, a.output)
