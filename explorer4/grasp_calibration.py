"""Stationary, read-only localization check for the frozen ROSMASTER grasp policy."""

import fcntl
import json
import math
import os
import shutil
import tempfile
import time
import uuid
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial import Delaunay
from scipy.spatial.transform import Rotation

from .conditioned_grasp import (
    MOTOR_SHA256,
    VISION_SHA256,
    file_hash,
    load_localizer,
    locate_cube,
)
from .grasp_shadow import close_to_look_state, look_distance
from .paths import DATA
from .sensors import SensorClient, stream_age

ROOT = DATA / "runs/grasp-calibration"
VISION = DATA / "runs/recorded-start-cube-20261121/night/visual-pick-v1/weights.pt"
MOTOR = DATA / "runs/article-closeout-20261122/learned-trajectories/motor.npz"
ROLES = {"calibration_check": 3, "verification": 2}
STREAMS = {
    "arm": "/arm_servo_state",
    "odometry": "/odom_raw",
    "rgb": "/camera/color/image_raw",
    "rgb_info": "/camera/color/camera_info",
}


def json_write(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    os.replace(tmp, path)


def open_session(ident, root=ROOT):
    if not isinstance(ident, str) or uuid.UUID(hex=ident).hex != ident:
        raise ValueError("Некорректный номер серии")
    path = root / ident
    if not (path / "session.json").is_file():
        raise ValueError("Серия не найдена")
    return path


def new_session(device, jaw_mm, cube_mm, root=ROOT):
    device = str(device or "").strip()
    jaw, cube = float(jaw_mm or 0), float(cube_mm or 0)
    if not 1 <= len(device) <= 100:
        raise ValueError("Введите заводской или инвентарный номер камеры")
    if not (math.isfinite(jaw) and math.isfinite(cube) and 0 < cube < jaw):
        raise ValueError("Проверьте измерения: ширина раскрытия должна превышать ширину кубика")
    path = root / uuid.uuid4().hex
    path.mkdir(parents=True, mode=0o700)
    json_write(
        path / "session.json",
        {
            "id": path.name,
            "created_at": time.time(),
            "robot": "rosmaster",
            "camera": "front",
            "device_id": device,
            "device_identity_source": "operator_read_serial_or_inventory_label",
            "jaw_opening_mm": jaw,
            "cube_width_mm": cube,
            "measured_allowable_xy_error_m": (jaw - cube) / 2000,
            "vision_sha256": VISION_SHA256,
            "training_eligible": False,
            "motion_commands_sent": 0,
        },
    )
    return path


def session_rows(path):
    return [json.loads(p.read_text()) for p in sorted(path.glob("point-*/point.json"))]


def summary(path):
    session = json.loads((path / "session.json").read_text())
    rows = session_rows(path)
    checks = [r["independently_measured_base_xy_m"] for r in rows if r["role"] == "calibration_check"]
    full_check = (
        len(checks) >= ROLES["calibration_check"]
        and np.linalg.matrix_rank(np.asarray(checks) - np.mean(checks, axis=0)) == 2
    )
    counts = {role: sum(r["role"] == role for r in rows) for role in ROLES}
    complete = full_check and counts["verification"] == ROLES["verification"]
    failed = any(not r["within_measured_margin"] or not r["inside_demonstration_hull"] for r in rows)
    return {
        "session": session["id"],
        "status": "negative" if failed else "positive" if complete else "incomplete",
        "complete": bool(complete),
        "independent_geometry": bool(full_check),
        "counts": counts,
        "measured_allowable_xy_error_m": session["measured_allowable_xy_error_m"],
        "points": [
            {
                k: r[k]
                for k in (
                    "role",
                    "independently_measured_base_xy_m",
                    "predicted_xy_m",
                    "residual_xy_mm",
                    "error_mm",
                    "within_measured_margin",
                    "inside_demonstration_hull",
                )
            }
            for r in rows
        ],
        "evidence_scope": "static RGB localization in measured workspace",
        "physical_grasp_trials": 0,
        "motion_commands_sent": 0,
    }


def live_stream(packet, key, max_age):
    meta = packet["meta"]
    stream = meta.get("streams", {}).get(key, {})
    if (
        meta.get("robot") != "rosmaster"
        or meta.get("read_only") is not True
        or meta.get("motion_commands_sent") != 0
        or meta.get("clock_pair", {}).get("use_sim_time") is not False
        or not meta.get("boot_id")
    ):
        raise ValueError("Нужен пассивный мост реального ROSMASTER с активными часами")
    # At receipt time. The three snapshots are validated together after acquisition.
    age = stream_age(packet, key, packet["received_ns"])
    if (
        stream.get("topic") != STREAMS[key]
        or not 0 <= age <= max_age
        or not stream.get("source_timestamp_ns", 0) > 0
    ):
        raise ValueError(f"Нет свежего сообщения {STREAMS[key]} с исходной меткой времени")
    return stream


def measured_pose(packet):
    from .rosmaster_session import ARM_FEEDBACK_MAX_AGE_S, BASE_FEEDBACK_MAX_AGE_S

    arm_source = live_stream(packet, "arm", ARM_FEEDBACK_MAX_AGE_S)
    odom_source = live_stream(packet, "odometry", BASE_FEEDBACK_MAX_AGE_S)
    arm = np.asarray(packet["arrays"].get("arm"), dtype=float)
    odom = np.asarray(packet["arrays"].get("odometry"), dtype=float)
    if (
        arm_source.get("unit") != "servo_degrees_from_CubeBot_bridge"
        or arm.shape != (6,)
        or not np.isfinite(arm).all()
    ):
        raise ValueError("Нужны шесть измеренных углов родного ROS-моста в градусах")
    pos, angle = look_distance(arm)
    if not close_to_look_state(arm) or pos > 0.02 or angle > 5:
        raise ValueError(
            "Поза обзора не совпала; измерено "
            + str(arm.round(1).tolist())
            + f", камера {pos * 100:.1f} см / {angle:.1f}°"
        )
    if odom.shape != (9,) or not np.isfinite(odom).all() or not 0.98 <= np.linalg.norm(odom[2:6]) <= 1.02:
        raise ValueError("Нет достоверной одометрии шасси")
    if np.any(np.abs(odom[6:]) > 1e-4):
        raise ValueError("По энкодерам шасси движется")
    return {
        "arm_degrees": arm.tolist(),
        "joint_names": arm_source.get("names", []),
        "odometry": odom.tolist(),
        "odometry_frame": odom_source.get("frame_id"),
        "odometry_child": odom_source.get("child_frame"),
        "camera_delta_m": pos,
        "camera_delta_degrees": angle,
        "arm_stamp": arm_source["source_timestamp_ns"],
        "odom_stamp": odom_source["source_timestamp_ns"],
    }


def held_fixed(a, b, margin):
    oa, ob = np.array(a["odometry"]), np.array(b["odometry"])
    rotation = (Rotation.from_quat(oa[2:6]).inv() * Rotation.from_quat(ob[2:6])).magnitude()
    # Reject changes that could shift the far edge of the 0.25 m task region by the measured margin.
    shift = np.linalg.norm(oa[:2] - ob[:2]) + 2 * 0.25 * math.sin(rotation / 2)
    if (
        a["joint_names"] != b["joint_names"]
        or a["odometry_frame"] != b["odometry_frame"]
        or a["odometry_child"] != b["odometry_child"]
        or shift > margin
        or max(np.abs(np.asarray(a["arm_degrees"]) - b["arm_degrees"])) > 1
    ):
        raise ValueError("Шасси или рука сместились между измерениями")


def extract_capture(before, middle, after, margin):
    first, last = measured_pose(before), measured_pose(after)
    rgb = live_stream(middle, "rgb", 0.5)
    ci = live_stream(middle, "rgb_info", 0.5)
    image = np.asarray(middle["arrays"].get("rgb"))
    if (
        len({p["meta"]["boot_id"] for p in (before, middle, after)}) != 1
        or not first["arm_stamp"] <= rgb["source_timestamp_ns"] <= last["arm_stamp"]
        or not first["odom_stamp"] <= rgb["source_timestamp_ns"] <= last["odom_stamp"]
        or first["arm_stamp"] >= last["arm_stamp"]
        or first["odom_stamp"] >= last["odom_stamp"]
    ):
        raise ValueError(
            "RGB не попал между двумя разными отсчётами положения шасси и руки; повторите снимок"
        )
    held_fixed(first, last, margin)
    if (
        image.shape != (480, 640, 3)
        or image.dtype != np.uint8
        or rgb.get("encoding") not in ("rgb8", "bgr8")
        or (ci.get("width"), ci.get("height")) != (640, 480)
        or rgb.get("frame_id") != ci.get("frame_id")
        or not ci.get("frame_id")
    ):
        raise ValueError("Требуются совпадающие 640×480 RGB и CameraInfo передней камеры")
    info = {
        k: ci[k] for k in ("topic", "frame_id", "width", "height", "distortion_model", "k", "d", "p", "r")
    }
    k = np.asarray(info["k"])
    if (
        k.shape != (9,)
        or min(k[0], k[4]) <= 0
        or any(not np.isfinite(np.asarray(info[key])).all() for key in ("k", "d", "p", "r"))
    ):
        raise ValueError("Неполная калибровка RGB-камеры")
    return {
        "rgb": image,
        "camera_info": info,
        "before": first,
        "after": last,
        "rgb_stamp": rgb["source_timestamp_ns"],
        "camera_info_stamp": ci["source_timestamp_ns"],
        "boot_id": middle["meta"]["boot_id"],
    }


def acquire_snapshot(margin):
    # Native sensor bridge subscribes to feedback only. No serial lease or actuator endpoints.
    client = SensorClient(robot="rosmaster")
    try:
        before = client.snapshot(("arm", "odometry"))
        time.sleep(0.25)
        middle = client.snapshot(("rgb", "rgb_info"))
        time.sleep(0.3)
        after = client.snapshot(("arm", "odometry"))
        return extract_capture(before, middle, after, margin)
    finally:
        client.close()


@lru_cache(maxsize=1)
def predictor():
    if file_hash(MOTOR) != MOTOR_SHA256:
        raise ValueError("Контрольная сумма банка траекторий изменилась")
    with np.load(MOTOR, allow_pickle=False) as bank:
        hull = Delaunay(bank["xy"])
    return load_localizer(VISION), hull


def score_rgb(rgb):
    localizer, hull = predictor()
    xy = locate_cube(localizer, rgb)
    return xy, hull


def save_point(path, packet, role, x_mm, y_mm, visible, box, score=score_rgb):
    if role not in ROLES or not visible or x_mm is None or y_mm is None:
        raise ValueError(
            "Введите измеренные X/Y, выберите роль и подтвердите видимость целого кубика на снимке"
        )
    if len(box) != 4 or not 0 < box[0] < box[2] < 640 or not 0 < box[1] < box[3] < 480:
        raise ValueError("Отметьте внутри кадра два противоположных угла вокруг целого кубика")
    xy = np.array([x_mm, y_mm], dtype=float) / 1000
    if not np.isfinite(xy).all():
        raise ValueError("Обе координаты должны быть числами")
    with (path / ".lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        session = json.loads((path / "session.json").read_text())
        rows = session_rows(path)
        progress = summary(path)
        if progress["counts"][role] >= ROLES[role]:
            raise ValueError("Для этой роли точки уже записаны")
        if role == "verification" and not progress["independent_geometry"]:
            raise ValueError("Сначала сохраните три точки проверки вне одной прямой")
        checks = [r["independently_measured_base_xy_m"] for r in rows]
        if (
            checks
            and np.min(np.linalg.norm(np.asarray(checks) - xy, axis=1))
            <= session["measured_allowable_xy_error_m"]
        ):
            raise ValueError("Нужна отдельная позиция, дальше измеренного допуска от уже записанных")
        if (
            role == "calibration_check"
            and len(checks) == 2
            and np.linalg.matrix_rank(np.diff(np.asarray([*checks, xy]), axis=0)) < 2
        ):
            raise ValueError("Третью точку разместите вне прямой первых двух")
        camera_file = path / "camera-info.json"
        if rows:
            a = rows[0]
            if (
                packet["boot_id"] != a["boot_id"]
                or json.loads(camera_file.read_text()) != packet["camera_info"]
                or packet["rgb_stamp"] <= rows[-1]["rgb_stamp"]
            ):
                raise ValueError("Камера, загрузка ROS или последовательность кадров изменилась")
            held_fixed(a["before"], packet["before"], session["measured_allowable_xy_error_m"])
            held_fixed(a["before"], packet["after"], session["measured_allowable_xy_error_m"])
        predicted, hull = score(packet["rgb"])
        residual = np.asarray(predicted) - xy
        error = float(np.linalg.norm(residual))
        if not np.isfinite(error):
            raise ValueError("Модель вернула нечисловой прогноз")
        point = {k: v for k, v in packet.items() if k not in ("rgb", "camera_info")}
        name = f"point-{len(rows) + 1:02d}"
        point.update(
            role=role,
            independently_measured_base_xy_m=xy.tolist(),
            predicted_xy_m=np.asarray(predicted).tolist(),
            residual_xy_mm=(1000 * residual).tolist(),
            error_mm=1000 * error,
            within_measured_margin=error <= session["measured_allowable_xy_error_m"],
            inside_demonstration_hull=bool(hull.find_simplex(xy) >= 0 and hull.find_simplex(predicted) >= 0),
            cube_fully_visible_confirmed=True,
            confirmed_cube_bbox_xyxy_px=list(box),
            file=f"{name}/rgb.png",
        )
        stage = Path(tempfile.mkdtemp(dir=path))
        try:
            image = stage / "rgb.png"
            if not cv2.imwrite(str(image), cv2.cvtColor(packet["rgb"], cv2.COLOR_RGB2BGR)):
                raise OSError("Не удалось сохранить RGB")
            point["sha256"] = file_hash(image)
            if any(r["sha256"] == point["sha256"] for r in rows):
                raise ValueError("Эта фотография уже использована")
            json_write(stage / "point.json", point)
            if not rows:
                json_write(camera_file, packet["camera_info"])
            stage.rename(path / name)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        return rebuild_report(path)


def rebuild_report(path):
    session = json.loads((path / "session.json").read_text())
    current = summary(path)
    json_write(path / "summary.json", current)
    if current["status"] == "positive":
        camera_file = path / "camera-info.json"
        json_write(
            path / "localization-calibration.json",
            {
                **session,
                "camera_info": camera_file.name,
                "camera_calibration_sha256": file_hash(camera_file),
                "reference_frames": session_rows(path),
            },
        )
    return current


def list_sessions(root=ROOT):
    return [
        summary(p.parent)
        for p in sorted(root.glob("*/session.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    ]


def archived_plans(path):
    """Score the two recorded verification frames without accessing hardware."""
    from scripts.grasp_study.shadow import calibration

    from .grasp_shadow import ArchiveGraspActions
    from .sim.vendor_rosmaster.arm_model import SERVO_LIMITS

    with (path / ".lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if summary(path)["status"] != "positive":
            raise ValueError("Сначала завершите измерения и подтвердите статическую локализацию")
        proof = calibration(path / "localization-calibration.json", VISION)
        if not proof:
            raise ValueError("Не найдены проверенные снимки калибровки")
        bundle = DATA / "checkpoints/conditioned-grasp-v1"
        lower, upper = np.asarray(SERVO_LIMITS).T
        result = {
            "domain": "archived_real",
            "outcome": "proposals_only",
            "trajectory_semantics":"20 Hz open-loop proposed targets. Simulation holds the final target until terminal feedback or timeout; physical terminal feedback is unavailable here.",
            "motion_commands_sent": 0,
            "physical_trials": 0,
            "calibration_sha256": file_hash(path / "localization-calibration.json"),
            "vision_sha256": VISION_SHA256,
            "points": [],
        }
        for row in session_rows(path):
            if row["role"] != "verification":
                continue
            bgr = cv2.imread(str(path / row["file"]))
            state = row["before"]["arm_degrees"]
            obs = {
                "domain": "archived_real",
                "robot_id": "rosmaster",
                "device_id": proof["device_id"],
                "observation.state": state,
                "images": {"front": cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)},
                "confirmed_cube_bbox_xyxy_px": row["confirmed_cube_bbox_xyxy_px"],
                "camera_calibration_sha256": proof["camera_calibration_sha256"],
            }
            planners = {}
            for method in ("rbf", "act", "diffusion"):
                planner = ArchiveGraspActions(bundle, MOTOR, VISION, method, proof)
                commands = []
                try:
                    while True:
                        target = np.asarray(planner.next(obs))
                        if (
                            not np.isfinite(target).all()
                            or np.any(target < lower - 1e-5)
                            or np.any(target > upper + 1e-5)
                        ):
                            raise ValueError("Прогноз выходит за паспортные границы сервоприводов")
                        commands.append(target.tolist())
                except StopIteration:
                    planners[method] = {
                        "status": "predicted",
                        "frames": len(commands),
                        "commands_deg": commands,
                    }
                except ValueError as exc:
                    planners[method] = {"status": "unsupported", "reason": str(exc)}
                planners[method]["native_limit_projection_steps"] = planner.clipped_steps
                planners[method]["max_native_limit_projection_deg"] = planner.max_projection_deg.tolist()
                planners[method]["motor_artifact_sha256"] = (
                    file_hash(bundle / method / "model.safetensors") if method != "rbf" else MOTOR_SHA256
                )
            result["points"].append({"rgb_sha256": row["sha256"], "methods": planners})
        json_write(path / "offline-plans.json", result)
        return result
