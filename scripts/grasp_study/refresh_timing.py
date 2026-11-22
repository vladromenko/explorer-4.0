"""Measure the frozen wrist-image refresh on the 16 previously opened development views.

On Homebrain use the simulation environment with its site-packages first and the UI
environment's site-packages second in PYTHONPATH, MUJOCO_GL=egl, PYOPENGL_PLATFORM=egl,
OPENBLAS_NUM_THREADS=1 and OMP_NUM_THREADS=1. No actuators, fitting or test scenes.
"""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import random
import time

import cv2
import mujoco
import numpy as np
import scipy
import torch

from explorer4.conditioned_grasp import MOTOR_SHA256, VISION_SHA256, file_hash, load_localizer, locate_cube
from explorer4.grasp_admission import prewarm
from explorer4.grasp_shadow import ArchiveGraspActions
from .evaluate import SOURCE, VISION, environment, observe, save_json, sha_array
from .refresh import DEST, SEEDS, capture, restore, snapshot_hash


REPEATS = 6
BUDGET_MS = 40
STAGES = ("ready_rgb", "egl_render_to_plan")
DEVICES = ("cpu", "cuda")
CPU_TIMING_SCOPE = "Single-thread CPU localization and FP64-input SciPy thin-plate spline. One image per request."


def rgb_from_egl(env):
    return cv2.resize(env.render(), (160, 120), interpolation=cv2.INTER_AREA)


def plan(estimator, rgb, rbf):
    xy = locate_cube(estimator, rgb)
    return xy, rbf(xy.astype(np.float64)[None] / 0.05)[0]


def measured(estimator, rbf, device, get_image):
    if device == "cuda":
        torch.cuda.synchronize()
    start = time.perf_counter_ns()
    image = get_image()
    xy, targets = plan(estimator, image, rbf)
    if device == "cuda":
        torch.cuda.synchronize()
    elapsed = (time.perf_counter_ns() - start) / 1e6
    return elapsed, image, xy, targets


def describe(samples):
    return dict(n=len(samples), p50_ms=float(np.percentile(samples, 50)),
                p95_ms=float(np.percentile(samples, 95)), max_ms=float(np.max(samples)),
                within_40ms=sum(t <= BUDGET_MS for t in samples))


def main(output):
    if os.environ.get("MUJOCO_GL") != "egl" or os.environ.get("OPENBLAS_NUM_THREADS") != "1":
        raise ValueError("Timing requires EGL and one OpenBLAS thread")
    if not torch.cuda.is_available():
        raise ValueError("Timing requires the physical Homebrain CUDA GPU")
    cv2.setNumThreads(1)
    torch.set_num_threads(1)
    default_tf32 = dict(cudnn=torch.backends.cudnn.allow_tf32, matmul=torch.backends.cuda.matmul.allow_tf32)
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cuda.matmul.allow_tf32 = False
    cpu = load_localizer(VISION)
    gpu = prewarm()
    estimators = {"cpu": cpu, "cuda": gpu}
    policy = ArchiveGraspActions(None, SOURCE, VISION, "rbf", None, localizer=cpu)
    original = json.loads((DEST / "result.json").read_text())
    if original["protocol_sha256"] != file_hash(DEST / "protocol.json") or [r["seed"] for r in original["scenes"]] != list(SEEDS):
        raise ValueError("Unexpected source protocol or development scenes")
    if not all(p.dtype == torch.float32 for p in gpu.network.parameters()):
        raise ValueError("Original CUDA localizer must be FP32")
    warm = cv2.imread(str(DEST / original["scenes"][0]["conditions"]["static"]["second_rgb_file"]))[:, :, ::-1]
    for _ in range(REPEATS):
        for estimator in estimators.values():
            plan(estimator, warm, policy.rbf)
    torch.cuda.synchronize()
    samples = {s: defaultdict(list) for s in STAGES}
    rows = []
    env = environment()
    try:
        for i, scene in enumerate(original["scenes"]):
            seed = scene["seed"]
            random.seed(seed)
            np.random.seed(seed)
            torch.manual_seed(seed)
            reset, _ = observe(env, seed, render=False)
            initial = capture(env)
            if reset["reset_sha256"] != scene["reset_sha256"] or sha_array(initial["physics"]) != scene["look_physics_sha256"]:
                raise ValueError("Wrong development reset or look pose")
            for j, condition in enumerate(("static", "shifted")):
                ref = scene["conditions"][condition]
                stored = cv2.imread(str(DEST / ref["second_rgb_file"]))[:, :, ::-1].copy()
                if sha_array(stored) != ref["second_rgb_sha256"]:
                    raise ValueError("Archived second frame differs")
                cpu_xy, cpu_plan = plan(cpu, stored, policy.rbf)
                if cpu_xy.tolist() != ref["second_xy"] or sha_array(cpu_plan) != ref["arms"]["refreshed_xy"]["plan_sha256"]:
                    raise ValueError("CPU baseline does not reproduce the frozen archive")
                gpu_xy, gpu_plan = plan(gpu, stored, policy.rbf)
                # Runtime currently scales float32 XY before passing it to SciPy.
                field_plan = policy.rbf(gpu_xy[None] / 0.05)[0]
                row = dict(seed=seed, condition=condition, rgb_sha256=ref["second_rgb_sha256"],
                           xy_delta_mm=float(np.linalg.norm(gpu_xy.astype(float) - cpu_xy)*1000),
                           plan_max_abs_delta_deg=float(np.max(np.abs(gpu_plan - cpu_plan))),
                           field_scaling_delta_deg=float(np.max(np.abs(field_plan-gpu_plan))),
                           cpu_plan_sha256=sha_array(cpu_plan), gpu_plan_sha256=sha_array(gpu_plan),
                           cpu_xy=cpu_xy.tolist(), gpu_xy=gpu_xy.tolist(), times_ms={})
                restore(env, initial)
                env.data.qpos[int(env.model.joint("cube_free").qposadr[0])+1] += ref["shift_y_m"]
                mujoco.mj_forward(env.model, env.data)
                branch = capture(env)
                comparable = {k: v for k, v in branch.items() if k != "cuda_rng"}
                if (sha_array(branch["physics"]) != ref["branch_physics_sha256"] or
                    snapshot_hash(comparable) != ref["branch_full_state_sha256"]):
                    raise ValueError("Open branch dynamics, controls or non-CUDA random state changed")
                if i == 0 and j == 0:
                    t0 = time.perf_counter_ns()
                    first_frame = rgb_from_egl(env)
                    cold_egl_ms = (time.perf_counter_ns()-t0) / 1e6
                    cold_egl_rgb_sha256 = sha_array(first_frame)
                    from OpenGL import GL
                    gl = {k: GL.glGetString(v).decode() for k, v in
                          (("vendor", GL.GL_VENDOR), ("renderer", GL.GL_RENDERER), ("version", GL.GL_VERSION))}
                row["repeat_gpu_max_delta_deg"] = 0.
                row["egl_captures"] = []
                for stage in STAGES:
                    dt = {k: [] for k in DEVICES}
                    for repeat in range(REPEATS):
                        order = DEVICES if (i+j+repeat) % 2 == 0 else DEVICES[::-1]
                        # Both architectures receive the exact same fresh pixels. Only the
                        # first backend after a render has a contiguous capture-to-plan timer.
                        torch.cuda.synchronize()
                        start_ns = time.perf_counter_ns()
                        rgb = stored if stage == "ready_rgb" else rgb_from_egl(env)
                        outputs = {}
                        for position, device in enumerate(order):
                            ms, _, xy, targets = measured(estimators[device], policy.rbf, device, lambda: rgb)
                            elapsed = ms if stage == "ready_rgb" else (time.perf_counter_ns()-start_ns)/1e6
                            if stage == "ready_rgb" or position == 0:
                                samples[stage][device].append(elapsed)
                                dt[device].append(elapsed)
                            outputs[device] = xy, targets
                        pair_cpu_xy, pair_cpu = outputs["cpu"]
                        pair_gpu_xy, pair_gpu = outputs["cuda"]
                        if pair_cpu.shape != cpu_plan.shape or pair_gpu.shape != cpu_plan.shape or not all(
                            np.isfinite(a).all() for a in (pair_cpu, pair_gpu, pair_cpu_xy, pair_gpu_xy)
                        ):
                            raise ValueError("Invalid six-channel plan")
                        row["plan_max_abs_delta_deg"] = max(row["plan_max_abs_delta_deg"], float(np.max(np.abs(pair_gpu-pair_cpu))))
                        row["xy_delta_mm"] = max(row["xy_delta_mm"], float(np.linalg.norm(pair_gpu_xy.astype(float)-pair_cpu_xy)*1000))
                        if stage == "ready_rgb":
                            if not np.array_equal(pair_cpu, cpu_plan):
                                raise ValueError("Original CPU trajectory changed on a stored frame")
                            row["repeat_gpu_max_delta_deg"] = max(row["repeat_gpu_max_delta_deg"], float(np.max(np.abs(pair_gpu-gpu_plan))))
                        else:
                            difference = np.abs(rgb.astype(np.int16)-stored.astype(np.int16))
                            row["egl_captures"].append(dict(
                                rgb_sha256=sha_array(rgb), timed_backend=order[0],
                                changed_channels=int(np.count_nonzero(difference)), max_uint8_delta=int(difference.max())
                            ))
                    row["times_ms"][stage] = dt
                rows.append(row)
                print(f"{seed} {condition} verified", flush=True)
    finally:
        env.close()
    timings = {s: {d: describe(samples[s][d]) for d in DEVICES} for s in STAGES}
    out = dict(parent_protocol_sha256=original["protocol_sha256"], source_results_sha256=file_hash(DEST/"result.json"),
               runner_sha256=file_hash(Path(__file__)), vision_sha256=VISION_SHA256, motor_sha256=MOTOR_SHA256,
               scope="Eight existing synthetic development scenes, static and shifted. Six repetitions on every stored frame (96 per backend). For each of six fresh EGL frames per scene condition, the two backends share its bytes; alternating the first backend produces 48 contiguous readback-to-plan measurements per backend. Sixteen views, eight independent scenes.",
               cuda_path="The cached production prewarm() -> InferenceLocalizer with unchanged FP32 weights, including CPU preprocessing, host-device transfer, forward pass, device-host transfer, CPU SciPy trajectory, and explicit CUDA synchronization.",
               cpu_path=CPU_TIMING_SCOPE, egl_path="Warmed MuJoCo EGL render at 640x480, GPU readback, area resize to 160x120, localization and complete six-channel RBF plan. No physics ticks elapse during timing. All non-CUDA branch states match the original. CPU and CUDA consume the exact same captured image within each pair. Compare this warmed capture with the single archived capture using the reported pixel differences.",
               field_scope="Physical camera, exposure and frame age, network transport, calibrations, template checks, servo guards and transmission are outside this benchmark.",
               egl_captures_exactly_matching_archive=sum(c["rgb_sha256"]==r["rgb_sha256"] for r in rows for c in r["egl_captures"]),
               egl_largest_changed_channel_count=max(c["changed_channels"] for r in rows for c in r["egl_captures"]),
               egl_largest_uint8_delta=max(c["max_uint8_delta"] for r in rows for c in r["egl_captures"]),
               cold_egl_rgb_sha256=cold_egl_rgb_sha256,
               machine=Path("/proc/device-tree/model").read_bytes().rstrip(b"\0").decode(), cuda=torch.cuda.get_device_name(),
               libraries=dict(torch=torch.__version__, cuda=torch.version.cuda, scipy=scipy.__version__, mujoco=mujoco.__version__, opencv=cv2.__version__),
               egl=gl, torch_default_tf32=default_tf32, tested_tf32=False, fp16=False, reps_per_frame=REPEATS,
               budget_ms=BUDGET_MS, cold_egl_first_capture_ms=cold_egl_ms, warm_timings=timings,
               xy_max_delta_mm=max(r["xy_delta_mm"] for r in rows),
               joint_plan_max_abs_delta_deg=max(r["plan_max_abs_delta_deg"] for r in rows),
               gpu_repeat_max_abs_delta_deg=max(r["repeat_gpu_max_delta_deg"] for r in rows),
               field_input_scaling_max_abs_delta_deg=max(r["field_scaling_delta_deg"] for r in rows),
               frozen_cpu_plan_shapes=list(cpu_plan.shape), completed_rollouts=0, physical_trials=0, optimizer_updates=0,
               recommendation="Prewarm once before arming. Explicitly select FP32 without TF32 and convert metric XY to float64 before dividing by 0.05, matching the study. For field qualification, time exposure/frame timestamp to the fully validated plan on live passive camera samples; retain refusal on stale frames and the existing actuator gates.",
               frames=rows)
    save_json(output, out)
    print(json.dumps({k: v for k, v in out.items() if k != "frames"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEST / "cuda-timing.json")
    main(parser.parse_args().output)
