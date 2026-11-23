"""Optional, passive repeat-view evidence at measured point four. No actuator interface."""

import fcntl
import hashlib
import json
import os

import cv2
import numpy as np

from . import grasp_calibration as capture
from .conditioned_grasp import LOOK_COMMAND, SLEW_DEGREES_PER_SECOND, file_hash
from .grasp_admission import identity, initial_target
from .grasp_shadow import close_to_look_state, look_distance


def read(path):
    return json.loads(path.read_text())


def current(path):
    record = path / "passive-reobservation/result.json"
    return (
        read(record)
        if record.is_file()
        else {
            "schema": "rosmaster-passive-reobservation-v1",
            "stage": "first",
            "scope": "Repeat RGB localization for one stationary measured cube; no grasp test.",
            "actuation_authorized": False,
            "motion_commands_sent": 0,
            "physical_trials": 0,
        }
    )


def away_witness(first, packet):
    """A distinct native arm pose between views. The gripper alone cannot be the excursion."""
    from .rosmaster_session import ARM_FEEDBACK_MAX_AGE_S, BASE_FEEDBACK_MAX_AGE_S

    arm = capture.live_stream(packet, "arm", ARM_FEEDBACK_MAX_AGE_S)
    odom = capture.live_stream(packet, "odometry", BASE_FEEDBACK_MAX_AGE_S)
    q = np.asarray(packet["arrays"].get("arm"), float)
    chassis = np.asarray(packet["arrays"].get("odometry"), float)
    if (
        first["boot_id"] != packet["meta"]["boot_id"]
        or q.shape != (6,)
        or not np.isfinite(q).all()
        or arm.get("unit") != "servo_degrees_from_CubeBot_bridge"
        or tuple(arm.get("names", ())) != tuple(first["after"]["joint_names"])
        or not first["after"]["arm_stamp"] < arm["source_timestamp_ns"]
        or not first["after"]["odom_stamp"] < odom["source_timestamp_ns"]
        or chassis.shape != (9,)
        or not np.isfinite(chassis).all()
        or not 0.98 <= np.linalg.norm(chassis[2:6]) <= 1.02
        or np.any(abs(chassis[6:]) > 1e-4)
    ):
        raise ValueError("Нет нового отсчёта измеренной руки и неподвижной базы той же загрузки ROS")
    if np.all(abs(q[:5] - LOOK_COMMAND[:5]) <= SLEW_DEGREES_PER_SECOND[:5] / 20):
        raise ValueError("Уход руки из позы обзора не измерен; два снимка подряд не доказывают возврат")
    if abs(q[5] - LOOK_COMMAND[5]) > SLEW_DEGREES_PER_SECOND[5] / 20:
        raise ValueError("Промежуточное измерение должно показывать открытый захват до смыкания")
    pose = {
        "odometry": chassis.tolist(),
        "odometry_frame": odom.get("frame_id"),
        "odometry_child": odom.get("child_frame"),
        "arm_degrees": q.tolist(),
        "joint_names": arm["names"],
        "arm_stamp": arm["source_timestamp_ns"],
        "odom_stamp": odom["source_timestamp_ns"],
    }
    # Compare only the chassis against the first pose here; the arm must have moved.
    capture.held_fixed({**first["after"], "arm_degrees": q.tolist()}, pose, first["margin_m"])
    return pose


def inspect_view(path, proof, packet, measured, confirmed):
    ref = proof["reference_frames"][3]
    margin = proof["measured_allowable_xy_error_m"]
    xy = np.asarray(measured, dtype=float) / 1000
    if not confirmed or xy.shape != (2,) or not np.isfinite(xy).all():
        raise ValueError("Подтвердите тот же целый кубик и введите независимо измеренные X/Y")
    if np.linalg.norm(xy - ref["independently_measured_base_xy_m"]) > margin:
        raise ValueError("Измеренный центр не соответствует контрольной точке №4")
    if (
        packet["boot_id"] != ref["boot_id"]
        or packet["camera_info"] != read(path / proof["camera_info"])
        or packet["rgb_stamp"] <= proof["reference_frames"][-1]["rgb_stamp"]
    ):
        raise ValueError("Ожидается новый кадр откалиброванной камеры из той же загрузки ROS")
    if len(ref["before"]["joint_names"]) != 6 or len(set(ref["before"]["joint_names"])) != 6:
        raise ValueError("В исходной калибровке не установлены имена шести сервоприводов")
    for pose in (packet["before"], packet["after"]):
        capture.held_fixed(ref["before"], pose, margin)
        distance, angle = look_distance(pose["arm_degrees"])
        if not close_to_look_state(pose["arm_degrees"]) or distance > 0.02 or angle > 5:
            raise ValueError("Измеренная поза руки или камеры вне допущенного окна")
    localizer, hull = capture.predictor()
    target = initial_target(path, 4, packet["rgb"], localizer)
    prediction = np.asarray(target["predicted_xy_m"])
    error = np.linalg.norm(prediction - xy)
    if hull.find_simplex(xy) < 0 or hull.find_simplex(prediction) < 0 or error > margin:
        raise ValueError("Измеренный центр или прогноз вышел за область показов/допуск губок")
    return {
        **{k: v for k, v in packet.items() if k not in ("rgb", "camera_info")},
        **target,
        "measured_xy_m": xy.tolist(),
        "localization_error_mm": error * 1000,
        "margin_m": margin,
        "identity_basis": "operator confirms same object; point-four reference template matched",
        "raw_rgb_sha256": hashlib.sha256(packet["rgb"].tobytes()).hexdigest(),
    }


def add(path, expected, measured=None, confirmed=False):
    """Persist each completed step so reloading the page cannot lose the first observation."""
    if capture.summary(path)["status"] != "positive":
        raise ValueError("Сначала завершите обычную калибровку по пяти точкам")
    with (path / ".passive-reobservation.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = current(path)
        if expected != state["stage"] or expected not in ("first", "away", "second"):
            raise ValueError("Этап проверки изменился; обновите страницу")
        directory = path / "passive-reobservation"
        directory.mkdir(exist_ok=True)
        verified = identity(path)
        binding = {k: verified[k] for k in ("object_sha256", "calibration_sha256", "vision_sha256")}
        if expected != "first" and binding != state["binding"]:
            raise ValueError("Изменилась привязка кубика, камеры или локализатора")
        proof = read(path / "localization-calibration.json")
        if capture.session_rows(path) != proof["reference_frames"]:
            raise ValueError("Исходные измерения точек отличаются от сохранённой калибровки")
        if expected != "first" and file_hash(directory / "first.png") != state["first"]["png_sha256"]:
            raise ValueError("Изменился исходный файл первого наблюдения")
        try:
            if expected == "away":
                client = capture.SensorClient(robot="rosmaster")
                try:
                    state["away"] = away_witness(state["first"], client.snapshot(("arm", "odometry")))
                finally:
                    client.close()
            else:
                packet = capture.acquire_snapshot(proof["measured_allowable_xy_error_m"])
                view = inspect_view(path, proof, packet, measured, confirmed)
                if expected == "second":
                    first, away = state["first"], state["away"]
                    if (
                        packet["before"]["arm_stamp"] <= away["arm_stamp"]
                        or packet["before"]["odom_stamp"] <= away["odom_stamp"]
                        or packet["rgb_stamp"] <= first["rgb_stamp"]
                        or view["raw_rgb_sha256"] == first["raw_rgb_sha256"]
                    ):
                        raise ValueError("После ухода нужен другой RGB с более поздней телеметрией")
                    capture.held_fixed(first["after"], packet["before"], view["margin_m"])
                    displacement = np.asarray(view["measured_xy_m"]) - first["measured_xy_m"]
                    if np.linalg.norm(displacement) > view["margin_m"]:
                        raise ValueError("Кубик сместился за допуск парной проверки одной позиции")
                    estimate = np.asarray(view["predicted_xy_m"]) - first["predicted_xy_m"]
                    state["difference"] = {
                        "measured_xy_mm": (1000 * displacement).tolist(),
                        "predicted_xy_mm": (1000 * estimate).tolist(),
                        "error_change_xy_mm": (1000 * (estimate - displacement)).tolist(),
                        "rgb_interval_s": (view["rgb_stamp"] - first["rgb_stamp"]) / 1e9,
                    }
                image = directory / (expected + ".tmp.png")
                if not cv2.imwrite(str(image), cv2.cvtColor(packet["rgb"], cv2.COLOR_RGB2BGR)):
                    raise OSError("Не удалось сохранить снимок")
                view["png_sha256"] = file_hash(image)
                os.replace(image, directory / (expected + ".png"))
                state[expected] = view
        except (ValueError, OSError, RuntimeError) as exc:
            with (directory / "refusals.jsonl").open("a") as out:
                out.write(json.dumps({"stage": expected, "reason": str(exc)}, ensure_ascii=False) + "\n")
            raise
        state.update(
            binding=binding, stage={"first": "away", "away": "second", "second": "completed"}[expected]
        )
        capture.json_write(directory / "result.json", state)
        return state
