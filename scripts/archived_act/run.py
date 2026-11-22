"""Replay the eight development seeds on all three original checkpoints, after parity passes."""
import argparse
import json
from contextlib import closing

import numpy as np

from explorer4.profiles import profile
from explorer4.sim_protocol import model_identity, protocol
from scripts.audit_floor_checkpoints import PHYSICS, PROFILE, PUBLIC, SEEDS, STEPS, persist
from .common import QUEUE_LENGTH, UNUSED_RGB, array_hash, guard, read, source_ids


def make_floor():
    from explorer4.sim.factory import make
    # MuJoCo uploads the initial visual model when constructing the GL context.
    # Creating it only on the first development scene measurably changes its RGB.
    env = make(PROFILE, images=True)
    env.images = False
    return env


class FloorTrace:
    def __init__(self, env, seed):
        self.env = env
        self.obs, _ = env.reset(seed=seed)
        self.seed = seed
        self.task = {**profile(PROFILE), "task": getattr(env, "task_text", None) or profile(PROFILE)["task"]}
        self.qpos = [env.data.qpos.tolist()]
        self.actions = []
        self.initial = self.obs["state"].tolist()
        self.cube = env.data.body("task_cube").xpos.copy()
        self.minimum, self.lift, self.held = float("inf"), 0., False
        self.done = False

    def tick(self, action):
        if self.done:
            raise ValueError("Extra action after terminal step")
        self.obs, _, terminated, truncated, self.info = self.env.step(action)
        self.done = terminated or truncated
        self.qpos.append(self.env.data.qpos.tolist())
        self.actions.append(action)
        cube = self.env.data.body("task_cube").xpos
        self.minimum = min(self.minimum, float(np.linalg.norm(self.env.data.site("gripperframe").xpos - cube)))
        self.lift = max(self.lift, float(cube[2] - self.cube[2]))
        self.held |= bool(self.info["held"])

    def row(self):
        if not self.done:
            raise ValueError("Incomplete floor trial")
        return dict(seed=self.seed, outcome=self.info["outcome"], reason=self.info["termination_reason"],
                    steps=self.env.steps, sim_seconds=self.env.elapsed, initial_qpos_sha256=array_hash(self.qpos[0]),
                    initial_state=self.initial, cube_xyz0=self.cube.tolist(), min_tip_cube_cm=100 * self.minimum,
                    max_lift_cm=100 * self.lift, ever_held=self.held, actions_sha256=array_hash(self.actions),
                    all_qpos_sha256=array_hash(self.qpos), full_camera_frames=(len(self.actions)-1)//QUEUE_LENGTH+1)


def trace_record(trial, weight):
    return dict(profile=PROFILE, seed=trial.seed, fps=trial.env.fps, model=PHYSICS,
                outcome=trial.info["outcome"], qpos=trial.qpos, checkpoint_sha256=weight)


def block(step):
    from explorer4.act_client import PolicyClient
    bank, weight = guard(step)
    dest = PUBLIC / str(step)
    dest.mkdir(exist_ok=True)
    report = dest / "evaluation.json"
    with closing(make_floor()) as env:
        manifest = protocol(PROFILE, SEEDS, model_identity(env.manifest), bank)
        if manifest["xml_sha256"] != PHYSICS or manifest["checkpoint_sha256"] != weight:
            raise ValueError("Geometry or weights changed")
        rows = []
        if report.exists():
            previous = read(report)
            if previous.get("status") == "completed":
                if previous.get("protocol") != manifest or [r["seed"] for r in previous["trials"]] != SEEDS:
                    raise ValueError("Completed archival report differs from frozen plan")
                return
            rows = previous["trials"]
            if [r["seed"] for r in rows] != SEEDS[:len(rows)]:
                raise ValueError("Partial archive has unexpected scene order")
        for row in rows:
            env.reset(seed=row["seed"])
            file = read(dest / f'floor-trial-{row["seed"]}.json')
            if (file["seed"], file["model"], file["checkpoint_sha256"], len(file["qpos"]), array_hash(file["qpos"][0])) != (row["seed"], PHYSICS, weight, row["steps"]+1, row["initial_qpos_sha256"]):
                raise ValueError("Partial result does not belong to this checkpoint and reset")
        with closing(PolicyClient(bank, dest / "archived-fast.inference.log", device="cpu")) as client:
            if (client.ready["checkpoint_bundle_sha256"], client.ready["n_action_steps"], client.ready["policy_type"]) != (manifest["checkpoint_bundle_sha256"], QUEUE_LENGTH, "act"):
                raise ValueError("Worker could not attest the original ACT bundle and queue")
            for seed in SEEDS[len(rows):]:
                trial = FloorTrace(env, seed)
                client.request("reset", seed=seed)
                while not trial.done:
                    refresh = env.steps % QUEUE_LENGTH == 0
                    pixels = env.render() if refresh else UNUSED_RGB
                    trial.tick(client.action({**trial.obs, "rgb": pixels}, trial.task))
                trace = trace_record(trial, weight)
                persist(dest / f"floor-trial-{seed}.json", trace)
                if seed == SEEDS[0]:
                    persist(dest / "first-floor-trial.json", trace)
                rows.append(trial.row())
                persist(report, dict(status="running", protocol=manifest, trials=rows))
                print(json.dumps(rows[-1]), flush=True)
        if protocol(PROFILE, SEEDS, model_identity(env.manifest), bank) != manifest:
            raise ValueError("Policy or scene changed during replay")
        persist(report, dict(status="completed", domain="sim", profile=PROFILE, policy="act", protocol=manifest,
               checkpoint=str(bank), checkpoint_sha256=weight, n_action_steps=QUEUE_LENGTH, model=env.manifest,
               policy_seed_per_scene=True, new_process_reload=True, privileged_input=False, trials=rows,
               success_fraction=sum(r["outcome"] == "success" for r in rows)/len(rows), physical_skill_verified=False,
               camera_schedule="Full native RGB on empty queues; queued ticks pass an unused 1x1 RGB to stock ACT.",
               latency_scope="Sensor-to-action latency comparison omitted because transport workload differs."))


def main():
    from scripts.audit_floor_checkpoints import main as summarize
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    guard(STEPS[0])
    proof = read(PUBLIC / "fast-parity-957300.json")
    if proof.get("verified") is not True or proof["sources_sha256"] != source_ids():
        raise ValueError("Verified whole-episode CPU parity on these sources is required")
    for step in STEPS:
        block(step)
    summarize()


if __name__ == "__main__":
    main()
