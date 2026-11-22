"""Resume the frozen DAgger screen using its byte-exact recorded first development images."""

import json
from pathlib import Path
from unittest.mock import patch

import cv2

from scripts.grasp_study import dagger

ORIGINAL_PROTOCOL = "ed08b02795e73baa74b030cd2f27dceff6fda8a129217dc7bdbe87ad21d0d8b3"
observe_live = dagger.observe


def observe_first(env, seed, render=True):
    if seed not in dagger.DEV or not render:
        return observe_live(env, seed, render)
    initial, _ = observe_live(env, seed, render=False)
    path = dagger.OUTPUT / "development/frames" / f"{seed}.png"
    bgr = cv2.imread(str(path))
    if bgr is None or bgr.shape != (120, 160, 3):
        raise ValueError(f"Missing frozen native study input: {path}")
    # The frozen caller checks initial state, physics, exact RGB bytes and localizer output.
    # Subsequent moving-camera or post-return measurements call env.render() directly.
    return initial, bgr[:, :, ::-1].copy()


def main():
    if dagger.file_hash(dagger.OUT / "protocol.json") != ORIGINAL_PROTOCOL:
        raise ValueError("Recovery only applies to the registered DAgger v1 protocol")
    note = {
        "protocol_sha256": ORIGINAL_PROTOCOL,
        "implementation_sha256": dagger.file_hash(Path(__file__)),
        "difference": "A repeated EGL render could change one intensity level at one or two edge pixels of the downsampled first image despite identical reset and post-look physics. This adapter supplies the already published lossless 160x120 first development image to both first-view consumers. The original runner enforces its exact RGB hash, reset, physics and model output. Every observation after motion begins still comes directly from MuJoCo.",
        "unchanged": "Dynamics, displacement, model inputs and weights, native guards, expert, training and evaluation rules, seeds, measured first-view equality, previous verified receipts.",
        "command": ".venv-sim/bin/python -m scripts.grasp_study.dagger_archive run",
    }
    receipt = dagger.OUT / "first-image-replay.json"
    if receipt.exists():
        if json.loads(receipt.read_text()) != note:
            raise ValueError("Conflicting first-image replay implementation")
    else:
        dagger.save_json(receipt, note)
    with patch.object(dagger, "observe", observe_first):
        dagger.main()


if __name__ == "__main__":
    main()
