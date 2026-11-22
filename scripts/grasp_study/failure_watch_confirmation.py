"""Evaluate the frozen failure probe with one recorded RGB per identical camera/physics state."""

import argparse
import hashlib
import os
import sys
import types
from unittest.mock import patch

import cv2
import numpy as np
import torch

from explorer4.conditioned_grasp import file_hash
from explorer4.paths import ROOT
from scripts.grasp_study import dagger, failure_watch as base
from scripts.grasp_study.coverage_design import frozen, read
from scripts.grasp_study.evaluate import environment, sha_array

ORIGINAL = base.OUT
OUT = ORIGINAL / "paired-test"
ORIGINAL_PROTOCOL = "1eff51ad6914f8002a7ae5e436122180759c451098f1b4eaf4ec5d4f9c880b00"


def prepare():
    if file_hash(ORIGINAL / "protocol.json") != ORIGINAL_PROTOCOL or base.protocol() != read(
        ORIGINAL / "protocol.json"
    ):
        raise ValueError("Changed original study")
    model = read(ORIGINAL / "model.json")
    if model["protocol_sha256"] != ORIGINAL_PROTOCOL:
        raise ValueError("Model does not match the original protocol")
    for group, episodes in model["source_episodes"].items():
        for seed, digest in episodes.items():
            if file_hash(ORIGINAL / group / seed / "record.json") != digest:
                raise ValueError("Changed original fitting or calibration episode")
    if list((ORIGINAL / "test").glob("*/record.json")):
        raise ValueError("Superseded confirmation unexpectedly has published endpoints")
    plan = {
        "original_protocol": ORIGINAL_PROTOCOL,
        "model_sha256": file_hash(ORIGINAL / "model.json"),
        "recovery_source_sha256": file_hash(__file__),
        "first_incomplete_decision": file_hash(ORIGINAL / "test/985300/decision.json"),
        "change": "Start each assigned test scene with a fresh environment. Archive the first lossless RGB for each unique seed, full integration state and camera optics and serve those identical bytes at the same physical state in both counterfactuals. A different physics hash still rejects a pair. Estimate each outcome from actual separate post-decision physics, retaining the original monitor, threshold, response, seed order and endpoints.",
        "training_updates": 0,
        "test_seeds": list(base.SPLITS["test"]),
        "physical_trials": 0,
    }
    frozen(OUT / "confirmation.json", plan)
    for name in ("model.json", "protocol.json"):
        destination = OUT / name
        if not destination.exists():
            destination.write_bytes((ORIGINAL / name).read_bytes())
        if file_hash(destination) != file_hash(ORIGINAL / name):
            raise ValueError("Reissued frozen model/protocol has different bytes")


def cache_sensor(env, seed):
    render = env.render
    folder = OUT / "exposures" / str(seed)
    folder.mkdir(parents=True, exist_ok=True)
    cam = env.model.camera(env.camera_name).id

    def acquire():
        optics = np.r_[
            env.data.cam_xpos[cam],
            env.data.cam_xmat[cam].ravel(),
            env.model.cam_fovy[cam],
            env.model.cam_intrinsic[cam],
            env.model.cam_sensorsize[cam],
        ]
        key = hashlib.sha256((sha_array(env.snapshot()["physics"]) + sha_array(optics)).encode()).hexdigest()
        png = folder / f"{key}.png"
        if not png.exists():
            image = render()
            temp = png.with_suffix(".tmp.png")
            if not cv2.imwrite(str(temp), image[:, :, ::-1]):
                raise OSError(temp)
            os.replace(temp, png)
        return cv2.imread(str(png), cv2.IMREAD_COLOR)[:, :, ::-1].copy()

    return acquire


def run():
    prepare()
    torch.set_num_threads(1)
    cv2.setNumThreads(1)
    model = read(OUT / "model.json")

    def no_serial(*a, **k):
        raise AssertionError("No physical transport")

    rows = []
    with (
        patch.object(base, "OUT", OUT),
        patch.dict(sys.modules, {"serial": types.SimpleNamespace(Serial=no_serial)}),
        patch.object(sys, "path", [str(ROOT / "agents/rosmaster"), str(dagger.NATIVE), *sys.path]),
    ):
        for seed in base.SPLITS["test"]:
            env = environment()
            try:
                with patch.object(env, "render", cache_sensor(env, seed)):
                    rows.append(base.Study(env).trial("test", seed, model))
            finally:
                env.close()
        result = base.summarize(rows)
    result["confirmation_sha256"] = file_hash(OUT / "confirmation.json")
    frozen(OUT / "result.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    if parser.parse_args().action == "prepare":
        prepare()
    else:
        run()
