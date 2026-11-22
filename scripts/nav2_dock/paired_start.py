"""Repeat the camera comparison with one measured, stored initial RGB for every arm."""

import argparse
from pathlib import Path

import cv2
import numpy as np

from explorer4.paths import ROOT
from scripts import tank_nav2_camera as study
from scripts import tank_ppo_camera as base
from scripts.nav2_dock.shared_start import STUDY_SHA, FirstRGB
from scripts.peer_dock_study import frozen

OUT = study.OUT.with_name("tank-nav2-camera-paired-replication-v1")


def capture_start(env, camera, seed, folder):
    """Archive the complete reset, RGB and detection before any branch acts."""
    folder.mkdir(parents=True, exist_ok=True)
    reset = base.reset(env, seed)
    receipt = folder / "capture.json"
    image = folder / "initial.png"
    if not receipt.is_file():
        rgb, detection = camera.measure(env)
        if not cv2.imwrite(str(image), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)):
            raise OSError("Cannot save the common initial camera image")
        frozen(
            receipt,
            {
                "reset": reset,
                "rgb_sha256": base.sha(rgb.tobytes()),
                "detection": detection,
            },
        )
    saved = base.read(receipt)
    if saved["reset"] != reset:
        raise ValueError("Full registered world reset differs")
    return saved


def attach_first_rgb(env, camera, renderer, frame, folder):
    """Verify the reset and original OpenCV packet before advancing physics."""
    import copy

    seed = frame["reset"]["seed"]
    if base.reset(env, seed) != frame["reset"]:
        raise ValueError("Arm failed its paired reset")
    bgr = cv2.imread(str(folder / "initial.png"))
    if bgr is None:
        raise ValueError("Initial RGB is missing")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    if base.sha(rgb.tobytes()) != frame["rgb_sha256"]:
        raise ValueError("Initial RGB checksum differs")
    probe = copy.copy(camera)
    probe.renderer = FirstRGB(renderer, rgb)
    decoded, packet = probe.measure(env)
    if not np.array_equal(decoded, rgb) or packet != frame["detection"]:
        raise ValueError("OpenCV did not recover the registered marker packet")
    camera.renderer = FirstRGB(renderer, rgb)


def register(out):
    spec = base.read(study.OUT / "protocol.json")
    if base.file_sha(study.OUT / "protocol.json") != STUDY_SHA or any(
        base.file_sha(ROOT / k) != v for k, v in spec["sources"].items()
    ):
        raise ValueError("Original scientific sources differ")
    if base.file_sha(study.LIBRARY) != spec["build"]["library_sha256"]:
        raise ValueError("Nav2 executable differs from the original run")
    if base.file_sha(base.POLICY / "policy.npz") != spec["actor"]["policy.npz"]:
        raise ValueError("PPO weights differ from the original run")
    metadata = {
        **spec,
        "study": "tank-nav2-camera-paired-replication-v1",
        "original_protocol_sha256": STUDY_SHA,
        "design": "Repeat on the same 16 previously opened starts. Save one lossless initial image and its real OpenCV packet for every scene before running any policy. Check full reset, raw RGB hash and re-detected packet for each arm. First tick uses exactly the saved RGB; every later measurement uses the live simulator. No new training or independent sample.",
        "paired_source_sha256": base.file_sha(Path(__file__)),
        "renderer_adapter_sha256": base.file_sha(
            ROOT / "scripts/nav2_dock/shared_start.py"
        ),
    }
    out.mkdir(parents=True, exist_ok=True)
    frozen(out / "protocol.json", metadata)


def run(out):
    import torch

    from explorer4.resources import ResourceLease
    from explorer4.simlab.dock_mujoco import DockMujoco

    if not (out / "protocol.json").is_file():
        raise ValueError("Register before measuring")
    register(out)
    cv2.setNumThreads(1)
    torch.set_num_threads(1)
    with ResourceLease("tank-nav2-camera-comparison"):
        env = DockMujoco("tank", curriculum=0.5)
        camera = base.Camera(env)
        renderer = camera.renderer
        actor = study.Policy(base.POLICY)
        nav = study.Nav2()
        rows = []
        protocol_sha = base.file_sha(out / "protocol.json")
        try:
            base.calibration_check(env, camera, out)
            captures = [
                capture_start(env, camera, s, out / "initial" / str(s))
                for s in study.SEEDS
            ]
            frozen(out / "starts.json", [c["reset"] for c in captures])
            for frame in captures:
                seed = frame["reset"]["seed"]
                scene = out / "scenes" / str(seed)
                for arm in study.ARMS:
                    dest = scene / (arm + ".json")
                    if not dest.is_file():
                        attach_first_rgb(
                            env, camera, renderer, frame, out / "initial" / str(seed)
                        )
                        row = study.run_scene(
                            env, camera, actor, nav, seed, arm, scene, protocol_sha
                        )
                        if camera.renderer.rgb is not None:
                            raise ValueError(
                                "The branch did not consume its initial image"
                            )
                        camera.renderer = renderer
                        frozen(dest, row)
                    row = base.read(dest)
                    first = base.read(scene / (arm + "-trace.json"))[0]
                    if (
                        row["seed"],
                        row["arm"],
                        row["protocol_sha256"],
                        row["initial_rgb_sha256"],
                        first["packet"],
                    ) != (
                        seed,
                        arm,
                        protocol_sha,
                        frame["rgb_sha256"],
                        frame["detection"],
                    ):
                        raise ValueError(
                            "Saved branch violates the frozen sensor contract"
                        )
                    rows.append(row)
                print(f"Confirmed three branches at scene {seed}", flush=True)
            if not (out / "comparison.mp4").is_file():
                study.make_video(out, rows)
            study.summarize(out, rows, [])
        finally:
            renderer.close()


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("phase", choices=("register", "run"))
    cli.add_argument("--output", type=Path, default=OUT)
    args = cli.parse_args()
    (register if args.phase == "register" else run)(args.output)
