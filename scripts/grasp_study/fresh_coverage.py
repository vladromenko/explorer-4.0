"""Descriptive reanalysis of the published 20 fresh scenes; performs no model inference or simulation."""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial import Delaunay, cKDTree

from explorer4.conditioned_grasp import MOTOR_SHA256, file_hash
from explorer4.paths import ROOT
from .evaluate import SOURCE, save_json

STUDY = ROOT / "docs/results/conditioned_grasp_v1"
METHODS = ("act", "diffusion", "rbf", "ik")
METRICS = (
    "reset_to_nearest_train_mm",
    "input_to_nearest_train_mm",
    "input_to_reset_xy_error_mm",
)


def outcomes(raw, methods):
    return {
        name: {
            k: raw[name][k]
            for k in (
                "outcome",
                "bilateral_contact",
                "ever_held",
                "peak_lift_m",
                "max_stable_carry_s",
            )
        }
        for name in methods
    }


def describe(rows, executor, method):
    def successful(row):
        return row[executor][method]["outcome"] == "success"

    groups = {}
    for key in ("reset_in_train_hull", "input_in_train_hull"):
        counts = {}
        for inside in (True, False):
            subset = [row for row in rows if row[key] == inside]
            counts["inside" if inside else "outside"] = dict(
                n=len(subset), holds=sum(map(successful, subset))
            )
        groups[key] = counts
    for result in ("success", "failure"):
        subset = [r for r in rows if r[executor][method]["outcome"] == result]
        groups[result] = dict(
            n=len(subset),
            median={
                k: float(np.median([r[k] for r in subset])) if subset else None
                for k in METRICS
            },
            bilateral_contact=sum(
                r[executor][method]["bilateral_contact"] for r in subset
            ),
            ever_held=sum(r[executor][method]["ever_held"] for r in subset),
            peak_lift_over_50mm=sum(
                r[executor][method]["peak_lift_m"] > 0.05 for r in subset
            ),
        )
    return groups


def analyze(motor):
    if file_hash(motor) != MOTOR_SHA256:
        raise ValueError("Unexpected demonstration bank")
    with np.load(motor, allow_pickle=False) as source:
        xy = source["xy"]
    if (
        xy.shape != (32, 2)
        or not np.isfinite(xy).all()
        or len(np.unique(xy, axis=0)) != 32
    ):
        raise ValueError("Expected 32 distinct finite training XYs")
    hull, tree = Delaunay(xy), cKDTree(xy)
    fresh_file, native_file = STUDY / "fresh.json", STUDY / "native-execution.json"
    fresh = json.loads(fresh_file.read_text())
    native = json.loads(native_file.read_text())
    seeds = list(range(940200, 940220))
    if [r["seed"] for r in fresh["trials"]] != seeds or [
        r["seed"] for r in native["trials"]
    ] != seeds:
        raise ValueError("The previously published scene identities or order changed")
    rows = []
    for t, n in zip(fresh["trials"], native["trials"], strict=True):
        reset = np.array(t["initial"]["cube"][:2])
        estimated = np.array(t["predicted_xy"])
        if not np.isfinite([*reset, *estimated]).all():
            raise ValueError("Nonfinite scene position")
        if not all(
            n["methods"][m]["published_sim_outcome"] == t["arms"][m]["outcome"]
            for m in native["methods"]
        ):
            raise ValueError("Native row is not paired with the original rollout")
        rows.append(
            dict(
                seed=t["seed"],
                reset_xy_m=reset.tolist(),
                input_xy_m=estimated.tolist(),
                reset_in_train_hull=bool(hull.find_simplex(reset) >= 0),
                input_in_train_hull=bool(hull.find_simplex(estimated) >= 0),
                reset_to_nearest_train_mm=float(tree.query(reset)[0] * 1000),
                input_to_nearest_train_mm=float(tree.query(estimated)[0] * 1000),
                input_to_reset_xy_error_mm=float(
                    np.linalg.norm(estimated - reset) * 1000
                ),
                mujoco=outcomes(t["arms"], METHODS),
                native_in_mujoco=outcomes(n["methods"], native["methods"]),
            )
        )
    return dict(
        scope="Retrospective description of all 20 already published seeded scenes. Seven executor/method combinations share those 20 inputs. No inferential tests, fitted thresholds, scene exclusions or new rollouts.",
        reference="https://proceedings.mlr.press/v229/mandlekar23a.html",
        reference_connection="MimicGen evaluates changes to the initial object-pose distribution. Explorer describes geometric support of its own 32 motor demonstrations without running MimicGen or generating additional demonstrations.",
        definitions="Euclidean distances in base-frame XY. Reset truth is the archived cube centre immediately before the fixed camera-look motion. Input is the single wrist-localizer prediction used by every planner. Cartesian discrepancy is relative to the archived reset, not independent calibrated camera truth or measured TCP-at-contact error. Terminal hold is the published one-second success.",
        source_sha256={
            "fresh.json": file_hash(fresh_file),
            "native-execution.json": file_hash(native_file),
            "motor.npz": MOTOR_SHA256,
        },
        motor_data="data/motor.npz in the published simulation-grasp-bundle.zip",
        training_xy_m=xy.tolist(),
        physical_trials=0,
        new_rollouts=0,
        optimizer_updates=0,
        support_matrix={
            f"reset_{truth}_input_{estimate}": sum(
                r["reset_in_train_hull"] == truth
                and r["input_in_train_hull"] == estimate
                for r in rows
            )
            for truth in (True, False)
            for estimate in (True, False)
        },
        by_executor={
            "mujoco": {m: describe(rows, "mujoco", m) for m in METHODS},
            "native_in_mujoco": {
                m: describe(rows, "native_in_mujoco", m) for m in native["methods"]
            },
        },
        rows=rows,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--motor",
        type=Path,
        default=SOURCE,
        help="Use data/motor.npz from the public study bundle",
    )
    parser.add_argument("--output", type=Path, default=STUDY / "fresh-coverage.json")
    args = parser.parse_args()
    save_json(args.output, analyze(args.motor))
