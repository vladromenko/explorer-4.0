"""Render the first prespecified fresh scene and verify the saved terminal outcome."""

import argparse
import json
from pathlib import Path

import av
import cv2
import mujoco
import numpy as np

from explorer4.conditioned_grasp import SLEW_DEGREES_PER_SECOND, file_hash
from scripts.grasp_study.evaluate import (
    OUTPUT,
    environment,
    observe,
    save_json,
    seed_range,
    trajectory_targets,
)


def render(report, architecture):
    seed = seed_range("fresh")[0]
    row = json.loads((report / "fresh" / f"{seed}.json").read_text())
    expected = row["arms"][architecture]
    destination = report / f"{architecture}-{seed}.mp4"
    temporary = destination.with_suffix(".tmp.mp4")
    env = environment()
    renderer = mujoco.Renderer(env.model, height=360, width=480)
    try:
        initial, _ = observe(env, seed, render=False)
        if initial != row["initial"]:
            raise ValueError("Video reset differs from scored scene")
        camera = mujoco.MjvCamera()
        camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        camera.lookat[:] = [0.05, 0, 0.13]
        camera.distance = 0.7
        camera.azimuth, camera.elevation = 135, -25
        with np.load(report / "fresh/plans.npz", allow_pickle=False) as plans:
            trajectory = plans[f"{seed}_{architecture}"]
        with av.open(str(temporary), "w", options={"movflags": "+faststart"}) as movie:
            stream = movie.add_stream("libx264", rate=10)
            stream.width, stream.height, stream.pix_fmt = 480, 360, "yuv420p"
            stream.options = {"crf": "23", "preset": "veryfast"}
            command = env.observation()["state"].astype(float)
            for i, target in enumerate(trajectory_targets(trajectory)):
                command += np.clip(
                    target - command, -SLEW_DEGREES_PER_SECOND * env.dt, SLEW_DEGREES_PER_SECOND * env.dt
                )
                _, _, done, timeout, info = env.step(command)
                if i % 2 == 0 or done or timeout:
                    renderer.update_scene(env.data, camera=camera)
                    frame = renderer.render().copy()
                    text = f"MuJoCo | {architecture.upper()} | scene {seed} | {env.elapsed:.1f} s"
                    cv2.rectangle(frame, (0, 328), (480, 360), (18, 18, 18), -1)
                    cv2.putText(
                        frame,
                        text,
                        (8, 349),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.52,
                        (250, 250, 250),
                        1,
                        cv2.LINE_AA,
                    )
                    for packet in stream.encode(av.VideoFrame.from_ndarray(frame, format="rgb24")):
                        movie.mux(packet)
                if done or timeout:
                    if info["termination_reason"] != expected["reason"] or env.steps != expected["steps"]:
                        raise ValueError("Video outcome differs from independent scored trial")
                    break
            for packet in stream.encode():
                movie.mux(packet)
        temporary.replace(destination)
        save_json(
            destination.with_suffix(".json"),
            dict(
                seed=seed,
                planner=architecture,
                weights=json.loads((report / "models.json").read_text())["weights"][architecture],
                result=expected,
                video_sha256=file_hash(destination),
                extra_scored_trials=0,
            ),
        )
    finally:
        renderer.close()
        env.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report-dir", type=Path, default=OUTPUT)
    p.add_argument("--architecture", choices=("act", "diffusion"), default="diffusion")
    args = p.parse_args()
    render(args.report_dir, args.architecture)
