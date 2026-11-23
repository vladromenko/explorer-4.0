"""Fit measured controls through the field entry and verify the resulting builder contract."""

import hashlib
import json

import numpy as np
import pytest

from explorer4 import (
    so101_metric_calibration as metric,
)
from explorer4 import (
    so101_metric_page as page,
)
from explorer4 import (
    so101_packet_builder as builder,
)
from explorer4.so101_geometry import CALIBRATION, MODEL, fixed_frames

EPISODE = "e" * 32


def capture(tmp_path, monkeypatch):
    root = tmp_path / "recordings" / EPISODE
    geometry = root / "donor_geometry"
    geometry.mkdir(parents=True)
    (root / "provenance.json").write_text('{"domain":"real"}')
    raw = CALIBRATION.read_text()
    meta = {
        "calibration_source_json": raw,
        "calibration_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "model_sha256": metric.sha256_file(MODEL),
        "camera": {"device": "fixture-c920"},
        "frames": 120,
    }
    meta["settings"] = {
        "instance_id": "cube",
        "size_m": [0.029] * 3,
        "marker_dictionary": "DICT_APRILTAG_36h11",
        "marker_id": 1,
        "marker_side_m": 0.020,
        "marker_from_object": np.eye(4).tolist(),
    }
    (geometry / "provenance.json").write_text(json.dumps(meta))
    picture = geometry / "sample.jpg"
    picture.write_bytes(b"camera fixture")
    image_sha = metric.sha256_file(picture)
    rows, native, survey = [], [], []
    offset = np.array([0.004, 0.009, -0.003])
    axis = np.array([0.0, 1.0, 0.0])
    for i, percent in enumerate([0, 50, 90, 15, 35, 65]):
        state = [i * 10.0, -45.0, 20.0, 30.0, 2.0, float(percent)]
        tip = fixed_frames(state, json.loads(raw))["gripper_frame_link"]
        fixed = tip[:3, 3] + tip[:3, :3] @ offset
        width = 0.0006 * percent
        moving = fixed - tip[:3, :3] @ axis * width
        survey.append(
            {
                "frame": i * 20 + 10,
                "group": "fit" if i < 3 else "control",
                "fixed_mm": (1000 * fixed).tolist(),
                "moving_mm": (1000 * moving).tolist(),
                "opening_mm": 1000 * width,
            }
        )
        obj = np.eye(4)
        obj[:3, 3] = [0.1, 0.15, 0.01 + 0.03 * i]
        if i >= 3:
            survey[-1]["cube_mm"] = (1000 * obj[:3, 3]).tolist()
        for j in range(20):
            seq = 20 * i + j
            stamp = 1_000_000_000 + seq * 35_000_000
            rows.append(
                {
                    "frame_index": seq,
                    "image": picture.name,
                    "image_sha256": image_sha,
                    "observation_timestamp_ns": stamp,
                    "camera_timestamp_ns": stamp - 12_000_000,
                    "camera_sequence": seq,
                    "visual": {
                        "valid": True,
                        "orientation_ambiguous": False,
                        "world_object_pose": obj.tolist(),
                    },
                    "measured_native_joints": state,
                    "world_fixed_tip_pose": tip.tolist(),
                }
            )
            native.append(
                {
                    "observation_timestamp_ns": stamp,
                    "observation.state": state,
                    "command_source": "human",
                    "state_valid": True,
                }
            )
    for file, data in (
        (root / "research.jsonl", native),
        (geometry / "measurements.jsonl", rows),
    ):
        file.write_text("".join(json.dumps(r) + "\n" for r in data))
    for module in (metric, builder, page):
        monkeypatch.setattr(module, "DATA", tmp_path)
    monkeypatch.setattr(metric, "recordings", lambda: {EPISODE: root})
    return meta, survey, geometry


def test_survey_binds_independent_geometry_timing_and_actual_encoder_window(
    tmp_path, monkeypatch
):
    meta, survey, geometry = capture(tmp_path, monkeypatch)
    timing = (
        tmp_path
        / "validation/so101-timing/measured"
        / (metric.camera_fingerprint(meta["camera"]) + ".json")
    )
    args = (EPISODE, EPISODE, survey, 0.2, 0.3, "observer", "fixture gauge")
    with pytest.raises(ValueError, match="задержки"):
        metric.save_calibration(*args)
    timing.parent.mkdir(parents=True)
    timing.write_text(
        json.dumps(
            {
                **metric.sensor_identity(meta),
                "usable": True,
                "lag_s": 0.03,
                "uncertainty_s": 0.006,
                "method": "synthetic timing fixture",
            }
        )
    )
    with pytest.raises((ValueError, KeyError)):
        metric.save_calibration(*args)
    # Isolate the spatial fit. The timing importer's separate integration test
    # reconstructs the optical reference from all seven immutable source files.
    monkeypatch.setattr(
        metric, "timing_report", lambda meta: (timing, json.loads(timing.read_bytes()))
    )
    result = metric.save_calibration(*args)
    body = builder.calibration_for_review(result, meta)
    assert np.allclose(
        np.array(body["fixed_tip_from_tcp"])[:3, 3], [0.004, 0.009, -0.003]
    )
    assert (
        np.allclose(body["closing_axis_tcp"], [0, 1, 0])
        and body["camera_delay_s"] == 0.03
    )
    evidence = body["independent_control_evidence"]
    checks = builder.read_artifact(evidence["reference"], evidence["sha256"])
    assert len(checks["jaw_controls"]) == 3 and all(
        r["camera_timestamp_ns"] < r["observed_ns"]
        for r in checks["source_encoder_and_image_receipts"]
    )
    _, points = metric.measured_points(EPISODE, survey, 0.2)
    points[-1]["fixed"] = points[-2]["fixed"].copy()
    with pytest.raises(ValueError, match="различаться"):
        metric.fit_geometry(points, 0.2)
    raw = (geometry.parent / "research.jsonl").read_text().splitlines()
    native = json.loads(raw[6])
    native["observation.state"] = [99.0] * 6
    raw[6] = json.dumps(native)
    (geometry.parent / "research.jsonl").write_text("\n".join(raw) + "\n")
    with pytest.raises(ValueError, match="исходным"):
        metric.measured_points(EPISODE, survey, 0.2)
