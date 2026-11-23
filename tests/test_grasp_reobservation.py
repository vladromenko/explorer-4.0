"""Read-only sensor substitutes for optional field evidence. No device transport."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.spatial import Delaunay

from explorer4 import grasp_admission
from explorer4 import grasp_calibration as capture
from explorer4 import grasp_reobservation as relook
from explorer4.conditioned_grasp import LOOK_COMMAND


def view(stamp, frame):
    pose = {
        "arm_degrees": LOOK_COMMAND,
        "joint_names": list("abcdef"),
        "odometry": [0, 0, 0, 0, 0, 1, 0, 0, 0],
        "odometry_frame": "odom",
        "odometry_child": "base",
    }
    return {
        "rgb": frame,
        "rgb_stamp": stamp,
        "boot_id": "recorded-boot",
        "camera_info_stamp": stamp,
        "camera_info": {"frame_id": "front"},
        "before": dict(pose, arm_stamp=stamp - 1, odom_stamp=stamp - 1),
        "after": dict(pose, arm_stamp=stamp + 1, odom_stamp=stamp + 1),
    }


def test_only_witnessed_return_and_new_images_are_reported(tmp_path, monkeypatch):
    path = capture.new_session("camera fixture", 36, 30, tmp_path)
    frame = np.random.default_rng(3).integers(0, 256, (480, 640, 3), dtype=np.uint8)
    hull = Delaunay([[0.15, -0.05], [0.25, -0.05], [0.2, 0.06]])
    positions = [(180, -10), (220, -20), (205, 30), (200, 0), (211, 0)]
    for i, (x, y) in enumerate(positions):
        img = frame.copy()
        img[0, 0, 0] = i
        capture.save_point(
            path,
            view((i + 1) * 10, img),
            "calibration_check" if i < 3 else "verification",
            x,
            y,
            True,
            [27, 27, 42, 42],
            score=lambda _, v=(x, y): (np.array(v) / 1000, hull),
        )
    monkeypatch.setattr(capture, "predictor", lambda: (None, hull))
    monkeypatch.setattr(grasp_admission, "locate_cube", lambda *_: np.array([0.2, 0.0]))
    monkeypatch.setattr(
        relook,
        "identity",
        lambda _: {"object_sha256": "cube", "calibration_sha256": "cal", "vision_sha256": "vision"},
    )
    first = view(100, frame.copy())
    new = view(300, frame.copy())
    new["rgb"][0, 1, 0] ^= 1
    repeated = view(300, first["rgb"])
    changed_camera = deepcopy(new)
    changed_camera["boot_id"] = "new-boot"
    packets = iter([first, changed_camera, repeated, new, new])
    monkeypatch.setattr(capture, "acquire_snapshot", lambda margin: next(packets))
    assert relook.add(path, "first", [200, 0], True)["stage"] == "away"
    mid = {
        "arrays": {"arm": list(LOOK_COMMAND), "odometry": first["after"]["odometry"]},
        "meta": {
            "robot": "rosmaster",
            "read_only": True,
            "motion_commands_sent": 0,
            "boot_id": first["boot_id"],
            "clock_pair": {"use_sim_time": False},
            "streams": {
                "arm": {
                    "topic": capture.STREAMS["arm"],
                    "age_s": 0.0,
                    "source_timestamp_ns": 200,
                    "unit": "servo_degrees_from_CubeBot_bridge",
                    "names": list("abcdef"),
                },
                "odometry": {
                    "topic": capture.STREAMS["odometry"],
                    "age_s": 0.0,
                    "source_timestamp_ns": 200,
                    "frame_id": "odom",
                    "child_frame": "base",
                },
            },
        },
        "received_ns": 150,
        "request_elapsed_s": 0.0,
    }
    monkeypatch.setattr(
        capture, "SensorClient", lambda **_: SimpleNamespace(snapshot=lambda _: mid, close=lambda: None)
    )
    with pytest.raises(ValueError, match="Уход руки"):
        relook.add(path, "away")
    mid["arrays"]["arm"][2] += 8
    mid["arrays"]["arm"][5] += 10
    with pytest.raises(ValueError, match="открытый захват"):
        relook.add(path, "away")
    mid["arrays"]["arm"][5] -= 10
    assert relook.add(path, "away")["stage"] == "second"
    with pytest.raises(ValueError, match="загрузки ROS"):
        relook.add(path, "second", [200, 0], True)
    with pytest.raises(ValueError, match="другой RGB"):
        relook.add(path, "second", [200, 0], True)
    with pytest.raises(ValueError, match="контрольной точке"):
        relook.add(path, "second", [215, 0], True)
    answer = relook.add(path, "second", [200, 0], True)
    assert answer["stage"] == "completed" and answer["difference"]["error_change_xy_mm"] == [0.0, 0.0]
    assert answer["physical_trials"] == 0 and not answer["actuation_authorized"]
    assert len((path / "passive-reobservation/refusals.jsonl").read_text().splitlines()) == 5
    assert not (path / grasp_admission.EVIDENCE).exists()
