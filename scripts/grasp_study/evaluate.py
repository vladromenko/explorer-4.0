"""Prepare calibrated RGB inputs, predict motor plans, and run paired MuJoCo trials."""

import argparse
import fcntl
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

from explorer4.conditioned_grasp import (
    LOOK_COMMAND,
    LOOK_STEPS,
    MOTOR_SHA256,
    PHYSICS_SHA256,
    PROFILE,
    SLEW_DEGREES_PER_SECOND,
    TrajectoryPolicy,
    file_hash,
    load_localizer,
    locate_cube,
)
from explorer4.paths import DATA

PROTOCOL_PATH = Path(__file__).with_name("protocol.json")
PROTOCOL = json.loads(PROTOCOL_PATH.read_text())
SOURCE = DATA / "runs/article-closeout-20261122/learned-trajectories/motor.npz"
VISION = DATA / "runs/recorded-start-cube-20261121/night/visual-pick-v1/weights.pt"
OUTPUT = DATA / "simlab/reports/conditioned-grasp-v1"
BUNDLE = DATA / "checkpoints/conditioned-grasp-v1"


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def sha_array(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def seed_range(block):
    first, last = PROTOCOL[block]
    return range(first, last + 1)


def environment():
    from explorer4.sim.factory import make

    env = make(PROFILE, images=False)
    if env.manifest["xml_sha256"] != PHYSICS_SHA256:
        env.close()
        raise ValueError("MuJoCo geometry differs from the frozen task")
    return env


def observe(env, seed, render=True):
    obs, _ = env.reset(seed=seed)
    initial = dict(
        arm=obs["state"].tolist(),
        cube=env.data.body("task_cube").xpos.copy().tolist(),
        reset_sha256=sha_array(env.snapshot()["physics"]),
    )
    for _ in range(LOOK_STEPS):
        _, _, done, timeout, _ = env.step(LOOK_COMMAND)
        if done or timeout:
            raise ValueError("Look terminated unexpectedly")
    image = env.render() if render else None
    return initial, image


def collect_inputs(block, output, vision, reference=None):
    import cv2
    import torch

    torch.set_num_threads(1)
    estimator = load_localizer(vision)
    destination = output / block
    target = destination / "observations.json"
    source = reference / block if reference else destination
    if target.exists() or reference:
        observation_file = source / "observations.json"
        observations = json.loads(observation_file.read_text())
        if target.exists() and json.loads(target.read_text()) != observations:
            raise ValueError("Different observations are already frozen here")
        if set(observations) != {str(i) for i in seed_range(block)}:
            raise ValueError("Frozen observations do not cover the declared seeds")
        for seed in seed_range(block):
            row = observations[str(seed)]
            frame = source / "frames" / f"{seed}.png"
            bgr = cv2.imread(str(frame))
            if bgr is None or sha_array(bgr[:, :, ::-1]) != row["rgb_sha256"]:
                raise ValueError("Frozen RGB bytes changed")
            xy = locate_cube(estimator, bgr[:, :, ::-1])
            if not np.allclose(xy, row["predicted_xy"], atol=1e-7, rtol=0):
                raise ValueError("Frozen localizer does not reproduce the stored XY")
            if reference:
                (destination / "frames").mkdir(parents=True, exist_ok=True)
                shutil.copyfile(frame, destination / "frames" / frame.name)
        if not target.exists():
            save_json(target, observations)
        return
    env = environment()
    try:
        observations = {}
        for seed in seed_range(block):
            initial, image = observe(env, seed)
            image = cv2.resize(image, (160, 120), interpolation=cv2.INTER_AREA)
            frame = destination / "frames" / f"{seed}.png"
            frame.parent.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(frame), image[:, :, ::-1]):
                raise OSError("Could not preserve the RGB policy input")
            observations[seed] = dict(
                initial=initial,
                lookup_state_sha256=sha_array(env.snapshot()["physics"]),
                rgb_sha256=sha_array(image),
                predicted_xy=locate_cube(estimator, image).tolist(),
            )
        save_json(target, observations)
    finally:
        env.close()


def verified_models(bundle):
    decoder = file_hash(bundle / "decoder.npz")
    models = {}
    for name in ("act", "diffusion"):
        metrics = json.loads((bundle / f"{name}-training.json").read_text())
        config_hash = file_hash(bundle / name / "config.json")
        if (
            metrics.get("config_sha256", config_hash) != config_hash
            or metrics["source_sha256"] != MOTOR_SHA256
            or metrics["decoder_sha256"] != decoder
            or metrics["weights_sha256"] != file_hash(bundle / name / "model.safetensors")
        ):
            raise ValueError(f"Changed bundle for {name}")
        models[name] = {**metrics, "config_sha256": config_hash}
    if len({m["seed"] for m in models.values()}) != 1:
        raise ValueError("Cannot combine models from different optimizer seeds")
    return models


def bind_output(output, bundle):
    models = verified_models(bundle)
    identity = dict(
        optimizer_seed=models["act"]["seed"],
        protocol_sha256=file_hash(PROTOCOL_PATH),
        decoder_sha256=file_hash(bundle / "decoder.npz"),
        weights={name: metrics["weights_sha256"] for name, metrics in models.items()},
    )
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".output.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = output / "models.json"
        if path.exists() and json.loads(path.read_text()) != identity:
            raise ValueError("Output directory belongs to different weights or protocol")
        config_path = output / "policy-configs.json"
        config_hashes = {name: m["config_sha256"] for name, m in models.items()}
        if config_path.exists() and json.loads(config_path.read_text()) != config_hashes:
            raise ValueError("Policy configs changed after the study began")
        if not config_path.exists():
            save_json(config_path, config_hashes)
        if not path.exists():
            if output.resolve() == OUTPUT.resolve() and identity["optimizer_seed"] != 1000:
                raise ValueError("Choose a new report directory for a replication")
            save_json(path, identity)


def build_plans(block, output, bundle, source):
    import torch
    from scipy.interpolate import RBFInterpolator

    torch.set_num_threads(1)
    if file_hash(source) != MOTOR_SHA256:
        raise ValueError("Wrong motor demonstration bank")
    with np.load(source, allow_pickle=False) as samples:
        xy, actions = samples["xy"], samples["action"]
    rbf = RBFInterpolator(xy / 0.05, actions, smoothing=0.005, kernel="thin_plate_spline")
    neural = {arch: TrajectoryPolicy(bundle, arch) for arch in ("act", "diffusion")}
    observations = json.loads((output / block / "observations.json").read_text())
    plans = {}
    for seed in seed_range(block):
        goal = np.array(observations[str(seed)]["predicted_xy"])
        mean = xy.mean(axis=0)
        plans[f"{seed}_rbf"] = rbf(goal[None] / 0.05)[0]
        plans[f"{seed}_constant"] = rbf(mean[None] / 0.05)[0]
        for arch, planner in neural.items():
            plans[f"{seed}_{arch}"] = planner.trajectory(goal)
            plans[f"{seed}_{arch}_constant"] = planner.trajectory(mean)
    np.savez_compressed(output / block / "plans.npz", **plans)


class GraspMetrics:
    def __init__(self, env, initial_height):
        self.initial_height = initial_height
        self.cube = env.model.body("task_cube").id
        self.jaw_side = {
            env.model.body(prefix + str(i)).id: side
            for side, prefix in [("left", "llink"), ("right", "rlink")]
            for i in (1, 2, 3)
        }
        self.contact = self.bilateral = self.held = False
        self.peak_lift = self.stable = 0.0

    def measure(self, env, info):
        sides = set()
        for contact in env.data.contact:
            a, b = env.model.geom_bodyid[[contact.geom1, contact.geom2]]
            other = b if a == self.cube else a if b == self.cube else None
            if other in self.jaw_side:
                sides.add(self.jaw_side[other])
        self.contact |= bool(sides)
        self.bilateral |= len(sides) == 2
        self.held |= info["held"]
        self.peak_lift = max(self.peak_lift, env.data.body("task_cube").xpos[2] - self.initial_height)
        self.stable = max(self.stable, env.stable)

    def result(self, reason, steps):
        return dict(
            outcome="success" if reason == "held_in_carry_pose" else "failure",
            reason=reason,
            steps=steps,
            contact=self.contact,
            bilateral_contact=self.bilateral,
            ever_held=bool(self.held),
            peak_lift_m=float(self.peak_lift),
            max_stable_carry_s=float(self.stable),
        )


def ik_targets(env, xy):
    from explorer4.sim.vendor_rosmaster.arm_model import ArmModel

    arm = ArmModel(tcp_offset=float(env.model.site("gripperframe").pos[2]))
    origin = env.elapsed
    for end, height, grip in [
        (2.5, 0.10, 30),
        (4.5, 0.004, 30),
        (6.5, 0.004, 150),
        (8.0, 0.12, 150),
        (float("inf"), None, 150),
    ]:
        if height is None:
            target = np.r_[env.cfg["carry_pose"], grip]
        else:
            solution, _ = arm.grasp_ik([*xy, 0.018 + height], env.observation()["state"])
            if solution is None:
                return
            target = np.r_[solution, grip]
        while env.elapsed - origin < end:
            yield target


def trajectory_targets(plan):
    for target in plan:
        yield target
    while True:
        yield plan[-1]


def rollout(env, targets, height):
    metrics = GraspMetrics(env, height)
    command = env.observation()["state"].astype(float)
    limit = SLEW_DEGREES_PER_SECOND * env.dt
    for target in targets:
        command += np.clip(target - command, -limit, limit)
        _, _, done, timeout, info = env.step(command)
        metrics.measure(env, info)
        if done or timeout:
            return metrics.result(info["termination_reason"], env.steps)
    return metrics.result("unreachable_target", env.steps)


def score_worker(block, output, seeds):
    env = environment()
    observations = json.loads((output / block / "observations.json").read_text())
    plans_path = output / block / "plans.npz"
    signature = dict(
        protocol=file_hash(PROTOCOL_PATH),
        plans=file_hash(plans_path),
        observations=file_hash(output / block / "observations.json"),
    )
    try:
        with np.load(plans_path, allow_pickle=False) as plans:
            for seed in seeds:
                path = output / block / f"{seed}.json"
                if path.is_file():
                    if json.loads(path.read_text())["inputs"] != signature:
                        raise ValueError("Inputs changed after a trial was saved")
                    continue
                row = observations[str(seed)]
                initial, _ = observe(env, seed, render=False)
                import cv2

                frame = cv2.imread(str(output / block / "frames" / f"{seed}.png"))
                if (
                    initial != row["initial"]
                    or sha_array(env.snapshot()["physics"]) != row["lookup_state_sha256"]
                    or frame is None
                    or sha_array(frame[:, :, ::-1]) != row["rgb_sha256"]
                ):
                    raise ValueError("Seeded physics or the stored policy RGB input differs")
                snapshot = env.snapshot()
                outcomes = {}
                for arm in PROTOCOL["arms"]:
                    env.restore(snapshot)
                    if not np.array_equal(env.snapshot()["physics"], snapshot["physics"]):
                        raise ValueError("Physics restore did not reproduce initial state")
                    targets = (
                        ik_targets(env, row["predicted_xy"])
                        if arm == "ik"
                        else trajectory_targets(plans[f"{seed}_{arm}"])
                    )
                    outcomes[arm] = rollout(env, targets, initial["cube"][2])
                save_json(path, dict(seed=seed, inputs=signature, **row, arms=outcomes))
                print(block, seed, [k for k, r in outcomes.items() if r["outcome"] == "success"], flush=True)
    finally:
        env.close()


def score(block, output, workers):
    if workers < 1 or workers > 4:
        raise ValueError("Choose one to four simulation workers")
    seeds = list(seed_range(block))
    if workers == 1:
        score_worker(block, output, seeds)
        return
    from concurrent.futures import ProcessPoolExecutor
    from multiprocessing import get_context

    with ProcessPoolExecutor(workers, mp_context=get_context("spawn")) as pool:
        jobs = [pool.submit(score_worker, block, output, seeds[i::workers]) for i in range(workers)]
        for job in jobs:
            job.result()


def summarize(block, output, bundle):
    from scipy.stats import binomtest

    rows = [json.loads((output / block / f"{i}.json").read_text()) for i in seed_range(block)]
    models = verified_models(bundle)
    sums = {arm: sum(r["arms"][arm]["outcome"] == "success" for r in rows) for arm in PROTOCOL["arms"]}
    paired = {}
    for a, b in [
        ("act", "act_constant"),
        ("diffusion", "diffusion_constant"),
        ("rbf", "constant"),
        ("act", "rbf"),
        ("diffusion", "rbf"),
        ("act", "ik"),
        ("diffusion", "ik"),
    ]:
        gains = sum(
            r["arms"][a]["outcome"] == "success" and r["arms"][b]["outcome"] == "failure" for r in rows
        )
        losses = sum(
            r["arms"][a]["outcome"] == "failure" and r["arms"][b]["outcome"] == "success" for r in rows
        )
        paired[a + "_vs_" + b] = dict(
            gains=gains,
            losses=losses,
            exact_p=binomtest(gains, gains + losses).pvalue if gains + losses else 1.0,
        )
    summary = dict(
        protocol={**PROTOCOL, "training_seed": models["act"]["seed"]},
        protocol_sha256=file_hash(PROTOCOL_PATH),
        block=block,
        total=len(rows),
        counts=sums,
        paired=paired,
        models=models,
        trials=rows,
    )
    if block == "historical_confirmation":
        reference = DATA / "simlab/reports/recorded-start-night"
        summary["native_rgb_references"] = {}
        for key, name in [("act", "25"), ("diffusion", "diffusion")]:
            file = reference / f"improvement-confirmation-{name}-trials.json"
            digests = {
                "act": "f27bdfdb2ee012eaf5919501cebea3aebc873e78f9edcddce35c38f44b95c2f3",
                "diffusion": "dc8e2ac188d518dc4897f8b203685472db5ca64d48b6a4d186859e6c29dda194",
            }
            if file_hash(file) != digests[key]:
                raise ValueError("The historical native RGB baseline artifact changed")
            previous = json.loads(file.read_text())
            if previous["model"]["xml_sha256"] != PHYSICS_SHA256:
                raise ValueError("Baseline physics mismatch")
            for r, old in zip(rows, previous["trials"], strict=True):
                if (
                    r["seed"] != old["seed"]
                    or not np.array_equal(r["initial"]["arm"], old["initial_state"])
                    or not np.array_equal(r["initial"]["cube"], old["cube_xyz0"])
                ):
                    raise ValueError("Historical baseline reset mismatch")
                r["arms"]["native_rgb_" + key] = dict(
                    outcome=old["outcome"],
                    reason=old["reason"],
                    peak_lift_m=old["max_lift_cm"] / 100,
                    ever_held=old["ever_held"],
                    steps=old["steps"],
                )
            summary["native_rgb_references"][key] = dict(
                source=file.name,
                sha256=file_hash(file),
                weights_sha256=previous["checkpoint_sha256"],
                n_action_steps=previous["n_action_steps"],
            )
            sums["native_rgb_" + key] = sum(
                r["arms"]["native_rgb_" + key]["outcome"] == "success" for r in rows
            )
    save_json(output / block / "summary.json", summary)
    if block == "development":
        passed = sums["act"] + sums["diffusion"] > 0
        save_json(
            output / "development-screen.json",
            dict(
                status="completed",
                passed=passed,
                terminal_holds={key: sums[key] for key in ("act", "diffusion")},
                total=len(rows),
                optimizer_seed=models["act"]["seed"],
                next_stage="fresh" if passed else None,
            ),
        )
    if block == "fresh":
        save_json(output / "summary.json", summary)
    print(block, sums)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("observe", "plan", "score", "summarize"))
    parser.add_argument("block", choices=("development", "fresh", "historical_confirmation"))
    parser.add_argument("--output", "--report-dir", type=Path, default=OUTPUT)
    parser.add_argument("--reference-observations", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--vision", type=Path, default=VISION)
    parser.add_argument("--bundle", "--checkpoint-dir", type=Path, default=BUNDLE)
    args = parser.parse_args()
    bind_output(args.output, args.bundle)
    if args.block != "development":
        dev = json.loads((args.output / "development/summary.json").read_text())
        if (
            dev["protocol_sha256"] != file_hash(PROTOCOL_PATH)
            or dev["counts"]["act"] + dev["counts"]["diffusion"] == 0
        ):
            raise ValueError("Complete the frozen development screen first")
    if args.stage == "observe":
        collect_inputs(args.block, args.output, args.vision, args.reference_observations)
    elif args.stage == "plan":
        build_plans(args.block, args.output, args.bundle, args.source)
    elif args.stage == "score":
        score(args.block, args.output, args.workers)
    else:
        summarize(args.block, args.output, args.bundle)
