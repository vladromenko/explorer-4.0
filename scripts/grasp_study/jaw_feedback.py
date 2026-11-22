"""Passively replay the last pre-lift jaw samples of one published controller; no fitted threshold."""

import fcntl
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.stats import mannwhitneyu

from explorer4.datasets import fingerprint, load_plan
from explorer4.paths import DATA, ROOT
from scripts.grasp_study import coverage_design as coverage, native_execution as native
from scripts.grasp_study.evaluate import (
    GraspMetrics,
    environment,
    file_hash,
    observe,
    sha_array,
)

OUT = DATA / "simlab/reports/grasp-prelift-jaw-feedback-v1"
SOURCE = coverage.OUTPUT
PRIMARY_SHA = "74ba35588231a5e55934e283c847bd19b4ef7e19e5b940d8d88cf381eff5cccd"
TRAIN_PLAN = "df90f11b3b89ba67acc8c1a13e62d8781b79fc2e52c9322eed7f4fbac55371f0"
RULE = "farthest_first"


def prepare():
    if file_hash(SOURCE / "result.json") != PRIMARY_SHA:
        raise ValueError("Original measured outcomes changed")
    training = coverage.read(SOURCE / "training.json")["methods"][RULE]
    boundaries = []
    for seed in training["accepted_seeds"]:
        receipt = coverage.read(SOURCE / "expert" / f"{seed}.json")
        boundaries.append(
            next(p["first_tick"] for p in receipt["phases"] if p["phase"] == "lift")
        )
    if set(boundaries) != {131}:
        raise ValueError("The expert demonstrations do not share one pre-lift boundary")
    spec = {
        "method": RULE,
        "version": 1,
        "archive_sha256": PRIMARY_SHA,
        "motor_bank_sha256": training["bank_sha256"],
        "source_sha256": {
            n: file_hash(ROOT / n)
            for n in (
                "scripts/grasp_study/jaw_feedback.py",
                "scripts/grasp_study/coverage_design.py",
                "scripts/grasp_study/native_execution.py",
                "scripts/grasp_study/evaluate.py",
                "agents/rosmaster/runtime.py",
            )
        },
        "seeds": coverage.TEST,
        "first_lift_tick": 131,
        "observe_after_motor_ticks": list(range(126, 131)),
        "primary": "Median of the last five signed sent-minus-measured gripper angles in native whole degrees, immediately before the first planned lift command. Larger positive residual predicts an obstructed closure and eventual terminal hold. Compare ten successes with ten failures on the previously opened coverage scenes. One observation per scene; no threshold or window search.",
        "technical_gate": "Proceed to an intervention only if the prespecified score has AUC >=0.75 and a fixed >=1 degree obstruction test reaches sensitivity and specificity >=0.70 for eventual native hold. Both label classes required. Do not change scoring direction if the result is weak or reversed.",
        "diagnostics": "Report native jaw residual against any simultaneous bilateral cube contact in the last five ticks. MuJoCo contacts are labels only. Unrounded simulated angles are descriptive. Verify every original terminal and native-guard metric. Count timestamped sent commands and measured readbacks in the five original real training takes only; human recordings supply no matched force or miss labels.",
        "source": "https://people.csail.mit.edu/kjhsiao/webpagefiles/papers/contactreactive.pdf",
        "scope": "Post-hoc question prompted by the published 20 outcomes. Signal and gate fixed before replay of the missing jaw traces. No policy change or new holdout at the diagnostic stage.",
    }
    coverage.frozen(OUT / "protocol.json", spec)
    return spec


def physical_channels():
    plan = load_plan(TRAIN_PLAN, verify=False)
    entries = plan["splits"]["train"]
    if len(entries) != 5 or plan["profile"] != "rosmaster_pick_place":
        raise ValueError("Unexpected permitted training data")
    episodes = []
    readbacks = []
    for entry in entries:
        root = DATA / "datasets/rosmaster_pick_place" / entry["id"]
        if (
            entry["excluded"]
            or root.resolve() != Path(entry["dataset"]).resolve()
            or fingerprint(root) != entry["sha256"]
        ):
            raise ValueError("Original training take differs")
        valid = 0
        ages = []
        for line in (root / "research.jsonl").read_text().splitlines():
            r = json.loads(line)
            sent = r.get("action_sent")
            measured = r.get("measured_response")
            age = r.get("measured_response_age_s")
            if (
                r["measured_response_kind"] == "servo_position_readback"
                and isinstance(sent, list)
                and isinstance(measured, list)
                and isinstance(age, list)
                and len(sent) == len(measured) == len(age) == 6
                and r["arm_measured_valid"][5]
                and np.isfinite([sent[5], measured[5], age[5]]).all()
                and 0 <= age[5] <= 0.6
            ):
                valid += 1
                ages.append(age[5])
                readbacks.append(round(measured[5], 6))
        episodes.append(
            {
                "episode": entry["id"],
                "frames": entry["frames"],
                "valid_jaw_pairs": valid,
                "median_age_s": float(np.median(ages)) if ages else None,
            }
        )
    unique = np.unique(readbacks)
    return {
        "role": "original human training only",
        "episodes": episodes,
        "unique_jaw_degrees": len(unique),
        "smallest_observed_positive_increment_deg": float(np.diff(unique).min())
        if len(unique) > 1
        else None,
        "validated_contact_or_force_labels": 0,
    }


def replay(spec):
    source = coverage.read(SOURCE / "result.json")
    bank = SOURCE / "banks" / f"{RULE}.npz"
    if file_hash(bank) != spec["motor_bank_sha256"]:
        raise ValueError("Changed motor bank")
    rbf = coverage.fit(bank)
    arm = coverage.read(SOURCE / "protocol.json")["arm_settings"]
    env = environment()
    env.deadline_s = (coverage.LOOK_STEPS + coverage.MAX_TICKS) * env.dt
    rows = []

    def no_serial(*args, **kwargs):
        raise AssertionError("No physical transport")

    try:
        with (
            patch.dict(
                sys.modules, {"serial": types.SimpleNamespace(Serial=no_serial)}
            ),
            patch.object(
                sys,
                "path",
                [str(ROOT / "agents/rosmaster"), str(native.NATIVE), *sys.path],
            ),
        ):
            for original in source["rows"]:
                seed = original["seed"]
                path = OUT / "trials" / f"{seed}.json"
                if path.is_file():
                    row = coverage.read(path)
                    if (
                        row["protocol_sha256"] != file_hash(OUT / "protocol.json")
                        or row["seed"] != seed
                    ):
                        raise ValueError("Wrong saved diagnostic")
                else:
                    first, _ = observe(env, seed, render=False)
                    prior = original["methods"][RULE]
                    commands = rbf(
                        np.array(original["predicted_xy"], dtype=float)[None] / 0.05
                    )[0]
                    if (
                        first != original["initial"]
                        or sha_array(commands) != prior["plan_sha256"]
                    ):
                        raise ValueError("Original start or plan differs")
                    executor = native.mock_executor(env, arm)
                    original_step = env.step
                    trace = []

                    def observe_step(command):
                        result = original_step(command)
                        tick = env.steps - coverage.LOOK_STEPS - 1
                        if tick in spec["observe_after_motor_ticks"]:
                            sent = executor.io.arm_command()[5]
                            measured = executor.io.measured_arm()[5]
                            raw = float(env.observation()["state"][5])
                            label = GraspMetrics(env, first["cube"][2])
                            label.measure(env, result[4])
                            trace.append(
                                {
                                    "tick": tick,
                                    "sent_deg": sent,
                                    "native_measured_deg": measured,
                                    "sim_measured_deg": raw,
                                    "bilateral_contact_label": label.bilateral,
                                    "either_contact_label": label.contact,
                                }
                            )
                        return result

                    with (
                        patch.object(native, "mock_executor", return_value=executor),
                        patch.object(env, "step", observe_step),
                    ):
                        metrics = native.simulate(env, commands, first["cube"][2], arm)
                    if (
                        any(prior[k] != v for k, v in metrics.items())
                        or [r["tick"] for r in trace]
                        != spec["observe_after_motor_ticks"]
                    ):
                        raise ValueError(
                            "Incomplete prefix or divergent native outcome"
                        )
                    score = float(
                        np.median(
                            [r["sent_deg"] - r["native_measured_deg"] for r in trace]
                        )
                    )
                    row = {
                        "seed": seed,
                        "protocol_sha256": file_hash(OUT / "protocol.json"),
                        "original_plan_sha256": prior["plan_sha256"],
                        "trace": trace,
                        "score_deg": score,
                        "sim_unrounded_score_deg": float(
                            np.median(
                                [r["sent_deg"] - r["sim_measured_deg"] for r in trace]
                            )
                        ),
                        "native_hold": metrics["outcome"] == "success",
                        "bilateral_contact": any(
                            r["bilateral_contact_label"] for r in trace
                        ),
                    }
                    coverage.frozen(path, row)
                rows.append(row)
    finally:
        env.close()
    return rows


def performance(rows, label):
    positives = [r["score_deg"] for r in rows if r[label]]
    negatives = [r["score_deg"] for r in rows if not r[label]]
    if not positives or not negatives:
        return {"positives": len(positives), "negatives": len(negatives), "auc": None}
    sensitivity = sum(v >= 1 for v in positives) / len(positives)
    specificity = sum(v < 1 for v in negatives) / len(negatives)
    auc = float(mannwhitneyu(positives, negatives).statistic) / (
        len(positives) * len(negatives)
    )
    return {
        "positives": len(positives),
        "negatives": len(negatives),
        "auc": auc,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "positive_median_residual_deg": float(np.median(positives)),
        "negative_median_residual_deg": float(np.median(negatives)),
        "true_positive": sum(v >= 1 for v in positives),
        "false_positive": sum(v >= 1 for v in negatives),
    }


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / ".lock").open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        spec = prepare()
        field = physical_channels()
        records = replay(spec)
        final = performance(records, "native_hold")
        contact = performance(records, "bilateral_contact")
        gate = bool(
            final["auc"] is not None
            and final["auc"] >= 0.75
            and min(final["sensitivity"], final["specificity"]) >= 0.7
        )
        result = {
            "protocol_sha256": file_hash(OUT / "protocol.json"),
            "status": "completed",
            "replay_scenes": len(records),
            "terminal_hold": final,
            "bilateral_pre_lift_label": contact,
            "eligible_for_heldout_intervention": gate,
            "physical_observability": field,
            "rows": records,
            "physical_trials": 0,
            "new_weights": 0,
        }
        coverage.frozen(OUT / "result.json", result)
        print(final, contact, gate, flush=True)
