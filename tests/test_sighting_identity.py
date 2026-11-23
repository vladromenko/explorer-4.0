"""A named object must be decoded on the recipient, including in the presence of a class twin."""

import hashlib
import threading
import time

import cv2
import numpy as np
import pytest

from explorer4 import catalog, fleet_agents, goto, knowledge, scout, so101_geometry, world_memory
from explorer4.cognitive import store
from explorer4.sighting_identity import bind_cube, digest


@pytest.fixture
def recipient(tmp_path, monkeypatch):
    monkeypatch.setattr(so101_geometry, "CONFIG", tmp_path / "registration.json")
    monkeypatch.setattr(world_memory, "MEMORY", tmp_path / "world.json")
    monkeypatch.setattr(world_memory, "SNAPSHOTS", tmp_path / "snapshots")
    monkeypatch.setattr(world_memory, "POSES", {r: world_memory.Pose(r) for r in ("tank", "rosmaster")})
    monkeypatch.setattr(knowledge, "STORE", tmp_path / "knowledge.json")
    monkeypatch.setattr(catalog, "DATA", tmp_path)
    monkeypatch.setattr(store, "DATA", tmp_path)
    store.initialize()
    so101_geometry.configure_capture(
        enabled=True,
        instance_id="cube-A",
        marker_side_m=0.018,
        size_m=[0.029] * 3,
        marker_dictionary="DICT_APRILTAG_36h11",
        marker_id=1,
    )
    world_memory.POSES["rosmaster"].fix(0.0, 0.0, 0.0, source="lidar", frame_id="fleet_map:original")
    agent = fleet_agents.FleetAgents(None, domain=lambda: "sim")
    agent.start("fetch", "cube", ["rosmaster", "tank"])
    monkeypatch.setattr(world_memory, "LISTENERS", [agent.sighting])
    sensor = scout.Scout.__new__(scout.Scout)
    sensor.robot, sensor.cam = "rosmaster", goto.CAMERAS["rosmaster"]
    sensor.lock, sensor.last_source = threading.Lock(), None
    return agent, sensor


def twins(right=2):
    rgb = np.full((480, 640, 3), 235, np.uint8)
    boxes = [[90, 210, 210, 330, 0.61], [390, 210, 510, 330, 0.99]]
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    for box, tag in zip(boxes, [1, right]):
        x, y = box[:2]
        rgb[y : y + 120, x : x + 120] = 190
        rgb[y + 31 : y + 89, x + 31 : x + 89] = cv2.aruco.generateImageMarker(dictionary, tag, 58)[:, :, None]
    return rgb, boxes


def test_two_same_class_boxes_use_observed_tag_and_original_clock(recipient):
    agent, sensor = recipient
    rgb, boxes = twins()
    source = {
        "source_timestamp_ns": 211,
        "source_clock": "robot_ros",
        "sequence": 24,
        "frame_id": "wrist_rgb",
    }
    receive = time.monotonic_ns()
    sensor.feed(rgb, camera_info=source, received_monotonic_ns=receive)
    original_frame = sensor.frame_context
    sensor.feed(rgb, camera_info=source, received_monotonic_ns=time.monotonic_ns())
    assert sensor.frame_context is original_frame
    camera, frame = original_frame
    top = world_memory.record_boxes("rosmaster", "find cube", "cube", boxes, rgb, camera, frame)
    assert top["object_instance"] is None and top["bbox_xyxy_px"] == boxes[1][:4]
    named = world_memory.target_for("rosmaster", "cube", object_instance="cube-A")
    assert named["bbox_xyxy_px"] == boxes[0][:4] and named["room_xy"] != top["room_xy"]
    assert named["sample_id"] != top["sample_id"] and len(world_memory.known_objects()) == 2
    assert not world_memory.target_for("tank", "cube", object_instance="cube-A")
    ev = store.evidence([agent.sighting(named)])[0]
    assert ev.received_timestamp_ns == receive and ev.clock_domain == "homebrain_monotonic"
    assert ev.source_timestamp_ns == 211 and ev.payload["rgb"]["source_clock"] == "robot_ros"
    assert ev.camera_id == "wrist_rgb" and ev.frame_id == "fleet_map:original"
    assert ev.payload["rgb"]["camera_model"] == camera
    assert ev.payload["rgb"]["camera_model_sha256"] == digest(camera)
    assert ev.payload["rgb"]["calibration_sha256"] is None and ev.payload["measured_error_bound_m"] is None
    assert ev.payload["identity_evidence"]["rgb_sha256"] == hashlib.sha256(rgb).hexdigest()
    assert np.array_equal(cv2.imread(str(store.DATA / ev.artifact_ref))[:, :, ::-1], rgb)
    facts = knowledge.assess("rosmaster", "cube", context={"object_instance": "cube-A"})
    assert not facts["readiness"]["object_identity_unknown"]
    assert not facts["readiness"]["continuous_recipient_identity_verified"]
    fake = knowledge.assess(
        "rosmaster", "cube", context={"object_instance": "cube-B", "recipient_instance_verified": True}
    )
    assert fake["readiness"]["object_identity_unknown"] and fake["where"] is None
    world_memory.POSES["rosmaster"].fix(1.0, 0.0, 0.0, source="lidar", frame_id="fleet_map:replacement")
    assert world_memory.target_for("rosmaster", "cube", object_instance="cube-A") is None


def test_duplicated_or_ambiguous_tags_and_later_failure(recipient):
    _, sensor = recipient
    rgb, boxes = twins()
    sensor.feed(rgb)
    camera, frame = sensor.frame_context
    assert frame["source_timestamp_ns"] is None
    world_memory.record_boxes("rosmaster", "cube", "cube", boxes, rgb, camera, frame)
    assert world_memory.recent_instance("rosmaster", "cube", "cube-A", 60)
    assert bind_cube(rgb, "cube", [*boxes, [70, 200, 230, 340, 0.56]]) is None
    double, _ = twins(right=1)
    sensor.feed(double)
    camera, frame = sensor.frame_context
    world_memory.record_boxes("rosmaster", "cube", "cube", boxes, double, camera, frame)
    assert not world_memory.recent_instance("rosmaster", "cube", "cube-A", 60)
    previous = sensor.frame_context
    sensor.feed(rgb, camera_info={"reused": True})
    assert previous is sensor.frame_context


def test_observed_pixel_identity_survives_without_range(recipient):
    agent, sensor = recipient
    rgb, boxes = twins()
    sensor.cam = {**sensor.cam, "pitch_down": -60.0}
    sensor.feed(rgb)
    camera, frame = sensor.frame_context
    assert world_memory.record_boxes("rosmaster", "cube", "cube", boxes, rgb, camera, frame) is None
    recognition = world_memory.recent_instance("rosmaster", "cube", "cube-A", 60)
    assert recognition["distance"] is None and recognition["room_xy"] is None
    fact = store.evidence([agent.sighting(recognition)])[0]
    assert fact.status == "observed" and not fact.units
    assessment = knowledge.assess("rosmaster", "cube", context={"object_instance": "cube-A"})
    assert assessment["readiness"]["where_missing"] and not assessment["readiness"]["object_identity_unknown"]
