"""Replay archived ACT checkpoints without fitting weights or opening confirmation scenes."""

import hashlib
import json
import os
from pathlib import Path
import subprocess

from explorer4.paths import DATA, ROOT

PROFILE = "rosmaster_floor_pick_recorded_start_sim"
ORIGINAL = "0350a44a477346b8bcf1c12dc9fd2323"
SEEDS = list(range(957300, 957308))
STEPS = (1000, 3000, 10000)
PUBLIC = DATA / "simlab/reports/archived-floor-checkpoints-v1"
PHYSICS = "0e44d9f93c8dd4b9a6452e009097b205209f509ebe0653dc78a339783e5925dc"


def persist(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    PUBLIC.mkdir(parents=True, exist_ok=True)
    banks = {
        step: DATA
        / "checkpoints"
        / (ORIGINAL + "-b8")
        / "checkpoints"
        / f"{step:06d}"
        / "pretrained_model"
        for step in STEPS
    }
    identities = {
        str(step): digest(path / "model.safetensors") for step, path in banks.items()
    }
    plan = {
        "source_job": ORIGINAL,
        "optimizer_updates_in_audit": 0,
        "role": "development only",
        "seeds": SEEDS,
        "checkpoints": identities,
        "physics_xml_sha256": PHYSICS,
        "score": "stable carry and any cube lift of 1 cm from reset",
        "render": "Mesa llvmpipe (CPU), native MuJoCo scene",
        "inference": "CPU",
        "decision": "Two consecutive checkpoints without a stable hold or a 1 cm lift stop the pilot. The archived final weights provide a retrospective check of a possible missed gain.",
    }
    if (PUBLIC / "protocol.json").is_file() and json.loads(
        (PUBLIC / "protocol.json").read_text()
    ) != plan:
        raise ValueError("Archived checkpoint protocol changed")
    persist(PUBLIC / "protocol.json", plan)
    summaries = {}
    starts = None
    for step, bank in banks.items():
        destination = PUBLIC / str(step)
        destination.mkdir(exist_ok=True)
        report = destination / "evaluation.json"
        if (
            not report.is_file()
            or json.loads(report.read_text()).get("status") != "completed"
        ):
            args = [
                ROOT / ".venv-sim/bin/python",
                "-m",
                "explorer4.sim.evaluate",
                bank,
                report,
                "--profile",
                PROFILE,
                "--start",
                str(SEEDS[0]),
                "--count",
                str(len(SEEDS)),
                "--expected-model-sha256",
                PHYSICS,
                "--device",
                "cpu",
                "--record-floor",
                "--seed-policy-per-scene",
            ]
            with (destination / "evaluation.log").open("a") as output:
                subprocess.run(
                    list(map(str, args)),
                    cwd=ROOT,
                    check=True,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                )
        outcome = json.loads(report.read_text())
        rows = outcome["trials"]
        if (
            outcome["checkpoint_sha256"] != identities[str(step)]
            or [r["seed"] for r in rows] != SEEDS
        ):
            raise ValueError("Replayed weight or scene order differs from the plan")
        state = [r["initial_qpos_sha256"] for r in rows]
        if starts is not None and state != starts:
            raise ValueError("Initial states differ across checkpoints")
        starts = state
        summaries[str(step)] = {
            "weight_sha256": identities[str(step)],
            "holds": sum(r["outcome"] == "success" for r in rows),
            "ever_held": sum(r["ever_held"] for r in rows),
            "lifted_1cm": sum(r["max_lift_cm"] >= 1 for r in rows),
            "n": len(rows),
            "details": f"{step}/evaluation.json",
        }
    intermediate = [summaries[str(step)] for step in STEPS[:2]]
    persist(
        PUBLIC / "result.json",
        {
            "protocol_sha256": digest(PUBLIC / "protocol.json"),
            "results": summaries,
            "would_stop_after_3000": all(r["holds"] == r["lifted_1cm"] == 0 for r in intermediate),
            "native_draft_would_stop_after_3000": all(r["ever_held"] == r["lifted_1cm"] == 0 for r in intermediate),
            "identical_reset_states": True,
            "optimizer_updates": 0,
            "physical_trials": 0,
        },
    )


if __name__ == "__main__":
    if (
        os.environ.get("LIBGL_ALWAYS_SOFTWARE") != "1"
        or os.environ.get("GALLIUM_DRIVER") != "llvmpipe"
    ):
        raise SystemExit(
            "This historical comparison requires the CPU render specified in its protocol."
        )
    main()
