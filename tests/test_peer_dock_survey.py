"""The measured donor reference is a prior; only normal lidar tracking can supply a field pose."""

import hashlib
import io
import json
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from explorer4 import fleet_map, sim2d
from explorer4 import peer_dock_survey as survey
from explorer4.peer_dock_localizer import PhysicalFleetMap


@pytest.fixture
def floor(monkeypatch, tmp_path):
    fleet = PhysicalFleetMap()
    tank = (1.0, 1.0, 0.3)
    offset = (0.65, 0.3, -0.2)
    donor = fleet_map.compose(tank, offset)
    rng = np.random.default_rng(101)
    room = sim2d.make_room(rng)
    samples = []
    for i in range(6):
        pkt = sim2d.lidar_packet(
            room, fleet_map.MOUNTS["rosmaster"], donor, rng, noise=0.002
        )
        pkt["meta"].update(
            robot="rosmaster",
            read_only=True,
            motion_commands_sent=0,
            boot_id="fixture",
            clock_pair={
                "ros_time_ns": 1_000_000_000 + i,
                "monotonic_ns": 700_000_000 + i,
                "uncertainty_ns": 10,
                "use_sim_time": False,
            },
        )
        pkt["arrays"]["odometry"] = np.array(
            [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
        )
        pkt["meta"]["streams"]["odometry"] = {"child_frame": "base_footprint"}
        for k, frame in zip(
            survey.STREAMS, ("laser0_frame", "laser1_frame", "odom_raw")
        ):
            pkt["meta"]["streams"][k].update(
                frame_id=frame,
                source_timestamp_ns=900_000_000 + i,
                source_clock="rosmaster_ros_time",
                age_s=0.0,
            )
        stream = io.BytesIO()
        np.savez_compressed(
            stream,
            metadata=np.frombuffer(json.dumps(pkt["meta"]).encode(), dtype=np.uint8),
            **pkt["arrays"],
        )
        pkt["payload"] = stream.getvalue()
        pkt.update(received_ns=time.monotonic_ns(), request_elapsed_s=0.005)
        samples.append(pkt)
    fleet.grid.add(
        fleet_map.transform(fleet_map.scan_points("rosmaster", samples[0]), donor),
        donor,
    )
    fleet._set("tank", pose=tank, state="tracking")
    fleet._set("rosmaster", pose=None, state="submap")
    ctrl = SimpleNamespace(
        owner=None, generation=0, stop_event=threading.Event(), lock=threading.RLock()
    )
    ctrl.stop_event.set()
    queue = iter(samples[1:3])

    def capture(only):
        pkt = next(queue)
        pkt.update(received_ns=time.monotonic_ns(), request_elapsed_s=0.005)
        return pkt

    monkeypatch.setattr(survey.field, "RUNS", tmp_path / "field")
    monkeypatch.setattr(survey.field, "CALIBRATION", tmp_path / "cameras.json")
    monkeypatch.setattr(
        survey.field,
        "SensorClient",
        lambda robot: SimpleNamespace(snapshot=capture, close=lambda: None),
    )
    monkeypatch.setattr(survey.fleet_map.LOCALIZER, "running", lambda: True)
    return fleet, ctrl, offset, samples


def test_survey_requires_next_regular_lidar_pose(floor):
    fleet, ctrl, offset, samples = floor
    assert fleet.pose_frame("rosmaster")[0] is None
    original_grid = fleet.grid.hits.copy()
    before = fleet.grid.scans
    evidence = survey.anchor_donor(
        ctrl, fleet, *offset[:2], np.degrees(offset[2]), True
    )
    assert (
        evidence["status"] == "awaiting_regular_lidar_tracking"
        and evidence["motor_commands_sent"] == 0
    )
    assert fleet.pose_frame("rosmaster")[0] is None
    assert (
        len(evidence["observations"]) == 2
        and np.array_equal(original_grid, fleet.grid.hits)
        and fleet.grid.scans == before
    )
    assert not survey.field.CALIBRATION.exists()
    archive = survey.field.RUNS / "surveys" / (evidence["id"] + ".npz")
    assert (
        hashlib.sha256(archive.read_bytes()).hexdigest() == evidence["archive_sha256"]
    )
    with np.load(archive, allow_pickle=False) as logged:
        assert np.array_equal(logged["hits"], original_grid)
        assert (
            logged["first_packet"].tobytes() == samples[1]["payload"]
            and logged["second_packet"].tobytes() == samples[2]["payload"]
        )
    assert (
        fleet.relative("tank", "rosmaster") is None
        and survey.field.real_pose(fleet, "rosmaster")[0] is None
    )
    assert fleet.track["rosmaster"]["floor_survey"]["boot_id"] == "fixture"
    # Real transport repeats the same packet and may refresh only one lidar in the next packet.
    assert fleet.update("rosmaster", samples[2])["state"] == "survey_prior"
    assert (
        survey.field.real_pose(fleet, "rosmaster")[0] is None
        and fleet.relative("tank", "rosmaster") is None
    )
    from copy import deepcopy

    partly_new = deepcopy(samples[3])
    partly_new["meta"]["streams"]["scan_rear"]["source_timestamp_ns"] = samples[2][
        "meta"
    ]["streams"]["scan_rear"]["source_timestamp_ns"]
    fleet.update("rosmaster", partly_new)
    assert (
        survey.field.real_pose(fleet, "rosmaster")[0] is None
        and fleet.relative("tank", "rosmaster") is None
    )
    state = fleet.update("rosmaster", samples[3], fleet_map.odom_pose(samples[3]))
    assert (
        state["state"] == "tracking" and fleet.relative("tank", "rosmaster") is not None
    )
    assert fleet.track["rosmaster"]["floor_survey"]["status"] == "confirmed"
    proof = json.loads(
        (archive.parent / (evidence["id"] + "-confirmation.json")).read_text()
    )
    assert proof["global_uniqueness_established"] is False
    pose, _, _, source = survey.field.observation_pose(fleet, "rosmaster")
    assert (
        pose is not None
        and source["survey"] == evidence["id"]
        and source["global_uniqueness_established"] is False
    )
    assert (
        source["confirmation_sha256"]
        == hashlib.sha256(
            (archive.parent / (evidence["id"] + "-confirmation.json")).read_bytes()
        ).hexdigest()
    )
    assert all(
        new > before
        for new, before in zip(proof["source_ns"], proof["survey_last_source_ns"])
    )
    assert (
        hashlib.sha256(
            (archive.parent / (evidence["id"] + "-confirmation.npz")).read_bytes()
        ).hexdigest()
        == proof["packet_sha256"]
    )
    last = fleet.track["rosmaster"]["at"]
    fleet.update("rosmaster", samples[3])
    assert last == fleet.track["rosmaster"]["at"]
    assert np.allclose(
        fleet.pose_frame("rosmaster")[0],
        evidence["observations"][1]["survey_pose"],
        atol=0.035,
    )


@pytest.mark.parametrize(
    "error",
    [
        "old_scan",
        "wrong_geometry",
        "moving",
        "virtual",
        "no_reference",
        "owner",
        "stale_source",
        "unsigned",
        "sim_clock",
    ],
)
def test_survey_blocks_unusable_inputs(floor, monkeypatch, error):
    fleet, ctrl, offset, samples = floor
    if error == "old_scan":
        for k in survey.STREAMS:
            samples[2]["meta"]["streams"][k]["source_timestamp_ns"] = 900_000_001
    if error == "wrong_geometry":
        offset = (6.0, 4.0, 0.0)
    if error == "moving":
        samples[1]["arrays"]["odometry"][6] = 0.1
    if error == "virtual":
        from explorer4 import swarm_sim

        monkeypatch.setattr(swarm_sim, "WORLD", object())
    if error == "no_reference":
        fleet.track["tank"]["at"] -= 2.0
    if error == "owner":
        ctrl.owner = "another operator"
    if error == "sim_clock":
        samples[1]["meta"]["clock_pair"]["use_sim_time"] = True
    if error == "stale_source":
        samples[1]["meta"]["clock_pair"]["ros_time_ns"] += 1_000_000_000
    with pytest.raises(ValueError):
        survey.anchor_donor(
            ctrl, fleet, *offset[:2], np.degrees(offset[2]), error != "unsigned"
        )
    assert fleet.pose_frame("rosmaster")[0] is None
    assert not (survey.field.RUNS / "surveys").exists()


def test_marked_pilot_from_two_calibrations_through_stop_and_independent_score(
    floor, monkeypatch, tmp_path
):
    """The first A/selective slot consumes the donor. STOP and a floor measurement record an honest failure."""
    from contextlib import nullcontext

    from explorer4 import (
        catalog,
        drive,
        episodes,
        explore,
        peer_field_shadow,
    )
    from explorer4 import (
        peer_dock_series as series,
    )
    from explorer4.control import Control
    from explorer4.tank import TankSource

    fleet, stopped, offset, samples = floor
    survey.anchor_donor(stopped, fleet, *offset[:2], np.degrees(offset[2]), True)
    fleet.update("rosmaster", samples[3], fleet_map.odom_pose(samples[3]))
    # Isolate every output and intercept hardware transport. Exercise the actual series and controller.
    field = series.field
    monkeypatch.setattr(series, "SERIES", tmp_path / "pilot/series.json")
    monkeypatch.setattr(episodes, "ROOT", tmp_path / "episodes")
    monkeypatch.setattr(series.fleet_config, "locked", nullcontext)
    monkeypatch.setattr(catalog, "event", lambda *a: None)
    monkeypatch.setattr(peer_field_shadow, "capture_hook", lambda *a, **kw: None)
    monkeypatch.setattr(
        TankSource, "send", lambda *a: pytest.fail("physical transport reached")
    )
    monkeypatch.setattr(drive, "FLEET", fleet)
    monkeypatch.setattr(explore, "FLEET", fleet)
    fleet.track["tank"]["scan"] = np.array([[2.0, 0.0], [0.0, 2.0], [-2.0, 0.0]])
    ground = {"centre": [2.0, 1.0, 0.35], "blind": False}

    def observation(robot, directory, fleet):
        pose = fleet.pose_frame(robot)[0]
        transform = field.board_in_map(*ground["centre"], 180.0)
        return {
            "source_robot": robot,
            "board_valid": not (robot == "tank" and ground["blind"]),
            "reason": "board hidden",
            "map_frame_id": fleet.frame_id,
            "base_pose_map": list(pose),
            "camera_sha256": robot,
            "optical_from_board": (
                np.linalg.inv(field.map_from_base(pose)) @ transform
            ).tolist(),
            "arm_deg": [90.0] * 6,
            "odometry_frames": ["odom_raw", "base_footprint"],
            "rgb_age_s": 0.01,
            "received_monotonic_ns": time.monotonic_ns(),
        }

    monkeypatch.setattr(field, "observe", observation)
    # Twin survey captures use the original independent two-position validation on both cameras.
    for i in range(2):
        ground["centre"][1] = 1.0 + 0.13 * i
        capture = field.record(fleet)
        for robot in field.ROBOTS:
            entry = field.calibrate(
                capture["id"], robot, ground["centre"], 180.0, validate=bool(i)
            )
            assert entry["verified"] == bool(i)

    def arm(only):
        return {
            "arrays": {"arm": np.full(6, 90.0)},
            "received_ns": time.monotonic_ns(),
            "request_elapsed_s": 0.0,
            "meta": {
                "streams": {
                    "odometry": {
                        "frame_id": "odom_raw",
                        "child_frame": "base_footprint",
                        "age_s": 0.0,
                    },
                    "arm": {
                        "unit": "servo_degrees_from_CubeBot_bridge",
                        "age_s": 0.0,
                        "names": [f"servo{i}" for i in range(1, 7)],
                    },
                }
            },
        }

    monkeypatch.setattr(
        field,
        "SensorClient",
        lambda robot: SimpleNamespace(snapshot=arm, close=lambda: None),
    )
    control = Control()
    series.prepare()
    series.label_layout(
        "A", "Marked centre and axis on the floor", fleet, control, 0.60
    )
    control.robot = "tank"
    control.owner = "operator"
    control.session = "fixture"
    control.stop_event.clear()
    monkeypatch.setattr(control, "authorized", lambda: True)
    control.heartbeat("operator")
    session = SimpleNamespace(
        thread=SimpleNamespace(is_alive=lambda: True),
        phase="following",
        record_requested=False,
        trial_plan=None,
        pilot=None,
        autonomous=False,
    )
    ground["blind"] = True
    ident = series.start(control, session, "operator", fleet, fixture_restored=True)
    attempt = control.goal
    for _ in range(2):
        attempt.future.result(timeout=2.0)
        attempt.command(np.zeros((100, 100, 3), dtype="uint8"))
    assert attempt.measured_goal["source_robot"] == "rosmaster"
    with pytest.raises(ValueError, match="STOP"):
        series.score(control, ident, 0.3, 0.0, 0.0, True, True, "Tape")
    control.stop("operator_stop")
    assert not attempt.active
    score = series.score(
        control,
        ident,
        0.3,
        0.0,
        0.0,
        True,
        True,
        "Tape measured 300 mm from taped target",
    )
    assert (
        not score["success"]
        and score["perception_admitted"]
        and score["operator_intervention"]
    )
    report = series.report()
    assert report["outcomes"]["selective"] == {
        "started": 1,
        "measured": 1,
        "independent_successes": 0,
    }
    assert series.next_slot(report) == ["A", "local_scan"]


@pytest.mark.parametrize(
    "fault",
    [
        "boot",
        "clock_step",
        "sim_clock",
        "moving_base",
        "stale_lidar",
        "map_origin",
        "counterfeit_fit",
    ],
)
def test_independent_packet_rejects_contradiction_or_new_epoch(
    floor, fault, monkeypatch
):
    fleet, ctrl, offset, samples = floor
    receipt = survey.anchor_donor(ctrl, fleet, *offset[:2], np.degrees(offset[2]), True)
    pkt = samples[3]
    if fault == "boot":
        pkt["meta"]["boot_id"] = "second-boot"
    if fault == "clock_step":
        pkt["meta"]["clock_pair"]["monotonic_ns"] += 100_000_000
    if fault == "sim_clock":
        pkt["meta"]["clock_pair"]["use_sim_time"] = True
    if fault == "moving_base":
        pkt["arrays"]["odometry"][6] = 0.1
    if fault == "stale_lidar":
        pkt["meta"]["streams"]["scan_rear"]["source_timestamp_ns"] = 1
    if fault == "map_origin":
        fleet.frame_id = "other-room"
    if fault == "counterfeit_fit":
        original = fleet.grid.refine

        def contradicted(points, hint):
            _, pose = original(points, hint)
            return 1.0, (pose[0] + 0.2, pose[1], pose[2])

        monkeypatch.setattr(fleet.grid, "refine", contradicted)
    fleet.update("rosmaster", pkt)
    assert fleet.track["rosmaster"]["rejected_survey"] == receipt["id"]
    assert (
        fleet.pose_frame("rosmaster")[0] is None
        and fleet.relative("tank", "rosmaster") is None
    )
    assert not (
        survey.field.RUNS / "surveys" / (receipt["id"] + "-confirmation.json")
    ).exists()


def test_verified_survey_cannot_survive_reboot_or_old_registration_packet(floor):
    fleet, ctrl, offset, samples = floor
    evidence = survey.anchor_donor(
        ctrl, fleet, *offset[:2], np.degrees(offset[2]), True
    )
    fleet.update("rosmaster", samples[3])
    assert survey.field.real_pose(fleet, "rosmaster")[0] is not None
    samples[4]["meta"]["boot_id"] = "rebooted"
    fleet.update("rosmaster", samples[4])
    assert fleet.track["rosmaster"]["rejected_survey"] == evidence["id"]
    fleet.update("rosmaster", samples[2])
    assert survey.field.real_pose(fleet, "rosmaster")[0] is None
    assert fleet.relative("tank", "rosmaster") is None
