"""Predeclare, run and summarize the paired RGB-only cube localization and native grasp study."""

import argparse
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from scipy.stats import binomtest

from explorer4.conditioned_grasp import (
    MOTOR_SHA256,
    PHYSICS_SHA256,
    VISION_SHA256,
    file_hash,
    load_localizer,
    locate_cube,
)
from explorer4.paths import ROOT
from scripts.grasp_study import admission_native as native
from scripts.grasp_study.admission_native_v3 import IntegerVisibility, OUT as DIAGNOSTIC
from scripts.grasp_study.coverage_design import settings, SETTINGS_SOURCE
from scripts.grasp_study.evaluate import SOURCE, VISION, environment, observe, save_json, sha_array
from .data import OUT, SPLITS, TEST, original, shards

SOURCES = ["scripts/grasp_study/wrist_heatmap/" + s + ".py" for s in ("data", "model", "train", "study")]
SOURCES += list(native.SOURCE_FILES) + [
    "scripts/grasp_study/admission_native_v3.py",
    "scripts/recorded_start_visual_pick.py",
]
METHODS = ("baseline", "keypoint")


def read(path):
    return json.loads(path.read_text())


def protocol():
    import torch

    imagenet = Path(torch.hub.get_dir()) / "checkpoints/resnet18-f37072fd.pth"
    origin = read(original.RUN / "protocol.json")
    for role, ids in SPLITS.items():
        if origin[role] != [ids[0], ids[-1]] or set(TEST).intersection(ids):
            raise ValueError("Original image splits differ")
    if original.digest(imagenet) != read(original.RUN / "fit.json")["base_weights_sha256"]:
        raise ValueError("ImageNet source differs from the benchmark model")
    if file_hash(SOURCE) != MOTOR_SHA256 or file_hash(VISION) != VISION_SHA256:
        raise ValueError("Changed baseline or motor bank")
    return {
        "schema": "wrist-cube-keypoint-v1",
        "physical_trials": 0,
        "test_seeds": list(TEST),
        "training": [SPLITS["training"][0], SPLITS["training"][-1]],
        "validation": [SPLITS["validation"][0], SPLITS["validation"][-1]],
        "opened_diagnostics": read(DIAGNOSTIC / "result.json")["conditional"]["selected"],
        "image_shards_sha256": {split: {p.name: file_hash(p) for p in shards(split)} for split in SPLITS},
        "label_shards_sha256": {
            split: {p.name: file_hash(OUT / "labels" / split / p.name) for p in shards(split)}
            for split in SPLITS
        },
        "weights": {
            "imagenet": file_hash(imagenet),
            "direct_rgb_regression": VISION_SHA256,
            "motor": MOTOR_SHA256,
        },
        "physics_sha256": PHYSICS_SHA256,
        "sources_sha256": {s: file_hash(ROOT / s) for s in SOURCES},
        "native_settings_sha256": file_hash(SETTINGS_SOURCE),
        "hardware_adapter": {
            n: file_hash(native.NATIVE / "cubebot" / n) for n in ("robot_io.py", "arm_model.py")
        },
        "architecture": "Torchvision ImageNet-1K ResNet-18 through layer2, fused stride-4 heatmap, expected pixel, train-only planar homography and learned image-conditioned XY residual.",
        "inputs": "A single wrist RGB after 20 fixed look commands. Pinhole keypoints and XY supervise training only. At inference there is no state, ID mask, depth, bounding box, intrinsics, seed or known target coordinate.",
        "epochs": 30,
        "batch": 32,
        "seed": 1000,
        "selection": "One fit. Earliest lowest validation p90 metric error. No holdout tuning.",
        "method": "Projected object centre scored in low-resolution RGB. Gaussian target with 4-pixel sigma, soft cross entropy and Huber loss (beta=.2) for the trial-specific RGB residual in centimetres. Spatial expectation and planar homography return metric XY.",
        "optimization": "AdamW constant 1.5e-4 backbone, 1e-3 heads, 1e-4 weight decay; uniform saturation [0,1.1] and brightness [.8,1.2].",
        "endpoints": "All 48 ordered fresh starts, no exclusion or replacement. Millimetre p50/p90, error >10 and >20 mm, max and paired wins. Primary motor comparison is simulation-only unrestricted XY input to the same original 32-demo RBF, native bounds and 360 ticks: >50 mm above the floor, held in carry for the final 20 ticks. Separately apply the same v3 visible/full-box & individual predicted motor-hull contract and report whole 48 and common-admitted denominators. The v3 segmentation oracle only classifies admission and never locates the target for the actor.",
        "references": [
            "https://arxiv.org/abs/1711.08229",
            "https://arxiv.org/abs/1804.06208",
            "https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.resnet18.html",
        ],
    }


def verify_protocol():
    row = read(OUT / "protocol.json")
    if row != protocol():
        raise ValueError("Frozen study, source or inputs differ")
    return row


class UnrestrictedSimulation(native.SimulatedActions):
    """Simulation ablation of support/visible-box abstention; all actuator guards are retained."""

    def _start(self, observation, state):
        self.plan = self.plan_for_xy(self.locate(observation, observation["images"]["front"]))
        self.last = state.copy()


def point_result(rgb, old, new, truth):
    xy = locate_cube(old, rgb)
    predicted = new.locate(rgb)
    data = {"baseline": {"xy_m": xy.tolist()}, "keypoint": predicted}
    for prediction in data.values():
        prediction["error_mm"] = float(1000 * np.linalg.norm(np.asarray(prediction["xy_m"]) - truth))
    return data


def held(rows, predicate, counts):
    selected = [r for r in rows if predicate(r)]
    pair = [tuple(bool(counts(r, k)) for k in METHODS) for r in selected]
    gain = pair.count((False, True))
    loss = pair.count((True, False))
    return {
        "n": len(selected),
        "baseline": sum(a for a, b in pair),
        "keypoint": sum(b for a, b in pair),
        "keypoint_only": gain,
        "baseline_only": loss,
        "both": pair.count((True, True)),
        "neither": pair.count((False, False)),
        "two_sided_exact_p": float(binomtest(gain, gain + loss).pvalue) if gain + loss else 1.0,
    }


def evaluate():
    import torch
    from .model import WristCubeLocator
    from .train import errors

    spec = verify_protocol()
    torch.set_num_threads(1)
    cv2.setNumThreads(1)
    args = (None, SOURCE, VISION, "rbf", None)
    old = load_localizer(VISION)
    new = WristCubeLocator(OUT)
    model = UnrestrictedSimulation(*args, localizer=old)
    gate = native.SimulatedActions(*args, localizer=old)
    archive = read(DIAGNOSTIC / "result.json")
    diag_rows = []
    for row in (item for item in archive["candidates"] if item["seed"] in spec["opened_diagnostics"]):
        png = DIAGNOSTIC / "frames" / f"{row['seed']}.png"
        if file_hash(png) != row["png_sha256"]:
            raise ValueError("Changed diagnostic RGB")
        rgb = cv2.imread(str(png))[:, :, ::-1]
        out = point_result(rgb, old, new, row["initial"]["cube"][:2])
        if abs(out["baseline"]["error_mm"] - row["localization_error_mm"]) > 0.001:
            raise ValueError("Diagnostic baseline differs")
        diag_rows.append({"seed": row["seed"], "rgb_sha256": row["rgb_sha256"], **out})
    vis = IntegerVisibility()
    env = environment()
    cfg = settings()
    protocol_sha = file_hash(OUT / "protocol.json")
    fit_sha = file_hash(OUT / "fit.json")
    rows = []

    def no_serial(*args, **kwargs):
        raise AssertionError("The study has no robot transport")

    try:
        with (
            patch.dict(sys.modules, {"serial": types.SimpleNamespace(Serial=no_serial)}),
            patch.object(sys, "path", [str(ROOT / "agents/rosmaster"), str(native.NATIVE), *sys.path]),
            patch.object(native, "OUT", OUT),
        ):
            for seed in TEST:
                path = OUT / "trials" / f"{seed}.json"
                png = OUT / "frames" / f"{seed}.png"
                if path.exists():
                    row = read(path)
                    if (
                        row["seed"] != seed
                        or row["protocol_sha256"] != protocol_sha
                        or row["fit_sha256"] != fit_sha
                        or row["png_sha256"] != file_hash(png)
                    ):
                        raise ValueError("Wrong paired scene or image")
                else:
                    initial, rgb = observe(env, seed)
                    look = sha_array(env.snapshot()["physics"])
                    truth = env.data.body("task_cube").xpos[:2].copy()
                    predictions = point_result(rgb, old, new, truth)
                    png.parent.mkdir(parents=True, exist_ok=True)
                    if not cv2.imwrite(str(png), rgb[:, :, ::-1]):
                        raise OSError(png)
                    row = {
                        "seed": seed,
                        "initial": initial,
                        "truth_xy_m": truth.tolist(),
                        "look_physics_sha256": look,
                        "camera": native.camera(env),
                        "look_pose_native": env.observation()["state"].tolist(),
                        "visibility": vis(env),
                        "rgb_sha256": sha_array(rgb),
                        "png_sha256": file_hash(png),
                        "protocol_sha256": protocol_sha,
                        "fit_sha256": fit_sha,
                        "methods": predictions,
                    }
                    for method, prediction in predictions.items():
                        inputs = {**row, "predicted_xy_m": prediction["xy_m"]}
                        gate.calibration = row["camera"]
                        try:
                            observation = native.make_observation(inputs, rgb)
                            gate.reset()
                            gate._start(observation, np.asarray(row["look_pose_native"]))
                            reason = None
                        except ValueError as exc:
                            reason = str(exc)
                        prediction["field_contract_eligible"] = reason is None
                        prediction["abstention_reason"] = reason
                        prediction["native"] = native.episode(env, model, inputs, cfg)
                    save_json(path, row)
                rows.append(row)
                print("paired", seed, flush=True)
    finally:
        env.close()
        vis.close()

    def done(r, k):
        return r["methods"][k]["native"]["terminal_success"]

    def eligible(r, k):
        return r["methods"][k]["field_contract_eligible"]

    error_summary = {k: errors([r["methods"][k]["error_mm"] for r in rows]) for k in METHODS}
    result = {
        "protocol_sha256": protocol_sha,
        "fit_sha256": fit_sha,
        "weights_sha256": new.fit["weights_sha256"],
        "errors": error_summary,
        "keypoint_lower_error": sum(
            r["methods"]["keypoint"]["error_mm"] < r["methods"]["baseline"]["error_mm"] for r in rows
        ),
        "native_unrestricted_all_starts": held(rows, lambda _: True, done),
        "contract_all_starts": held(rows, lambda _: True, lambda r, k: eligible(r, k) and done(r, k)),
        "common_admitted": held(rows, lambda r: all(eligible(r, k) for k in METHODS), done),
        "individual_admitted": {
            k: {
                "n": sum(eligible(r, k) for r in rows),
                "holds": sum(eligible(r, k) and done(r, k) for r in rows),
            }
            for k in METHODS
        },
        "opened_v3": diag_rows,
        "rows": rows,
        "physical_trials": 0,
    }
    save_json(OUT / "result.json", result)
    print(error_summary, result["native_unrestricted_all_starts"], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "fit", "evaluate"))
    args = parser.parse_args()
    if args.action == "prepare":
        if (OUT / "protocol.json").exists():
            verify_protocol()
        else:
            save_json(OUT / "protocol.json", protocol())
    elif args.action == "fit":
        from .train import fit

        fit()
    else:
        evaluate()


if __name__ == "__main__":
    main()
