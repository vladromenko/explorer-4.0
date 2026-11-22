"""Terminal lift evidence is tied to the measured carry, its camera frames and an inspectable scale."""

import json
import threading
from contextlib import nullcontext
from types import SimpleNamespace

import av
import cv2
import numpy as np
import pytest

from explorer4 import grasp_terminal as terminal
from explorer4 import grasp_trial as trial
from explorer4.conditioned_grasp import file_hash


def video(path, frames=360):
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), "w") as output:
        stream = output.add_stream("mpeg4", rate=20)
        stream.width = stream.height = 16
        stream.pix_fmt = "yuv420p"
        for i in range(frames):
            picture = av.VideoFrame.from_ndarray(
                np.full((16, 16, 3), i % 255, np.uint8), format="rgb24"
            )
            output.mux(stream.encode(picture))
        output.mux(stream.encode(None))


@pytest.fixture
def capture(tmp_path, monkeypatch):
    monkeypatch.setattr(trial, "DATA", tmp_path)
    monkeypatch.setattr(trial, "RESULTS", tmp_path / "trials")
    monkeypatch.setattr(trial.fleet_config, "locked", nullcontext)
    monkeypatch.setattr(trial, "sync_recorded_outcome", lambda *_: None)
    ident, ep, tid = "1" * 32, "2" * 32, "3" * 32
    root = tmp_path / "datasets/rosmaster_pick_place" / ep
    clip = root / "videos/observation.images.front/chunk-000/file-000.mp4"
    video(clip)
    assert cv2.imwrite(
        str(root / "grasp-terminal.png"), np.zeros((16, 16, 3), np.uint8)
    )
    raw = {
        "domain": "real",
        "synthetic": False,
        "category": "rollout",
        "command_source": "policy",
        "hardware": {
            "trial_plan": {"id": ident, "kind": "conditioned_grasp"},
            "trial_id": tid,
            "clock_mapping": {"offset_ns": 1000, "rtt_ns": 2_000_000},
            "terminal_stop": {
                "request_home_ns": 28_007_000_000,
                "response_home_ns": 28_011_000_000,
            },
            "terminal_still_sha256": file_hash(root / "grasp-terminal.png"),
        },
    }
    (root / "provenance.json").write_text(json.dumps(raw))
    rows = []
    for i in range(360):
        now = 10_000_000_000 + i * 50_000_000
        rows.append(
            {
                "episode_id": ep,
                "frame_index": i,
                "trial_id": tid,
                "command_source": "policy",
                "decision": {"command_tick": i + 1},
                "agent_monotonic_ns": now,
                "camera": {
                    "agent_receive_timestamp_ns": now - 5_000_000,
                    "sequence": i,
                },
                "grasp_response": {
                    "agent_ns": now + 50_000_000,
                    "camera_ns": now + 45_000_000,
                    "sequence": i + 1,
                    "valid": [True] * 6,
                },
                "measured_response": [90.0, 130.0, 0.0, 25.0, 90.0, 140.0],
                "measured_response_age_s": [0.015] * 6,
            }
        )

    def rewrite():
        (root / "research.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows)
        )

    rewrite()
    record = trial.amend(
        ident,
        plan_id=ident,
        capture_protocol=terminal.VERSION,
        episodes=[ep],
        frames=360,
        finished_at=118.0,
        started_at=100.0,
        sequence_completed=True,
        stop_acknowledged_by_agent=True,
        emergency=False,
        pending_at_capture_close=True,
        recording_saved_at=120.0,
    )
    return (
        ident,
        root,
        clip,
        rows,
        rewrite,
        record,
        SimpleNamespace(lock=threading.RLock(), lease=None),
    )


def test_terminal_wrist_requires_actual_record_then_attests_minimum_height(capture):
    ident, _root, clip, _rows, _rewrite, record, op = capture
    actual = trial.certify(record)["terminal_review"]["window"]
    assert (
        actual["first_frame"],
        actual["last_video_frame"],
        actual["terminal_sample"],
    ) == (340, 359, 360)
    assert actual["duration_s"] == actual["min_joint_readback_span_s"] == 1.0
    for height, manual_duration, checked in (
        (9999, None, True),
        (62, 3600, True),
        (62, None, False),
    ):
        with pytest.raises(ValueError):
            trial.observe_outcome(
                ident,
                op,
                "held",
                height,
                manual_duration,
                "scale",
                source="wrist",
                confirmed=checked,
            )
    assert not trial.result(ident).get("endpoint")
    final = trial.observe_outcome(
        ident, op, "held", 61.0, None, "floor ruler", source="wrist", confirmed=True
    )
    assert final["success"] and trial.grade_status(final) == "success"
    assert final["endpoint"]["height_evidence"]["video_sha256"] == file_hash(clip)
    assert final["endpoint"]["terminal_window"] == actual


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_final_pose",
        "time_gap",
        "stale_final_frame",
        "stale_joint",
        "missing_frame",
    ],
)
def test_final_interval_cannot_be_replaced_with_an_earlier_hold(capture, mutation):
    ident, _root, _clip, rows, rewrite, record, op = capture
    if mutation == "wrong_final_pose":
        rows[-1]["measured_response"][0] = 102.0
    if mutation == "time_gap":
        rows[-1]["grasp_response"]["agent_ns"] += 400_000_000
    if mutation == "stale_final_frame":
        rows[-1]["grasp_response"]["camera_ns"] -= 55_000_000
    if mutation == "stale_joint":
        rows[-1]["measured_response_age_s"][3] = 0.8
    if mutation == "missing_frame":
        rows.pop(355)
    rewrite()
    assert trial.certify(record)["terminal_review"]["status"] == "unconfirmed"
    with pytest.raises(ValueError):
        trial.observe_outcome(
            ident, op, "held", 70.0, None, "ruler", source="wrist", confirmed=True
        )
    failure = trial.observe_outcome(
        ident, op, "failed", None, None, "cube dropped in final carry"
    )
    assert not failure["success"] and trial.grade_status(failure) == "failure"


def test_side_footage_binds_pts_stop_and_cannot_override_changed_wrist_evidence(
    capture,
):
    ident, _root, _clip, _rows, _rewrite, record, op = capture
    trial.certify(record)
    side = trial.side_video(ident)
    video(side, frames=41)
    with pytest.raises(ValueError):
        trial.observe_outcome(
            ident,
            op,
            "held",
            60.0,
            None,
            "side ruler",
            source="side_video",
            stop_s=0.3,
            confirmed=True,
        )
    with pytest.raises(ValueError):
        trial.observe_outcome(
            ident,
            op,
            "held",
            60.0,
            None,
            "side ruler",
            source="side_video",
            stop_s=3.0,
            confirmed=True,
        )
    final = trial.observe_outcome(
        ident,
        op,
        "held",
        50.0,
        None,
        "side ruler",
        source="side_video",
        stop_s=1.9,
        confirmed=True,
    )
    assert not final["success"]
    evidence = final["endpoint"]["height_evidence"]
    assert evidence["stop_frame"] == 38 and evidence["sha256"] == file_hash(side)


def test_changed_recording_and_unverifiable_legacy_grade(capture):
    ident, _root, _clip, rows, rewrite, record, op = capture
    trial.certify(record)
    rows[-1]["measured_response"][1] = 105.0
    rewrite()
    with pytest.raises(ValueError):
        trial.observe_outcome(
            ident, op, "held", 60.0, None, "ruler", source="wrist", confirmed=True
        )
    historical = {
        "success": True,
        "endpoint": {"visible_outcome": "held", "continuous_hold_s": 3600},
    }
    snapshot = json.dumps(historical)
    assert (
        trial.grade_status(historical) == "unconfirmed"
        and json.dumps(historical) == snapshot
    )


def test_delayed_stop_cannot_use_an_earlier_terminal_image(capture):
    _ident, root, _clip, _rows, _rewrite, record, _op = capture
    path = root / "provenance.json"
    raw = json.loads(path.read_text())
    for key in ("request_home_ns", "response_home_ns"):
        raw["hardware"]["terminal_stop"][key] += 100_000_000
    path.write_text(json.dumps(raw))
    assert trial.certify(record)["terminal_review"]["status"] == "unconfirmed"


def test_console_binds_one_side_video_and_exposes_only_the_confirmed_grade(capture):
    import asyncio

    from fastapi import HTTPException

    from explorer4 import rosmaster_console as console

    ident, root, clip, _rows, _rewrite, record, op = capture
    trial.certify(record)

    class Upload:
        def __init__(self, path):
            self.path = path

        async def stream(self):
            yield self.path.read_bytes()

    result = asyncio.run(console.attach_grasp_video(ident, Upload(clip)))
    assert result["frames"] == 360 and result["sha256"] == file_hash(clip)
    assert console.grasp_terminal_image(ident).path == root / "grasp-terminal.png"
    assert console.grasp_side_video(ident).path == trial.side_video(ident)
    different = root / "other.mp4"
    video(different, 50)
    with pytest.raises(HTTPException):
        asyncio.run(console.attach_grasp_video(ident, Upload(different)))
    final = trial.observe_outcome(
        ident, op, "unobservable", None, None, "Scale was outside the terminal frame"
    )
    assert (
        final["success"] is None
        and console.grasp_trial_result(ident)["evidence_status"] == "unconfirmed"
    )
    old_endpoint = {"visible_outcome": "held", "continuous_hold_s": 3600}
    trial.amend(ident, success=True, endpoint=old_endpoint)
    old_view = console.grasp_trial_result(ident)
    assert old_view["success"] is None and old_view["recorded_success"] is True
    assert trial.result(ident)["endpoint"] == old_endpoint
