import hashlib
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import pytest

from explorer4 import rosmaster_object_marker as marker
from explorer4.sensors import decode_packet

CARD = {
    "instance_id": "cube-29mm-tag1",
    "marker_dictionary": "DICT_APRILTAG_36h11",
    "marker_id": 1,
}


def sensor_packet(ids=(1,), age=0.02):
    now = time.monotonic_ns()
    ros_now = time.time_ns()
    stamp = ros_now - int(age * 1e9)
    pair = {
        "ros_time_ns": ros_now,
        "monotonic_ns": now,
        "uncertainty_ns": 1000,
        "use_sim_time": False,
    }
    stream = {
        "width": 640,
        "height": 480,
        "encoding": "rgb8",
        "topic": "/camera/color/image_raw",
        "frame_id": "camera_color_optical_frame",
        "source_clock": "rosmaster_ros_time",
        "source_timestamp_ns": stamp,
        "age_s": age,
        "sequence": 125,
    }
    meta = {
        "version": 1,
        "robot": "rosmaster",
        "boot_id": "camera-boot",
        "clock_pair": pair,
        "read_only": True,
        "motion_commands_sent": 0,
        "streams": {"rgb": stream},
    }
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    gray = np.full((480, 640), 255, np.uint8)
    for n, ident in enumerate(ids):
        start = 40 + 140 * n
        gray[100:200, start : start + 100] = cv2.aruco.generateImageMarker(
            dictionary, ident, 100
        )
    ok, jpeg = cv2.imencode(".jpg", gray)
    assert ok
    raw = io.BytesIO()
    np.savez_compressed(
        raw,
        metadata=np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8),
        rgb_jpeg=jpeg,
    )
    packet = decode_packet(raw.getvalue(), now, 0.001)
    prior = int((age + 0.03) * 1e9)
    checkpoint = {
        "before_ns": now - prior - 1000,
        "after_ns": now - prior,
        "remote": {
            **meta,
            "clock_pair": {
                **pair,
                "ros_time_ns": ros_now - prior,
                "monotonic_ns": now - prior,
            },
        },
    }
    return packet, checkpoint


@pytest.mark.parametrize(
    ("ids", "status"), [((1,), "observed"), ((2,), "missing"), ((1, 1), "duplicate")]
)
def test_one_receipt_per_exposure(tmp_path, ids, status):
    packet, checkpoint = sensor_packet(ids)

    def capture(_):
        return marker.measure(packet, checkpoint, CARD, tmp_path)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(capture, range(2)))
    assert sorted(r["status"] for r in results) == sorted([status, "replayed"])
    result = next(r for r in results if r["status"] == status)
    assert result["target_count"] == ids.count(1)
    assert result["card"] == CARD and result["motion_commands_sent"] == 0
    assert json.loads((tmp_path / result["id"] / "result.json").read_text()) == result
    image = (tmp_path / result["id"] / "rgb.png").read_bytes()
    assert hashlib.sha256(image).hexdigest() == result["png_sha256"]
    recovered_rgb = cv2.cvtColor(
        cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR),
        cv2.COLOR_BGR2RGB,
    )
    assert np.array_equal(recovered_rgb, packet["arrays"]["rgb"])
    assert result["packet_sha256"] == hashlib.sha256(packet["payload"]).hexdigest()
    assert result["markers"][0]["corners_px"]


def test_stale_and_replay_are_not_marker_misses(tmp_path):
    packet, checkpoint = sensor_packet(age=1.2)
    assert marker.measure(packet, checkpoint, CARD, tmp_path)["status"] == "stale"
    checkpoint["remote"]["clock_pair"] = packet["meta"]["clock_pair"]
    result = marker.measure(packet, checkpoint, CARD, tmp_path)
    assert result["status"] == "replayed" and "markers" not in result
    assert not (tmp_path / result["id"] / "rgb.png").exists()


@pytest.mark.parametrize(
    "change", ["boot", "robot", "rgb_origin", "simulated", "epoch"]
)
def test_other_origin_fails_closed(change):
    packet, checkpoint = sensor_packet()
    if change == "boot":
        checkpoint["remote"]["boot_id"] = "other-boot"
    elif change == "robot":
        packet["meta"]["robot"] = "tank"
    elif change == "rgb_origin":
        packet["meta"]["streams"]["rgb"]["topic"] = "/so101/overview"
    elif change == "simulated":
        checkpoint["remote"]["clock_pair"]["use_sim_time"] = True
    else:
        packet["meta"]["clock_pair"]["ros_time_ns"] += 200_000_000
    assert marker.check_source(packet, checkpoint) == "unverified"
