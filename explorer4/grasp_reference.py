"""Link a newly recorded human development episode to its measured camera check."""

import fcntl
import json
import re
from pathlib import Path

import numpy as np

from . import catalog, collection
from .conditioned_grasp import file_hash
from .grasp_calibration import json_write, live_stream, open_session, summary
from .grasp_shadow import close_to_look_state, look_distance
from .paths import DATA
from .sensors import SensorClient

LINKS = DATA / "runs/grasp-calibration-development"


def reference_series(path):
    """Resume an unfinished placement; one successful episode closes that placement."""
    if summary(path)["status"] != "positive":
        raise ValueError("Нужна принятая статическая калибровка")
    LINKS.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (path / ".lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        bindings = sorted(
            (
                record
                for p in LINKS.glob("*.json")
                if (record := json.loads(p.read_text()))["session"] == path.name
            ),
            key=lambda r: r["placement"],
        )
        successful = 0
        with catalog.connect() as db:
            for binding in bindings:
                episode = db.execute(
                    "SELECT id FROM episodes WHERE session=? AND outcome='success' AND excluded=0 LIMIT 1",
                    (binding["series"],),
                ).fetchone()
                if episode is None:
                    return binding["series"]
                successful += 1
        if successful >= 3:
            raise ValueError(
                "Три расстановки записаны; следующая операция — офлайн-проверка на независимых записях"
            )
        # The existing split builder reserves this exact series purpose for development.
        record = collection.create_series(
            "rosmaster_pick_place",
            "rosmaster_pick_place",
            None,
            "cube, диагностика",
            instruction="pick up the cube",
        )
        binding = {
            "session": path.name,
            "series": record["id"],
            "layout": record["layout"],
            "placement": successful + 1,
            "calibration_sha256": file_hash(path / "localization-calibration.json"),
            "role": "validation",
            "training_eligible": False,
        }
        json_write(LINKS / (record["id"] + ".json"), binding)
        return record["id"]


def prepare_recording(series):
    if not isinstance(series, str) or not re.fullmatch(r"rosmaster_pick_place-s\d+", series):
        return None
    binding_path = LINKS / (series + ".json")
    if not binding_path.is_file():
        return None
    binding = json.loads(binding_path.read_text())
    return current_camera(binding)


def current_camera(binding):
    path = open_session(binding["session"])
    calibration = path / "localization-calibration.json"
    if file_hash(calibration) != binding["calibration_sha256"] or summary(path)["status"] != "positive":
        raise ValueError("Изменилась принятая калибровка; запись отложена")
    proof = json.loads(calibration.read_text())
    info = json.loads((path / proof["camera_info"]).read_text())
    client = SensorClient(robot="rosmaster")
    try:
        packet = client.snapshot(("rgb", "rgb_info"))
    finally:
        client.close()
    rgb = live_stream(packet, "rgb", 0.5)
    ci = live_stream(packet, "rgb_info", 0.5)
    if (
        not np.shape(packet["arrays"].get("rgb")) == (480, 640, 3)
        or any(ci.get(key) != value for key, value in info.items())
        or rgb.get("frame_id") != ci.get("frame_id")
        or packet["meta"]["boot_id"] != proof["reference_frames"][0]["boot_id"]
    ):
        raise ValueError("Камера, калибровка или загрузка робота изменилась после проверки")
    return {
        **binding,
        "device_id": proof["device_id"],
        "camera_info_sha256": proof["camera_calibration_sha256"],
        "boot_id": packet["meta"]["boot_id"],
        "frame_id": rgb["frame_id"],
        "topic": rgb["topic"],
        "camera_sample_source_ns": rgb["source_timestamp_ns"],
        "device_identity_source": proof["device_identity_source"],
    }


def verify_start(sample, binding):
    state = np.asarray(sample.get("arm_measured"), dtype=float)
    ages = np.asarray(sample.get("arm_measured_ages_s"), dtype=float)
    velocity = np.asarray(sample.get("base_measured"), dtype=float)
    rgb_stamp = (sample.get("camera") or {}).get("source_timestamp_ns")
    if (
        state.shape != (6,)
        or not np.isfinite(state).all()
        or ages.shape != (6,)
        or not np.all((ages >= 0) & (ages <= 0.6))
        or sample.get("arm_measured_valid") != [True] * 6
        or velocity.shape != (3,)
        or not np.all(np.abs(velocity) <= 0.01)
        or sample.get("base_measured_age_s") is None
        or not 0 <= sample["base_measured_age_s"] <= 0.5
        or not rgb_stamp
        or rgb_stamp < binding["camera_sample_source_ns"]
        or sample["rgb"].shape != (480, 640, 3)
    ):
        raise ValueError(
            "Перед первой записью нужны свежие RGB, энкодеры неподвижной базы и шесть измеренных углов"
        )
    distance, angle = look_distance(state)
    if not close_to_look_state(state) or distance > 0.02 or angle > 5:
        raise ValueError("Начало этого показа должно совпадать с проверенной позой обзора")
    return {**binding, "recording_start_rgb_source_ns": rgb_stamp, "recording_start_arm_deg": state.tolist()}


def evidence_path(episode, provenance):
    local = Path(episode) / "localization-calibration.json"
    identity = provenance.get("hardware", {}).get("rgb_camera_identity", {})
    if local.is_file() or not identity.get("session"):
        return local
    path = open_session(identity["session"]) / "localization-calibration.json"
    if file_hash(path) != identity.get("calibration_sha256"):
        raise ValueError("Calibration bound at capture changed")
    return path
