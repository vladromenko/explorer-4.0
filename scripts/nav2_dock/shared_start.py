"""Recover strict RGB pairing when EGL produces different initial pixel hashes."""

import argparse
import shutil
from collections import Counter
from pathlib import Path

from scripts import tank_nav2_camera as study
from scripts import tank_ppo_camera as base
from scripts.peer_dock_study import frozen

STUDY_SHA = "4faacfe661d705715ef980b2c8b7f57274f19aeff36d8aa84c1ecaa05629e772"
SEEDS = (104013, 104015)


def original_evidence(out):
    if base.file_sha(out / "protocol.json") != STUDY_SHA:
        raise ValueError("Unexpected initial registration")
    rows = [
        base.read(out / "scenes" / str(s) / (a + ".json"))
        for s in study.SEEDS
        for a in study.ARMS
    ]
    mismatch = []
    for seed in study.SEEDS:
        group = [r for r in rows if r["seed"] == seed]
        if any(
            r["initial_observation"] != group[0]["initial_observation"] for r in group
        ):
            raise ValueError("Numeric policy observations also differ")
        if len({r["initial_rgb_sha256"] for r in group}) != 1:
            mismatch.append(seed)
    if mismatch != list(SEEDS):
        raise ValueError(
            "Observed mismatches differ from the registered recovery scope"
        )
    return rows


def register(out):
    rows = original_evidence(out)
    folder = out / "shared-initial-v1"
    folder.mkdir(exist_ok=True)
    frozen(
        folder / "original-strict.json",
        {
            "original_protocol_sha256": STUDY_SHA,
            "total_scenes": len(study.SEEDS),
            "matched_seeds": [s for s in study.SEEDS if s not in SEEDS],
            "mismatched_seeds": list(SEEDS),
            "methods_on_strict_subset": {
                a: dict(
                    Counter(
                        r["outcome"]
                        for r in rows
                        if r["seed"] not in SEEDS and r["arm"] == a
                    )
                )
                for a in study.ARMS
            },
            "rows": [
                {
                    k: r[k]
                    for k in (
                        "seed",
                        "arm",
                        "outcome",
                        "steps",
                        "initial_rgb_sha256",
                        "observation_action_sha256",
                    )
                }
                for r in rows
            ],
        },
    )
    frozen(
        folder / "registration.json",
        {
            "status": "post-hoc technical recovery before any new replay",
            "original_protocol_sha256": STUDY_SHA,
            "original_strict_evidence_sha256": base.file_sha(
                folder / "original-strict.json"
            ),
            "mismatched_seeds": list(SEEDS),
            "replay_all_arms": list(study.ARMS),
            "rule": "On each of the two mismatched resets independently recover a raw front RGB frame that matches the original majority SHA (two of three methods). Supply those exact pixels to the original OpenCV detector at tick zero of each arm. All later sensor calls use the live simulator. Preserve the original three raw outcomes and each hash. Require identical saved stochastic reset and identical initial numeric observation. Report all replay outcomes and whether they reproduce their own original numerical trajectories and endpoints.",
            "source_sha256": base.file_sha(Path(__file__)),
        },
    )
    return folder


class FirstRGB:
    """Inject the archived measurement before detection, on exactly one sensor read."""

    def __init__(self, renderer, rgb):
        self.renderer = renderer
        self.rgb = rgb

    def __getattr__(self, name):
        return getattr(self.renderer, name)

    def render(self):
        image = self.renderer.render()
        if self.rgb is None:
            return image
        shared, self.rgb = self.rgb, None
        return shared.copy()


def recover(out):
    import cv2
    import torch

    from explorer4.resources import ResourceLease
    from explorer4.simlab.dock_mujoco import DockMujoco

    folder = out / "shared-initial-v1"
    if not (folder / "registration.json").is_file():
        raise ValueError("Register the scope before replay")
    if register(out) != folder:
        raise ValueError("Invalid recovery directory")
    rows = original_evidence(out)
    initial = {s["seed"]: s for s in base.read(out / "starts.json")}
    cv2.setNumThreads(1)
    torch.set_num_threads(1)
    with ResourceLease("tank-nav2-camera-comparison"):
        env = DockMujoco("tank", curriculum=0.5)
        camera = base.Camera(env)
        renderer = camera.renderer
        nav = study.Nav2()
        actor = study.Policy(base.POLICY)
        correction = []
        try:
            for seed in SEEDS:
                target = folder / "scenes" / str(seed)
                target.mkdir(parents=True, exist_ok=True)

                def reset():
                    if base.reset(env, seed) != initial[seed]:
                        raise ValueError("Frozen initial state changed")

                originals = [r for r in rows if r["seed"] == seed]
                majority, n = Counter(
                    r["initial_rgb_sha256"] for r in originals
                ).most_common(1)[0]
                if n != 2:
                    raise ValueError("No archived majority frame")
                for _ in range(32):
                    reset()
                    rgb, _ = camera.measure(env)
                    if base.sha(rgb.tobytes()) == majority:
                        break
                else:
                    raise ValueError(
                        "Could not reproduce the original majority RGB bytes"
                    )
                cv2.imwrite(
                    str(target / "shared.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                )
                for i, prev in enumerate(rows):
                    if prev["seed"] != seed:
                        continue
                    reset()
                    camera.renderer = FirstRGB(renderer, rgb)
                    row = study.run_scene(
                        env, camera, actor, nav, seed, prev["arm"], target, STUDY_SHA
                    )
                    if (
                        camera.renderer.rgb is not None
                        or row["initial_rgb_sha256"] != majority
                        or row["initial_observation"] != prev["initial_observation"]
                    ):
                        raise ValueError(
                            "Comparison did not consume the frozen first observation"
                        )
                    camera.renderer = renderer
                    frozen(target / (prev["arm"] + ".json"), row)
                    correction.append(
                        {
                            "seed": seed,
                            "arm": row["arm"],
                            "shared_initial_sha256": majority,
                            "observation_action_trace_matches_original": row[
                                "observation_action_sha256"
                            ]
                            == prev["observation_action_sha256"],
                            "endpoint_and_steps_match_original": all(
                                row[k] == prev[k]
                                for k in (
                                    "outcome",
                                    "steps",
                                    "terminal_distance_m",
                                    "absolute_terminal_yaw_rad",
                                )
                            ),
                            "original_outcome": prev["outcome"],
                            "replay_outcome": row["outcome"],
                        }
                    )
                    rows[i] = row
            for filename in ("protocol.json", "starts.json", "comparison.mp4"):
                shutil.copyfile(out / filename, folder / filename)
            diagnostics = []
            for s in study.DEVELOPMENT:
                old = base.read(out / "development" / str(s) / "legacy_geometry.json")
                archived = base.read(base.OUT / "scenes" / str(s) / "rgb_geometry.json")
                diagnostics.append(
                    {
                        "seed": s,
                        **{
                            k: old[k]
                            for k in (
                                "outcome",
                                "mode_ticks",
                                "terminal_distance_m",
                                "absolute_terminal_yaw_rad",
                                "frames",
                                "detections",
                            )
                        },
                        "matched_archived_outcome": old["outcome"]
                        == archived["outcome"],
                        "matched_archived_observation_action_trace": old[
                            "observation_action_sha256"
                        ]
                        == archived["observation_action_sha256"],
                    }
                )
            study.summarize(folder, rows, diagnostics)
            result = base.read(folder / "result.json")
            result.update(
                phase="14 original strict plus 2 post-hoc identical-first-RGB replays",
                shared_initial_recovery={
                    "registration_sha256": base.file_sha(folder / "registration.json"),
                    "original_strict_sha256": base.file_sha(
                        folder / "original-strict.json"
                    ),
                    "original_strict_matched_scenes": 14,
                    "original_scenes": 16,
                    "corrected_seeds": list(SEEDS),
                    "replays": correction,
                },
            )
            frozen(out / "result.json", result)
        finally:
            renderer.close()


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("phase", choices=("register", "run"))
    args = cli.parse_args()
    (register if args.phase == "register" else recover)(study.OUT)
