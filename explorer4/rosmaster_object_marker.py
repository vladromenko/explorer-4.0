"""One operator-requested ID measurement in the mobile robot's own RGB image."""

import fcntl
import hashlib
import json
import math
import time
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import httpx
import numpy as np

from .paths import DATA
from .peer_dock_survey import clock_epoch, source_age
from .sensors import SensorClient
from .so101_geometry import MARKERS, configuration

PUBLIC = DATA / "simlab/reports/rosmaster-object-marker-v1"
MAX_AGE_S = 0.75
STATES = {
    "observed": "Искомый ID виден в одном месте",
    "missing": "Искомый ID в кадре не найден",
    "duplicate": "В кадре несколько меток с этим ID",
    "replayed": "Повторный кадр или съёмка до начала проверки",
    "stale": "Кадр устарел",
    "unverified": "Источник камеры или часы не подтверждены",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def registered_card():
    settings = configuration()
    card = {
        "instance_id": settings.get("instance_id"),
        "marker_id": settings.get("marker_id"),
        "marker_dictionary": settings.get("marker_dictionary", "DICT_4X4_50"),
    }
    if (
        settings.get("enabled") is not True
        or not card["instance_id"]
        or card["marker_dictionary"] not in MARKERS
        or type(card["marker_id"]) is not int
        or not 0 <= card["marker_id"] < 50
    ):
        raise ValueError("В карточке предмета не зарегистрирована действующая метка")
    return card


def clock_checkpoint():
    for isolated in (False, True):
        client = SensorClient(robot="rosmaster", isolated=isolated)
        try:
            return client.clock_sample()
        except httpx.HTTPError:
            if isolated:
                raise
        finally:
            client.close()


def checked_clock(pair):
    return (
        pair.get("use_sim_time") is False
        and all(
            type(pair.get(key)) is int and pair[key] > 0
            for key in ("monotonic_ns", "ros_time_ns")
        )
        and type(pair.get("uncertainty_ns")) is int
        and 0 <= pair["uncertainty_ns"] < 50_000_000
    )


def check_source(packet, checkpoint):
    meta = packet["meta"]
    rgb = packet["arrays"].get("rgb")
    camera = meta.get("streams", {}).get("rgb", {})
    remote = checkpoint["remote"]
    pairs = [item.get("clock_pair", {}) for item in (remote, meta)]
    if (
        any(
            item.get("robot") != "rosmaster"
            or item.get("read_only") is not True
            or item.get("motion_commands_sent") != 0
            for item in (remote, meta)
        )
        or not remote.get("boot_id")
        or remote["boot_id"] != meta.get("boot_id")
        or not all(checked_clock(pair) for pair in pairs)
        or abs(clock_epoch(packet) - clock_epoch({"meta": remote})) > 50_000_000
        or not 0 <= checkpoint["after_ns"] - checkpoint["before_ns"] <= MAX_AGE_S * 1e9
        or rgb is None
        or rgb.dtype != np.uint8
        or rgb.shape != (camera.get("height"), camera.get("width"), 3)
        or camera.get("frame_id") != "camera_color_optical_frame"
        or camera.get("topic") != "/camera/color/image_raw"
        or camera.get("encoding") not in ("rgb8", "bgr8")
        or camera.get("source_clock") != "rosmaster_ros_time"
        or type(camera.get("source_timestamp_ns")) is not int
        or camera["source_timestamp_ns"] <= 0
        or not isinstance(camera.get("age_s"), (int, float))
        or not math.isfinite(camera["age_s"])
        or camera["age_s"] < 0
    ):
        return "unverified"
    if (
        packet["received_ns"] <= checkpoint["after_ns"]
        or camera["source_timestamp_ns"]
        <= pairs[0]["ros_time_ns"] + pairs[0]["uncertainty_ns"]
    ):
        return "replayed"
    age = source_age(packet, "rgb")
    if not math.isfinite(age):
        return "unverified"
    if age > MAX_AGE_S:
        return "stale"
    return "fresh"


def measure(packet, checkpoint, card, directory=PUBLIC):
    """Commit a receipt and the decoded pixels together; one observation per source exposure."""
    directory.mkdir(parents=True, exist_ok=True)
    meta = packet["meta"]
    stream = meta.get("streams", {}).get("rgb", {})
    stamp = stream.get("source_timestamp_ns")
    status = check_source(packet, checkpoint)
    ident = (
        digest(f"{meta.get('boot_id')}:{stamp}".encode())
        if status == "fresh"
        else uuid.uuid4().hex
    )
    with (
        (directory / ".capture.lock").open("a") as lock,
        TemporaryDirectory(dir=directory) as staging,
    ):
        fcntl.flock(lock, fcntl.LOCK_EX)
        if status == "fresh" and (directory / ident / "result.json").is_file():
            status = "replayed"
            ident = uuid.uuid4().hex
        report = {
            "schema": "rosmaster_object_marker_v1",
            "id": ident,
            "recorded_unix_ns": time.time_ns(),
            "measurement": "marker_id_in_rosmaster_rgb",
            "card": dict(card),
            "boot_id": meta.get("boot_id"),
            "card_identity_sha256": digest(
                json.dumps(card, sort_keys=True, separators=(",", ":")).encode()
            ),
            "camera": {
                key: stream.get(key)
                for key in (
                    "topic",
                    "frame_id",
                    "source_clock",
                    "source_timestamp_ns",
                    "sequence",
                    "width",
                    "height",
                    "encoding",
                    "age_s",
                )
            },
            "checkpoint": {
                "boot_id": checkpoint["remote"].get("boot_id"),
                "clock_pair": checkpoint["remote"].get("clock_pair"),
                "homebrain_before_ns": checkpoint["before_ns"],
                "homebrain_after_ns": checkpoint["after_ns"],
            },
            "packet_clock_pair": meta.get("clock_pair"),
            "packet_sha256": digest(packet["payload"]),
            "packet_received_homebrain_ns": packet["received_ns"],
            "request_elapsed_s": packet["request_elapsed_s"],
            "bridge_source_sha256": meta.get("source_sha256"),
            "opencv_version": cv2.__version__,
            "motion_commands_sent": 0,
        }
        out = Path(staging) / ident
        out.mkdir()
        if status == "fresh":
            rgb = packet["arrays"]["rgb"]
            dictionary = cv2.aruco.getPredefinedDictionary(
                getattr(cv2.aruco, card["marker_dictionary"])
            )
            corners, ids, _ = cv2.aruco.ArucoDetector(dictionary).detectMarkers(
                cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            )
            markers = (
                []
                if ids is None
                else [
                    {"id": int(value), "corners_px": quad.reshape(4, 2).tolist()}
                    for value, quad in zip(ids.ravel(), corners, strict=True)
                ]
            )
            count = sum(marker["id"] == card["marker_id"] for marker in markers)
            status = (
                "missing" if count == 0 else "observed" if count == 1 else "duplicate"
            )
            ok, png = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            if not ok:
                raise ValueError("Не удалось сохранить RGB")
            image = png.tobytes()
            (out / "rgb.png").write_bytes(image)
            report.update(
                markers=markers,
                target_count=count,
                rgb_sha256=digest(rgb.tobytes()),
                png_sha256=digest(image),
                source_age_limit_s=MAX_AGE_S,
            )
        report["status"] = status
        (out / "result.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        )
        out.rename(directory / ident)
    return report
