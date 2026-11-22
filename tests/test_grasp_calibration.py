"""Regression checks for stationary real-camera evidence using no hardware or weights."""

import json

import numpy as np
import pytest
from scipy.spatial import Delaunay

from explorer4.conditioned_grasp import LOOK_COMMAND
from explorer4.grasp_calibration import held_fixed, new_session, save_point, summary


def observation(index):
    pose = {
        "arm_degrees": LOOK_COMMAND,
        "joint_names": ["a", "b", "c", "d", "e", "gripper"],
        "odometry": [0, 0, 0, 0, 0, 1, 0, 0, 0],
        "odometry_frame": "odom",
        "odometry_child": "base_link",
    }
    return {
        "before": pose,
        "after": pose,
        "boot_id": "fixture",
        "rgb_stamp": index,
        "camera_info_stamp": index,
        "rgb": np.full((480, 640, 3), index, dtype=np.uint8),
        "camera_info": {"frame_id": "front"},
    }


def test_new_points_cannot_hide_failed_localization(tmp_path):
    session = new_session("test camera", 35, 29, tmp_path)
    positions = [(190, -20), (230, -20), (210, 20), (200, 0), (220, 0)]
    hull = Delaunay([(0.15, -0.05), (0.26, -0.05), (0.20, 0.06)])
    for i, (x, y) in enumerate(positions):
        # The first point exceeds the measured 3 mm clearance by 1 mm.
        predicted = np.array([x + (4 if i == 0 else 0), y]) / 1000
        save_point(
            session,
            observation(i),
            "calibration_check" if i < 3 else "verification",
            x,
            y,
            True,
            (10, 10, 20, 20),
            score=lambda _, pred=predicted: (pred, hull),
        )
    result = summary(session)
    assert result["complete"] and result["status"] == "negative"
    assert result["points"][0]["error_mm"] == pytest.approx(4)
    assert not (session / "localization-calibration.json").exists()
    assert json.loads((session / "summary.json").read_text()) == result


def test_calibration_rejects_chassis_drift_even_with_stopped_wheels():
    initial = observation(1)["before"]
    shifted = {**initial, "odometry": [0.02, 0, 0, 0, 0, 1, 0, 0, 0]}
    with pytest.raises(ValueError, match="сместились"):
        held_fixed(initial, shifted, 0.003)
