"""Physical UI integration for locally confirming an independently measured donor pose."""

import hashlib
import math
import threading
import time

from . import fleet_map
from . import peer_dock_survey as survey
from .peer_dock_config import MAX_AGE_S


class PhysicalFleetMap(fleet_map.FleetMap):
    """Run the original mapper, with a provenance gate only for operator-surveyed ROSMASTER poses."""

    def __init__(self):
        super().__init__()
        # Keep update, provenance and all published poses atomic, including the parent update.
        self.lock = threading.RLock()

    def relative(self, a, b):
        with self.lock:
            if any(self.pose_frame(robot, MAX_AGE_S)[0] is None for robot in (a, b)):
                return None
            return super().relative(a, b)

    def invalidate(self, message):
        track = self.track["rosmaster"]
        reference = track["floor_survey"]
        reference["status"] = "rejected"
        return self._set(
            "rosmaster",
            pose=None,
            scan=None,
            odom=None,
            quality=None,
            state="no_scan",
            candidate=None,
            global_at=time.time(),
            rejected_survey=reference["id"],
            message=message,
        )

    def update(self, robot, packet, odom=None):
        if robot != "rosmaster":
            return super().update(robot, packet, odom)
        with self.lock:
            track = self.track.get(robot, {})
            ref = track.get("floor_survey")
            if ref is None:
                return super().update(robot, packet, odom)
            pending = ref["status"] == "pending"
            if ref["status"] == "rejected":
                # Discarded survey geometry can never seed this search. Keep source watermarks
                # until the ordinary independent global localizer finds a pose from new data.
                try:
                    stamps, encoders, _ = survey.check_scan(packet, stationary=False)
                    epoch = survey.clock_epoch(packet)
                except (KeyError, TypeError, ValueError):
                    return {k: v for k, v in track.items() if k not in fleet_map.HIDDEN}
                boot = packet["meta"]["boot_id"]
                if boot == ref["boot_id"] and any(
                    new <= old for new, old in zip(stamps, ref["source_ns"])
                ):
                    return {k: v for k, v in track.items() if k not in fleet_map.HIDDEN}
                if (
                    boot != ref["boot_id"]
                    or abs(epoch - ref["clock_epoch_ns"]) > 50_000_000
                ):
                    track.update(
                        candidate=None, global_at=time.time(), pose=None, odom=None
                    )
                ref.update(boot_id=boot, clock_epoch_ns=epoch, source_ns=stamps)
                super().update(robot, packet, encoders)
                if track.get("state") in ("tracking", "mapping"):
                    track.pop("floor_survey", None)
                return {k: v for k, v in track.items() if k not in fleet_map.HIDDEN}
            if pending and time.monotonic() > ref["expires_monotonic"]:
                return self.invalidate(
                    "Не получен независимый скан вовремя. Повторите привязку при STOP"
                )
            try:
                if (
                    self.frame_id != ref["map_frame_id"]
                    or packet["meta"].get("boot_id") != ref["boot_id"]
                    or abs(survey.clock_epoch(packet) - ref["clock_epoch_ns"])
                    > 50_000_000
                ):
                    raise ValueError(
                        "Изменилась карта, загрузка или эпоха часов ROSMASTER. Нужна новая локализация"
                    )
                stamps, encoders, points = survey.check_scan(packet, stationary=pending)
                info = packet["meta"]["streams"]["odometry"]
                if [info["frame_id"], info["child_frame"]] != ref["odom_frames"]:
                    raise ValueError(
                        "Изменилась система одометрии. Нужна новая локализация"
                    )
                if any(new <= old for new, old in zip(stamps, ref["source_ns"])):
                    # The native transport may repeat the last scan. Never extend a pose's time on it.
                    return {k: v for k, v in track.items() if k not in fleet_map.HIDDEN}
                if pending:
                    tank = self.pose_frame("tank", MAX_AGE_S)[0]
                    if (
                        tank is None
                        or not survey.close_pose(ref["tank_pose"], tank, 0.025, 0.04)
                        or not survey.close_pose(ref["odom"], encoders, 0.015, 0.025)
                        or hashlib.sha256(
                            self.grid.hits.tobytes() + self.grid.free.tobytes()
                        ).hexdigest()
                        != ref["map_grid_sha256"]
                    ):
                        raise ValueError("Опора или карта изменились после измерения")
                    fit, inliers, conflict = survey.checked_fit(
                        self, points, ref["survey_pose"]
                    )
                    if not survey.close_pose(
                        fit, ref["lidar_fit"], 0.035, math.radians(4)
                    ):
                        raise ValueError(
                            "Новый скан противоречит измеренной исходной позе"
                        )
                    age = max(survey.source_age(packet, k) for k in survey.STREAMS)
                    if not 0 <= age <= MAX_AGE_S:
                        raise ValueError("Независимый скан устарел до подтверждения")
                    proof = {
                        "id": ref["id"],
                        "method": "independent floor survey + local lidar verification",
                        "global_uniqueness_established": False,
                        "boot_id": ref["boot_id"],
                        "clock_epoch_ns": survey.clock_epoch(packet),
                        "source_ns": stamps,
                        "survey_last_source_ns": ref["source_ns"],
                        "source_age_s": age,
                        "odom": list(encoders),
                        "map_frame_id": self.frame_id,
                        "lidar_fit": list(fit),
                        "map_conflict": conflict,
                        "inlier_fraction": inliers,
                        "packet_sha256": hashlib.sha256(packet["payload"]).hexdigest(),
                    }
                    folder = survey.field.RUNS / "surveys"
                    (folder / (ref["id"] + "-confirmation.npz")).write_bytes(
                        packet["payload"]
                    )
                    report = folder / (ref["id"] + "-confirmation.json")
                    survey.field.write_json(report, proof)
                    ref.update(
                        status="confirmed",
                        confirmation_sha256=hashlib.sha256(
                            report.read_bytes()
                        ).hexdigest(),
                    )
                    self._set(
                        robot,
                        pose=fit,
                        scan=points,
                        odom=encoders,
                        state="tracking",
                        quality=inliers,
                        message="Положение по разметке Tank подтверждено локальным совпадением новых лидарных сканов",
                    )
                else:
                    super().update(robot, packet, encoders)
                age = max(survey.source_age(packet, k) for k in survey.STREAMS)
                if not 0 <= age <= MAX_AGE_S:
                    raise ValueError("Скан устарел до публикации позиции")
                ref["source_ns"] = stamps
                track["at"] = time.time() - age
                return {k: v for k, v in track.items() if k not in fleet_map.HIDDEN}
            except (KeyError, TypeError, ValueError) as exc:
                return self.invalidate(str(exc))
