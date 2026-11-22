"""Run a separately identified seed replication after the operator starts its job."""

import argparse
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

from explorer4.paths import DATA, ROOT

PRIMARY_REPORT = DATA / "simlab/reports/conditioned-grasp-v1"
SOURCE = DATA / "runs/article-closeout-20261122/learned-trajectories/motor.npz"
VISION = DATA / "runs/recorded-start-cube-20261121/night/visual-pick-v1/weights.pt"


def verify_reference_inputs(base, source, vision):
    import cv2

    from explorer4.conditioned_grasp import MOTOR_SHA256, VISION_SHA256, file_hash
    from scripts.grasp_study.evaluate import PROTOCOL_PATH, seed_range, sha_array

    expected = ROOT / "docs/results/conditioned_grasp_v1"
    if file_hash(source) != MOTOR_SHA256 or file_hash(vision) != VISION_SHA256:
        raise ValueError("The original camera or motor training data changed")
    for block in ("development", "fresh", "historical_confirmation"):
        original = json.loads((expected / (block + ".json")).read_text())
        observations = json.loads((base / block / "observations.json").read_text())
        if original["protocol_sha256"] != file_hash(PROTOCOL_PATH) or set(observations) != {
            str(n) for n in seed_range(block)
        }:
            raise ValueError("Unexpected protocol or observations in " + block)
        for row in original["trials"]:
            seed = str(row["seed"])
            reference = {k: row[k] for k in ("initial", "lookup_state_sha256", "rgb_sha256", "predicted_xy")}
            rgb = cv2.imread(str(base / block / "frames" / f"{seed}.png"))
            if (
                rgb is None
                or sha_array(rgb[:, :, ::-1]) != reference["rgb_sha256"]
                or reference != observations[seed]
            ):
                raise ValueError("Changed frozen reference scene " + seed)


def run(seed, checkpoint_dir, report_dir, reference, source, vision, workers):
    report_dir, checkpoint_dir = report_dir.resolve(), checkpoint_dir.resolve()
    base = reference.resolve()
    if report_dir == base or (
        seed != 1000 and checkpoint_dir == (DATA / "checkpoints/conditioned-grasp-v1").resolve()
    ):
        raise ValueError("Replication requires its own output and weights directories")
    verify_reference_inputs(base, source, vision)
    report_dir.mkdir(parents=True, exist_ok=True)
    with (report_dir / ".study.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        environment = {
            **os.environ,
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MUJOCO_GL": "egl",
            "HF_HUB_OFFLINE": "1",
            "PYTHONUNBUFFERED": "1",
        }
        # The normal interpreter and the simulation interpreter intentionally have separate dependencies.
        normal = Path(sys.executable)
        simulator = ROOT / ".venv-sim/bin/python"
        commands = [
            (
                "train",
                [
                    normal,
                    "-m",
                    "scripts.grasp_study.train",
                    "--source",
                    source,
                    "--output",
                    checkpoint_dir,
                    "--device",
                    "cuda",
                    "--seed",
                    str(seed),
                ],
            )
        ]
        for block in ("development", "fresh", "historical_confirmation"):
            for stage in ("observe", "plan", "score", "summarize"):
                interpreter = simulator if stage in ("observe", "score") else normal
                commands.append(
                    (
                        block + "/" + stage,
                        [
                            interpreter,
                            "-m",
                            "scripts.grasp_study.evaluate",
                            stage,
                            block,
                            "--source",
                            source,
                            "--vision",
                            vision,
                            "--checkpoint-dir",
                            checkpoint_dir,
                            "--report-dir",
                            report_dir,
                            "--reference-observations",
                            base,
                            "--workers",
                            str(workers),
                        ],
                    )
                )
        for name, command in commands:
            print(json.dumps(dict(stage=name, optimizer_seed=seed)), flush=True)
            subprocess.run(command, cwd=ROOT, env=environment, check=True)
            if name == "development/summarize":
                decision = json.loads((report_dir / "development-screen.json").read_text())
                if not decision["passed"]:
                    result = json.loads((report_dir / "development/summary.json").read_text())
                    result.update(
                        status="completed", result="development_screen_failed", confirmation_opened=False
                    )
                    temporary = report_dir / ".summary.tmp"
                    temporary.write_text(json.dumps(result, indent=2) + "\n")
                    os.replace(temporary, report_dir / "summary.json")
                    return
        # Publish a distinct completion record only after both confirmation blocks.
        result = json.loads((report_dir / "fresh/summary.json").read_text())
        result.update(status="completed", result="confirmation_completed", confirmation_opened=True)
        temporary = report_dir / ".summary.tmp"
        temporary.write_text(json.dumps(result, indent=2) + "\n")
        os.replace(temporary, report_dir / "summary.json")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", required=True, type=int)
    p.add_argument("--checkpoint-dir", required=True, type=Path)
    p.add_argument("--report-dir", required=True, type=Path)
    p.add_argument("--reference-observations", type=Path, default=PRIMARY_REPORT)
    p.add_argument("--source", type=Path, default=SOURCE)
    p.add_argument("--vision", type=Path, default=VISION)
    p.add_argument("--workers", type=int, choices=(1, 2, 3, 4), default=2)
    a = p.parse_args()
    run(a.seed, a.checkpoint_dir, a.report_dir, a.reference_observations, a.source, a.vision, a.workers)
