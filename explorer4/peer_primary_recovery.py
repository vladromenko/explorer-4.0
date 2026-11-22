"""Resume the registered peer evaluation using its published fit and append-only scene evidence."""

import argparse
import fcntl
import json
import os
import shutil
import tempfile
from pathlib import Path

from . import catalog, study_queue
from .paths import DATA
from .peer_confirmation import primary, require
from .peer_request_policy import checksum, read


def has_fit(cfg):
    if cfg.get("track") != "peer_learning":
        return False
    root = primary(cfg)
    if (root / "fit.json").exists():
        require((root / "model.json").is_file(), "A published fit has lost its model")
        return True
    require(
        not (root / "test").exists() and not (root / "evaluation.json").exists(),
        "Held-out evidence without a published fit cannot be resumed",
    )
    return False


def publish_missing(source, folder, names):
    """Compare the entire step before appending anything. The final name is the step receipt."""
    for name in names:
        original = folder / name
        if original.exists():
            require(
                study_queue.digest(original) == study_queue.digest(source / name),
                f"Replay differs from archived {folder.name}/{name}; original preserved",
            )
    for name in names:
        if not (folder / name).exists():
            os.link(source / name, folder / name)


CAPTURE = (
    "initial-state.json",
    "start.json",
    "recipient-before.png",
    "decision.json",
    "model-decision.json",
    "donor-observation.png",
    "world-observation.png",
    "after-donor.json",
    "donor.json",
)
ROLLOUT = ("recipient-final.png", "world-final.png", "verifier.json", "outcomes.json")


class ArchivedReset:
    """Inject the exact already-published integration and task state after deterministic scene setup."""

    def __init__(self, world, snapshot):
        self.world_ref = world
        self.snapshot = snapshot

    def __getattr__(self, name):
        return getattr(self.world_ref, name)

    @property
    def output(self):
        return self.world_ref.output

    @output.setter
    def output(self, folder):
        self.world_ref.output = folder

    def reset(self, seed):
        self.world_ref.reset(seed)
        self.world_ref.world.restore(self.snapshot)
        self.world_ref.initial = self.snapshot


def recover_scenes(root, plan, model, make_world):
    from scripts import peer_dock_policy as policy, peer_dock_study as study
    from .sim.state_codec import load

    seeds = plan["test_seeds"]
    folders = [root / "test" / str(seed) for seed in seeds]
    require(
        not any(
            folder.is_dir() and folder not in folders
            for folder in (root / "test").glob("*")
        ),
        "Unexpected scene outside the frozen split",
    )
    world = None
    try:
        if any(not (folder / "donor.json").exists() for folder in folders):
            world = make_world(root / "scratch", seeds[0], plan["test_room"])
        for seed, folder in zip(seeds, folders, strict=True):
            folder.mkdir(parents=True, exist_ok=True)
            decision = folder / "decision.json"
            start = folder / "start.json"
            snapshot = folder / "initial-state.json"
            if start.exists():
                value = read(start)
                require(
                    value["seed"] == seed
                    and value["room"] == plan["test_room"]
                    and value["initial_state_sha256"] == study.digest(snapshot),
                    "Initial state differs",
                )
            if decision.exists():
                require(
                    start.is_file()
                    and read(decision)["local_image_sha256"]
                    == study.digest(folder / "recipient-before.png"),
                    "Saved recipient decision differs from its original camera frame",
                )
            if any((folder / name).exists() for name in CAPTURE[5:]):
                require(
                    (folder / "model-decision.json").is_file() and decision.is_file(),
                    "A donor observation lacks a pre-request model decision",
                )
            if (folder / "donor.json").is_file():
                require(
                    all((folder / name).is_file() for name in CAPTURE)
                    and read(folder / "donor.json")["after_donor_state_sha256"]
                    == study.digest(folder / "after-donor.json"),
                    "Incomplete committed donor capture",
                )
                with tempfile.TemporaryDirectory(dir=folder) as tmp:
                    policy.freeze_prediction(Path(tmp), seed, model, read(decision))
                    publish_missing(Path(tmp), folder, ("model-decision.json",))
                if world is not None:
                    world.reset(seed)
                    world.world.restore(load(folder / "after-donor.json"))
                continue
            require(
                not any((folder / name).exists() for name in ROLLOUT),
                "Rollout exists without donor receipt",
            )
            replay = (
                ArchivedReset(world, load(snapshot)) if snapshot.exists() else world
            )
            with tempfile.TemporaryDirectory(dir=folder) as tmp:
                staging = Path(tmp)

                def decide(value):
                    policy.freeze_prediction(staging, seed, model, value)
                    publish_missing(staging, folder, CAPTURE[:5])

                study.scene_inputs(replay, staging, seed, before_donor=decide)
                publish_missing(staging, folder, CAPTURE)

        # The pinned evaluator skips completed outcome rows. Only a torn rollout needs staging.
        for index, folder in enumerate(folders):
            if (folder / "outcomes.json").exists() or not any(
                (folder / n).exists() for n in ROLLOUT[:-1]
            ):
                continue
            if world is None:
                world = make_world(root / "scratch", seeds[0], plan["test_room"])
            other = (index + 1) % len(seeds)
            packet = read(folders[other] / "donor.json")["packet"]
            with tempfile.TemporaryDirectory(dir=folder) as tmp:
                staging = Path(tmp)
                for name in CAPTURE:
                    shutil.copyfile(folder / name, staging / name)
                study.rollouts(world, staging, seeds[index], packet, seeds[other])
                publish_missing(staging, folder, ROLLOUT)
    finally:
        if world is not None:
            world.close()


def resume(cfg, work):
    from scripts import peer_dock_policy as policy, peer_screen_evidence as screen

    study_queue.verify(cfg["study_plan"])
    require(has_fit(cfg), "A fitted peer selector is required for recovery")
    root = primary(cfg)
    with (root / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = policy.verify_plan(root)
        with tempfile.TemporaryDirectory() as tmp:
            require(
                plan == policy.prepare(Path(tmp), DATA / "runs" / screen.NAME),
                "Saved plan differs from registered development inputs",
            )
        model, fit = read(root / "model.json"), read(root / "fit.json")
        require(
            model["plan_sha256"] == checksum(plan)
            and fit["model_sha256"] == checksum(model)
            and fit["threshold"] == model["threshold"]
            and fit["test_results_read"] is False
            and fit["motor_weights_updated"] is False,
            "Saved fit or threshold differs from its plan",
        )
        if not (root / "evaluation.json").exists():
            from .sim.cooperation import CooperationWorld

            recover_scenes(root, plan, model, CooperationWorld)
            policy.evaluate(root)
        evaluation = read(root / "evaluation.json")
        require(
            evaluation["status"] == "completed"
            and evaluation["model_sha256"] == checksum(model)
            and evaluation["test_seeds"] == plan["test_seeds"]
            and evaluation["fit_on_test"] is False,
            "Saved evaluation differs from the fitted model or split",
        )
        result = {
            **evaluation,
            "study_plan": cfg["study_plan"],
            "track": cfg["track"],
            "physical_trials": 0,
            "report": "/simlab-media/"
            + str(root.relative_to(DATA / "simlab") / "result.json"),
        }
        for destination in (root / "result.json", work / "result.json"):
            if destination.exists():
                require(
                    read(destination) == result,
                    "Saved result differs from the registered evaluation",
                )
            else:
                study_queue.write_json(destination, result)


def partial_confirmation(cfg):
    from .peer_confirmation import directory

    out = directory(cfg["peer_confirmation"])
    if not out.is_dir():
        return False
    return any(
        folder.is_dir()
        and folder.name.isdecimal()
        and not (folder / "result.json").exists()
        and any(p.is_file() and not p.name.endswith(".tmp") for p in folder.iterdir())
        for folder in out.iterdir()
    )


def preserve_confirmation(run_room, spec, out, split):
    """The registered confirmation runs all checks, then calls its original runner on pending rows."""
    for scene in spec["scenes"]:
        folder = out / str(scene["seed"])
        if not folder.is_dir() or (folder / "result.json").exists():
            continue
        saved = [
            p.name
            for p in folder.iterdir()
            if p.is_file() and not p.name.endswith(".tmp")
        ]
        if not saved:
            continue
        if "initial.png" in saved:
            require(
                study_queue.digest(folder / "initial.png")
                == scene["initial_rgb_sha256"],
                "Interrupted confirmation differs from the primary image; original preserved",
            )
        with tempfile.TemporaryDirectory(dir=out) as tmp:
            staging = Path(tmp)
            shutil.copyfile(out / "protocol.json", staging / "protocol.json")
            run_room({"scenes": [scene]}, staging, split)
            trial = staging / folder.name
            require(
                study_queue.digest(trial / "initial.png")
                == scene["initial_rgb_sha256"],
                "Confirmation replay differs from the original primary camera frame",
            )
            files = sorted(
                p.name
                for p in trial.iterdir()
                if p.is_file() and p.name != "result.json"
            )
            require(
                set(saved) <= set(files),
                "Confirmation replay lacks an archived observation",
            )
            publish_missing(trial, folder, [*files, "result.json"])
    return run_room(spec, out, split)


def resume_confirmation(ident):
    from functools import partial
    from unittest.mock import patch
    from scripts import peer_sequential_control
    from .peer_confirmation import confirm

    # The frozen confirmation still performs registration, original evidence and endpoint checks.
    protected = partial(preserve_confirmation, peer_sequential_control.run_room)
    with patch.object(peer_sequential_control, "run_room", protected):
        return confirm(ident)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_id")
    parser.add_argument("--confirmation", action="store_true")
    args = parser.parse_args()
    ident = args.job_id
    with catalog.connect() as db:
        row = db.execute(
            "SELECT status, config FROM jobs WHERE id=?", (ident,)
        ).fetchone()
    require(
        row is not None and row["status"] == "running",
        "Only the running Jobs worker may resume evaluation",
    )
    cfg = json.loads(row["config"])
    require(
        cfg.get("kind") == "workspace_study" and cfg["track"] == "peer_learning",
        "Wrong research job",
    )
    if args.confirmation:
        print(resume_confirmation(ident))
    else:
        resume(cfg, DATA / "jobs" / ident)
