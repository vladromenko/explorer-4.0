"""Evidence for one physical terminal grasp. Servo readback measures pose; a visible scale measures lift."""

import itertools
import json
import math

import av
import numpy as np

from .conditioned_grasp import file_hash
from .grasp_measured import TRIAL_TICKS
from .paths import ROOT

VERSION = "measured-terminal-window-v1"
GAP_NS = 250_000_000  # same control feedback discontinuity that stops LiveGrasp
MIN_NS = 1_000_000_000


def footage(path):
    """Actual presentation times, including variable-frame-rate or phone video."""
    with av.open(
        str(path), format="mov", options={"protocol_whitelist": "file,pipe"}
    ) as stream:
        video = stream.streams.video
        if len(video) != 1:
            raise ValueError("Нужна запись с одним видеопотоком")
        times = []
        for frame in stream.decode(video[0]):
            if frame.pts is None:
                raise ValueError("В кадре отсутствует время экспозиции видео")
            timestamp = float(frame.pts * frame.time_base)
            if len(times) >= 18_000 or (times and timestamp - times[0] > 300):
                raise ValueError(
                    "Нужен фрагмент терминального наблюдения длительностью до пяти минут"
                )
            times.append(timestamp)
    if (
        len(times) < 2
        or not all(math.isfinite(t) for t in times)
        or any(b <= a for a, b in itertools.pairwise(times))
    ):
        raise ValueError("Нет возрастающих меток времени видеокадров")
    return np.asarray(times) - times[0]


def window(root, record):
    """Verify a complete sequence and find the last contiguous second of measured carry before STOP."""
    raw = json.loads((root / "provenance.json").read_text())
    hw = raw["hardware"]
    if not (
        record["episodes"] == [root.name]
        and record.get("capture_protocol") == VERSION
        and record.get("sequence_completed")
        and record.get("stop_acknowledged_by_agent")
        and not record.get("emergency")
        and not record.get("recording_error")
        and record["frames"] == TRIAL_TICKS
        and raw.get("domain") == "real"
        and raw.get("synthetic") is False
        and raw.get("category") == "rollout"
        and raw.get("command_source") == "policy"
        and hw["trial_plan"]["id"] == record["plan_id"]
        and hw["trial_plan"]["kind"] == "conditioned_grasp"
    ):
        raise ValueError(
            "Нет полной записи штатной последовательности с подтверждённым STOP"
        )
    rows = [json.loads(x) for x in (root / "research.jsonl").read_text().splitlines()]
    if len(rows) != TRIAL_TICKS or any(
        r.get("frame_index") != i
        or r.get("episode_id") != root.name
        or r.get("trial_id") != hw["trial_id"]
        or r.get("command_source") != "policy"
        or (r.get("decision") or {}).get("command_tick") != i + 1
        for i, r in enumerate(rows)
    ):
        raise ValueError("Нет 360 связанных наблюдений и команд этой пробы")
    videos = sorted((root / "videos/observation.images.front").glob("*/*.mp4"))
    if len(videos) != 1 or len(footage(videos[0])) != len(rows):
        raise ValueError("Видео не подтверждает все кадры терминальной пробы")
    last_still = root / "grasp-terminal.png"
    if file_hash(last_still) != hw["terminal_still_sha256"]:
        raise ValueError("Изменился конечный снимок перед STOP")
    config = json.loads((ROOT / "configs/sim-alignment.json").read_text())[
        "rosmaster_floor_pick"
    ]
    carry = np.asarray(config["carry_pose"])
    samples = []
    for i, row in enumerate(rows):
        s = row["grasp_response"]
        now, camera = s["agent_ns"], s["camera_ns"]
        if i < len(rows) - 1:
            following = rows[i + 1]
            if (
                s["agent_ns"] != following["agent_monotonic_ns"]
                or s["sequence"] != following["camera"]["sequence"]
                or s["camera_ns"] != following["camera"]["agent_receive_timestamp_ns"]
            ):
                raise ValueError(
                    "Терминальная телеметрия не совпадает с метками следующего сохранённого кадра"
                )
        state = np.asarray(row["measured_response"], dtype=float)
        ages = np.asarray(row["measured_response_age_s"], dtype=float)
        valid = (
            type(now) is int
            and type(camera) is int
            and 0 <= now - camera <= 500_000_000
            and len(s["valid"]) == 6
            and all(v is True for v in s["valid"])
            and state.shape == (6,)
            and ages.shape == (6,)
            and np.isfinite(state).all()
            and np.all((ages >= 0) & (ages <= 0.6))
            and np.all(np.abs(state[:5] - carry) < config["carry_tolerance_deg"])
        )
        if samples and not (
            0 < now - samples[-1][1] <= GAP_NS
            and 0 <= camera - samples[-1][2] <= GAP_NS
            and (
                s["sequence"] > samples[-1][3]
                or (s["sequence"] == samples[-1][3] and camera == samples[-1][2])
            )
        ):
            samples.clear()
        if valid:
            # Each command response is observed at the next video frame; the last response is the saved still.
            samples.append(
                (
                    i + 1,
                    now,
                    camera,
                    s["sequence"],
                    now - np.rint(ages[:5] * 1e9).astype(np.int64),
                )
            )
        else:
            samples.clear()
    if not samples or samples[-1][0] != TRIAL_TICKS:
        raise ValueError(
            "В конечном отсчёте перед STOP нет свежей измеренной позы переноса"
        )
    last = samples[-1]
    if last[1] - last[2] > 50_000_000:
        raise ValueError(
            "Последний визуальный отсчёт отстаёт от терминального отсчёта руки больше чем на один такт 20 Гц"
        )
    starts = [
        s
        for s in samples
        if min(last[1] - s[1], last[2] - s[2], np.min(last[4] - s[4])) >= MIN_NS
        and last[0] - s[0] >= 19
    ]
    if not starts:
        raise ValueError(
            "В конце записи нет непрерывной секунды в измеренной позе переноса"
        )
    first = starts[-1]
    mapping, stop = hw["clock_mapping"], hw["terminal_stop"]
    offset, rtt = mapping["offset_ns"], mapping["rtt_ns"]
    dispatch, response = stop["request_home_ns"], stop["response_home_ns"]
    mapped = last[2] + offset
    # /stop acknowledges disarming; it does not measure when the physical motors stopped.
    # Include half the round-trip clock error in the upper elapsed-time bounds.
    if (
        not all(type(t) is int for t in (offset, rtt, dispatch, response))
        or rtt < 0
        or response < dispatch
        or dispatch < mapped - rtt // 2
        or dispatch - mapped + rtt // 2 > 50_000_000
        or response - mapped + rtt // 2 > GAP_NS
    ):
        raise ValueError(
            "Нет синхронизации конечного кадра с запросом STOP в пределах одного такта камеры"
        )
    return {
        "version": VERSION,
        "episode": root.name,
        "first_frame": first[0],
        "last_video_frame": TRIAL_TICKS - 1,
        "terminal_sample": last[0],
        "first_agent_ns": first[1],
        "last_agent_ns": last[1],
        "first_camera_ns": first[2],
        "last_camera_ns": last[2],
        "duration_s": (last[2] - first[2]) / 1e9,
        "camera_to_stop_request_upper_s": max(0, dispatch - mapped + rtt // 2) / 1e9,
        "camera_to_stop_response_upper_s": max(0, response - mapped + rtt // 2) / 1e9,
        "native_carry_s": (last[1] - first[1]) / 1e9,
        "terminal_camera_lag_s": (last[1] - last[2]) / 1e9,
        "min_joint_readback_span_s": float(np.min(last[4] - first[4]) / 1e9),
        "carry_pose_deg": carry.tolist(),
        "carry_tolerance_deg": config["carry_tolerance_deg"],
        "video_sha256": file_hash(videos[0]),
        "still_sha256": hw["terminal_still_sha256"],
        "sidecar_sha256": file_hash(root / "research.jsonl"),
    }


def bind_height(window, source, stop_s, clip, height_mm, confirmed):
    if (
        confirmed is not True
        or isinstance(height_mm, bool)
        or not isinstance(height_mm, (int, float))
        or not math.isfinite(height_mm)
        or height_mm < 0
    ):
        raise ValueError(
            "Подтвердите видимую шкалу, кубик и минимальную высоту за всё финальное окно"
        )
    # Conservative displacement bound for the registered cube: twice the full arm reach plus the cube
    # diagonal. It can reject impossible entries but never estimates the measured cube height.
    from .sim.vendor_rosmaster.arm_model import CHAIN, ArmModel

    reach = sum(np.linalg.norm(xyz) for xyz, _, _ in CHAIN) + ArmModel().tcp_offset
    if height_mm > (2 * reach + math.sqrt(3) * 0.032) * 1000:
        raise ValueError(
            "Указанный отрыв превышает возможный размах неподвижной руки; проверьте единицы"
        )
    if source == "wrist":
        return {
            "source": "wrist",
            "video_sha256": window["video_sha256"],
            "terminal_still_sha256": window["still_sha256"],
            "start_frame": window["first_frame"],
            "last_video_frame": window["last_video_frame"],
            "terminal_sample": window["terminal_sample"],
        }
    if (
        source != "side_video"
        or clip is None
        or isinstance(stop_s, bool)
        or not isinstance(stop_s, (float, int))
        or not math.isfinite(stop_s)
    ):
        raise ValueError("Выберите доступный ролик и видимый на нём момент STOP")
    pts = footage(clip)
    # A manually aligned STOP can correspond to either dispatch or receipt. Cover the
    # complete admissible interval before that marker, including camera/clock uncertainty.
    start_s = stop_s - window["duration_s"] - window["camera_to_stop_response_upper_s"]
    if start_s < 0 or stop_s > pts[-1]:
        raise ValueError("Выбранная запись не покрывает всё окно до STOP")
    a = int(np.searchsorted(pts, start_s, side="right") - 1)
    b = int(np.searchsorted(pts, stop_s, side="left"))
    if a < 0 or b <= a or np.max(np.diff(pts[a : b + 1])) > GAP_NS / 1e9:
        raise ValueError("В терминальном окне боковой записи есть пропуск кадров")
    return {
        "source": source,
        "sha256": file_hash(clip),
        "start_frame": a,
        "stop_frame": b,
        "start_pts_s": float(pts[a]),
        "stop_pts_s": float(pts[b]),
        "operator_aligned_stop_s": stop_s,
    }
