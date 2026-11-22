"""Compare two frozen optimizer runs on identical observations and terminal outcomes."""

import argparse
import hashlib
import json
from pathlib import Path

from explorer4.paths import ROOT
from explorer4.study_queue import write_json


def load(path):
    return json.loads(path.read_bytes())


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def compare(original_dir, replication_dir, checkpoints):
    baseline = load(original_dir / "study.json")
    replica = load(replication_dir / "models.json")
    completion = load(replication_dir / "summary.json")
    if completion.get("result") != "confirmation_completed":
        raise ValueError("The two confirmation blocks have not completed")
    if baseline["protocol_sha256"] != replica["protocol_sha256"]:
        raise ValueError("The replication used a different protocol")
    if baseline["training_seed"] == replica["optimizer_seed"]:
        raise ValueError("Expected independently optimized weights")
    for name, expected in replica["weights"].items():
        if (
            expected == baseline["models"][name]
            or digest(checkpoints / name / "model.safetensors") != expected
        ):
            raise ValueError(f"Unverified new weights for {name}")

    coverage = {
        r["seed"]: r["reset_in_train_hull"]
        for r in load(original_dir / "fresh-coverage.json")["rows"]
    }
    result = {
        "domain": "MuJoCo, terminal one-second carry hold",
        "physical_trials": 0,
        "original_optimizer_seed": baseline["training_seed"],
        "original_weights": baseline["models"],
        "replication": replica,
        "blocks": {},
    }
    for block in ("development", "fresh", "historical_confirmation"):
        files = [
            original_dir / f"{block}.json",
            replication_dir / block / "summary.json",
        ]
        first, second = map(load, files)
        for name, weights in replica["weights"].items():
            old, new = first["models"][name], second["models"][name]
            for field in (
                "source_sha256",
                "decoder_sha256",
                "batch",
                "steps",
                "optimizer",
                "learning_rate",
            ):
                if old[field] != new[field]:
                    raise ValueError(f"Changed {name} training {field}")
            if (
                new["weights_sha256"] != weights
                or old["weights_sha256"] != baseline["models"][name]
            ):
                raise ValueError(f"Invalid {name} weight versions in {block}")
        if {first["total"], second["total"]} != {baseline["n"][block]}:
            raise ValueError(f"Changed denominator for {block}")
        rows = []
        outcomes = {}
        for old, new in zip(first["trials"], second["trials"], strict=True):
            seed = old["seed"]
            for field in (
                "seed",
                "initial",
                "lookup_state_sha256",
                "rgb_sha256",
                "predicted_xy",
            ):
                if old[field] != new[field]:
                    raise ValueError(f"Unmatched scene {seed} at {field}")
            if set(old["arms"]) != set(new["arms"]):
                raise ValueError(f"Different controllers at {seed}")
            row = {
                "seed": seed,
                "reset_sha256": old["initial"]["reset_sha256"],
                "rgb_sha256": old["rgb_sha256"],
            }
            if block == "fresh":
                row["inside_training_hull"] = coverage[seed]
            row["terminal_holds"] = {}
            for name, before in old["arms"].items():
                after = new["arms"][name]
                if name in ("rbf", "ik", "constant") and before != after:
                    raise ValueError(
                        f"Deterministic controller {name} did not reproduce scene {seed}"
                    )
                pair = [r["outcome"] == "success" for r in (before, after)]
                row["terminal_holds"][name] = pair
                counts = outcomes.setdefault(
                    name,
                    {"both": 0, "original_only": 0, "replica_only": 0, "neither": 0},
                )
                category = {
                    (True, True): "both",
                    (True, False): "original_only",
                    (False, True): "replica_only",
                    (False, False): "neither",
                }[tuple(pair)]
                counts[category] += 1
            rows.append(row)
        if len(rows) != first["total"] or len({row["seed"] for row in rows}) != len(
            rows
        ):
            raise ValueError(f"Incomplete scene list for {block}")
        for name, count in outcomes.items():
            if (
                count["both"] + count["original_only"],
                count["both"] + count["replica_only"],
            ) != (
                first["counts"][name],
                second["counts"][name],
            ):
                raise ValueError(
                    f"Aggregate disagrees with {block} per-scene results for {name}"
                )
        result["blocks"][block] = {
            "total": len(rows),
            "paired_counts": outcomes,
            "source_summary_sha256": list(map(digest, files)),
            "scenes": rows,
        }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replication-dir", type=Path, required=True)
    parser.add_argument("--checkpoints", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = ROOT / "docs/results/conditioned_grasp_v1"
    write_json(args.output, compare(source, args.replication_dir, args.checkpoints))
