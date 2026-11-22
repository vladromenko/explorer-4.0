"""Check two frozen real development recordings against the grasp observation contract."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from explorer4.conditioned_grasp import (
    VISION_SHA256,
    file_hash,
    load_localizer,
    locate_cube,
)
from explorer4.grasp_shadow import (
    ArchiveGraspActions,
    close_to_look_state,
    look_distance,
)
from explorer4.paths import DATA
from scripts.grasp_study.evaluate import (
    BUNDLE,
    OUTPUT,
    SOURCE,
    VISION,
    save_json,
    verified_models,
)

PLAN = "22a6506624dc67b0ff460e0e9d4a45b078fb0ad91a6a764c766026606e7f5978"
DEVELOPMENT = {"d8187db7e725432596d90e9111ccb2d6", "6352595336064846b59a13a52feee5eb"}


def calibration(path, vision):
    """Verify linked real CameraInfo and independently measured reference images."""
    if not path.is_file():
        return None
    import cv2

    record = json.loads(path.read_text())
    if (
        record["robot"] != "rosmaster"
        or record["camera"] != "front"
        or record["vision_sha256"] != VISION_SHA256
    ):
        raise ValueError("Calibration record names a different source")
    intrinsics = path.parent / record["camera_info"]
    if file_hash(intrinsics) != record["camera_calibration_sha256"]:
        raise ValueError("RGB calibration hash differs from its evidence")
    info = json.loads(intrinsics.read_text())
    k = np.asarray(info.get("k", []))
    if (
        (info.get("width"), info.get("height")) != (640, 480)
        or k.shape != (9,)
        or not np.isfinite(k).all()
        or min(k[0], k[4]) <= 0
    ):
        raise ValueError("Invalid camera intrinsics")
    estimator = load_localizer(vision)
    truth = []
    error = []
    for ref in record["reference_frames"]:
        image_path = path.parent / ref["file"]
        if file_hash(image_path) != ref["sha256"]:
            raise ValueError("Calibration image digest differs")
        image = cv2.imread(str(image_path))
        if image is None or image.shape != (480, 640, 3):
            raise ValueError("Calibration image unavailable")
        loc = np.asarray(ref["independently_measured_base_xy_m"], dtype=float)
        if loc.shape != (2,) or not np.isfinite(loc).all():
            raise ValueError("Invalid measured reference position")
        truth.append(loc)
        error.append(float(np.linalg.norm(locate_cube(estimator, image[:, :, ::-1]) - loc)))
    # A small non-collinear layout identifies XY offsets in both table axes.
    if len(truth) < 3 or np.linalg.matrix_rank(np.array(truth) - np.mean(truth, axis=0)) < 2:
        raise ValueError("Missing independent non-collinear target measurements")
    tolerance = float(record["measured_allowable_xy_error_m"])
    if not np.isfinite(tolerance) or tolerance <= 0 or max(error) > tolerance:
        raise ValueError("Localization error exceeds the measured jaw-to-object margin")
    return record


def audit_episode(entry, bundle, source, vision):
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    root = Path(entry["dataset"])
    info = json.loads((root / "meta/info.json").read_text())
    journal = [json.loads(line) for line in (root / "research.jsonl").read_text().splitlines()]
    if len(journal) != entry["frames"] or info["robot_type"] != "rosmaster" or info["fps"] != 20:
        raise ValueError("Wrong recording metadata")
    if any(row.get("domain") != "real" for row in journal):
        raise ValueError("Expected real demonstration frames")
    reasons = []
    provenance = json.loads((root / "provenance.json").read_text())
    image_key = "observation.images.front"
    if info["features"].get(image_key, {}).get("shape") != [480, 640, 3]:
        reasons.append("front_rgb_format_mismatch")
    camera_digest = None
    evidence = root / "localization-calibration.json"
    try:
        cal = calibration(evidence, vision)
    except (ValueError, KeyError, OSError) as exc:
        reasons.append("invalid_localization_calibration: " + str(exc))
        cal = None
    if cal is None:
        reasons.append("missing_recording_bound_measured_localization_calibration")
    else:
        camera_digest = cal["camera_calibration_sha256"]
        # The original capture must identify its camera independently of this optional sidecar.
        recorded = provenance.get("hardware", {}).get("rgb_camera_identity", {})
        if (
            recorded.get("camera_info_sha256") != camera_digest
            or not recorded.get("device_id")
            or recorded.get("device_id") != cal.get("device_id")
        ):
            reasons.append("camera_identity_unbound_to_original_capture")
    samples = [
        row
        for row in journal
        if row.get("measured_response_kind") == "servo_position_readback"
        and all(row.get("arm_measured_valid", []))
        and len(row.get("arm_measured_valid", [])) == 6
        and len(row.get("observation.state", [])) == 6
        and np.isfinite(row["observation.state"]).all()
    ]
    times = np.array(
        [r["observation_timestamp_ns"] - max(r["measured_response_age_s"]) * 1e9 for r in samples]
    )
    states = np.array([r["observation.state"] for r in samples])
    order = np.argsort(times, kind="stable")
    times, indices = np.unique(times[order], return_index=True)
    states = states[order][indices]
    eligible = []
    camera_pose_only = []
    poses = []
    seen = set()
    for index, row in enumerate(journal):
        cam = row.get("camera") or {}
        seq = cam.get("sequence")
        t = cam.get("timestamp_ns")
        if seq is None or seq in seen or not t or not len(times) or not times[0] <= t <= times[-1]:
            continue
        seen.add(seq)
        if np.max(np.abs(row.get("base_requested", [1.0]))) > 1e-6:
            continue
        high = np.searchsorted(times, t)
        low = max(0, high - 1)
        if max(t - times[low], times[high] - t) > 150_000_000:
            continue
        state = np.array([np.interp(t, times, states[:, j]) for j in range(6)])
        translation, angle = look_distance(state)
        poses.append((max(translation / 0.02, angle / 5), index, translation, angle))
        if translation <= 0.02 and angle <= 5:
            camera_pose_only.append(index)
            if close_to_look_state(state):
                eligible.append((index, state))
    if not camera_pose_only:
        reasons.append("no_camera_frame_in_fixed_look_window")
    if not eligible:
        reasons.append("no_frame_with_matching_arm_wrist_and_open_gripper")
    annotations = root / "shadow-cube-visibility.json"
    reviewed = json.loads(annotations.read_text()) if annotations.is_file() else {}
    visible = [(i, state) for i, state in eligible if str(i) in reviewed]
    if eligible and not visible:
        reasons.append("no_confirmed_full_cube_in_eligible_frame")
    row = dict(
        episode=entry["id"],
        frames=len(journal),
        timed_stationary_unique_rgb_frames=len(poses),
        camera_pose_only_frames=len(camera_pose_only),
        look_eligible_frames=len(eligible),
        calibration_sha256=camera_digest,
        unsupported_reasons=reasons,
        nearest_look=(
            dict(frame=min(poses)[1], translation_m=min(poses)[2], angle_deg=min(poses)[3]) if poses else None
        ),
        method="Nominal vendor camera FK, measured servo states interpolated to camera reception. 2 cm/5 degrees describes the reference view, independent metric calibration is required for real localization.",
        commands_sent=0,
        planners={},
    )
    methods = ("rbf", "act", "diffusion")
    if reasons:
        row["planners"] = {name: dict(status="unsupported", predicted_actions=0) for name in methods}
        return row
    # Each candidate gets the identical first qualifying image, with no labels/actions in its inputs.
    index, state = visible[0]
    dataset = LeRobotDataset("local/archived-shadow", root=root, video_backend="pyav")
    tensor = dataset[index][image_key]
    rgb = np.clip(np.rint(tensor.permute(1, 2, 0).numpy() * 255), 0, 255).astype(np.uint8)
    if hashlib.sha256(rgb.tobytes()).hexdigest() != reviewed[str(index)].get("rgb_sha256"):
        raise ValueError("Visibility annotation does not match decoded pixels")
    observation = {
        "domain": "archived_real",
        "robot_id": "rosmaster",
        "observation.state": state,
        "images": {"front": rgb},
        "camera_calibration_sha256": camera_digest,
        "device_id": cal["device_id"],
        "confirmed_cube_bbox_xyxy_px": reviewed[str(index)]["bbox_xyxy_px"],
    }
    for name in methods:
        adapter = ArchiveGraspActions(bundle, source, vision, name, cal)
        commands = []
        try:
            for _ in range(min(220, len(journal) - index)):
                commands.append(adapter.next(observation))
        except ValueError as exc:
            row["planners"][name] = dict(status="unsupported", reason=str(exc), predicted_actions=0)
            continue
        row["planners"][name] = dict(
            status="archive_shadow",
            predicted_actions=len(commands),
            frame=index,
            native_servo_targets=commands,
            units="native_servo_degrees",
            physical_success=None,
        )
    return row


def audit(report, bundle, source, vision):
    plan_path = DATA / "plans" / (PLAN + ".json")
    plan = json.loads(plan_path.read_text())
    records = plan["splits"]["validation"]
    if {r["id"] for r in records} != DEVELOPMENT or len(records) != 2:
        raise ValueError("Only the two approved development recordings can be opened")
    models = verified_models(bundle)
    rows = [audit_episode(r, bundle, source, vision) for r in records]
    outcome = dict(
        domain="archived_real",
        status="completed",
        physical_commands=0,
        physical_trials=0,
        plan_id=PLAN,
        split="validation",
        reserved_test_opened=False,
        reference_vision_sha256=VISION_SHA256,
        models={k: m["weights_sha256"] for k, m in models.items()},
        supported_episodes=sum(
            any(p["status"] == "archive_shadow" for p in r["planners"].values()) for r in rows
        ),
        episodes=rows,
    )
    save_json(report / "physical-shadow.json", outcome)
    print("Supported development episodes:", outcome["supported_episodes"], "of", len(rows))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report-dir", type=Path, default=OUTPUT)
    p.add_argument("--checkpoint-dir", type=Path, default=BUNDLE)
    p.add_argument("--source", type=Path, default=SOURCE)
    p.add_argument("--vision", type=Path, default=VISION)
    a = p.parse_args()
    audit(a.report_dir, a.checkpoint_dir, a.source, a.vision)
