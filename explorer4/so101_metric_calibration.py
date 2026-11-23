"""Estimate SO-101 fixed-jaw contact geometry from a recorded metrology session."""

import hashlib
import json
import math
from itertools import combinations
from pathlib import Path

import numpy as np

from . import catalog, fleet_config
from .paths import DATA
from .sim_protocol import sha256_file
from .skill_packets import transform
from .so101_geometry import MODEL, fixed_frames
from .so101_packet_builder import (
    camera_fingerprint,
    marker_geometry_identity,
    validate_geometry_calibration,
)


def recordings():
    result = {}
    for entry in catalog.rows("episodes"):
        if entry["profile"] == "so101_pick_place" and not entry["excluded"]:
            root = Path(entry["dataset"]).resolve()
            if (
                root.is_relative_to(DATA.resolve())
                and (root / "donor_geometry/provenance.json").is_file()
            ):
                result[entry["id"]] = root
    return result


def load_capture(episode):
    root = recordings().get(episode)
    if root is None:
        raise ValueError("Нет доступной реальной записи SO-101 с обзорной камерой")
    geometry = root / "donor_geometry"
    meta = json.loads((geometry / "provenance.json").read_bytes())
    raw = meta["calibration_source_json"]

    if (
        hashlib.sha256(raw.encode()).hexdigest() != meta["calibration_sha256"]
        or meta["model_sha256"] != sha256_file(MODEL)
        or json.loads((root / "provenance.json").read_bytes()).get("domain", "real")
        != "real"
    ):
        raise ValueError("Калибровка, модель или происхождение записи изменились")
    return geometry, meta


def sensor_identity(meta):
    return {
        "camera_sha256": camera_fingerprint(meta["camera"]),
        "source_model_sha256": meta["model_sha256"],
        "source_calibration_sha256": meta["calibration_sha256"],
    }


def stationary_samples(geometry, meta, frames):
    rows = [
        json.loads(line)
        for line in (geometry / "measurements.jsonl").read_text().splitlines()
    ]
    native = [
        json.loads(line)
        for line in (geometry.parent / "research.jsonl").read_text().splitlines()
    ]
    if not rows or len(rows) != meta["frames"] or len(native) != len(rows):
        raise ValueError("Запись с измерениями не завершена")
    times = np.asarray([r["observation_timestamp_ns"] for r in rows], dtype=np.int64)
    if np.any(np.diff(times) <= 0):
        raise ValueError("Нарушен порядок отсчётов энкодеров")
    result = {}
    for frame in frames:
        if type(frame) is not int or not 0 <= frame < len(rows):
            raise ValueError("Укажите существующий номер исходного кадра")
        row = rows[frame]
        receive = row["camera_timestamp_ns"]
        if not 0 <= times[frame] - receive <= 100_000_000:
            raise ValueError(f"Кадр {frame}: нет свежего снимка C920")
        # Bracket every possible exposure under the packet builder's 250 ms latency limit.
        start = int(np.searchsorted(times, receive - 250_000_000, side="right")) - 1
        end = int(np.searchsorted(times, times[frame] + 150_000_000)) + 1
        if (
            start < 0
            or end > len(times)
            or np.max(np.diff(times[start:end])) > 100_000_000
        ):
            raise ValueError(
                f"Кадр {frame}: мало непрерывных отсчётов вокруг экспозиции"
            )
        for index in range(start, end):
            measured, original = rows[index], native[index]
            if (
                measured["frame_index"] != index
                or measured["observation_timestamp_ns"]
                != original["observation_timestamp_ns"]
                or measured["measured_native_joints"] != original["observation.state"]
                or original.get("state_valid") is not True
                or original.get("command_source") != "human"
            ):
                raise ValueError("Отсчёт не совпадает с исходным измерением руки")
        window = rows[start:end]
        q = np.asarray([r["measured_native_joints"] for r in window], dtype=float)
        if (
            row["frame_index"] != frame
            or len(window) < 3
            or q.shape != (len(window), 6)
            or not np.isfinite(q).all()
            or times[end - 1] - times[start] < 200_000_000
            or np.max(np.ptp(q, axis=0)) > 1
        ):
            raise ValueError(
                f"Кадр {frame}: нужен неподвижный интервал с измерениями всех шести суставов"
            )
        image = (geometry / row["image"]).resolve()
        if (
            not image.is_relative_to(geometry.resolve())
            or sha256_file(image) != row["image_sha256"]
        ):
            raise ValueError("Обзорный кадр изменился")
        tip = fixed_frames(
            row["measured_native_joints"], json.loads(meta["calibration_source_json"])
        )["gripper_frame_link"]
        if not np.allclose(tip, transform(row["world_fixed_tip_pose"]), atol=1e-8):
            raise ValueError("Поза не совпадает с исходными энкодерами и моделью")
        result[frame] = (tip, float(q[frame - start, 5]), row)
    return result


def measured_points(episode, measurements, reference_mm):
    geometry, meta = load_capture(episode)
    if not math.isfinite(reference_mm) or not 0 < reference_mm <= 3:
        raise ValueError("Нужна положительная погрешность отсчёта инструмента до 3 мм")
    frames = [row["frame"] for row in measurements]
    if len(frames) != len(set(frames)):
        raise ValueError("Один и тот же кадр нельзя использовать дважды")
    samples = stationary_samples(geometry, meta, frames)
    result = []
    for measure in measurements:
        frame = measure["frame"]
        tip, percent, row = samples[frame]
        fixed, moving = (
            np.asarray(measure[k], dtype=float) / 1000
            for k in ("fixed_mm", "moving_mm")
        )
        width = measure["opening_mm"] / 1000
        if (
            measure["group"] not in ("fit", "control")
            or fixed.shape != (3,)
            or moving.shape != (3,)
            or not np.isfinite(np.r_[fixed, moving, width]).all()
            or not 0 <= width <= 0.2
        ):
            raise ValueError("Нужны две измеренные точки XYZ и раскрытие губок")
        span = np.linalg.norm(fixed - moving)
        # The vector points across the two opposed faces into the fixed contact.
        if abs(span - width) > 3 * reference_mm / 1000:
            raise ValueError(
                f"Кадр {frame}: точки напротив друг друга должны согласовываться с измеренным раскрытием"
            )
        view = {}
        if measure["group"] == "control":
            visual = row.get("visual", {})
            cube = np.asarray(measure.get("cube_mm"), dtype=float) / 1000
            if (
                cube.shape != (3,)
                or not np.isfinite(cube).all()
                or not visual.get("valid")
                or visual.get("orientation_ambiguous", True)
            ):
                raise ValueError(
                    f"Кадр {frame}: нужны видимая однозначная метка и измеренный центр кубика XYZ"
                )
            view = {
                "cube": cube,
                "optical_xyz": transform(visual["world_object_pose"])[:3, 3],
            }
        result.append(
            {
                **view,
                **measure,
                "tip": tip,
                "percent": percent,
                "axis": tip[:3, :3].T @ ((fixed - moving) / span)
                if span > 2 * reference_mm / 1000
                else None,
                "width": width,
                "fixed": fixed,
                "span": span,
                "image_sha256": row["image_sha256"],
                "stamp_ns": row["observation_timestamp_ns"],
                "camera_stamp_ns": row["camera_timestamp_ns"],
                "camera_sequence": row["camera_sequence"],
            }
        )
    if len({r["camera_sequence"] for r in result}) != len(result) or len(
        {r["camera_stamp_ns"] for r in result}
    ) != len(result):
        raise ValueError("Для каждого измерения нужен отдельный исходный снимок C920")
    return meta, result


def fit_geometry(rows, reference_mm):
    fit = sorted((r for r in rows if r["group"] == "fit"), key=lambda r: r["percent"])
    controls = [r for r in rows if r["group"] == "control"]
    if len(fit) < 3 or len(controls) < 3:
        raise ValueError(
            "Нужны три исходных положения и три отдельно измеренных проверочных"
        )
    curve = np.array([[r["percent"], r["width"]] for r in fit])
    if not np.all(np.diff(curve, axis=0) > 0):
        raise ValueError("Кривая раскрытия должна расти по измеренным положениям губок")
    if any(
        abs(a["stamp_ns"] - b["stamp_ns"]) < 300_000_000
        for i, a in enumerate(rows)
        for b in rows[i + 1 :]
    ):
        raise ValueError("Интервалы неподвижных измерений перекрываются")
    comparisons = [*combinations(controls, 2), *((a, b) for a in fit for b in controls)]
    if any(
        np.linalg.norm(a["fixed"] - b["fixed"]) <= 2 * reference_mm / 1000
        for a, b in comparisons
    ):
        raise ValueError(
            "Проверочные положения должны различаться между собой и с положениями подгонки"
        )
    if any(
        abs(a["width"] - b["width"]) <= 2 * reference_mm / 1000
        for a, b in combinations(controls, 2)
    ):
        raise ValueError("Для независимой проверки снимите три различимых раскрытия")
    if np.ptp([r["cube"][2] for r in controls]) + 2 * reference_mm / 1000 < 0.05:
        raise ValueError("Проверьте центр кубика и на столе, и на высоте подъёма 50 мм")
    offset = np.mean(
        [r["tip"][:3, :3].T @ (r["fixed"] - r["tip"][:3, 3]) for r in fit], axis=0
    )
    directions = [r["axis"] for r in fit if r["axis"] is not None]
    if not directions or not any(r["axis"] is not None for r in controls):
        raise ValueError(
            "Для проверки оси нужны разведённые губки при подгонке и при контроле"
        )
    axis = np.mean(directions, axis=0)
    if np.linalg.norm(axis) < 0.5:
        raise ValueError("Проверьте, где неподвижная и подвижная губки")
    axis /= np.linalg.norm(axis)
    error = reference_mm / 1000
    pose_controls, jaw_controls, camera_controls, angles = [], [], [], []
    for row in controls:
        if not curve[0, 0] <= row["percent"] <= curve[-1, 0]:
            raise ValueError("Проверочное раскрытие находится вне измеренной кривой")
        predicted = row["tip"][:3, :3] @ offset + row["tip"][:3, 3]
        widths = np.interp(row["percent"], curve[:, 0], curve[:, 1])
        common = {
            "id": str(row["frame"]),
            "measurement_sigma_m": error,
            "image_sha256": row["image_sha256"],
        }
        camera_controls.append(
            {
                **common,
                "predicted_m": row["optical_xyz"].tolist(),
                "measured_m": row["cube"].tolist(),
            }
        )
        pose_controls.append(
            {
                **common,
                "predicted_m": predicted.tolist(),
                "measured_m": row["fixed"].tolist(),
            }
        )
        jaw_controls.append(
            {**common, "predicted_m": float(widths), "measured_m": row["width"]}
        )
        if row["axis"] is not None:
            angles.append(
                math.acos(float(np.clip(axis @ row["axis"], -1, 1)))
                + math.asin(2 * error / row["span"])
            )

    def bound(items):
        return max(
            float(np.linalg.norm(np.subtract(c["predicted_m"], c["measured_m"])))
            + error
            for c in items
        )

    tip_from_tcp = np.eye(4)
    tip_from_tcp[:3, 3] = offset
    return (
        {
            "fixed_tip_from_tcp": tip_from_tcp.tolist(),
            "closing_axis_tcp": axis.tolist(),
            "jaw_curve_percent_m": curve.tolist(),
            "position_sigma_m": max(bound(pose_controls), bound(camera_controls)),
            "orientation_sigma_rad": max(angles),
            "jaw_sigma_m": bound(jaw_controls),
        },
        {
            "pose_controls": pose_controls,
            "jaw_controls": jaw_controls,
            "camera_controls": camera_controls,
        },
    )


def seal(directory, value):
    from .cognitive.store import digest

    path = directory / (digest(value) + ".json")
    if path.exists() and json.loads(path.read_bytes()) != value:
        raise ValueError("Измерение изменилось")
    if not path.exists():
        fleet_config.atomic_write(path, value)
    return {
        "reference": str(path.relative_to(DATA)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def timing_report(meta):
    root = DATA / "validation/so101-timing"
    filename = camera_fingerprint(meta["camera"]) + ".json"
    measured = root / "measured" / filename
    p = measured if measured.is_file() else root / filename
    if not p.is_file():
        raise ValueError(
            "Для этих настроек C920 отсутствует измерение задержки экспозиции"
        )
    if p != measured:
        raise ValueError(
            "Архивная C920 не подтвердила время экспозиции. Нужен независимый замер для этих настроек."
        )
    from scripts.so101_timing_import import verified_installed

    timing = verified_installed(p, meta)
    if (
        timing.get("usable") is not True
        or any(
            timing.get(k) != sensor_identity(meta)[k]
            for k in ("source_calibration_sha256", "camera_sha256")
        )
        or not timing.get("method")
        or type(timing.get("lag_s")) not in (float, int)
        or not 0 <= timing["lag_s"] <= 0.25
        or type(timing.get("uncertainty_s")) not in (float, int)
        or not 0 < timing["uncertainty_s"] <= 0.020
    ):
        raise ValueError("Измерение времени камеры пока не допускается для этой записи")
    return p, timing


def save_calibration(
    donor_episode,
    control_episode,
    rows,
    reference_mm,
    size_sigma_mm,
    operator,
    instrument,
):
    if not operator.strip() or not instrument.strip():
        raise ValueError("Укажите наблюдателя и измерительный инструмент")
    _, donor_meta = load_capture(donor_episode)
    meta, samples = measured_points(control_episode, rows, reference_mm)
    identity = sensor_identity(meta)
    if identity != sensor_identity(donor_meta) or marker_geometry_identity(
        meta
    ) != marker_geometry_identity(donor_meta):
        raise ValueError("У записи с контролями другая камера, модель или калибровка")
    if not math.isfinite(size_sigma_mm) or size_sigma_mm <= 0:
        raise ValueError("Нужна фактическая погрешность измерения размеров кубика")
    fitted, controls = fit_geometry(samples, reference_mm)
    timing_path, timing = timing_report(meta)
    out = DATA / "validation/so101-metric"
    reference = seal(
        out,
        {
            "kind": "independent_geometry_controls",
            "used_for_fit": False,
            **identity,
            "operator": operator,
            "instrument": instrument,
            "capture_episode": control_episode,
            "survey": rows,
            "source_encoder_and_image_receipts": [
                {
                    "frame": r["frame"],
                    "observed_ns": r["stamp_ns"],
                    "camera_timestamp_ns": r["camera_stamp_ns"],
                    "camera_sequence": r["camera_sequence"],
                    "sha256": r["image_sha256"],
                }
                for r in samples
            ],
            **controls,
        },
    )
    time_ref = seal(out, timing)
    cal = {
        "schema": "so101-donor-geometry-validation-v1",
        **identity,
        **fitted,
        "independent_control_evidence": reference,
        "marker_geometry_sha256": marker_geometry_identity(meta),
        "size_sigma_m": [size_sigma_mm / 1000] * 3,
        "operator": operator,
        "camera_device": meta["camera"]["device"],
        "camera_delay_s": timing["lag_s"],
        "camera_delay_sigma_s": timing["uncertainty_s"],
        "timing_evidence": time_ref,
        "timing_source": str(timing_path.relative_to(DATA)),
        "tcp_definition": "Surveyed fixed pad contact point; axes retain the source rigid tip axes. Closing direction measured across opposing faces.",
        "uncertainty_method": "Maximum held-out residual plus survey bound. Axis bound uses signed contact direction and uncertainty at both surveyed points.",
    }
    validate_geometry_calibration(cal, donor_meta)
    artifact = seal(out, cal)
    review = {
        "calibration_ref": artifact["reference"],
        "calibration_sha256": artifact["sha256"],
    }
    return review
