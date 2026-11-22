"""Episode-calibrated RGB failure alarm and measured return-to-look response on independent grasp scenes."""

import argparse
import math
from importlib.metadata import version
import sys
import types
from unittest.mock import patch

import cv2
import numpy as np
import torch
from scipy.stats import binomtest
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler
from torch.nn.functional import adaptive_avg_pool2d

from explorer4.conditioned_grasp import MOTOR_SHA256, VISION_SHA256, file_hash, locate_cube
from explorer4.paths import DATA, ROOT
from scripts.grasp_study import dagger
from scripts.grasp_study.coverage_design import frozen, read
from scripts.grasp_study.evaluate import environment, observe, save_json, sha_array
from scripts.grasp_study.refresh import capture
from scripts.grasp_study.wrist_heatmap.data import original

OUT = DATA / "simlab/reports/wrist-video-failure-watch-v1"
SPLITS = {"fit": range(985100, 985140), "calibration": range(985200, 985224), "test": range(985300, 985332)}
TICKS = (3, 7)
METHODS = ("tracker", "visual_probe")


def protocol():
    return {
        "question": "Can a risk alarm before grasp closure select a useful return to the calibrated look?",
        "scope": "Exploratory MuJoCo study with the original RGB-RBF policy, native guards, no physical trials.",
        "seeds": {k: list(v) for k, v in SPLITS.items()},
        "displacement": "Within each split, ordered four-scene blocks receive 0, +10, 0, -10 mm in Y after six moving ticks before contact; assignment is unavailable to the predictors.",
        "monitor": "RGB at look and ticks 3 and 7. Baseline = clipped normalized-template confidence loss (1 invalid). Adaptation of SAFE: one scalar logistic failure probe on frozen policy visual embeddings, with current and initial-relative 2x2-pool features. No VLA, no FIPER entropy and no stochastic action samples.",
        "fit": "40 independent scenes. Each valid monitor time from an episode shares that episode's terminal label and the episode has total unit training weight. Standard scaling, eight PCA features, L2 logistic C=1, deterministic solver. One fit.",
        "calibration": "24 disjoint scenes. For each method use the finite-sample ceil((m+1)*.8) order statistic of the maximum score among m successful calibration episodes; alarm strictly above threshold. If rank exceeds m, never alarm. No test threshold adjustment.",
        "test": "32 fresh independent starts. Seal predictions before terminal scoring, then run both stale and actual return-to-look branches from the same initial state. Verify shared RGB/physics through the last decision. One alarm per episode; first tick above threshold latches a return at tick 7. Report false alarms per successful episode and all episodes, misses per failed episode, time from first alert to stale terminal verdict (failure onset is unlabelled), plus actual terminal holds and elapsed simulated seconds under all four strategies. Episode result follows the existing native experiment's first stable-carry/timeout scorer; it differs from the RGB study's fixed 360-command end-of-sequence criterion.",
        "reaction": "Existing physical simulation execution: drive back to the look pose for at most 40 native updates, reacquire one RGB, restart same RBF under the unchanged clock. Refusals and guard-stops count as unsuccessful attempts. Operators and other robots do not intervene.",
        "sources": {
            p: file_hash(ROOT / p)
            for p in [
                "scripts/grasp_study/failure_watch.py",
                "scripts/grasp_study/dagger.py",
                "scripts/grasp_study/moving_view.py",
                "scripts/grasp_study/evaluate.py",
                "scripts/grasp_study/native_execution.py",
                "scripts/grasp_study/refresh.py",
                "explorer4/conditioned_grasp.py",
                "agents/rosmaster/runtime.py",
                "scripts/recorded_start_visual_pick.py",
            ]
        },
        "software": {n: version(n) for n in ("scikit-learn", "torch", "torchvision", "mujoco")},
        "motor_sha256": MOTOR_SHA256,
        "vision_sha256": VISION_SHA256,
        "references": [
            "https://tum-lsy.github.io/fiper_website/",
            "https://proceedings.neurips.cc/paper_files/paper/2025/hash/392d0d05e2f514063e6ce6f8b370834c-Abstract-Conference.html",
        ],
    }


def embedded(backbone, rgb):
    image = cv2.resize(rgb, (160, 120), interpolation=cv2.INTER_AREA)
    x = original.normalize(torch.from_numpy(image.copy())[None], torch.device("cpu"))
    with torch.inference_mode():
        return adaptive_avg_pool2d(backbone(x), (2, 2)).flatten().numpy()


def infer(model, features):
    x = np.asarray(features)
    z = (x - np.asarray(model["mean"])) / model["scale"]
    pc = (z - model["pca_mean"]) @ np.asarray(model["components"]).T
    logit = float(pc @ np.asarray(model["weight"]) + model["intercept"])
    return float(1 / (1 + np.exp(-np.clip(logit, -40.0, 40.0))))


def decisions(records, model):
    out = {}
    for method in METHODS:
        scores = []
        for record in records:
            score = (
                record["tracker_score"] if method == "tracker" else infer(model, record["visual_features"])
            )
            scores.append({"tick": record["tick"], "at_s": record["sim_seconds"], "score": score})
        first = next((s["tick"] for s in scores if s["score"] > model["threshold"][method]), None)
        at = next((s["at_s"] for s in scores if s["tick"] == first), None)
        out[method] = {"scores": scores, "first_alarm": first, "first_alarm_s": at}
    return out


def fit_model(rows):
    x, y, weight = [], [], []
    for row in rows:
        features = row["observations"]
        for rec in features:
            x.append(rec["visual_features"])
            y.append(int(row["stale"]["outcome"] != "success"))
            weight.append(1 / len(features))
    if len(set(y)) != 2:
        raise ValueError("Both observed terminal outcomes are required for supervised fitting")
    scaler = StandardScaler().fit(x, sample_weight=weight)
    pca = PCA(n_components=8, svd_solver="full").fit(scaler.transform(x))
    estimator = LogisticRegression(C=1, solver="lbfgs", max_iter=500, random_state=1000)
    estimator.fit(pca.transform(scaler.transform(x)), y, sample_weight=weight)
    return {
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "pca_mean": pca.mean_.tolist(),
        "components": pca.components_.tolist(),
        "weight": estimator.coef_[0].tolist(),
        "intercept": float(estimator.intercept_[0]),
        "threshold": {k: 1.0 for k in METHODS},
    }


def calibrate(model, rows):
    successes = [r for r in rows if r["stale"]["outcome"] == "success"]
    m = len(successes)
    rank = math.ceil((m + 1) * 0.8)
    for method in METHODS:
        maxima = [
            max((s["score"] for s in decisions(r["observations"], model)[method]["scores"]), default=0.0)
            for r in successes
        ]
        model["threshold"][method] = float(sorted(maxima)[rank - 1]) if rank <= m else 1.0
    model["success_calibration_episodes"] = m
    model["calibration_rank"] = rank
    return model


class Study:
    def __init__(self, env):
        self.env = env
        self.base = dagger.Study(env)
        self.backbone = self.base.localizer[:6].eval()
        self.protocol_sha = file_hash(OUT / "protocol.json")

    def trial(self, split, seed, model=None):
        folder = OUT / split / str(seed)
        receipt = folder / "record.json"
        prediction_path = folder / "decision.json"
        if receipt.exists():
            row = read(receipt)
            if (
                row["protocol_sha256"] != self.protocol_sha
                or row["seed"] != seed
                or (
                    split == "test"
                    and (
                        row["decision_sha256"] != file_hash(prediction_path)
                        or read(prediction_path)["model_sha256"] != file_hash(OUT / "model.json")
                    )
                )
            ):
                raise ValueError("Wrong saved episode identity")
            return row
        folder.mkdir(parents=True, exist_ok=True)
        first, rgb = observe(self.env, seed)
        xy = locate_cube(self.base.localizer, rgb).astype(float)
        tracker = dagger.WristTracker(rgb, self.env.observation()["state"], xy)
        scene = (
            first,
            capture(self.env),
            xy,
            tracker,
            self.base.rbf,
            self.base.localizer,
            self.base.settings,
        )
        initial_embedding = embedded(self.backbone, rgb)
        first_step = self.env.steps
        delta = (0.0, 0.01, 0.0, -0.01)[(seed - SPLITS[split][0]) % 4]
        observations = []
        stamps = {}
        original_step = dagger.NativeEpisode.step
        branch = "stale"

        def record_step(sim, target):
            tick = self.env.steps - first_step
            if tick in TICKS and tick not in stamps[branch]:
                image = self.env.render()
                physics = sha_array(self.env.snapshot()["physics"])
                stamp = {"rgb_sha256": sha_array(image), "physics_sha256": physics}
                stamps[branch][tick] = stamp
                if branch == "stale":
                    pose = self.env.observation()["state"]
                    _, valid, correlation = tracker.read(image, pose)
                    x = embedded(self.backbone, image)
                    features = np.r_[x, x - initial_embedding].tolist()
                    observations.append(
                        {
                            "tick": tick,
                            "sim_seconds": float(self.env.elapsed),
                            **stamp,
                            "tracker_score": 1 - float(np.clip(correlation, 0, 1)) if valid else 1.0,
                            "tracking_valid": valid,
                            "visual_features": features,
                        }
                    )
                    png = folder / f"tick-{tick}.png"
                    if not cv2.imwrite(
                        str(png), cv2.resize(image, (160, 120), interpolation=cv2.INTER_AREA)[:, :, ::-1]
                    ):
                        raise OSError(png)
                    if split == "test" and tick == TICKS[-1]:
                        pred = {
                            "seed": seed,
                            "protocol_sha256": self.protocol_sha,
                            "model_sha256": file_hash(OUT / "model.json"),
                            "observations": [r["rgb_sha256"] for r in observations],
                            "decisions": decisions(observations, model),
                        }
                        frozen(prediction_path, pred)
                elif stamp != stamps["stale"].get(tick):
                    raise ValueError("The reaction changed an input before initiation")
            return original_step(sim, target)

        folder.mkdir(parents=True, exist_ok=True)
        row = {"seed": seed, "delta_m": delta, "protocol_sha256": self.protocol_sha, "initial": first}
        with patch.object(dagger.NativeEpisode, "step", record_step):
            for branch in ("stale", "return_to_look") if split == "test" else ("stale",):
                stamps[branch] = {}
                row[branch] = dagger.run_episode(self.env, scene, branch, delta)
        row["observations"] = observations
        if split == "test":
            if not prediction_path.exists():
                # An interrupted prefix supplies no actionable return, even if an early warning occurred.
                frozen(
                    prediction_path,
                    {
                        "seed": seed,
                        "protocol_sha256": self.protocol_sha,
                        "model_sha256": file_hash(OUT / "model.json"),
                        "observations": [r["rgb_sha256"] for r in observations],
                        "decisions": decisions(observations, model),
                        "window_ended_before_reaction": True,
                    },
                )
            if stamps["stale"] != stamps["return_to_look"]:
                raise ValueError("Unmatched shared decision prefix")
            row["decision_sha256"] = file_hash(prediction_path)
        save_json(receipt, row)
        print(split, seed, flush=True)
        return row


def summarize(rows):
    fails = np.array([r["stale"]["outcome"] != "success" for r in rows])
    output = {}
    pairs = []
    for r in rows:
        pred = read(OUT / "test" / str(r["seed"]) / "decision.json")
        pairs.append(
            {
                "seed": r["seed"],
                "stale_hold": r["stale"]["outcome"] == "success",
                "recovery_hold": r["return_to_look"]["outcome"] == "success",
                "stale_s": r["stale"]["elapsed_sim_s"],
                "recovery_s": r["return_to_look"]["elapsed_sim_s"],
                "reactable": not pred.get("window_ended_before_reaction"),
                "decisions": pred["decisions"],
                "prefix_rgb_sha256": pred["observations"],
                "decision_sha256": r["decision_sha256"],
            }
        )
    for method in METHODS:
        scores = np.array(
            [max((i["score"] for i in p["decisions"][method]["scores"]), default=0.0) for p in pairs]
        )
        alarm = np.array([p["decisions"][method]["first_alarm"] is not None for p in pairs])
        saved = [
            p["stale_s"] - p["decisions"][method]["first_alarm_s"]
            for p, a, f in zip(pairs, alarm, fails)
            if a and f
        ]
        false = int((alarm & ~fails).sum())
        output[method] = {
            "alarms": int(alarm.sum()),
            "failures": int(fails.sum()),
            "successes": int((~fails).sum()),
            "false_alarms": false,
            "false_alarms_per_episode": false / len(rows),
            "false_alarms_per_successful_episode": false / int((~fails).sum()) if (~fails).any() else None,
            "missed_failures": int((~alarm & fails).sum()),
            "detected_failures": int((alarm & fails).sum()),
            "lead_to_terminal_failure_seconds": saved,
            "median_lead_s": float(np.median(saved)) if saved else None,
            "episode_auc": float(roc_auc_score(fails, scores)) if len(set(fails)) == 2 else None,
            "max_score_brier": float(brier_score_loss(fails, scores)),
        }
    strategies = {}
    for method in ("never_return", "always_return", *METHODS):
        chosen = [
            p["reactable"]
            and (
                method == "always_return"
                or method in METHODS
                and p["decisions"][method]["first_alarm"] is not None
            )
            for p in pairs
        ]
        final = [p["recovery_hold"] if take else p["stale_hold"] for p, take in zip(pairs, chosen)]
        times = [p["recovery_s"] if take else p["stale_s"] for p, take in zip(pairs, chosen)]
        gain = int(sum(a and b for a, b in zip(final, fails)))
        loss = int(sum(not a and not b for a, b in zip(final, fails)))
        strategies[method] = {
            "holds": sum(final),
            "recoveries": sum(chosen),
            "mean_episode_s": float(np.mean(times)),
            "gains_over_never": gain,
            "losses_against_never": loss,
            "paired_p": float(binomtest(gain, gain + loss).pvalue) if gain + loss else 1.0,
        }
    return {
        "protocol_sha256": file_hash(OUT / "protocol.json"),
        "model_sha256": file_hash(OUT / "model.json"),
        "n": len(rows),
        "alarms": output,
        "strategies": strategies,
        "pairs": pairs,
        "physical_trials": 0,
    }


def run():
    if read(OUT / "protocol.json") != protocol():
        raise ValueError("Changed frozen monitoring protocol")
    torch.set_num_threads(1)
    cv2.setNumThreads(1)
    env = environment()

    def no_serial(*a, **k):
        raise AssertionError("No physical transport")

    try:
        with (
            patch.dict(sys.modules, {"serial": types.SimpleNamespace(Serial=no_serial)}),
            patch.object(sys, "path", [str(ROOT / "agents/rosmaster"), str(dagger.NATIVE), *sys.path]),
        ):
            study = Study(env)
            paths = {}
            for split in ("fit", "calibration"):
                paths[split] = [study.trial(split, s) for s in SPLITS[split]]
            model_path = OUT / "model.json"
            if not model_path.exists():
                model = calibrate(fit_model(paths["fit"]), paths["calibration"])
                model["protocol_sha256"] = study.protocol_sha
                model["source_episodes"] = {
                    sp: {str(r["seed"]): file_hash(OUT / sp / str(r["seed"]) / "record.json") for r in rows}
                    for sp, rows in paths.items()
                }
                frozen(model_path, model)
            model = read(model_path)
            if model["protocol_sha256"] != study.protocol_sha or any(
                file_hash(OUT / sp / seed / "record.json") != sha
                for sp, sources in model["source_episodes"].items()
                for seed, sha in sources.items()
            ):
                raise ValueError("Changed detector training/calibration sources")
            test = [study.trial("test", s, model) for s in SPLITS["test"]]
            frozen(OUT / "result.json", summarize(test))
    finally:
        env.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    action = parser.parse_args().action
    if action == "prepare":
        frozen(OUT / "protocol.json", protocol())
    else:
        run()
