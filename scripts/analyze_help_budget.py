"""Exact fixed-budget comparison for the archived, fully paired help pilot."""

import argparse
import csv
import json
from collections import Counter, defaultdict
from math import comb
from pathlib import Path


def summarize(path):
    scenes = defaultdict(dict)
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["study"] != "before-grasp-help":
                continue
            conditions = scenes[int(row["seed"])]
            name, outcome, asked = row["condition"], row["outcome"], row["requested_library"]
            if name in conditions or outcome not in {"success", "failure"} or asked not in {"0", "1"}:
                raise ValueError(f"Invalid paired outcome at seed {row['seed']} for {name}")
            conditions[name] = outcome == "success", int(asked)
    if not scenes:
        raise ValueError("No before-grasp-help scenes in input")

    differences = Counter()
    local_holds = selected_holds = budget = 0
    for seed, conditions in scenes.items():
        local, _ = conditions["local"]
        helper, _ = conditions["helper"]
        selected, asked = conditions["gated"]
        if selected != (helper if asked else local):
            raise ValueError(f"Selected outcome disagrees with recorded action at seed {seed}")
        differences[helper - local] += 1
        local_holds += local
        selected_holds += selected
        budget += asked

    # Each equally likely assignment chooses helped, harmed and tied scenes.
    improved, harmed, tied = differences[1], differences[-1], differences[0]
    counts = Counter()
    for gains in range(min(budget, improved) + 1):
        for losses in range(min(budget - gains, harmed) + 1):
            neutral = budget - gains - losses
            if neutral <= tied:
                counts[local_holds + gains - losses] += (
                    comb(improved, gains) * comb(harmed, losses) * comb(tied, neutral)
                )
    total = comb(len(scenes), budget)
    assert sum(counts.values()) == total
    return {
        "scenes": len(scenes), "budget": budget, "local_holds": local_holds,
        "selected_holds": selected_holds, "improved": improved, "harmed": harmed, "tied": tied,
        "assignments": total, "assignments_by_holds": dict(sorted(counts.items())),
        "uniform_expected_holds": sum(holds * count for holds, count in counts.items()) / total,
        "uniform_fraction_at_least_selected": sum(n for h, n in counts.items() if h >= selected_holds) / total,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paired_csv", type=Path)
    print(json.dumps(summarize(parser.parse_args().paired_csv), indent=2))
