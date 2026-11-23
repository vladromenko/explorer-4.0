"""Package the scene-table replay and the separately registered simulation experiments."""

import argparse
import json
import subprocess
from pathlib import Path

from explorer4.paths import DATA, ROOT
from scripts.grasp_study.package import file_hash, verified_archive
from scripts.research_claims import A, D, G, claims


def release(destination):
    reports = DATA / "simlab/reports"
    files = {}

    def include(path):
        files[str(path.relative_to(ROOT))] = path

    for path in (
        ROOT / "README.md",
        ROOT / "scripts/research_claims.py",
        ROOT / "docs/paper/peer-assisted-robots.tex",
        ROOT / "docs/paper/references.bib",
        ROOT / "docs/RESEARCH_AUDIT.md",
        ROOT / "scripts/package_research_audit.py",
        ROOT / "scripts/plot_docking_outcomes.py",
        ROOT / "scripts/grasp_study/package.py",
    ):
        include(path)
    for directory in (
        A,
        G / "native-residual",
        G / "wrist-heatmap",
        G / "failure-watch",
        ROOT / "docs/paper/figures",
    ):
        for path in sorted(directory.glob("*")):
            if path.is_file():
                include(path)
    for _, _, source in claims():
        include(ROOT / source)
    for path in sorted((D / "research-audit").glob("*.json")):
        include(path)
    for path in (
        G / "study.json",
        G / "trials.csv",
        D / "knowledge_gap_sim/20261122-e1/protocol.json",
        D / "knowledge_gap_sim/20261122-e1/manifest.json",
        D / "peer-camera-docking/sequential-confirmation-protocol.json",
        D / "peer-camera-docking/action-value-pilot.json",
    ):
        include(path)
    components = json.loads(
        (D / "research-audit/simulation-components.json").read_bytes()
    )
    for name, receipt in components.items():
        path = reports / name
        if (
            path.stat().st_size != receipt["bytes"]
            or file_hash(path) != receipt["sha256"]
        ):
            raise ValueError(
                f"Experiment archive differs from its reviewed inputs: {name}"
            )
        files["experiments/" + name] = path
    for directory in (
        "grasp-active-initial-look-v1",
        "wrist-video-failure-watch-v1",
        "grasp-native-residual-v1",
    ):
        for path in sorted((reports / directory).rglob("*.json")):
            files["experiments/" + str(path.relative_to(reports))] = path
    for pattern in (
        "scripts/grasp_study/wrist_heatmap/*.py",
        "scripts/grasp_study/failure_watch*.py",
        "scripts/grasp_study/*residual*.py",
        "scripts/grasp_study/active_initial_look.py",
        "scripts/peer_action_value*.py",
        "explorer4/cognitive/action_value.py",
        "explorer4/grasp_residual.py",
        "configs/*lock*",
    ):
        for path in sorted(ROOT.glob(pattern)):
            if path.is_file():
                include(path)
    archive = destination / "reproduction.zip"
    destination.mkdir(parents=True, exist_ok=True)
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    for name, path in files.items():
        if path.is_relative_to(ROOT):
            committed = subprocess.check_output(
                ["git", "show", f"{source_commit}:{name}"], cwd=ROOT
            )
            if committed != path.read_bytes():
                raise ValueError(
                    f"Release input differs from its committed source: {name}"
                )
    metadata = {
        "source_commit": source_commit,
        "source_tree": f"https://github.com/vladromenko/explorer-4.0/tree/{source_commit}",
        "standalone_rebuild": "python3 scripts/research_claims.py --check",
        "print_table": "python3 scripts/research_claims.py",
        "physical_trials_contributed": 0,
        "scope": "Read-only replay of measured rows. Engine versions and the registered source/weight identities are inside the component experiments.",
    }
    descriptor = destination / "release.json"
    if descriptor.exists() and json.loads(descriptor.read_bytes()) != metadata:
        raise ValueError("Use a new release directory for a different revision")
    descriptor.write_text(json.dumps(metadata, indent=2) + "\n")
    files["release.json"] = descriptor
    verified_archive(archive, dict(sorted(files.items())))
    return {
        "file": archive.name,
        "sha256": file_hash(archive),
        "bytes": archive.stat().st_size,
        **metadata,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    print(json.dumps(release(parser.parse_args().out), indent=2))
