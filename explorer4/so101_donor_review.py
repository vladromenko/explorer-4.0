"""Review private overview images and keep annotations outside the original dataset."""

import fcntl
import hashlib
import json
import re
from pathlib import Path

from scripts.so101_donor_phase_review import distinct_views, unambiguous, visibility

from . import catalog, datasets
from . import so101_packet_builder as builder
from .fleet_config import atomic_write
from .paths import DATA, ROOT
from .skill_packets import PHASES


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def episode_root(episode):
    if not re.fullmatch(r"[0-9a-f]{32}", episode):
        raise ValueError("Неизвестная запись SO-101")
    with catalog.connect() as db:
        row = db.execute(
            "SELECT dataset FROM episodes WHERE id=? AND profile='so101_pick_place'", (episode,)
        ).fetchone()
    if not row:
        raise ValueError("Запись SO-101 отсутствует в каталоге")
    root = Path(row[0]).resolve()
    if (
        not root.is_relative_to((DATA / "datasets").resolve())
        or not (root / "donor_geometry/provenance.json").is_file()
    ):
        raise ValueError("В записи отсутствует исходная геометрия верхней камеры")
    return root


def measurements(root):
    folder = root / "donor_geometry"
    meta = json.loads((folder / "provenance.json").read_text())
    rows = [json.loads(line) for line in (folder / "measurements.jsonl").read_text().splitlines()]
    if not rows or len(rows) != meta["frames"] or any(row["frame_index"] != i for i, row in enumerate(rows)):
        raise ValueError("Журнал обзорной камеры неполон")
    return meta, rows


def frame(root, rows, index):
    if not 0 <= index < len(rows):
        raise ValueError("Номер кадра вне записи")
    row = rows[index]
    folder = (root / "donor_geometry").resolve()
    image = (folder / row["image"]).resolve()
    if (
        not image.is_relative_to(folder)
        or image.suffix != ".jpg"
        or hashlib.sha256(image.read_bytes()).hexdigest() != row["image_sha256"]
    ):
        raise ValueError("Контрольная сумма обзорного снимка не совпала")
    return image


def folder(episode):
    if not re.fullmatch(r"[0-9a-f]{32}", episode):
        raise ValueError("Некорректный номер эпизода")
    return DATA / "validation/so101-donor-review" / episode


def draft(episode):
    paper = folder(episode) / "draft.json"
    if paper.is_file():
        return json.loads(paper.read_text())
    return {
        "episode": episode,
        "ranges_inclusive": {p: [None, None] for p in PHASES},
        "calibration_ref": "",
        "calibration_sha256": "",
        "revision": "",
        "signed": False,
    }


def archived_suggestion(episode, root):
    result = ROOT / "docs/results/so101_donor_phase_review.json"
    if result.is_file():
        proposal = json.loads(result.read_text())
        if (
            proposal["episode"] == episode
            and hashlib.sha256((root / "donor_geometry/measurements.jsonl").read_bytes()).hexdigest()
            == proposal["source_sha256"]["donor_geometry/measurements.jsonl"]
        ):
            return {p["phase"]: [p["first_frame"], p["last_frame"]] for p in proposal["proposed_intervals"]}
    return None


def validated_ranges(ranges, length, *, complete):
    if set(ranges) != set(PHASES):
        raise ValueError("Нужны четыре фазы показа")
    previous_end = -1
    converted = {}
    for phase in PHASES:
        low, high = ranges[phase]
        for index in (low, high):
            if index is not None and (type(index) is not int or not 0 <= index < length):
                raise ValueError(f"{phase}: нужен целый номер кадра в пределах записи")
        if low is None or high is None:
            if complete:
                raise ValueError(f"{phase}: укажите первый и последний кадры")
        else:
            if not previous_end < low < high:
                raise ValueError(
                    f"{phase}: нужны минимум два кадра, фазы должны идти по порядку без наложения"
                )
            previous_end = high
            converted[phase] = [low, high + 1]
    return converted


def save_draft(episode, ranges, ref, sha, expected):
    root = episode_root(episode)
    _, rows = measurements(root)
    validated_ranges(ranges, len(rows), complete=False)
    out = folder(episode)
    out.mkdir(parents=True, exist_ok=True)
    with (out / ".lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if draft(episode)["revision"] != expected:
            raise ValueError("Черновик изменён в другой вкладке. Обновите страницу перед редактированием")
        record = {
            "episode": episode,
            "episode_sha256": datasets.fingerprint(root),
            "ranges_inclusive": ranges,
            "calibration_ref": ref.strip(),
            "calibration_sha256": sha.strip(),
            "signed": False,
        }
        record["revision"] = digest(record)
        atomic_write(out / "draft.json", record)
        return record


def review_fields(episode, record):
    _, rows = measurements(episode_root(episode))
    ranges = validated_ranges(record["ranges_inclusive"], len(rows), complete=True)
    if not record["calibration_ref"] or not re.fullmatch(r"[0-9a-f]{64}", record["calibration_sha256"]):
        raise ValueError("Требуются файл проверенной калибровки с независимыми измерениями и его SHA256")
    return {
        "episode_sha256": record["episode_sha256"],
        "phase_frames": ranges,
        "calibration_ref": record["calibration_ref"],
        "calibration_sha256": record["calibration_sha256"],
    }


def inspect(episode, record):
    _, rows = measurements(episode_root(episode))
    ranges = validated_ranges(record["ranges_inclusive"], len(rows), complete=True)
    counts = {}
    previous = -1
    for phase, (low, end) in ranges.items():
        selected = [r for r in distinct_views(rows[low:end]) if r["camera_timestamp_ns"] > previous]
        if selected:
            previous = selected[-1]["camera_timestamp_ns"]
        counts[phase] = {
            **visibility(selected),
            "phase_start_visible": bool(selected and unambiguous(selected[0])),
        }
    answer = {"phase_visibility": counts, "hold_s": None, "lift_m": None, "ready_to_sign": False}
    reasons = [
        f"{p}: в начале фазы нет однозначной привязки кубика или двух разных кадров"
        for p, c in counts.items()
        if c["distinct_views"] < 2 or not c["phase_start_visible"]
    ]
    try:
        form = review_fields(episode, record)
        if not reasons:
            evidence = builder.measure_real_donor(episode, form)
            answer.update(hold_s=evidence["held_s"], lift_m=evidence["lift_m"])
            if evidence["held_s"] < 1:
                reasons.append("По измеренной высоте кубика нет 50 мм с непрерывным удержанием не менее 1 с")
    except (ValueError, KeyError, OSError, TypeError) as exc:
        reasons.append(str(exc))
    return {**answer, "ready_to_sign": not reasons, "reasons": reasons}


def sign(episode, revision, operator, confirmed, allow_training):
    operator = str(operator or "").strip()
    if not confirmed or not operator:
        raise ValueError("Требуются имя оператора и явное подтверждение разметки и разрешения использования")
    out = folder(episode)
    with (out / ".lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        record = draft(episode)
        if not revision or record["revision"] != revision:
            raise ValueError("Сначала сохраните текущую разметку")
        check = inspect(episode, record)
        if not check["ready_to_sign"]:
            raise ValueError(" · ".join(check["reasons"]))
        review = {
            **review_fields(episode, record),
            "operator": operator,
            "source_use": {
                "granted_by": operator,
                "reference": f"reviewed-donor/{episode}/{revision}",
                "allowed": ["adaptation", "training"] if allow_training else ["adaptation"],
            },
        }
        key = digest(review)
        atomic_write(out / ("signed-" + key + ".json"), review)
        return key


def signed(episode, key):
    if not re.fullmatch(r"[0-9a-f]{64}", key):
        raise ValueError("Неизвестная версия подписанного разбора")
    report = folder(episode) / ("signed-" + key + ".json")
    if not report.is_file() or digest(json.loads(report.read_text())) != key:
        raise ValueError("Подписанный разбор отсутствует или изменён")
    return report


def register(episode, key):
    with (folder(episode) / ".lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        review = json.loads(signed(episode, key).read_text())
        item, _ = builder.build_real_packet(episode, review)
        return item["skill_packet_sha256"]
