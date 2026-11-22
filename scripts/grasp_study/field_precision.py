"""Check the production FP32 localizer and SciPy plan path on the already opened 16 RGB images."""
import json
from pathlib import Path
import time
import cv2
import numpy as np
import torch

from explorer4.conditioned_grasp import file_hash, locate_cube
from explorer4.grasp_admission import MeasuredActions
from explorer4.grasp_localizer import close_field, prewarm_field
from explorer4.paths import DATA, ROOT
from .evaluate import SOURCE, VISION, save_json, sha_array

STUDY = DATA / "simlab/reports/grasp-look-refresh-development-v1-1"


def verify():
    reference = json.loads((STUDY / "cuda-timing.json").read_text())
    if [r["seed"] for r in reference["frames"]] != [s for s in range(940100, 940108) for _ in range(2)]:
        raise ValueError("Unrecognized development frames or order")
    scenes = {r["seed"]: r for r in json.loads((STUDY/"result.json").read_text())["scenes"]}
    cv2.setNumThreads(1)
    torch.set_num_threads(1)
    flags = (torch.backends.cudnn.allow_tf32, torch.backends.cuda.matmul.allow_tf32)
    t0 = time.perf_counter()
    localizer = prewarm_field()
    if prewarm_field() is not localizer:
        raise ValueError("Field worker was not reused")
    startup = (time.perf_counter()-t0)*1000
    policy = MeasuredActions(None, SOURCE, VISION, "rbf", None, localizer=localizer)
    rows = []
    try:
        for ref in reference["frames"]:
            seed, condition = ref["seed"], ref["condition"]
            frame = scenes[seed]["conditions"][condition]["second_rgb_file"]
            rgb = cv2.imread(str(STUDY / frame))[:, :, ::-1].copy()
            if sha_array(rgb) != ref["rgb_sha256"]:
                raise ValueError("Frame identity mismatch")
            cpu = policy.plan_for_xy(np.asarray(ref["cpu_xy"], dtype=np.float32))
            if sha_array(cpu) != ref["cpu_plan_sha256"]:
                raise ValueError("Field XY scaling diverges from the archived CPU trajectory")
            times = []
            for _ in range(6):
                started = time.perf_counter_ns()
                xy = locate_cube(localizer, rgb)
                plan = policy.plan_for_xy(xy)
                times.append((time.perf_counter_ns()-started)/1e6)
                if xy.tolist() != ref["gpu_xy"] or sha_array(plan) != ref["gpu_plan_sha256"]:
                    raise ValueError("Isolated field worker diverges from original FP32 GPU result")
            rows.append(dict(seed=seed, condition=condition, rgb_sha256=ref["rgb_sha256"], plan_sha256=sha_array(plan),
                        six_servo_targets=len(plan), times_ms=times, xy_in_demonstration_hull=bool(policy.support.find_simplex(xy)>=0),
                        cpu_delta_deg=float(np.max(np.abs(cpu-plan)))))
    finally:
        close_field()
    if localizer.process.poll() is None or flags != (torch.backends.cudnn.allow_tf32, torch.backends.cuda.matmul.allow_tf32):
        raise ValueError("Worker cleanup or UI precision isolation failed")
    samples = [v for row in rows for v in row["times_ms"]]
    result = dict(scope="Six warmed end-to-end RGB-to-plan measurements on each of 16 previously opened synthetic development images. Includes CPU preprocessing, both IPC directions, GPU transfers, synchronous FP32 inference, and the production SciPy calculation of 220 six-servo targets. No physical calibration, image acquisition, ROS transport, hull admission or action dispatch was timed.",
                  source_sha256={s:file_hash(ROOT/s) for s in ("explorer4/grasp_localizer.py","explorer4/grasp_admission.py","explorer4/grasp_shadow.py","explorer4/grasp_trial.py","explorer4/rosmaster_session.py","scripts/grasp_study/field_precision.py")},
                  previous_timing_sha256=file_hash(STUDY/"cuda-timing.json"), original_gpu_plans_matched=len(rows),
                  prior_cpu_plans_matched_on_identical_xy=len(rows), all_repeat_gpu_plan_hashes_matched=len(samples),
                  eligible_by_xy_hull=sum(r["xy_in_demonstration_hull"] for r in rows),
                  scope_of_hull="The numeric planner was compared on all views, including unsupported XY. Field start separately requires an admitted point inside the hull and all physical checks.",
                  parent_tf32_flags=list(flags), parent_flags_preserved=True, child_exited_after_release=True,
                  cold_worker_startup_ms=startup, ready_rgb_plan_ms=dict(n=len(samples),p50=float(np.median(samples)),p95=float(np.percentile(samples,95)),maximum=max(samples),within_40ms=sum(t<=40 for t in samples)),
                  largest_cpu_gpu_trajectory_difference_deg=max(r["cpu_delta_deg"] for r in rows), physical_trials=0, optimizer_updates=0, frames=rows)
    save_json(STUDY / "field-precision-v2.json", result)
    print(json.dumps({k:v for k,v in result.items() if k!="frames"}, indent=2))


if __name__ == "__main__":
    verify()
