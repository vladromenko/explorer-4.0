"""Replay the first rescued held-out case, validating the frozen outcome before releasing the film."""

import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
from unittest.mock import patch

import av
import cv2
import mujoco
import numpy as np
import torch

from explorer4.paths import ROOT
from scripts.grasp_study import dagger, failure_watch as study, failure_watch_confirmation as paired
from scripts.grasp_study.coverage_design import frozen, read
from scripts.grasp_study.evaluate import environment, sha_array

FPS = 5
SAMPLE_STEPS = 4  # 20 Hz native controller


def overview_camera():
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [0.16, -0.01, 0.12]
    camera.distance, camera.azimuth, camera.elevation = 0.75, 110.0, -18.0
    return camera


def write_film(path, films, seed):
    with av.open(str(path), mode="w", format="mp4") as container:
        stream = container.add_stream("libx264", rate=FPS)
        stream.width, stream.height, stream.pix_fmt = 800, 360, "yuv420p"
        for i in range(max(len(frames) for frames in films)):
            canvas = np.zeros((360, 800, 3), dtype=np.uint8)
            for j, (frames, title) in enumerate(zip(films, ("Keep original plan", "Return to look once"))):
                image, sim_time = frames[min(i, len(frames) - 1)]
                x = j * 400
                canvas[34:334, x : x + 400] = image
                cv2.putText(
                    canvas,
                    title,
                    (x + 8, 23),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.56,
                    (245, 245, 245),
                    1,
                    cv2.LINE_AA,
                )
                tail = " | stopped" if i >= len(frames) - 1 else ""
                cv2.putText(
                    canvas,
                    f"MuJoCo {seed}   {sim_time:.1f} s" + tail,
                    (x + 8, 353),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.47,
                    (225, 225, 225),
                    1,
                    cv2.LINE_AA,
                )
            for packet in stream.encode(av.VideoFrame.from_ndarray(canvas, format="rgb24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def replay():
    result = read(paired.OUT / "result.json")
    seed = min(r["seed"] for r in result["pairs"] if not r["stale_hold"] and r["recovery_hold"])
    original = paired.OUT / "test" / str(seed) / "record.json"
    row = read(original)
    if not row["decision_sha256"] == study.file_hash(original.with_name("decision.json")):
        raise ValueError("Changed decision")
    torch.set_num_threads(1)
    cv2.setNumThreads(1)
    with tempfile.TemporaryDirectory(dir=paired.OUT) as dirname:
        tmp = Path(dirname)
        exposures = tmp / "exposures" / str(seed)
        shutil.copytree(paired.OUT / "exposures" / str(seed), exposures)
        expected_images = {f.name: study.file_hash(f) for f in exposures.iterdir()}
        env = environment()
        renderer = mujoco.Renderer(env.model, height=300, width=400)
        camera = overview_camera()
        films, checks = [], {}
        try:
            with (
                patch.object(paired, "OUT", tmp),
                patch.dict(
                    sys.modules,
                    {
                        "serial": types.SimpleNamespace(
                            Serial=lambda *a, **k: (_ for _ in ()).throw(AssertionError("offline only"))
                        )
                    },
                ),
                patch.object(sys, "path", [str(ROOT / "agents/rosmaster"), str(dagger.NATIVE), *sys.path]),
                patch.object(env, "render", paired.cache_sensor(env, seed)),
            ):
                base = dagger.Study(env)
                initial, rgb = study.observe(env, seed)
                if initial != row["initial"]:
                    raise ValueError("Reset differs from recorded scene")
                xy = study.locate_cube(base.localizer, rgb).astype(float)
                tracker = dagger.WristTracker(rgb, env.observation()["state"], xy)
                state = (initial, study.capture(env), xy, tracker, base.rbf, base.localizer, base.settings)
                start = env.steps
                step = dagger.NativeEpisode.step
                for branch in ("stale", "return_to_look"):
                    frames, prefix = [], {}

                    def capture_frame():
                        renderer.update_scene(env.data, camera=camera)
                        frames.append((renderer.render().copy(), float(env.elapsed)))

                    def record(sim, target):
                        tick = env.steps - start
                        if tick in study.TICKS and tick not in prefix:
                            prefix[tick] = (sha_array(env.render()), sha_array(env.snapshot()["physics"]))
                        if tick % SAMPLE_STEPS == 0:
                            capture_frame()
                        return step(sim, target)

                    with patch.object(dagger.NativeEpisode, "step", record):
                        outcome = dagger.run_episode(env, state, branch, row["delta_m"])
                    capture_frame()
                    if outcome != row[branch] or list(prefix.values()) != [
                        (obs["rgb_sha256"], obs["physics_sha256"]) for obs in row["observations"]
                    ]:
                        raise ValueError(
                            "Replay differs from original observation, branch physics or terminal verdict"
                        )
                    films.append(frames)
                    checks[branch] = {
                        "frames": len(frames),
                        "outcome": outcome["outcome"],
                        "steps": outcome["steps"],
                        "elapsed_sim_s": outcome["elapsed_sim_s"],
                        "reason": outcome["reason"],
                    }
        finally:
            renderer.close()
            env.close()
        if expected_images != {f.name: study.file_hash(f) for f in exposures.iterdir()}:
            raise ValueError("Replay asked for an unrecorded camera input")
        movie = tmp / "first-rescued.mp4"
        write_film(movie, films, seed)
        with av.open(str(movie)) as content:
            decoded = sum(1 for _ in content.decode(video=0))
        if decoded != max(len(frames) for frames in films):
            raise ValueError("Unexpected number of decoded frames")
        report = {
            "selection": "Lowest original test seed rescued by the unconditional return.",
            "seed": seed,
            "source_sha256": study.file_hash(__file__),
            "original_record_sha256": study.file_hash(original),
            "decision_sha256": row["decision_sha256"],
            "result_sha256": study.file_hash(paired.OUT / "result.json"),
            "branches": checks,
            "rgb_and_physics_at_both_monitor_times_verified": True,
            "score_and_all_terminal_fields_match": True,
            "fps": FPS,
            "video_frames": decoded,
            "video_sha256": study.file_hash(movie),
            "camera": "Independent operator overview; each policy input came from the lossless recorded wrist exposures.",
        }
        frozen(paired.OUT / "first-rescued.json", report)
        os.replace(movie, paired.OUT / "first-rescued.mp4")


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    replay()
