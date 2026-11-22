"""Recover object labels for published paired SmolVLA outcomes by replaying only the original resets."""

import json
from collections import Counter
from pathlib import Path

from explorer4.conditioned_grasp import file_hash
from explorer4.paths import ROOT
from explorer4.sim.factory import make

ARCHIVE = ROOT / "docs/results/e3_diagnostics/smolvla_v4_state.json"
PHASES = ROOT / "docs/results/e3_diagnostics/smolvla_v4_knowledge_phases.json"
OUTPUT = ROOT / "docs/results/research-audit-20261122/smolvla-v4-objects.json"


def audit():
    data = json.loads(ARCHIVE.read_bytes())
    measured_tasks = {r["seed"]: r["task"] for r in json.loads(PHASES.read_bytes())}
    hinted, plain = data["protocol"]["profiles"]
    trials = {name: data["jobs"][name]["result"]["trials"] for name in (hinted, plain)}
    first, last = data["protocol"]["evaluation_seeds"]
    expected = list(range(first, last + 1))
    if any([r["seed"] for r in block] != expected for block in trials.values()):
        raise ValueError("Published comparisons do not use the same ordered seeds")
    env = make(hinted, images=False)
    rows = []
    try:
        if env.manifest["xml_sha256"] != data["protocol"]["model_sha256"]:
            raise ValueError("MuJoCo model differs from the paired study")
        for a, b in zip(trials[hinted], trials[plain], strict=True):
            seed = a["seed"]
            env.reset(seed=seed)
            if seed in measured_tasks and measured_tasks[seed] != env.task_text:
                raise ValueError("Reset no longer matches the archived phase record")
            rows.append(
                {
                    "seed": seed,
                    "object": env.object_name,
                    "instruction": env.task_text,
                    "with_size": a["outcome"],
                    "without_size": b["outcome"],
                }
            )
    finally:
        env.close()
    by_object = {}
    for obj in sorted({r["object"] for r in rows}):
        subset = [r for r in rows if r["object"] == obj]
        by_object[obj] = {
            k: dict(Counter(r[k] for r in subset))
            for k in ("with_size", "without_size")
        }
    return {
        "input_sha256": file_hash(ARCHIVE),
        "phase_checks_sha256": file_hash(PHASES),
        "simulation_xml_sha256": data["protocol"]["model_sha256"],
        "source_sha256": file_hash(Path(__file__)),
        "scope": "The reset supplies the object and instruction for each seed. All terminal outcomes come unchanged from the historical evaluation. The phase diagnostics serve only to check the instructions.",
        "phase_crosschecks": len(measured_tasks),
        "counts": by_object,
        "rows": rows,
    }


if __name__ == "__main__":
    result = audit()
    if OUTPUT.exists() and json.loads(OUTPUT.read_bytes()) != result:
        raise ValueError("Existing audit differs from the archived study")
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(result["counts"])
