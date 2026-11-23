"""Publish the simulation-only weights, frozen inputs, trial rows and a reproducibility manifest."""

import argparse
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

from explorer4.conditioned_grasp import file_hash
from scripts.grasp_study.evaluate import (
    BUNDLE,
    OUTPUT,
    PROTOCOL_PATH,
    SOURCE,
    VISION,
    save_json,
    verified_models,
)


def verified_archive(archive, files):
    """Build an immutable deterministic ZIP and verify an existing copy against its inputs."""
    archive.parent.mkdir(parents=True, exist_ok=True)
    manifest = {k: file_hash(v) for k, v in files.items()}
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            if (
                set(z.namelist()) != {*manifest, "manifest.json"}
                or json.loads(z.read("manifest.json")) != manifest
                or any(
                    hashlib.sha256(z.read(member)).hexdigest() != digest
                    for member, digest in manifest.items()
                )
            ):
                raise ValueError(
                    "An existing release differs from the requested files. Use a new report directory."
                )
    else:
        temporary = archive.with_suffix(".tmp.zip")
        with zipfile.ZipFile(temporary, "w") as z:
            for member, file in files.items():
                z.writestr(zipfile.ZipInfo(member), file.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
            z.writestr(
                zipfile.ZipInfo("manifest.json"),
                json.dumps(manifest, indent=2),
                compress_type=zipfile.ZIP_DEFLATED,
            )
        temporary.replace(archive)


def publish(report, bundle, source, vision, repository_results):
    blocks = ("development", "fresh", "historical_confirmation")
    summaries = {b: json.loads((report / b / "summary.json").read_text()) for b in blocks}
    models = verified_models(bundle)
    for summary in summaries.values():
        if summary["protocol_sha256"] != file_hash(PROTOCOL_PATH) or any(
            summary["models"][a]["weights_sha256"] != m["weights_sha256"] for a, m in models.items()
        ):
            raise ValueError("Scored weights or task differ from the bundle")
    csv_text = io.StringIO()
    writer = csv.writer(csv_text)
    writer.writerow(
        [
            "block",
            "seed",
            "planner",
            "outcome",
            "reason",
            "steps",
            "jaw_contact",
            "bilateral_jaw_contact",
            "ever_held",
            "peak_lift_m",
            "max_stable_carry_s",
        ]
    )
    for block, summary in summaries.items():
        for row in summary["trials"]:
            for name, result in row["arms"].items():
                writer.writerow(
                    [block, row["seed"], name]
                    + [
                        result.get(key)
                        for key in (
                            "outcome",
                            "reason",
                            "steps",
                            "contact",
                            "bilateral_contact",
                            "ever_held",
                            "peak_lift_m",
                            "max_stable_carry_s",
                        )
                    ]
                )
    (report / "trials.csv").write_text(csv_text.getvalue())
    name = "simulation-grasp-bundle.zip"
    files = {
        "data/motor.npz": source,
        "data/vision.pt": vision,
        "protocol.json": PROTOCOL_PATH,
        "weights/decoder.npz": bundle / "decoder.npz",
        "trials.csv": report / "trials.csv",
        "weights.json": report / "models.json",
        "policy-configs.json": report / "policy-configs.json",
        "development-screen.json": report / "development-screen.json",
    }
    for arch in models:
        for fname in ("config.json", "model.safetensors"):
            files[f"weights/{arch}/{fname}"] = bundle / arch / fname
        files[f"weights/{arch}-training.json"] = bundle / f"{arch}-training.json"
    for block in blocks:
        for fname in ("summary.json", "observations.json", "plans.npz"):
            files[f"{block}/{fname}"] = report / block / fname
        for frame in sorted((report / block / "frames").glob("*.png")):
            files[f"{block}/frames/{frame.name}"] = frame
    for optional in ("physical-shadow.json", "diffusion-940200.json", "diffusion-940200.mp4"):
        if (report / optional).is_file():
            files[optional] = report / optional
    archive = report / name
    verified_archive(archive, files)
    index = dict(
        domain="MuJoCo",
        physical_trials=0,
        training_seed=models["act"]["seed"],
        sha256=file_hash(archive),
        file=name,
        counts={b: s["counts"] for b, s in summaries.items()},
        n={b: s["total"] for b, s in summaries.items()},
        protocol_sha256=file_hash(PROTOCOL_PATH),
        models={k: m["weights_sha256"] for k, m in models.items()},
    )
    save_json(report / "study.json", index)
    if repository_results:
        repository_results.mkdir(parents=True, exist_ok=True)
        (repository_results / "trials.csv").write_text(csv_text.getvalue())
        save_json(repository_results / "study.json", index)
        shadow = report / "physical-shadow.json"
        if shadow.exists():
            save_json(repository_results / "physical-shadow.json", json.loads(shadow.read_text()))
        for block, summary in summaries.items():
            save_json(repository_results / (block + ".json"), summary)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report-dir", type=Path, default=OUTPUT)
    p.add_argument("--checkpoint-dir", type=Path, default=BUNDLE)
    p.add_argument("--source", type=Path, default=SOURCE)
    p.add_argument("--vision", type=Path, default=VISION)
    p.add_argument("--repository-results", type=Path)
    args = p.parse_args()
    publish(args.report_dir, args.checkpoint_dir, args.source, args.vision, args.repository_results)
