"""Compare a pinned upstream wrist policy to holding position on saved training-role frames."""

import argparse
import importlib.metadata
import json
import os
from pathlib import Path

import numpy as np
from lerobot.datasets.lerobot_dataset import LeRobotDataset

from explorer4.datasets import load_plan
from explorer4.paths import DATA
from explorer4.policy_runtime import PolicyCore, checkpoint_fingerprint
from explorer4.profiles import profile

PLAN = "a800f4387723cf55ea800f691b10578a2aa9315fe371f18621b2f6a54f181bd7"
from explorer4.wrist_pretraining import MODEL, REVISION, WEIGHTS, source_path

DEFAULT_MODEL = source_path()


def replay(checkpoint, output):
    import hashlib

    with (checkpoint / "model.safetensors").open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != WEIGHTS:
            raise ValueError("Unexpected upstream checkpoint")
    plan = load_plan(PLAN)
    contract = profile("so101_pick_place")
    model = PolicyCore(checkpoint, device="cpu", instruction=contract["task"])
    trials = []
    for entry in plan["splits"]["train"]:
        root = Path(entry["dataset"])
        info = json.loads((root / "meta/info.json").read_text())
        hardware = json.loads((root / "provenance.json").read_text())["hardware"]
        if (
            info["fps"] != 30
            or info["features"]["action"]["names"] != contract["channels"]
            or hardware["units"] != contract["units"]
            or hardware["source"] != "hardware"
        ):
            raise ValueError("Unexpected archived hardware contract")
        calibration = hardware["calibration_snapshot"]["values"]["follower"]
        dof = [calibration[name] for name in contract["channels"][:5]]
        if any(m["drive_mode"] for m in dof):
            raise ValueError("Drive inversion requires explicit verification")
        # As in LeRobot MotorsBus, +/-100 spans each joint range; degrees use a 4095-tick turn.
        joint_span = np.array(
            [(m["range_max"] - m["range_min"]) * 360 / 4095 for m in dof]
        )
        normalized = np.r_[200 / joint_span, 1.0]
        ds = LeRobotDataset("local/so101-shadow", root=root, video_backend="pyav")
        for index in np.linspace(0, len(ds) - 1, 12, dtype=int):
            sample = ds[int(index)]
            rgb = (
                sample["observation.images.wrist"]
                .permute(1, 2, 0)
                .mul(255)
                .round()
                .byte()
                .numpy()
            )
            state = sample["observation.state"].numpy()
            action = sample["action"].numpy()
            predictions = {"hold": state.tolist()}
            for assumption, factor in [
                ("degree_source", np.ones(6)),
                ("normalized_source", normalized),
            ]:
                model.reset()
                source_state = (state * factor).astype(np.float32)
                if assumption == "normalized_source":
                    source_state[:5] = np.clip(source_state[:5], -100, 100)
                prediction = (
                    np.asarray(model.act(source_state, {"wrist": rgb})) / factor
                )
                predictions[assumption] = prediction.tolist()
            trials.append(
                dict(
                    episode=entry["id"],
                    index=int(index),
                    reference=action.tolist(),
                    predictions=predictions,
                )
            )
    mae = {}
    for method in trials[0]["predictions"]:
        errors = [
            np.abs(np.subtract(t["predictions"][method], t["reference"]))
            for t in trials
        ]
        mae[method] = np.mean(errors, axis=0).tolist()
    result = dict(
        source=MODEL,
        revision=REVISION,
        source_data_revision="d10137caea03c8149119558118c1b6abb69a90f3",
        weights_sha256=WEIGHTS,
        bundle_sha256=checkpoint_fingerprint(checkpoint),
        lerobot=importlib.metadata.version("lerobot"),
        local_plan=PLAN,
        role="train_replay",
        frames=len(trials),
        episodes=len(plan["splits"]["train"]),
        channels=contract["channels"],
        units=contract["units"],
        mae_by_channel=mae,
        motion_commands=0,
        physical_trials=0,
        limitation="Conditional action error on operator observations. Source calibration and units are unconfirmed. Holding position is a one-frame reference. No task-success estimate.",
        trials=trials,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    os.replace(temporary, output)
    print(
        json.dumps(
            {k: result[k] for k in ("frames", "episodes", "mae_by_channel")}, indent=2
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_MODEL)
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA / "simlab/reports/so101-external-shadow.json",
    )
    args = parser.parse_args()
    replay(args.checkpoint, args.output)
