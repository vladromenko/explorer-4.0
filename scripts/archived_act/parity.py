"""Whole-episode verification using one existing full-render trace, with sequential model and simulator stages."""
import argparse
import json
from pathlib import Path
import resource
import subprocess
import tempfile
import time

import numpy as np

from explorer4.paths import ROOT, offline_environment
from scripts.audit_floor_checkpoints import PHYSICS, PROFILE, PUBLIC, SEEDS, STEPS, digest, persist
from .common import QUEUE_LENGTH, UNUSED_RGB, array_hash, guard, read, source_ids
from .run import FloorTrace, make_floor

SEED = SEEDS[0]
STEP = STEPS[0]
REFERENCE = PUBLIC / str(STEP) / f"floor-trial-{SEED}.json"
METRICS = PUBLIC / str(STEP) / "evaluation.json"
PROOF = PUBLIC / f"fast-parity-{SEED}.json"


def simulator(work):
    from contextlib import closing
    _, weight = guard(STEP)
    old = read(REFERENCE)
    if (old["profile"], old["seed"], old["model"], old["checkpoint_sha256"]) != (PROFILE, SEED, PHYSICS, weight):
        raise ValueError("Reference is not the frozen archival trial")
    recorded = np.asarray(old["qpos"], dtype="<f8")
    with closing(make_floor()) as env:
        if env.manifest["xml_sha256"] != PHYSICS:
            raise ValueError("Simulator geometry mismatch")
        trial = FloorTrace(env, SEED)
        actions = np.load(work / "actions.npy")
        for action in actions:
            trial.tick(action.tolist())
        realized = np.asarray(trial.qpos, dtype="<f8")
        if realized.tobytes() != recorded[:len(realized)].tobytes():
            where = np.where(np.any(realized.view("u8") != recorded[:len(realized)].view("u8"), axis=1))[0]
            raise ValueError(f"Legacy and reduced-camera physics differ at tick {where[0]}")
        if trial.done:
            row = trial.row()
            baseline = next(r for r in read(METRICS)["trials"] if r["seed"] == SEED)
            differences = {k: (x, row[k]) for k, x in baseline.items() if row[k] != x}
            if len(recorded) != len(realized) or differences or old["outcome"] != row["outcome"]:
                raise ValueError(f"Legacy and reduced-camera terminal diagnostics differ: {differences}")
            persist(work / "metrics.json", row)
            return
        end = min(len(actions) + QUEUE_LENGTH, len(recorded)-1)
        if end <= len(actions):
            raise ValueError("Archived trace ended before simulator termination")
        states = np.asarray([env.from_radians(q[:6]).astype(np.float32) for q in recorded[len(actions):end]])
        if states[0].tobytes() != trial.obs["state"].tobytes():
            raise ValueError("Native servo observation differs")
        np.savez(work / "inputs.npz", rgb=env.render(), states=states, task=trial.task["task"], camera=trial.task["camera"])


def inference(work):
    import torch
    from explorer4.policy_runtime import PolicyCore
    from explorer4.sim_protocol import bundle_identity
    bank, weight = guard(STEP)
    torch.set_num_threads(2)
    identity = bundle_identity(bank)
    if identity["checkpoint_sha256"] != weight:
        raise ValueError("Incorrect reference checkpoint")
    core = PolicyCore(bank, "cpu")
    with np.load(work / "inputs.npz") as inputs:
        rgb, states, task = inputs["rgb"], inputs["states"], str(inputs["task"])
        name = "observation.images." + str(inputs["camera"])
    previous = np.load(work / "actions.npy")
    outputs = []
    for tiny in (False, True):
        torch.manual_seed(SEED)
        core.reset()
        actions = []
        for index, state in enumerate(states):
            if core.needs_inference() != (index == 0):
                raise ValueError("Official LeRobot queue consumed RGB on an unexpected tick")
            # The reference previously rendered every image. ACT's queue neither sees the prepared
            # batch nor consults RGB between predictions. Use the latest full RGB for these inert calls.
            pixels = UNUSED_RGB if tiny and index else rgb
            actions.append(core.act(state.tolist(), {name: pixels}, task))
        outputs.append(np.asarray(actions, dtype="<f8"))
    if outputs[0].tobytes() != outputs[1].tobytes():
        raise ValueError("Native full-size and reduced ACT input produced different actions")
    np.save(work / "actions.npy", np.concatenate([previous, outputs[1]]))
    np.save(work / "reference.npy", np.concatenate([np.load(work / "reference.npy"), outputs[0]]))
    print(f"Verified actions {len(previous)}..{len(previous)+len(states)-1}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("simulator", "inference"))
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    if args.stage:
        (simulator if args.stage == "simulator" else inference)(args.work)
        return
    bank, weight = guard(STEP)
    from explorer4.sim_protocol import bundle_identity
    identity = bundle_identity(bank)
    if identity["checkpoint_sha256"] != weight:
        raise ValueError("Archival model mismatch")
    if not REFERENCE.exists() or not METRICS.exists():
        raise SystemExit("Wait for the first complete legacy floor trial and its diagnostics")
    reference_hash = digest(REFERENCE)
    proof_sources = source_ids()
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="explorer-archived-act-") as temporary:
        work = Path(temporary)
        for name in ("actions", "reference"):
            np.save(work / (name + ".npy"), np.empty((0, 6), dtype="<f8"))
        def stage(name, venv):
            subprocess.run([ROOT / venv / "bin/python", "-m", "scripts.archived_act.parity", "--stage", name,
                            "--work", work], cwd=ROOT, check=True, env={**offline_environment(), "OMP_NUM_THREADS": "1" if name=="simulator" else "4"}, timeout=180)
        while True:
            stage("simulator", ".venv-sim")
            if (work / "metrics.json").exists():
                break
            stage("inference", ".venv")
        actions = np.load(work / "actions.npy")
        reference_actions = np.load(work / "reference.npy")
        if not len(actions) or reference_hash != digest(REFERENCE) or proof_sources != source_ids() or bundle_identity(bank) != identity:
            raise ValueError("Inputs changed while verifying parity")
        row = read(work / "metrics.json")
        proof = dict(verified=True, seed=SEED, training_step=STEP, optimizer_updates=0, physical_trials=0,
                     checkpoint_sha256=weight, checkpoint_bundle_sha256=identity["checkpoint_bundle_sha256"],
                     physics_xml_sha256=PHYSICS, legacy_trace_sha256=reference_hash, sources_sha256=proof_sources,
                     full_renderer_qpos_sha256=array_hash(read(REFERENCE)["qpos"]), optimized_qpos_sha256=row["all_qpos_sha256"],
                     native_reference_actions_sha256=array_hash(reference_actions), optimized_actions_sha256=array_hash(actions),
                     byte_encoding="Little-endian float64 in time, channel order, including reset qpos.",
                     native_reference="Native full-renderer archive supplies every qpos and terminal metrics. The archive does not store actions. Actions are reconstructed with stock CPU LeRobot, true refresh frames, authentic servo states and full-sized previous RGB on queued ticks whose model inputs are ignored. The independent candidate uses 1x1 RGB on those same ticks.",
                     metrics_comparison="Exact equality for every legacy field and every qpos byte, no tolerance.",
                     peak_child_rss_mib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024,
                     sequential_child_wall_seconds=round(time.monotonic()-start, 3), trial=row)
        if proof["full_renderer_qpos_sha256"] != proof["optimized_qpos_sha256"] or proof["native_reference_actions_sha256"] != proof["optimized_actions_sha256"]:
            raise ValueError("Final whole-episode parity check failed")
        persist(PROOF, proof)
        print(json.dumps(proof), flush=True)


if __name__ == "__main__":
    main()
