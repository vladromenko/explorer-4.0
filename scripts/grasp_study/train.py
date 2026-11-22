"""Fit or resume compact LeRobot motor policies from frozen train-only trajectories."""

import argparse
import fcntl
import json
import os
import shutil
import time
from pathlib import Path

import numpy as np
import torch

from explorer4.conditioned_grasp import (
    MOTOR_SHA256,
    create_policy,
    file_hash,
    fit_decoder,
    lerobot_inputs,
)
from explorer4.paths import DATA

DEFAULT_SOURCE = DATA / "runs/article-closeout-20261122/learned-trajectories/motor.npz"
DEFAULT_OUTPUT = DATA / "checkpoints/conditioned-grasp-v1"
BUDGET = {"act": 1000, "diffusion": 2000}


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(temporary, path)


def fit_architecture(name, output, inputs, targets, seed, device):
    steps = BUDGET[name]
    final = output / name
    metrics = output / f"{name}-training.json"
    decoder_hash = file_hash(output / "decoder.npz")
    identity = dict(
        architecture=name,
        seed=seed,
        steps=steps,
        batch=32,
        source_sha256=MOTOR_SHA256,
        decoder_sha256=decoder_hash,
    )
    if metrics.is_file():
        saved = json.loads(metrics.read_text())
        if (
            any(saved[k] != v for k, v in identity.items())
            or saved["weights_sha256"] != file_hash(final / "model.safetensors")
            or saved.get("config_sha256", file_hash(final / "config.json"))
            != file_hash(final / "config.json")
        ):
            raise ValueError("Existing model differs from the requested training run")
        return
    progress = output / f"{name}-optimizer.pt"
    if final.exists() and not progress.is_file():
        raise ValueError("Found unpublished model without a matching training checkpoint")
    torch.manual_seed(seed)
    policy = create_policy(name, device)
    optimizer = torch.optim.AdamW(policy.parameters(), lr=0.0006, weight_decay=0.0001)
    completed, elapsed, points = 0, 0.0, []
    if progress.exists():
        saved = torch.load(progress, map_location="cpu", weights_only=True)
        if saved["identity"] != identity or saved["device"] != device:
            raise ValueError("Resume checkpoint belongs to another recipe")
        policy.load_state_dict(saved["model"])
        optimizer.load_state_dict(saved["optimizer"])
        torch.set_rng_state(saved["cpu_rng"])
        if device == "cuda":
            torch.cuda.set_rng_state(saved["cuda_rng"])
        completed, elapsed, points = saved["step"], saved["elapsed"], saved["history"]
    policy.train()
    started = time.monotonic()
    batch = lerobot_inputs(inputs, name)
    batch.update(
        action=targets, action_is_pad=torch.zeros(targets.shape[:2], device=device, dtype=torch.bool)
    )
    for step in range(completed + 1, steps + 1):
        optimizer.zero_grad(set_to_none=True)
        loss, _ = policy(batch)
        if not torch.isfinite(loss):
            raise ValueError("Nonfinite optimization loss")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(policy.parameters(), 5.0)
        optimizer.step()
        if step % 100 == 0:
            duration = elapsed + time.monotonic() - started
            points.append(dict(step=step, objective=float(loss.detach()), seconds=duration))
            print(name, points[-1], flush=True)
        if step % 1000 == 0 or step == steps:
            checkpoint = dict(
                identity=identity,
                device=device,
                model=policy.state_dict(),
                optimizer=optimizer.state_dict(),
                step=step,
                elapsed=duration,
                history=points,
                cpu_rng=torch.get_rng_state(),
                cuda_rng=torch.cuda.get_rng_state() if device == "cuda" else None,
            )
            temporary = progress.with_suffix(".tmp")
            torch.save(checkpoint, temporary)
            os.replace(temporary, progress)
    if not final.is_dir():
        temporary = output / f".{name}-publishing"
        if temporary.is_dir():
            shutil.rmtree(temporary)
        policy.eval().save_pretrained(temporary)
        os.rename(temporary, final)
    else:
        # A stop after renaming the final directory may precede writing its metrics.
        from safetensors.torch import load_file

        weights = load_file(final / "model.safetensors")
        if set(weights) != set(policy.state_dict()) or any(
            not torch.equal(value.cpu(), weights[key]) for key, value in policy.state_dict().items()
        ):
            raise ValueError("Existing weights do not match the recovered final checkpoint")
    write_json(
        metrics,
        dict(
            **identity,
            parameters=sum(p.numel() for p in policy.parameters()),
            weights_sha256=file_hash(final / "model.safetensors"),
            config_sha256=file_hash(final / "config.json"),
            optimizer="AdamW",
            learning_rate=0.0006,
            device=device,
            history=points,
        ),
    )


def train(source, output, device, seed, architectures):
    if file_hash(source) != MOTOR_SHA256:
        raise ValueError("The frozen 32-demonstration source differs")
    if not 0 <= seed < 2**31:
        raise ValueError("Optimizer seed must be between 0 and 2^31-1")
    output.mkdir(exist_ok=True, parents=True)
    with (output / ".training.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        recipe_path = output / "recipe.json"
        recipe = dict(seed=seed, source_sha256=MOTOR_SHA256, budget=BUDGET, version=1)
        if recipe_path.is_file() and json.loads(recipe_path.read_text()) != recipe:
            raise ValueError("Choose an empty output directory for a different run")
        for metrics in output.glob("*-training.json"):
            if json.loads(metrics.read_text())["seed"] != seed:
                raise ValueError("Output belongs to a different optimizer seed")
        if not recipe_path.is_file():
            write_json(recipe_path, recipe)
        with np.load(source, allow_pickle=False) as archive:
            xy, actions = archive["xy"], archive["action"]
        if actions.shape != (32, 220, 6) or xy.shape != (32, 2):
            raise ValueError("Unexpected source dimensions")
        decoder, scores = fit_decoder(xy, actions)
        decoder_path = output / "decoder.npz"
        if decoder_path.is_file():
            with np.load(decoder_path) as old:
                if any(not np.allclose(old[k], decoder[k]) for k in decoder):
                    raise ValueError("Motor decoder changed")
        else:
            temporary = output / ".decoder.tmp.npz"
            np.savez(temporary, **decoder)
            os.rename(temporary, decoder_path)
        inputs = torch.tensor(
            (xy - decoder["xy_center"]) / decoder["xy_scale"], device=device, dtype=torch.float32
        )
        targets = torch.tensor(scores[:, :, None], device=device, dtype=torch.float32)
        for arch in architectures:
            fit_architecture(arch, output, inputs, targets, seed, device)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--architecture", choices=("act", "diffusion", "both"), default="both")
    args = parser.parse_args()
    torch.set_num_threads(1)
    train(
        args.source,
        args.output,
        args.device,
        args.seed,
        tuple(BUDGET) if args.architecture == "both" else (args.architecture,),
    )
