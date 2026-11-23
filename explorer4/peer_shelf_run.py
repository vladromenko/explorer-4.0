"""One supervised shelf approach using the existing Tank control and lidar localization."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import re
import time
import uuid

import numpy as np

from . import episodes, navigation, peer_dock_survey
from .fleet_map import FleetLocalizer, FleetMap, Grid, compose, inverse, scan_points, thin
from .paths import DATA, ROOT
from .peer_dock_config import MAX_AGE_S
from .peer_dock_real import map_from_base, operator_session, write_json
from .peer_dock_shelf import from_tf, goal_from_shelf, observe, tank_base_from_depth
from .sensors import SensorClient, decode_packet, stream_age
from .tank import CAMERA_MISSING, CAMERA_STALE

REFERENCE = ROOT / "docs/results/markerless-shelf-20261124"
EVIDENCE = DATA / "peer-dock/shelf"
STREAMS = ("rgb", "rgb_info", "depth", "depth_info", "tf_static", "scan", "arm", "odometry")
ROBOTS = ("tank", "rosmaster")


def read_still(robot):
    names = ("rgb", "depth", "scan") if robot == "tank" else ("rgb", "depth", "arm", "odometry")
    # Tank publishes to the isolated ROS domain once the Explorer operator takes over.
    for isolated in ((True, False) if robot == "tank" else (False,)):
        client = SensorClient(robot=robot, isolated=isolated)
        try:
            packet = client.snapshot(STREAMS)
        finally:
            client.close()
        if not packet["meta"].get("read_only") or packet["meta"].get("motion_commands_sent") != 0:
            raise ValueError(f"{robot}: нужен пассивный поток датчиков")
        if all(0 <= stream_age(packet, name) <= MAX_AGE_S for name in names):
            break
    else:
        raise ValueError(f"{robot}: нет свежего кадра. Камера Tank запускается при включении управления.")
    if robot == "tank" and isolated:
        client = SensorClient(robot=robot)
        try:
            packet["mount_source"] = client.clock_sample()["remote"]
        finally:
            client.close()
    if robot == "rosmaster":
        odom = packet["arrays"].get("odometry")
        if odom is None or odom.shape != (9,) or np.linalg.norm(odom[6:]) > .02:
            raise ValueError("ROSMASTER должен оставаться неподвижным")
    return packet


def tank_mount(packet):
    source = packet.get("mount_source")
    if source is None:
        return tank_base_from_depth(packet)
    active = packet["meta"]
    streams = active["streams"]
    factory = source["streams"]
    if (source.get("read_only") is not True or source.get("motion_commands_sent") != 0
            or any(not active.get(key) or active[key] != source.get(key)
                   for key in ("boot_id", "source_sha256"))):
        raise ValueError("Потоки Tank не подтвердили общий источник калибровки")
    camera_fields = ("frame_id", "width", "height", "k", "p", "r", "d", "distortion_model")
    if any(field not in streams[name] or streams[name][field] != factory.get(name, {}).get(field)
           for name in ("rgb_info", "depth_info") for field in camera_fields):
        raise ValueError("Калибровка активной камеры Tank отличается от заводского потока")
    depth, rgb = (streams[name]["frame_id"] for name in ("depth", "rgb"))
    native_tf, factory_tf = (s["tf_static"]["transforms"] for s in (streams, factory))
    if not np.allclose(from_tf(depth, rgb, native_tf), from_tf(depth, rgb, factory_tf), atol=1e-6):
        raise ValueError("Потоки Tank расходятся по взаимному положению камер")
    return from_tf("base_footprint", depth, factory_tf)


def current_pose(fleet):
    pose, _, frame = fleet.pose_frame("tank", MAX_AGE_S)
    nav = fleet.nav("tank", MAX_AGE_S)
    if pose is None or nav is None or nav[0] != "main" or fleet.scan("tank", MAX_AGE_S) is None:
        raise ValueError("Tank пока не локализован по свежему лидару")
    return pose, frame


def visible_shelf(donor, reference, calibration):
    arm = donor["arrays"].get("arm")
    original_arm = np.asarray(calibration["rosmaster_arm_deg"])
    if arm is None or arm.shape != (6,) or not np.isfinite(arm).all() or np.max(np.abs(arm - original_arm)) > 1.:
        raise ValueError("Положение камеры ROSMASTER изменилось. Нужна повторная привязка.")
    observed = observe(donor, reference["rosmaster"])
    width = -observed["witness_in_shelf_m"][0]
    if abs(width - calibration["width_m"]["rosmaster"]) > .010:
        raise ValueError("Кромка не совпадает с проверенной секцией стеллажа")
    return np.asarray(observed["depth_from_shelf"]), width


def calibrated_goal(tank, donor, reference, calibration):
    present = observe(tank, reference["tank"])
    tank_shelf = np.asarray(present["depth_from_shelf"])
    donor_shelf, donor_width = visible_shelf(donor, reference, calibration)
    tank_base = tank_mount(tank)
    base_from_donor = tank_base @ np.asarray(calibration["optical_from_donor"])
    tank_width = -present["witness_in_shelf_m"][0]
    if abs(tank_width - calibration["width_m"]["tank"]) > .010:
        raise ValueError("Кромка не совпадает с проверенной секцией стеллажа")
    local = goal_from_shelf(tank_base @ tank_shelf, tank_width)
    transferred = goal_from_shelf(base_from_donor @ donor_shelf, donor_width)
    position_error = math.dist(local[:2], transferred[:2])
    yaw_error = abs(navigation.wrap(local[2] - transferred[2]))
    if position_error > .015 or yaw_error > math.radians(3):
        raise ValueError("Наблюдения Tank и ROSMASTER больше не совпадают на этой расстановке")
    return transferred, position_error, yaw_error


def shelf_calibration():
    raw_reference = (REFERENCE / "shelf-reference.json").read_bytes()
    calibration = json.loads((EVIDENCE / "calibration.json").read_text())
    if hashlib.sha256(raw_reference).hexdigest() != calibration["reference_sha256"]:
        raise ValueError("Разметка кадра стеллажа изменилась после калибровки")
    return json.loads(raw_reference), calibration


def tank_health():
    from . import tank as tank_transport

    with tank_transport.client() as client:
        response = client.get("/health", timeout=1.5)
        response.raise_for_status()
        status = response.json()
    live_sources = status.get("software", {})
    if any(live_sources.get(k) != v for k, v in tank_transport.guard_sources().items()):
        raise ValueError("Tank не подтвердил версию бортовой защиты")
    return status


def probe():
    from scripts.peer_dock_shelf import replay_stopped_scan

    tank_health()
    reference, calibration = shelf_calibration()
    with ThreadPoolExecutor(2) as executor:
        tank, donor = executor.map(read_still, ROBOTS)
    goal, error, yaw_error = calibrated_goal(tank, donor, reference, calibration)
    replay = replay_stopped_scan(tank, goal, lateral_m=.10)
    if (replay["state"] != "arrived" or replay["minimum_scan_return_clearance_m"] < .25
            or replay["reverse_steps"]):
        raise ValueError("Свежий лидар не подтверждает маршрут к стеллажу")
    fleet = FleetMap()
    fleet.update("tank", tank)
    pose, frame = current_pose(fleet)
    if any(stream_age(p, "depth") > MAX_AGE_S for p in (tank, donor)):
        raise ValueError("Глубина устарела, повторите замер")
    relative = replay["goal"]
    xyz = map_from_base(pose) @ [*relative[:2], 0., 1.]
    ident = uuid.uuid4().hex
    receipt = {
        "id": ident, "frame": "tank_scan_local", "map_frame_id": frame,
        "pose": [*xyz[:2].tolist(), navigation.wrap(pose[2] + relative[2])],
        "tank_start_pose": list(pose), "source_robot": "rosmaster",
        "evidence": ident, "calibration_run": calibration["id"],
        "expires_monotonic_s": min(
            time.monotonic() + MAX_AGE_S - stream_age(p, "depth") for p in (tank, donor)
        ),
        "donor_local_disagreement_m": error, "heading_disagreement_rad": yaw_error,
        "packets": {k: hashlib.sha256(p["payload"]).hexdigest()
                    for k, p in zip(ROBOTS, (tank, donor), strict=True)},
        "shadow_replay": replay, "physical_trial": False,
    }
    folder = EVIDENCE / ident
    folder.mkdir(mode=0o700, parents=True, exist_ok=False)
    for k, p in zip(ROBOTS, (tank, donor), strict=True):
        (folder / f"{k}.npz").write_bytes(p["payload"])
    if (mount := tank.get("mount_source")) is not None:
        write_json(folder / "tank-mount.json", mount)
    write_json(folder / "result.json", receipt)
    return receipt, fleet


def resumable_shelf_run():
    last = next((item for item in episodes.load() if item.get("shelf_observation_id")), None)
    if (last and not last.get("resumed_episode") and last.get("outcome") == "cancelled"
            and last.get("message") in (CAMERA_MISSING, CAMERA_STALE)
            and last.get("localized_share", 0.) >= .95 and last.get("last_observed_pose")):
        return last
    return None


def shelf_anchor(run, calibration):
    ident = run.get("shelf_observation_id", "")
    if not re.fullmatch("[0-9a-f]{32}", ident):
        raise ValueError("В журнале нет сохранённой привязки стеллажа")
    directory = EVIDENCE / ident
    receipt = json.loads((directory / "result.json").read_text())
    if (receipt["id"] != ident or receipt["source_robot"] != "rosmaster"
            or receipt["calibration_run"] != calibration["id"] or receipt["pose"] != run["requested_pose"]
            or receipt["tank_start_pose"] != [0., 0., 0.]):
        raise ValueError("Привязка прерванного подъезда изменилась")
    packets = {}
    for robot in ROBOTS:
        raw = (directory / f"{robot}.npz").read_bytes()
        if hashlib.sha256(raw).hexdigest() != receipt["packets"][robot]:
            raise ValueError("Нарушена целостность исходного кадра стеллажа")
        packets[robot] = decode_packet(raw)
        if packets[robot]["meta"]["robot"] != robot:
            raise ValueError("Исходный кадр пришёл от другого робота")
    source = directory / "tank-mount.json"
    if source.is_file():
        packets["tank"]["mount_source"] = json.loads(source.read_text())
    return packets, receipt


def read_resume_scan(after=None):
    client = SensorClient(robot="tank", isolated=True)
    deadline = time.monotonic() + .35
    try:
        while time.monotonic() < deadline:
            packet = client.snapshot(("scan",))
            meta = packet["meta"]
            stamp = meta["streams"]["scan"]["source_timestamp_ns"]
            if (meta.get("read_only") is True and meta.get("motion_commands_sent") == 0
                    and stamp > (after or 0) and 0 <= stream_age(packet, "scan") <= MAX_AGE_S):
                return packet
            time.sleep(.025)
    finally:
        client.close()
    raise ValueError("Tank не подтвердил два свежих скана лидара")


def stopped_scan_pose(grid, anchor, current, expected):
    for key in ("boot_id", "source_sha256"):
        if not current["meta"].get(key) or anchor["meta"].get(key) != current["meta"][key]:
            raise ValueError("Поток лидара Tank изменился после первой попытки")
    if anchor["meta"]["streams"]["scan"]["frame_id"] != current["meta"]["streams"]["scan"]["frame_id"]:
        raise ValueError("Координаты лидара Tank изменились")
    scan = thin(scan_points("tank", current), .04, 360)
    if len(scan) < 70:
        raise ValueError("Слишком мало отражений от исходной расстановки")
    _, pose = grid.refine(scan, expected, rounds=((.15, .03, math.radians(16), math.radians(2)),
                                                   (.04, .01, math.radians(3), math.radians(.5))))
    overlap = grid.inliers(scan, pose)
    if overlap < .72 or not peer_dock_survey.close_pose(pose, expected, .04, math.radians(6)):
        raise ValueError("Tank сместился после остановки или исходная расстановка изменилась")
    return pose, overlap


def probe_resume(previous, *, supervised=False):
    from scripts.peer_dock_shelf import replay_stopped_scan

    state = tank_health()
    if (state.get("action") != [0., 0.] or state.get("armed") is not supervised
            or state.get("hardware_open") is not supervised):
        raise ValueError("Tank должен стоять. Продолжение доступно из готового пульта.")
    if supervised:
        callback = state.get("camera_timing", {}).get("callback_started_ns")
        if type(callback) is not int or not 0 <= state['monotonic_ns'] - callback < 500_000_000:
            raise ValueError("Дождитесь свежего кадра Tank в пульте")
    reference, calibration = shelf_calibration()
    anchors, original = shelf_anchor(previous, calibration)
    old_shelf, _ = visible_shelf(anchors["rosmaster"], reference, calibration)
    base_from_donor = tank_mount(anchors["tank"]) @ np.asarray(calibration["optical_from_donor"])
    grid = Grid()
    grid.add(scan_points("tank", anchors["tank"]), (0., 0., 0.))
    with ThreadPoolExecutor(2) as executor:
        donor_future = executor.submit(read_still, "rosmaster")
        first = read_resume_scan()
        scan = read_resume_scan(first["meta"]["streams"]["scan"]["source_timestamp_ns"])
        donor = donor_future.result()
    new_shelf, width = visible_shelf(donor, reference, calibration)
    if (np.linalg.norm(new_shelf[:3, 3] - old_shelf[:3, 3]) > .015
            or np.trace(old_shelf[:3, :3].T @ new_shelf[:3, :3]) < 1 + 2 * math.cos(math.radians(3))
            or donor["meta"]["boot_id"] != anchors["rosmaster"]["meta"]["boot_id"]):
        raise ValueError("ROSMASTER не подтвердил исходную секцию стеллажа")
    poses, overlaps = zip(*(stopped_scan_pose(grid, anchors["tank"], p, previous["last_observed_pose"])
                            for p in (first, scan)), strict=True)
    if not peer_dock_survey.close_pose(*poses, .025, math.radians(3)):
        raise ValueError("Два измерения позиции Tank расходятся")
    goal = goal_from_shelf(base_from_donor @ new_shelf, width)
    relative = compose(inverse(poses[1]), goal)
    replay = replay_stopped_scan(scan, relative, lateral_m=original["shadow_replay"]["lateral_offset_m"])
    if (replay["state"] != "arrived" or replay["minimum_scan_return_clearance_m"] < .25
            or replay["reverse_steps"] or not peer_dock_survey.close_pose(
                compose(poses[1], replay["goal"]), original["pose"], .015, math.radians(3))):
        raise ValueError("Свежий лидар не подтвердил безопасный путь к прежней цели")
    fleet = FleetMap()
    fleet.update("tank", scan)
    pose, frame = current_pose(fleet)
    expires = min(p["received_ns"] / 1e9 + MAX_AGE_S - stream_age(p, stream, p["received_ns"])
                  for p, stream in ((scan, "scan"), (donor, "depth")))
    if time.monotonic() >= expires:
        raise ValueError("Снимки устарели во время сверки стеллажа")
    ident = uuid.uuid4().hex
    receipt = {"id": ident, "map_frame_id": frame, "pose": replay["goal"], "tank_start_pose": list(pose),
               "source_robot": "rosmaster", "calibration_run": calibration["id"],
               "expires_monotonic_s": expires, "resumed_episode": previous["id"],
               "anchor_observation_id": original["id"], "tank_poses_in_anchor": poses,
               "scan_overlap": overlaps, "shadow_replay": replay, "physical_trial": False}
    if supervised:
        directory = EVIDENCE / ident
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        for name, packet in (("tank-first", first), ("tank", scan), ("rosmaster", donor)):
            (directory / f"{name}.npz").write_bytes(packet["payload"])
        write_json(directory / "result.json", receipt)
    return receipt, fleet


def handoff(control, session, owner, expected, receipt, fleet):
    from .drive import DriveTo

    reader = FleetLocalizer(interval=.15, fleet=fleet, sources={"tank": True}, persist=False)

    def measured(robot, _command):
        return fleet.pose(robot, MAX_AGE_S)[0]

    class SupervisedShelfDrive(DriveTo):
        camera_hold_started_ns = None
        first_fresh_frame = None

        def camera_recovery(self, hold, observation, now_ns):
            # Keep issuing neutral while the same observation fault is transient. A
            # lidar, lease or hardware fault still cancels immediately in TankSource.
            if hold in (CAMERA_MISSING, CAMERA_STALE):
                self.first_fresh_frame = None
                if self.camera_hold_started_ns is None:
                    self.camera_hold_started_ns = now_ns
                    self.episode.extra['camera_holds'] = self.episode.extra.get('camera_holds', 0) + 1
            elif hold or self.camera_hold_started_ns is None:
                return hold, False
            if now_ns - self.camera_hold_started_ns >= 800_000_000:
                return hold or CAMERA_STALE, False
            if hold:
                return hold, True
            frame = observation['images']['front']['sequence']
            if self.first_fresh_frame is None:
                self.first_fresh_frame = frame
            if frame <= self.first_fresh_frame:
                return 'Жду второй свежий кадр Tank', True
            self.camera_hold_started_ns = self.first_fresh_frame = None
            return None, False

        def finish(self, state, message):
            reader.stop()
            super().finish(state, message)

        def _command(self):
            try:
                _, frame = current_pose(fleet)
            except ValueError:
                frame = None
            if frame != receipt["map_frame_id"]:
                self.finish("lost_localization", "Остановка: потерян свежий лидар или положение Tank")
                return [0., 0.]
            scan = fleet.scan("tank", MAX_AGE_S)
            if (not navigation.usable_scan(scan)
                    or np.linalg.norm(scan, axis=1).min() < .235):
                self.finish("blocked", "Остановка: препятствие рядом с Tank")
                return [0., 0.]
            v, w = super()._command()
            if v < 0:
                self.finish("blocked", "Остановка: для этого опыта задний ход отключён")
                return [0., 0.]
            return [v, w]

    with control.lock:
        if expected != operator_session(control, session, owner):
            raise PermissionError("Сессия Tank изменилась после замера")
        pose, frame = current_pose(fleet)
        if (time.monotonic() >= receipt["expires_monotonic_s"]
                or frame != receipt["map_frame_id"]
                or not peer_dock_survey.close_pose(pose, receipt["tank_start_pose"], .015, .04)):
            raise ValueError("Замер устарел или Tank сместился")
        runner = SupervisedShelfDrive(
            "tank", receipt["pose"], text="к стеллажу", tol=.045, heading_tol=.15,
            v_max=.08, time_limit_s=20, record=True, fleet=fleet, pose_lookup=measured,
        )
        runner.episode.extra.update(shelf_observation_id=receipt["id"], source_robot="rosmaster",
                                    planned_stop=receipt["pose"])
        if "resumed_episode" in receipt:
            runner.episode.extra["resumed_episode"] = receipt["resumed_episode"]
        reader.start()
        control.goal = runner
        return runner
