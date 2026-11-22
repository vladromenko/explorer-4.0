"""Recover a complete development fit from its original receipts, or package a completed run."""

import argparse
import json
import random
import zipfile
from pathlib import Path

import cv2

from scripts import peer_action_value_pilot as pilot
from scripts.peer_dock_study import digest, frozen
from scripts.peer_screen_evidence import capture_source


def recovered_rows(out, stage):
    rows = []
    for index, seed in enumerate(pilot.SPLITS[stage][1]):
        folder = out / stage / str(seed)
        reset = pilot.read(folder / "reset.json")
        frame = cv2.cvtColor(cv2.imread(str(folder / "initial.png")), cv2.COLOR_BGR2RGB)
        if (
            digest(folder / "initial-state.json") != reset["reset_sha256"]
            or digest(folder / "initial.png") != reset["camera_sha256"]
            or pilot.sha(frame.tobytes()) != reset["initial_rgb_sha256"]
        ):
            raise ValueError(f"Original start changed for {seed}")
        methods = {}
        for method in pilot.FIXED:
            trial = pilot.read(folder / (method + ".json"))
            expected = {
                "reset": reset,
                "protocol_sha256": digest(out / "protocol.json"),
                "model_sha256": None,
                "method": method,
                **pilot.trace_costs(trial["events"]),
            }
            if any(trial[k] != v for k, v in expected.items()):
                raise ValueError(f"Trial receipt differs for {seed}/{method}")
            methods[method] = trial
        quote, fault = pilot.context(index)
        rows.append(
            {
                "seed": seed,
                "methods": methods,
                "quote": quote,
                "hidden_fault_scoring_only": fault,
            }
        )
    return rows


def recover(out):
    pilot.register(out)
    if (out / "confirmation").exists():
        raise ValueError("Development recovery is closed after confirmation starts")
    pilot.fit(recovered_rows(out, "fit"), recovered_rows(out, "calibration"), out)


def restore_process_rng(snapshot):
    import numpy as np
    import torch

    from explorer4.sim.state_codec import load

    env = load(snapshot)["tasks"]["tank"]["env"]
    random.setstate(env["python_rng"])
    np.random.set_state(env["numpy_rng"])
    torch.set_rng_state(env["torch_rng"])


def resume_confirmation(out):
    from scripts.peer_action_value_evidence import confirm

    snapshots = sorted((out / "confirmation").glob("*/initial-state.json"))
    if not snapshots or not (out / "test-binding.json").is_file():
        raise ValueError("There is no bound, partially recorded confirmation to resume")
    restore_process_rng(snapshots[0])
    confirm(out)


def verify_measurements(out, binding, verified):
    from explorer4.cognitive.action_value import choose_action

    for stage, expected in binding["dev_trials_sha256"].items():
        captured = sorted((out / stage).glob("*/*.json"))
        checksum = pilot.sha(b"".join(bytes.fromhex(digest(f)) for f in captured))
        if checksum != expected:
            raise ValueError(f"Frozen development receipts changed in {stage}")
    model = {
        **pilot.read(out / "verified-fit.json"),
        "identity": binding["model_sha256"],
    }
    decisions = 0
    branches = 0
    for scene in verified["scenes"]:
        directory = out / "confirmation" / str(scene["seed"])
        for method in scene["methods"]:
            row = pilot.read(directory / (method + ".json"))
            if (
                row["win"] != int(row["terminal"]["task"] == "success")
                or row["sensing_s"] > 6.00001
                or row["seconds"] > 20.0001
                or row["model_sha256"] != binding["model_sha256"]
            ):
                raise ValueError(
                    "Independent terminal receipt, model or budget differs"
                )
            if row["decision"]:
                actual = choose_action(
                    admissible=[pilot.LOCAL, pilot.ASK],
                    forecasts=pilot.forecast(model, row["history"]),
                    fallback=pilot.LOCAL,
                    time_weight=pilot.TIME_PRICE,
                    help_weight=pilot.HELP_PRICE,
                    domain="sim",
                    model_sha256=model["identity"],
                )
                if actual != row["decision"]:
                    raise ValueError(
                        "Archived short history and model cannot reproduce decision"
                    )
                decisions += 1
            branches += 1
    frozen(
        out / "measurement-check.json",
        {
            "independent_scenes": len(verified["scenes"]),
            "branches_matching_terminal_and_budgets": branches,
            "conditional_decisions_reconstructed": decisions,
            "physical_trials": 0,
        },
    )


def package(out):
    import scripts.peer_action_value_evidence as evidence

    verified = evidence.report(out)
    registration = pilot.read(out / "test-binding.json")
    sources = {
        **pilot.read(out / "runtime-environment.json")["files"],
        **verified["materials"],
        "scripts/peer_action_value_evidence.py": pilot.read(
            out / "artifact-binding-protocol.json"
        )["source_sha256"],
        "explorer4/cognitive/action_value.py": registration["broker_sha256"],
    }
    verify_measurements(out, registration, verified)
    capture_source(out, {"software_hashes": sources})
    with zipfile.ZipFile(out / "frozen-source.zip") as source_archive:
        if any(pilot.sha(source_archive.read(k)) != v for k, v in sources.items()):
            raise ValueError("Frozen source does not match registration")
    files = [
        p
        for stage in pilot.SPLITS
        for p in sorted((out / stage).glob("*/*"))
        if p.suffix in {".json", ".png"}
    ]
    files += [
        out / f
        for f in (
            "protocol.json",
            "artifact-binding-protocol.json",
            "model.json",
            "verified-fit.json",
            "model-card.json",
            "test-binding.json",
            "runtime-environment.json",
            "result.json",
            "evidence.json",
            "measurement-check.json",
            "frozen-source.zip",
        )
    ]
    for receipt in (
        "development-recovery.json",
        "reset-reproduction.json",
        "development.log",
    ):
        if (out / receipt).is_file():
            files.append(out / receipt)
    manifest = {str(p.relative_to(out)): digest(p) for p in files}
    frozen(out / "reproduction-manifest.json", manifest)
    dest = out / "reproduction.zip"
    if not dest.exists():
        with zipfile.ZipFile(
            dest.with_suffix(".tmp"), "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for item in [*files, out / "reproduction-manifest.json"]:
                archive.write(item, str(item.relative_to(out)))
        dest.with_suffix(".tmp").replace(dest)
    with zipfile.ZipFile(dest) as archive:
        if archive.testzip() or any(
            pilot.sha(archive.read(k)) != v for k, v in manifest.items()
        ):
            raise ValueError("Reproduction package failed integrity verification")
    print(
        json.dumps(
            {
                "files": len(manifest),
                "sha256": digest(dest),
                "bytes": dest.stat().st_size,
            }
        )
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("phase", choices=("recover", "resume", "package"))
    cli.add_argument("--output", type=Path, default=pilot.OUT)
    args = cli.parse_args()
    {"recover": recover, "resume": resume_confirmation, "package": package}[args.phase](
        args.output
    )
