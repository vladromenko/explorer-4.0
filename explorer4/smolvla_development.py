"""A bounded, offline SmolVLA adaptation to the original ROSMASTER cube demonstrations."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from importlib.metadata import version
from pathlib import Path

import numpy as np

from .conditioned_grasp import PHYSICS_SHA256, PROFILE
from .floor_development_gate import checked_summary, read, run_evaluator, write
from .paths import DATA, ROOT, offline_environment
from .policy_catalog import SMOL_REV, VLM_REV, smolvla_paths
from .sim_protocol import bundle_identity, scene_revision, sha256_file
from .training_drafts import load, save_content

ORIGINAL_DRAFT = "680354eb6c963ad0a4002dc4eda7d4e948992430214399c3c0e882be72d41f5e"
REFERENCE = ROOT / "docs/results/conditioned_grasp_v1/development.json"
DEV_SEEDS = list(range(940100, 940108))
PUBLIC = DATA / "simlab/reports/smolvla-recorded-start"
RAW_CONTROLS = {"act": ("25", 25), "diffusion": ("diffusion", 10)}
PUBLIC_WEIGHTS = {
    SMOL_REV: "7cd549ac2351fb069c0ddb3c34ad2d09cfc92b56a15dccdfc2e41467aaca01eb",
    VLM_REV: "b9bfd456c9472c0acd5719d6e514c4b859891af205ee1a736552fd3497b8b0c3",
}
STEPS = 500
BATCH = 8


def public_assets():
    base, vlm = smolvla_paths()
    assets = {
        root.name: {
            p.name: sha256_file(p)
            for p in sorted(root.iterdir())
            if p.suffix in (".safetensors", ".json", ".txt")
        }
        for root in (base, vlm)
    }
    if any(
        assets[rev]["model.safetensors"] != digest
        for rev, digest in PUBLIC_WEIGHTS.items()
    ):
        raise ValueError("Local weights differ from the pinned Hugging Face revision")
    return assets


def archived_model(arm):
    suffix, horizon = RAW_CONTROLS[arm]
    report = read(
        DATA
        / f"simlab/reports/recorded-start-night/improvement-confirmation-{suffix}-trials.json"
    )
    model = Path(report["checkpoint"])
    if (
        report["policy"] != arm
        or report["n_action_steps"] != horizon
        or report["checkpoint_sha256"] != sha256_file(model / "model.safetensors")
    ):
        raise ValueError(f"Archived {arm} control changed")
    return model


def freeze_starts():
    """Match the existing eight physics snapshots, then pin the raw reset camera before any action."""
    from .sim.factory import make
    from .sim.seeded_start import fingerprint, save_reference

    env = make(PROFILE, images=True)
    try:
        if env.manifest["xml_sha256"] != PHYSICS_SHA256:
            raise ValueError("Recorded-start physics changed")
        rows = read(REFERENCE)["trials"]
        if [r["seed"] for r in rows] != DEV_SEEDS:
            raise ValueError("Development scene order changed")
        starts = []
        for row in rows:
            seed = row["seed"]
            obs, _ = env.reset(seed=seed)
            reset = env.snapshot()["physics"]
            if (
                hashlib.sha256(reset.tobytes()).hexdigest()
                != row["initial"]["reset_sha256"]
                or obs["state"].tolist() != row["initial"]["arm"]
                or env.data.body("task_cube").xpos.tolist() != row["initial"]["cube"]
            ):
                raise ValueError(f"Physical start differs at {seed}")
            starts.append(
                {
                    **fingerprint(seed, env, obs),
                    "reference_png_sha256": save_reference(obs["rgb"]),
                }
            )
        return starts
    finally:
        env.close()


def training_statistics(train):
    stats = [read(Path(r["dataset"]) / "meta/stats.json") for r in train]
    result = {}
    for key in ("observation.state", "action"):
        means = np.array([s[key]["mean"] for s in stats])
        stds = np.array([s[key]["std"] for s in stats])
        counts = [s[key]["count"][0] for s in stats]
        mean = np.average(means, axis=0, weights=counts)
        variance = np.average(stds**2 + (means - mean) ** 2, axis=0, weights=counts)
        result[key] = {"mean": mean.tolist(), "std": np.sqrt(variance).tolist()}
    return result


def recipe(train):
    proc = subprocess.run(
        [
            str(ROOT / ".venv-sim/bin/python"),
            "-m",
            "explorer4.smolvla_development",
            "starts",
        ],
        cwd=ROOT,
        env={**offline_environment(), "MUJOCO_GL": "egl"},
        text=True,
        stdout=subprocess.PIPE,
        check=True,
        timeout=120,
    )
    return {
        "version": 1,
        "initialization": "lerobot/smolvla_base@" + SMOL_REV,
        "vlm_revision": VLM_REV,
        "assets": public_assets(),
        "lerobot": version("lerobot"),
        "evaluator_sha256": sha256_file(ROOT / "explorer4/sim/evaluate.py"),
        "study_source_sha256": sha256_file(Path(__file__)),
        "reference_sha256": sha256_file(REFERENCE),
        "raw_controls": {a: bundle_identity(archived_model(a)) for a in RAW_CONTROLS},
        "train_statistics": training_statistics(train),
        "ordered_seeds": DEV_SEEDS,
        "starts": json.loads(proc.stdout.splitlines()[-1]),
        "scene_revision": scene_revision(PROFILE),
        "expected_geometry_sha256": PHYSICS_SHA256,
        "lift_cm": 1.0,
        "control": "Public weights with identical ROSMASTER train-only processors, no optimizer updates.",
        "arms": ["smolvla_finetuned", "smolvla_0_updates", "act", "diffusion"],
        "decision": "Evaluate all arms on eight development scenes once; no automatic extension or confirmation.",
    }


def prepare():
    from .datasets import load_plan

    draft = load(ORIGINAL_DRAFT)
    if (
        draft["profile"] != PROFILE
        or draft["split_counts"] != {"train": 32, "validation": 4, "test": 4}
        or draft["frames"]["train"] != 11497
        or draft["initial_checkpoint"] is not None
    ):
        raise ValueError("Wrong original training split")
    # Reuse the original content-addressed plan verbatim, including held-out episode IDs.
    candidate = {
        **draft,
        "policy": "smolvla",
        "steps": STEPS,
        "batch_size": BATCH,
        "mode": "public_smolvla_finetune",
        "smolvla_development": recipe(
            load_plan(draft["plan_id"], verify=False)["splits"]["train"]
        ),
        "checkpoint_interval": 250,
    }
    return save_content(DATA / "training-drafts", candidate)


def verify_before_train(cfg):
    spec = cfg["smolvla_development"]
    if (
        cfg["profile"] != PROFILE
        or cfg["plan_id"] != load(ORIGINAL_DRAFT)["plan_id"]
        or cfg["policy"] != "smolvla"
        or cfg["steps"] != STEPS
        or cfg["batch_size"] != BATCH
        or cfg["seed"] != 1000
        or cfg.get("initial_checkpoint") is not None
        or cfg["checkpoint_interval"] != 250
        or spec["assets"] != public_assets()
        or spec["study_source_sha256"] != sha256_file(Path(__file__))
        or spec["evaluator_sha256"] != sha256_file(ROOT / "explorer4/sim/evaluate.py")
        or spec["lerobot"] != version("lerobot")
        or spec["scene_revision"] != scene_revision(PROFILE)
        or spec["reference_sha256"] != sha256_file(REFERENCE)
        or spec["ordered_seeds"] != DEV_SEEDS
    ):
        raise ValueError("The recorded-start SmolVLA pilot changed after preparation")


def verify_processors(model, dataset, spec):
    from safetensors import safe_open

    from .profiles import profile

    cfg = read(model / "config.json")
    p = profile(PROFILE)
    meta = read(dataset / "meta/info.json")
    stats = read(dataset / "meta/stats.json")
    state, action, camera = "observation.state", "action", "observation.images.front"
    if (
        meta["fps"] != 20
        or meta["total_episodes"] != 32
        or meta["total_frames"] != 11497
        or meta["features"][action]["names"] != p["channels"]
        or meta["features"][state]["names"] != p["state_channels"]
        or p["units"] != ["native_servo_degrees"] * 6
        or p["state_units"] != p["units"]
        or meta["features"][camera]["shape"] != [480, 640, 3]
        or cfg["type"] != "smolvla"
        or cfg["input_features"][camera]["shape"] != [3, 480, 640]
        or cfg["input_features"][state]["shape"] != [6]
        or cfg["output_features"][action]["shape"] != [6]
        or cfg["normalization_mapping"]
        != {"VISUAL": "IDENTITY", "STATE": "MEAN_STD", "ACTION": "MEAN_STD"}
        or cfg["adapt_to_pi_aloha"]
        or cfg["use_delta_joint_actions_aloha"]
        or cfg["n_action_steps"] != 50
        or cfg["empty_cameras"] != 0
    ):
        raise ValueError(
            "Wrong ROSMASTER camera, six native joint targets, clip or normalization"
        )
    for role, step, features in (
        ("pre", "normalizer_processor", (state, action)),
        ("post", "unnormalizer_processor", (action,)),
    ):
        pipeline = read(model / f"policy_{role}processor.json")
        (entry,) = [row for row in pipeline["steps"] if row["registry_name"] == step]
        with safe_open(model / entry["state_file"], framework="np") as data:
            for feature in features:
                for stat in ("mean", "std"):
                    expected = np.asarray(
                        spec["train_statistics"][feature][stat], dtype=np.float32
                    )
                    if not np.array_equal(
                        data.get_tensor(f"{feature}.{stat}"), expected
                    ) or not np.array_equal(
                        np.asarray(stats[feature][stat], dtype=np.float32), expected
                    ):
                        raise ValueError(
                            f"Checkpoint uses wrong {role} statistics for {feature}.{stat}"
                        )
    return {
        "dataset_stats_sha256": sha256_file(dataset / "meta/stats.json"),
        "frames": meta["total_frames"],
        "camera": camera,
        "actions": p["channels"],
        "units": p["units"],
        "fps": meta["fps"],
    }


def public_control(work, trained, dataset, spec):
    """The control differs from the candidate only in its weights. Statistics are fitted to target data."""
    output = work / "public-weights-target-processors"
    output.mkdir(exist_ok=True)
    base, _ = smolvla_paths()
    originals = [
        p
        for p in trained.iterdir()
        if p.name == "config.json" or p.name.startswith("policy_")
    ]
    if (
        sha256_file(base / "model.safetensors")
        != spec["assets"][SMOL_REV]["model.safetensors"]
    ):
        raise ValueError("Public initialization changed")
    for src in [*originals, base / "model.safetensors"]:
        dest = output / src.name
        if not dest.exists():
            temp = output / ("." + src.name + ".tmp")
            temp.unlink(missing_ok=True)
            try:
                os.link(src, temp)
            except OSError:
                shutil.copyfile(src, temp)
            os.replace(temp, dest)
        if sha256_file(src) != sha256_file(dest):
            raise ValueError(
                "Public-weight control no longer matches its frozen inputs"
            )
    verify_processors(output, dataset, spec)
    return output


def score(cfg, work, model):
    spec = cfg["smolvla_development"]
    output = PUBLIC / work.name
    output.mkdir(parents=True, exist_ok=True)
    dataset = work / "train"
    contract = verify_processors(model, dataset, spec)
    if (
        sha256_file(model / "model.safetensors")
        == spec["assets"][SMOL_REV]["model.safetensors"]
    ):
        raise ValueError("Public and fitted weights are identical")
    policies = {
        "smolvla_finetuned": model,
        "smolvla_0_updates": public_control(work, model, dataset, spec),
    }
    for name in RAW_CONTROLS:
        policies[name] = archived_model(name)
    results = {}
    for name, path in policies.items():
        identity = bundle_identity(path)
        if name in RAW_CONTROLS and identity != spec["raw_controls"][name]:
            raise ValueError("Archived control bundle changed")
        kind = name if name in RAW_CONTROLS else "smolvla"
        dest = output / name
        dest.mkdir(exist_ok=True)
        raw = dest / "evaluation.json"
        gate = {**spec, "policy": kind}
        print(
            f"SmolVLA development: {name}, {len(DEV_SEEDS)} scenes, {raw}", flush=True
        )
        write(dest / "starts.json", spec["starts"])
        complete = False
        if raw.exists():
            try:
                cached = read(raw)
                if cached.get("status") == "completed":
                    checked_summary(cached, gate, path, identity, None, dest)
                    complete = True
            except (KeyError, TypeError, ValueError, OSError):
                raw.rename(
                    dest / f"invalid-{len(list(dest.glob('invalid-*.json'))) + 1}.json"
                )
        if not complete:
            args = [
                str(ROOT / ".venv-sim/bin/python"),
                "-m",
                "explorer4.sim.evaluate",
                str(path),
                str(raw),
                "--profile",
                PROFILE,
                "--expected-model-sha256",
                PHYSICS_SHA256,
                "--record-floor",
                "--seed-policy-per-scene",
                "--development-starts",
                str(dest / "starts.json"),
                "--seeds",
                *map(str, DEV_SEEDS),
            ]
            if name == "act":
                args += ["--act-action-steps", "25"]
            env = {**offline_environment(), "MUJOCO_GL": "egl"}
            env.pop("EXPLORER_N_ACTION_STEPS", None)
            with (dest / "rollout.log").open("a") as log:
                run_evaluator(args, env=env, log=log).check_returncode()
        measured = read(raw)
        expected_horizon = RAW_CONTROLS[name][1] if name in RAW_CONTROLS else 50
        if measured["n_action_steps"] != expected_horizon:
            raise ValueError("Execution horizon differs from the declared control")
        summary = checked_summary(measured, gate, path, identity, None, dest)
        results[name] = {
            **summary,
            "per_scene": [
                {"seed": r["seed"], "outcome": r["outcome"], "reason": r["reason"]}
                for r in measured["trials"]
            ],
        }
        print(
            f"{name}: {summary['task_successes']}/{summary['scenes']} terminal successes",
            flush=True,
        )
    summary = {
        "role": "development",
        "draft": cfg["draft_id"],
        "plan": cfg["plan_id"],
        "optimizer_updates": STEPS,
        "training_seed": cfg["seed"],
        "contract": contract,
        "results": results,
        "conditioned_reference": read(REFERENCE)["counts"],
        "seeds": DEV_SEEDS,
        "initialization": spec["initialization"],
        "physical_trials": 0,
        "confirmation_opened": False,
        "scope": "From reset: native RGB and joint feedback. Conditioned references used a separate camera look, XY supervision and a trajectory decoder. Development comparisons describe entire pipelines.",
    }
    write(output / "result.json", summary)
    return str(output / "result.json")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("prepare", "starts", "stage"))
    cli.add_argument("--draft")
    args = cli.parse_args()
    if args.action == "starts":
        print(json.dumps(freeze_starts(), allow_nan=False))
    elif args.action == "prepare":
        print(prepare())
    else:
        from .jobs import Jobs

        if not args.draft or not load(args.draft).get("smolvla_development"):
            cli.error("Supply the prepared SmolVLA draft")
        print(Jobs(None).start_prepared_training(args.draft))
