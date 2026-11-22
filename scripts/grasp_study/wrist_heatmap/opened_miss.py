"""Post-hoc native replay of the already diagnosed 39 mm wrist-image miss."""

import sys
import types
from unittest.mock import patch

import cv2
import torch

from explorer4.conditioned_grasp import file_hash, load_localizer, locate_cube
from explorer4.paths import ROOT
from scripts.grasp_study import admission_native as native
from scripts.grasp_study.admission_native_v3 import OUT as DIAGNOSTIC
from scripts.grasp_study.coverage_design import frozen, read, settings
from scripts.grasp_study.evaluate import SOURCE, VISION, environment
from .data import OUT
from .model import WristCubeLocator


def run():
    torch.set_num_threads(1)
    cv2.setNumThreads(1)
    seed = 976115
    archive = read(DIAGNOSTIC / "result.json")
    row = next(r for r in archive["candidates"] if r["seed"] == seed)
    original = next(r for r in archive["trials"] if r["seed"] == seed)
    frozen(
        OUT / "opened-miss-protocol.json",
        {
            "purpose": "Post-hoc single-scene diagnosis. Does correcting a previously known large RGB error rescue its terminal hold under the original guarded field contract?",
            "seed": seed,
            "source_sha256": file_hash(__file__),
            "result_sha256": file_hash(OUT / "result.json"),
            "opened_source_sha256": file_hash(DIAGNOSTIC / "result.json"),
            "fresh_scenes": 0,
            "physical_trials": 0,
            "selection": "Already named in the research question for its 39 mm error. This case does not estimate generalization.",
        },
    )
    old = load_localizer(VISION)
    new = WristCubeLocator(OUT)
    actor = native.SimulatedActions(None, SOURCE, VISION, "rbf", None, localizer=old)
    rgb = cv2.imread(str(DIAGNOSTIC / "frames" / f"{seed}.png"))[:, :, ::-1]
    output = {}

    def no_serial(*args, **kwargs):
        raise AssertionError("No physical transport")

    env = environment()
    try:
        with (
            patch.dict(sys.modules, {"serial": types.SimpleNamespace(Serial=no_serial)}),
            patch.object(sys, "path", [str(ROOT / "agents/rosmaster"), str(native.NATIVE), *sys.path]),
            patch.object(native, "OUT", DIAGNOSTIC),
        ):
            for method, xy in [
                ("baseline", locate_cube(old, rgb).tolist()),
                ("keypoint", new.locate(rgb)["xy_m"]),
            ]:
                result = native.episode(env, actor, {**row, "predicted_xy_m": xy}, settings())
                if method == "baseline" and result != original:
                    raise ValueError("The original native action hash and outcome did not reproduce")
                output[method] = {"xy_m": xy, **result}
    finally:
        env.close()
    frozen(
        OUT / "opened-miss.json",
        {
            "protocol_sha256": file_hash(OUT / "opened-miss-protocol.json"),
            "seed": seed,
            "original_rgb_sha256": row["rgb_sha256"],
            "methods": output,
            "physical_trials": 0,
        },
    )
    print({k: r["terminal_success"] for k, r in output.items()})


if __name__ == "__main__":
    run()
