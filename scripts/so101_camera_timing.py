"""Estimate apparent jaw-image timing from approved archived SO-101 demonstrations."""

import argparse
import hashlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import cv2
import numpy as np

from explorer4.paths import DATA, ROOT
from explorer4.so101_geometry import MODEL, fixed_frames
from explorer4.so101_packet_builder import camera_fingerprint
from explorer4.so101_vendor.table_projection import TableProjection
from scripts.peer_dock_study import frozen

SOURCE = "d891e94d13014e3abcda7f1a3dce517e"
DETECTOR = (
    ROOT.parent
    / "so101_autonomous_pick_place/src/so101_pick_place/vision/calibration_marker.py"
)
DETECTOR_SHA = "94cc810a5825fb310fb47e103d6a35d6776efe04376e15dae9cb5b77f204579e"
LAGS = np.arange(-250, 251, 5) / 1000
SPLITS = {
    "fit_approach": (0, 334),
    "validation_grasp_lift": (335, 502),
    "validation_hold": (503, 690),
    "validation_return": (691, 870),
}
MIN_SPEED = 40.0
BASE = DATA / "validation/so101-timing"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def archive():
    with sqlite3.connect(f"file:{DATA / 'catalog.sqlite3'}?mode=ro", uri=True) as db:
        roster = db.execute(
            "SELECT id,dataset,excluded FROM episodes WHERE profile='so101_pick_place' AND category='demonstration' ORDER BY id"
        ).fetchall()
    eligible, excluded = [], []
    for ident, dataset, skip in roster:
        sidecar = Path(dataset) / "donor_geometry/provenance.json"
        if sidecar.is_file():
            (excluded if skip else eligible).append((ident, sidecar))
    matches = [f for k, f in eligible if k == SOURCE]
    if len(matches) != 1:
        raise ValueError("The archived episode must remain explicitly included")
    meta = json.loads(matches[0].read_text())
    return (
        matches[0].parent,
        meta,
        {
            "included_sidecars": [k for k, _ in eligible],
            "excluded_sidecars_count": len(excluded),
        },
    )


def detector_module():
    if sha(DETECTOR.read_bytes()) != DETECTOR_SHA:
        raise ValueError("Original red/white jaw-marker detector changed")
    spec = importlib.util.spec_from_file_location(
        "archived_so101_calibration_marker", DETECTOR
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sources():
    directory, meta, roster = archive()
    if (
        sha(meta["calibration_source_json"].encode()) != meta["calibration_sha256"]
        or sha(MODEL.read_bytes()) != meta["model_sha256"]
    ):
        raise ValueError("Geometry source changed")
    camera = camera_fingerprint(meta["camera"])
    path = BASE / "diagnostics" / camera
    path.mkdir(parents=True, exist_ok=True)
    protocol = {
        "scope": "Retrospective timing diagnostic. Fitting, validation and all clips come from one included demonstration. All excluded sidecars are omitted from every image and encoder analysis.",
        **roster,
        "source_episode": SOURCE,
        "calibration_sha256": meta["calibration_sha256"],
        "camera_sha256": camera,
        "model_sha256": meta["model_sha256"],
        "detector_sha256": DETECTOR_SHA,
        "state_log_sha256": sha((directory.parent / "research.jsonl").read_bytes()),
        "measurement_log_sha256": sha((directory / "measurements.jsonl").read_bytes()),
        "method": "Read-end time minus candidate lag is exposure time. Pair the measured encoder midpoint with the calibrated moving-jaw red-dot projection. Use each distinct PNG/JPEG exposure once. Search both signs from -250 to 250 ms by 5 ms, using a common fully bracketed set for all lags. Score median pixel residual on frames moving at >=40 px/s. Compare fixed geometry, constant image offset estimated only on fitting motion, and displacement at approximately 100 ms over the same track. Whole-image red-on-white detections independent of FK are primary. The original 55-px zero-lag hint is a sensitivity diagnostic; the hint is fixed across lag hypotheses. Calibration of exposure uncertainty requires independent timing evidence and representative held-out motion with uncertainty <=20 ms. A fine search grid is not precision.",
        "splits": SPLITS,
        "minimum_speed_px_s": MIN_SPEED,
    }
    # JSON reload turns period tuples into lists.
    frozen(path / "protocol.json", json.loads(json.dumps(protocol)))
    return directory, meta, path


def extract():
    directory, meta, out = sources()
    detector = detector_module()
    rows = read_rows(directory / "measurements.jsonl")
    research = read_rows(directory.parent / "research.jsonl")
    calibration = meta["calibration_snapshot"]
    projection = TableProjection(
        calibration["camera_matrix"],
        calibration["distortion"],
        calibration["camera_from_robot"],
    )
    sample, seen, frames = [], set(), []
    for i, (r, s) in enumerate(zip(rows, research, strict=True)):
        if (
            r["frame_index"] != i
            or not s["state_valid"]
            or s["observation_timestamp_ns"] != r["observation_timestamp_ns"]
            or s["observation.state"] != r["measured_native_joints"]
        ):
            raise ValueError("Encoder stream or row identity mismatch")
        hand = fixed_frames(r["measured_native_joints"], calibration)[
            calibration["marker_link"]
        ]
        xyz = (hand @ np.r_[calibration["marker_local_m"], 1])[:3]
        uv = projection.table_to_pixel(tuple(xyz))
        sample.append(
            {
                "index": i,
                "start": s["state_read_start_ns"],
                "end": s["state_read_end_ns"],
                "uv": list(uv),
            }
        )
        seq = r["camera_sequence"]
        if seq not in seen:
            seen.add(seq)
            raw = (directory / r["image"]).read_bytes()
            if sha(raw) != r["image_sha256"]:
                raise ValueError(f"Original frame bytes changed at {i}")
            bgr = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
            observed = {}
            for mode, hint in (("whole", None), ("hinted", uv)):
                try:
                    observation = detector.detect_marker(bgr, expected_center_px=hint)
                    observed[mode] = list(observation.center_px)
                except ValueError:
                    observed[mode] = None
            frames.append(
                {
                    "index": i,
                    "seq": seq,
                    "t": r["camera_timestamp_ns"],
                    "image_sha256": r["image_sha256"],
                    **observed,
                }
            )
    frozen(out / "positions.json", {"samples": sample, "frames": frames})


def profile(values):
    finite = np.flatnonzero(np.isfinite(values))
    if not len(finite):
        return None
    best = finite[np.argmin(values[finite])]
    near = finite[values[finite] <= values[best] + 0.5]
    return {
        "best_lag_s": round(float(LAGS[best]), 4),
        "median_error_px": float(values[best]),
        "at_minus100_zero_plus100_ms_px": [
            float(values[np.argmin(np.abs(LAGS - x))]) for x in (-0.1, 0, 0.1)
        ],
        "within_half_px_of_min_s": [float(LAGS[near[0]]), float(LAGS[near[-1]])],
        "grid_median_px": [round(float(x), 5) for x in values],
    }


def distribution(nums):
    a = np.asarray(nums, dtype=float)
    return (
        {
            "n": len(a),
            "median": float(np.median(a)),
            "p90": float(np.quantile(a, 0.9)),
            "max": float(np.max(a)),
        }
        if len(a)
        else {"n": 0}
    )


def align(track, mode):
    enc = track["samples"]
    rows = track["frames"]
    origin = enc[0]["start"]
    stamps = np.asarray([(r["start"] + r["end"] - 2 * origin) / 2e9 for r in enc])
    uv = np.asarray([r["uv"] for r in enc])

    def pose(t):
        return np.stack([np.interp(t, stamps, v) for v in uv.T], axis=-1)

    t = np.array([(r["t"] - origin) / 1e9 for r in rows])
    idx = np.array([r["index"] for r in rows])
    obs = np.array([r[mode] if r[mode] is not None else [np.nan, np.nan] for r in rows])
    measured = np.isfinite(obs[:, 0])
    common = measured & (t >= stamps[0] + 0.25) & (t <= stamps[-1] - 0.25)
    speed = np.linalg.norm(pose(t + 0.05) - pose(t - 0.05), axis=-1) / 0.1
    moving = common & (speed >= MIN_SPEED)
    pred = pose(t[None, :] - LAGS[:, None])
    dif = obs[None, :, :] - pred
    fit = moving & (idx <= SPLITS["fit_approach"][1])
    offsets = np.median(dif[:, fit, :], axis=1) if np.any(fit) else None
    result = {}
    for name, (a, b) in SPLITS.items():
        selected = (idx >= a) & (idx <= b)
        use = selected & moving
        still = selected & common & (speed < 10)
        absolute = biased = displacement = None
        pair = []
        if np.any(use):
            absolute = profile(
                np.median(np.linalg.norm(dif[:, use, :], axis=-1), axis=1)
            )
            if offsets is not None:
                biased = profile(
                    np.median(
                        np.linalg.norm(dif[:, use, :] - offsets[:, None, :], axis=-1),
                        axis=1,
                    )
                )
            eligible = np.flatnonzero(common & selected)
            for i in np.flatnonzero(use):
                j = eligible[np.argmin(np.abs(t[eligible] - (t[i] - 0.1)))]
                if 0.075 <= t[i] - t[j] <= 0.125:
                    pair.append((j, i))
            if pair:
                start, end = np.asarray(pair).T
                displacement = profile(
                    np.median(
                        np.linalg.norm(dif[:, end, :] - dif[:, start, :], axis=-1),
                        axis=1,
                    )
                )
        result[name] = {
            "distinct_rgb": int(np.sum(selected)),
            "detected": int(np.sum(selected & measured)),
            "moving_fully_bracketed": int(np.sum(use)),
            "displacement_pairs": len(pair),
            "speed_px_s": distribution(speed[use]),
            "20ms_projected_motion_px": distribution(
                np.linalg.norm(pose(t[use]) - pose(t[use] - 0.02), axis=-1)
            ),
            "static_zero_lag_error_px": distribution(
                np.linalg.norm(dif[len(LAGS) // 2, still, :], axis=-1)
            ),
            "fixed_geometry": absolute,
            "fit_spatial_offset": biased,
            "100ms_displacement": displacement,
        }
    applied = {}
    for method in ("fixed_geometry", "fit_spatial_offset", "100ms_displacement"):
        chosen = result["fit_approach"][method]
        if chosen:
            k = int(np.argmin(np.abs(LAGS - chosen["best_lag_s"])))
            applied[method] = {
                h: None
                if result[h][method] is None
                else {
                    "fit_lag_px": result[h][method]["grid_median_px"][k],
                    "zero_lag_px": result[h][method]["grid_median_px"][len(LAGS) // 2],
                }
                for h in SPLITS
                if h != "fit_approach"
            }
    return {"splits": result, "held_out_error_at_frozen_fit_lag": applied}


def score():
    directory, meta, out = sources()
    track = json.loads((out / "positions.json").read_bytes())
    frames, states = track["frames"], track["samples"]
    analyses = {m: align(track, m) for m in ("whole", "hinted")}
    sources_seen = {
        "source_episode": SOURCE,
        "state": sha((directory.parent / "research.jsonl").read_bytes()),
        "geometry_measurements": sha((directory / "measurements.jsonl").read_bytes()),
        "positions": sha((out / "positions.json").read_bytes()),
        "protocol": sha((out / "protocol.json").read_bytes()),
        "detector": DETECTOR_SHA,
        "analysis_script": sha(Path(__file__).read_bytes()),
    }
    receipt = {
        "schema": "so101-camera-timing-diagnostic-v1",
        "usable": False,
        "lag_s": None,
        "uncertainty_s": None,
        "method": "signed moving-jaw reprojection against interpolated encoder pixels; independent optical timing reference unavailable",
        "camera_sha256": camera_fingerprint(meta["camera"]),
        "source_calibration_sha256": meta["calibration_sha256"],
        "source_model_sha256": meta["model_sha256"],
        "camera_device": meta["camera"]["device"],
        "controls_before": meta["camera"]["controls_readback_before"],
        "controls_after": meta["camera"]["controls_readback_after"],
        "sources": sources_seen,
        "assigned_encoder_samples": len(states),
        "distinct_camera_reads": len(frames),
        "exposure_clock": None,
        "timestamp_basis": meta["camera"]["timestamp_basis"],
        "encoder_interval_ms": distribution(np.diff([r["end"] for r in states]) / 1e6),
        "encoder_read_ms": distribution(
            [(r["end"] - r["start"]) / 1e6 for r in states]
        ),
        "distinct_image_interval_ms": distribution(
            np.diff([r["t"] for r in frames]) / 1e6
        ),
        "independent_parked_fiducial_error_px": meta["calibration_snapshot"][
            "validation"
        ]["independent_physical_control"]["error_px"],
        "lag_grid_s": LAGS.tolist(),
        "alignment": analyses,
        "limitations": [
            "One included demonstration has this camera fingerprint. Its movement blocks are correlated. Two excluded recordings have a different white-balance readback and were omitted.",
            "A stationary spatial control has no exposure timing information. Apparent alignment conflates exposure midpoint, USB buffering, encoder timing, moving-jaw flex, projection bias and marker association. The archived camera reports host read completion.",
            "Per-frame offsets are not independent trials. A half-pixel profile width is a sensitivity diagnostic, not a confidence interval for physical delay.",
        ],
        "external_measurement": "Keep this camera, focus, resolution, frame rate and capture settings. Place a nonperiodically modulated LED at the jaw image row. Log optical transition times with a photodiode on a common Homebrain monotonic timebase, retaining its synchronization uncertainty. Record the measured brightness and read completion for each distinct camera frame. Identify exposure midpoint and any row-dependent offset from optical transitions, accounting for integration time. Fit one sequence, hold out a second sequence at new phases and report read-to-exposure lag and a validation uncertainty bound including edge, clock and exposure errors. Recheck the camera fingerprint. Admit only a nonnegative lag <=0.25 s with independently supported uncertainty <=0.020 s.",
    }
    frozen(out / "report.json", receipt)
    canonical = BASE / (receipt["camera_sha256"] + ".json")
    if canonical.exists() and json.loads(canonical.read_bytes()) != receipt:
        raise ValueError(
            f"Existing independent timing receipt preserved at {canonical}. Diagnostic is at {out / 'report.json'}"
        )
    frozen(canonical, receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("extract", "score"))
    args = parser.parse_args()
    cv2.setNumThreads(1)
    {"extract": extract, "score": score}[args.phase]()
