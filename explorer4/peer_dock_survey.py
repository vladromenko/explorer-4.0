"""Initialize a stationary donor's existing lidar tracker from an independently surveyed floor pose."""

import hashlib
import math
import time
import uuid

import numpy as np

from . import fleet_map
from . import peer_dock_real as field
from .peer_dock_config import MAX_AGE_S

STREAMS = ("scan", "scan_rear", "odometry")


def require_stopped(control):
    if control.owner is not None or not control.stop_event.is_set():
        raise ValueError(
            "Для измерения обе машины должны стоять. Нажмите STOP в пульте."
        )


def require_real_map():
    from . import swarm_sim

    if (
        swarm_sim.WORLD is not None
        or fleet_map.LOCALIZER.done.is_set()
        or not fleet_map.LOCALIZER.running()
    ):
        raise ValueError(
            "Нужна живая общая карта. В разделе «Рой» вернитесь из симуляции к настоящим роботам."
        )


def close_pose(left, right, metres, radians):
    return (
        math.dist(left[:2], right[:2]) <= metres
        and abs(fleet_map.wrap(left[2] - right[2])) <= radians
    )


def source_age(packet, name):
    pair = packet["meta"].get("clock_pair") or {}
    stream = packet["meta"]["streams"].get(name, {})
    stamp = stream.get("source_timestamp_ns")
    if (
        pair.get("use_sim_time") is not False
        or not pair.get("ros_time_ns")
        or type(stamp) is not int
        or stamp <= 0
        or stream.get("source_clock") != "rosmaster_ros_time"
    ):
        return math.inf
    age = (pair["ros_time_ns"] - stamp) / 1e9
    uncertainty = pair.get("uncertainty_ns")
    if age < 0 or type(uncertainty) is not int or uncertainty < 0:
        return math.inf
    transit = packet["request_elapsed_s"] + max(
        0.0, (time.monotonic_ns() - packet["received_ns"]) / 1e9
    )
    return max(field.stream_age(packet, name), age + uncertainty / 1e9 + transit)


def clock_epoch(packet):
    pair = packet["meta"].get("clock_pair") or {}
    if (
        type(pair.get("monotonic_ns")) is not int
        or type(pair.get("ros_time_ns")) is not int
    ):
        raise ValueError("Невозможно проверить эпоху часов ROSMASTER")
    return pair["ros_time_ns"] - pair["monotonic_ns"]


def checked_fit(fleet, points, hint):
    _, fit = fleet.grid.refine(points, hint)
    inliers = fleet.grid.inliers(points, fit)
    conflict = fleet.grid.consistency(points, fit)
    if (
        not close_pose(hint, fit, 0.035, math.radians(4))
        or inliers < 0.65
        or conflict > 0.25
        or not fleet._submap_fits("rosmaster", fit)
    ):
        raise ValueError(
            f"Лидар не подтверждает измерение на этой карте (совпадение {inliers:.0%}). "
            "Проверьте знаки, центр баз, направление и общие видимые стены"
        )
    return fit, float(inliers), float(conflict)


def check_scan(packet, *, stationary=True):
    streams = packet["meta"]["streams"]
    if (
        packet["meta"].get("robot") != "rosmaster"
        or packet["meta"].get("read_only") is not True
        or (
            packet["meta"].get("motion_commands_sent") != 0
            or not packet["meta"].get("boot_id")
        )
    ):
        raise ValueError("Нужен пакет настоящего ROSMASTER из канала чтения")
    if any(source_age(packet, k) > MAX_AGE_S for k in STREAMS):
        raise ValueError("Нужны свежие передний и задний лидары и одометрия ROSMASTER")
    if [streams[k].get("frame_id") for k in ("scan", "scan_rear")] != [
        "laser0_frame",
        "laser1_frame",
    ] or [
        streams["odometry"].get("frame_id"),
        streams["odometry"].get("child_frame"),
    ] not in (
        ["odom_raw", "base_footprint"],
        ["odom", "base_footprint"],
        ["odom", "base_link"],
    ):
        raise ValueError(
            "Кадры лидаров и одометрии не соответствуют измеренным креплениям ROSMASTER"
        )
    stamps = [streams[k].get("source_timestamp_ns") for k in STREAMS]
    odom = fleet_map.odom_pose(packet)
    if any(not isinstance(s, int) or s <= 0 for s in stamps) or odom is None:
        raise ValueError("Неизвестен источник замеров или поза по энкодерам")
    vx, vy, wz = packet["arrays"]["odometry"][6:]
    if stationary and (math.hypot(vx, vy) >= 0.025 or abs(wz) >= 0.05):
        raise ValueError("Энкодеры показывают движение ROSMASTER")
    points = fleet_map.thin(fleet_map.scan_points("rosmaster", packet))
    if len(points) < 40:
        raise ValueError("Недостаточно пригодных точек лидара ROSMASTER")
    return stamps, odom, points


def anchor_donor(control, fleet, forward_m, left_m, heading_deg, confirmed):
    if not confirmed or any(
        v is None or not math.isfinite(v) for v in (forward_m, left_m, heading_deg)
    ):
        raise ValueError(
            "Подтвердите независимый замер двух неподвижных баз и введите три значения"
        )
    from .peer_dock_localizer import PhysicalFleetMap

    if not isinstance(fleet, PhysicalFleetMap):
        raise TypeError(
            "Откройте страницу в основном физическом пульте с проверкой независимых сканов"
        )
    relative = [forward_m, left_m, math.radians(heading_deg)]
    with control.lock:
        require_stopped(control)
        generation = control.generation
    observations, payloads = [], []
    client = field.SensorClient(robot="rosmaster")
    try:
        for i in range(2):
            if i:
                time.sleep(0.24)
            require_stopped(control)
            require_real_map()
            packet = client.snapshot(only=STREAMS)
            stamps, odom, points = check_scan(packet)
            with control.lock, fleet.lock:
                require_stopped(control)
                require_real_map()
                if control.generation != generation:
                    raise ValueError(
                        "Состояние пульта изменилось между измерениями. Повторите при STOP"
                    )
                frame = fleet.frame_id
                grid_hash = hashlib.sha256(
                    fleet.grid.hits.tobytes() + fleet.grid.free.tobytes()
                ).hexdigest()
                tank = fleet.track.get("tank", {})
                donor = fleet.track.get("rosmaster", {})
                if (
                    fleet.grid.empty()
                    or tank.get("pose") is None
                    or tank.get("state") not in ("tracking", "mapping")
                    or not 0 <= time.time() - tank["at"] <= MAX_AGE_S
                ):
                    raise ValueError(
                        "Tank должен быть локализован на живой карте комнаты"
                    )
                if (
                    donor.get("state") in ("tracking", "mapping")
                    and time.time() - donor["at"] <= MAX_AGE_S
                ):
                    raise ValueError(
                        "ROSMASTER уже локализован. Переходите к обычному снимку двух камер"
                    )
                hint = fleet_map.compose(tank["pose"], relative)
                fit, inliers, conflict = checked_fit(fleet, points, hint)
                epoch = clock_epoch(packet)
                odom_meta = packet["meta"]["streams"]["odometry"]
                frames = [odom_meta["frame_id"], odom_meta["child_frame"]]
                if observations:
                    previous = observations[0]
                    if (
                        frame != previous["map_frame_id"]
                        or grid_hash != previous["map_grid_sha256"]
                        or packet["meta"]["boot_id"] != previous["boot_id"]
                        or frames != previous["odom_frames"]
                        or abs(epoch - previous["clock_epoch_ns"]) > 50_000_000
                        or any(b <= a for a, b in zip(previous["source_ns"], stamps))
                        or not close_pose(previous["odom"], odom, 0.015, 0.025)
                        or not close_pose(
                            previous["tank_pose"], tank["pose"], 0.025, 0.04
                        )
                        or not close_pose(
                            previous["lidar_fit"], fit, 0.035, math.radians(4)
                        )
                    ):
                        raise ValueError(
                            "Нужны два новых согласованных скана неподвижных машин в одной карте"
                        )
                if any(source_age(packet, k) > MAX_AGE_S for k in STREAMS):
                    raise ValueError("Лидарный замер устарел до проверки")
                payloads.append(packet["payload"])
                observations.append(
                    {
                        "map_frame_id": frame,
                        "map_grid_sha256": grid_hash,
                        "packet_sha256": hashlib.sha256(packet["payload"]).hexdigest(),
                        "source_ns": stamps,
                        "source_ages_s": [source_age(packet, k) for k in STREAMS],
                        "boot_id": packet["meta"]["boot_id"],
                        "clock_epoch_ns": epoch,
                        "odom_frames": frames,
                        "odom": list(odom),
                        "tank_pose": list(tank["pose"]),
                        "survey_pose": list(hint),
                        "lidar_fit": list(fit),
                        "inlier_fraction": float(inliers),
                        "map_conflict": float(conflict),
                    }
                )
                if i:
                    ident = uuid.uuid4().hex
                    evidence = {
                        "id": ident,
                        "created": time.time(),
                        "relative_to_tank_m_deg": [forward_m, left_m, heading_deg],
                        "observations": observations,
                        "motor_commands_sent": 0,
                        "status": "awaiting_regular_lidar_tracking",
                    }
                    folder = field.RUNS / "surveys"
                    folder.mkdir(parents=True, exist_ok=True)
                    archive = folder / (ident + ".npz")
                    np.savez_compressed(
                        archive,
                        hits=fleet.grid.hits,
                        free=fleet.grid.free,
                        cell_m=fleet_map.RES,
                        first_packet=np.frombuffer(payloads[0], dtype="uint8"),
                        second_packet=np.frombuffer(payloads[1], dtype="uint8"),
                    )
                    evidence["archive_sha256"] = hashlib.sha256(
                        archive.read_bytes()
                    ).hexdigest()
                    evidence["archive"] = (
                        "/api/peer-dock/survey/" + ident + "/inputs.npz"
                    )
                    if any(source_age(packet, k) > MAX_AGE_S for k in STREAMS):
                        archive.unlink()
                        raise ValueError(
                            "Замер устарел во время сохранения. Повторите при STOP"
                        )
                    field.write_json(folder / (ident + ".json"), evidence)
                    # Keep the hint outside pose/odom so ordinary map clients cannot publish it.
                    reference = {
                        **observations[-1],
                        "id": ident,
                        "status": "pending",
                        "expires_monotonic": time.monotonic() + 3.0,
                    }
                    fleet._set(
                        "rosmaster",
                        pose=None,
                        odom=None,
                        state="survey_prior",
                        quality=None,
                        scan=None,
                        floor_survey=reference,
                        message="Ожидаем новый независимый пакет лидаров после замера",
                    )
                    return evidence
    finally:
        client.close()
