"""One supervised shelf approach using the existing Tank control and lidar localization."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import time
import uuid

import numpy as np

from . import navigation, peer_dock_survey
from .paths import DATA, ROOT
from .peer_dock_config import MAX_AGE_S
from .peer_dock_real import map_from_base, operator_session, write_json
from .peer_dock_shelf import goal_from_shelf, observe, tank_base_from_depth
from .sensors import SensorClient, stream_age

REFERENCE = ROOT / "docs/results/markerless-shelf-20261124"
EVIDENCE = DATA / "peer-dock/shelf"
STREAMS = ("rgb", "rgb_info", "depth", "depth_info", "tf_static", "scan", "arm", "odometry")
ROBOTS = ("tank", "rosmaster")


def read_still(robot):
    client = SensorClient(robot=robot)
    try:
        packet = client.snapshot(STREAMS)
    finally:
        client.close()
    if not packet["meta"].get("read_only") or packet["meta"].get("motion_commands_sent") != 0:
        raise ValueError(f"{robot}: нужен пассивный поток датчиков")
    names = ("rgb", "depth", "scan") if robot == "tank" else ("rgb", "depth", "arm", "odometry")
    if any(not 0 <= stream_age(packet, name) <= MAX_AGE_S for name in names):
        raise ValueError(f"{robot}: устарели данные датчиков")
    if robot == "rosmaster":
        odom = packet["arrays"].get("odometry")
        if odom is None or odom.shape != (9,) or np.linalg.norm(odom[6:]) > .02:
            raise ValueError("ROSMASTER должен оставаться неподвижным")
    return packet


def current_pose(fleet):
    peer_dock_survey.require_real_map()
    pose, _, frame = fleet.pose_frame("tank", MAX_AGE_S)
    nav = fleet.nav("tank", MAX_AGE_S)
    if pose is None or nav is None or nav[0] != "main" or fleet.scan("tank", MAX_AGE_S) is None:
        raise ValueError("Tank пока не локализован по свежему лидару")
    return pose, frame


def calibrated_goal(tank, donor, reference, calibration):
    present = {name: observe(p, reference[name])
               for name, p in (("tank", tank), ("rosmaster", donor))}
    tank_shelf, donor_shelf = [np.asarray(present[name]["depth_from_shelf"]) for name in ROBOTS]
    tank_base = tank_base_from_depth(tank)
    arm = donor["arrays"].get("arm")
    original_arm = np.asarray(calibration["rosmaster_arm_deg"])
    if arm is None or arm.shape != (6,) or np.max(np.abs(arm - original_arm)) > 1.:
        raise ValueError("Положение камеры ROSMASTER изменилось. Нужна повторная привязка.")
    base_from_donor = tank_base @ np.asarray(calibration["optical_from_donor"])
    local = goal_from_shelf(tank_base @ tank_shelf, -present["tank"]["witness_in_shelf_m"][0])
    transferred = goal_from_shelf(base_from_donor @ donor_shelf, -present["rosmaster"]["witness_in_shelf_m"][0])
    position_error = math.dist(local[:2], transferred[:2])
    yaw_error = abs(navigation.wrap(local[2] - transferred[2]))
    if position_error > .015 or yaw_error > math.radians(3):
        raise ValueError("Наблюдения Tank и ROSMASTER больше не совпадают на этой расстановке")
    for name in ROBOTS:
        reference_width = calibration["width_m"][name]
        if abs(-present[name]["witness_in_shelf_m"][0] - reference_width) > .010:
            raise ValueError("Кромка не совпадает с проверенной секцией стеллажа")
    return transferred, position_error, yaw_error


def probe(fleet):
    from scripts.peer_dock_shelf import replay_stopped_scan

    before, initial_frame = current_pose(fleet)
    raw_reference = (REFERENCE / "shelf-reference.json").read_bytes()
    reference = json.loads(raw_reference)
    calibration = json.loads((EVIDENCE / "calibration.json").read_text())
    if hashlib.sha256(raw_reference).hexdigest() != calibration["reference_sha256"]:
        raise ValueError("Разметка кадра стеллажа изменилась после калибровки")
    with ThreadPoolExecutor(2) as executor:
        tank, donor = executor.map(read_still, ROBOTS)
    goal, error, yaw_error = calibrated_goal(tank, donor, reference, calibration)
    replay = replay_stopped_scan(tank, goal, lateral_m=.10)
    if replay["state"] != "arrived" or replay["minimum_scan_return_clearance_m"] < .25:
        raise ValueError("Свежий лидар не подтверждает маршрут к стеллажу")
    pose, frame = current_pose(fleet)
    if frame != initial_frame or not peer_dock_survey.close_pose(before, pose, .015, .04):
        raise ValueError("Tank сместился или карта изменилась во время замера")
    if any(stream_age(p, "depth") > MAX_AGE_S for p in (tank, donor)):
        raise ValueError("Глубина устарела, повторите замер")
    relative = replay["goal"]
    xyz = map_from_base(pose) @ [*relative[:2], 0., 1.]
    ident = uuid.uuid4().hex
    receipt = {
        "id": ident, "frame": "fleet_map", "map_frame_id": frame,
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
    write_json(folder / "result.json", receipt)
    return receipt


def handoff(control, session, owner, expected, receipt, fleet):
    from .drive import DriveTo

    class SupervisedShelfDrive(DriveTo):
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
            v_max=.08, time_limit_s=20, record=True,
        )
        runner.episode.extra.update(shelf_observation_id=receipt["id"], source_robot="rosmaster",
                                    planned_stop=receipt["pose"])
        control.goal = runner
