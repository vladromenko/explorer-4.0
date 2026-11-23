"""Locate candidate phase intervals in one archived human SO-101 demonstration.

Run with python -m scripts.so101_donor_phase_review. Pixel outputs stay on Homebrain.
This read-only review never creates a phase annotation, SkillPacket or operator signature.
"""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


EPISODE = "d891e94d13014e3abcda7f1a3dce517e"
# Other successful demonstrations present in the catalogue when this review was made.
COMPARISON_EPISODES = (
    "2b02f12c214b4d548483c7789a162a32", "451048674bfe4b579bcf3c6ea800c3aa",
    "47c74f2756df42edb42514658a43e04a", "7d44a181fd8e4d029bbb21acafc3a472",
    "cc209320e3af486b83e74791977dd913",
)
# Retrospective proposals from the overview and native gripper trace. Ends are inclusive.
PHASES = (
    ("approach", "Подход", 208, 334, (208, 278, 330),
     "Губки раскрываются и подводятся к кубику. В начале фазы поворот метки неоднозначен."),
    ("grasp", "Смыкание", 335, 389, (335, 350, 389),
     "Энкодер показывает смыкание. На снимках корпус и губки перекрывают верхнюю метку. Момент контакта неизвестен."),
    ("lift", "Подъём", 390, 502, (390, 425, 462),
     "Поднимается рука. Позднее в губках виден кубик. Метка снова обнаружена с кадра 410, первая однозначная оценка на кадре 425."),
    ("hold", "Удержание", 505, 690, (505, 664, 673),
     "Положение руки почти постоянно, на снимках виден кубик между губками. Высота и длительность метрического удержания не подтверждены."),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def distinct_views(rows):
    selected = []
    for row in rows:
        stamp = row["camera_timestamp_ns"]
        if selected and stamp < selected[-1]["camera_timestamp_ns"]:
            raise ValueError("Camera time moved backwards")
        if not selected or stamp != selected[-1]["camera_timestamp_ns"]:
            selected.append(row)
    return selected


def unambiguous(row):
    visual = row["visual"]
    return visual.get("valid") is True and visual.get("orientation_ambiguous") is False


def visibility(views):
    start = last = None
    longest = {"seconds": 0.0, "first_frame": None, "last_frame": None}
    for row in views:
        stamp = row["camera_timestamp_ns"]
        if unambiguous(row):
            if start is None or stamp - last > 150_000_000:
                start = row
            elapsed = (stamp - start["camera_timestamp_ns"]) / 1e9
            if elapsed > longest["seconds"] or longest["first_frame"] is None:
                longest = {"seconds": elapsed, "first_frame": start["frame_index"],
                           "last_frame": row["frame_index"]}
        else:
            start = None
        last = stamp
    return {"distinct_views": len(views),
            "marker_detected": sum(v["visual"].get("valid") is True for v in views),
            "unambiguous": sum(map(unambiguous, views)),
            "longest_uninterrupted_unambiguous": longest}


def time_s(row, origin):
    return round((row["camera_timestamp_ns"] - origin) / 1e9, 3)


def review_episode(root):
    geometry = root / "donor_geometry"
    rows = read_rows(geometry / "measurements.jsonl")
    original = read_rows(root / "research.jsonl")
    metadata = json.loads((geometry / "provenance.json").read_text())
    if metadata["frames"] != len(rows) or len(rows) != len(original):
        raise ValueError("Source row count mismatch")
    for i, (row, sample) in enumerate(zip(rows, original)):
        if (i != row["frame_index"] or sample["frame_index"] != i
                or row["observation_timestamp_ns"] != sample["observation_timestamp_ns"]
                or row["measured_native_joints"] != sample["observation.state"]
                or sample["command_source"] != "human" or sample["state_valid"] is not True
                or row["image"] != f"{i:06d}.jpg" or sha(geometry / row["image"]) != row["image_sha256"]):
            raise ValueError(f"Broken source, state or photo link at {i}")
    origin = rows[0]["camera_timestamp_ns"]
    selected = distinct_views(rows)
    phases = []
    for name, _, a, b, frames, _ in PHASES:
        part = rows[a:b + 1]
        phases.append({"phase": name, "first_frame": a, "last_frame": b,
                       "first_camera_time_s": time_s(rows[a], origin),
                       "last_camera_time_s": time_s(rows[b], origin),
                       "gripper_encoder_percent_start_end":
                           [round(r["measured_native_joints"][5], 2) for r in (rows[a], rows[b])],
                       "visibility": visibility(distinct_views(part)),
                       "thumbnail_indices": list(frames)})
    gaps = []
    first = None
    for i, row in enumerate(rows):
        detected = row["visual"].get("valid") is True
        if not detected and first is None:
            first = i
        if first is not None and (detected or i == len(rows) - 1):
            last = i - 1 if detected else i
            if last - first + 1 >= 15:
                gaps.append([first, last])
            first = None
    return rows, {
        "schema": "so101-donor-phase-proposal-v1", "episode": EPISODE,
        "status": "proposed_not_admitted", "human_signed": False, "packet_admitted": False,
        "domain": "physical human SO-101 demonstration", "measurement_rows": len(rows),
        "source_sha256": {str(p.relative_to(root)): sha(p) for p in (
            root / "research.jsonl", geometry / "measurements.jsonl", geometry / "provenance.json")},
        "verified_archived_jpeg_hashes": len(rows), "visibility": visibility(selected),
        "first_unambiguous_frame": next(r["frame_index"] for r in selected if unambiguous(r)),
        "undetected_intervals_at_least_15_rows_inclusive": gaps,
        "interval_convention": "Zero-based original frame numbers, both endpoints inclusive. "
                               "Camera times are relative to the first distinct overview timestamp.",
        "proposed_intervals": phases, "independent_object_lift_m": None,
        "verified_object_hold_s": None, "phase_anchors_confirmed": False,
        "explanation": "The archived detector cannot provide an unambiguous pre-grasp reference "
                       "or a one-second continuous observation. Images and encoder traces guide review only.",
    }


def alternatives(data):
    with sqlite3.connect(f"file:{data}/catalog.sqlite3?mode=ro", uri=True) as db:
        entries = db.execute("SELECT id,dataset,frames,excluded FROM episodes WHERE profile='so101_pick_place' "
                             "AND outcome='success' AND category IN ('demonstration','correction') "
                             "AND id IN (?,?,?,?,?) ORDER BY id", COMPARISON_EPISODES).fetchall()
    if tuple(row[0] for row in entries) != COMPARISON_EPISODES:
        raise ValueError("Archived comparison catalogue changed")
    alternatives = []
    for episode, folder, n, excluded in entries:
        root = Path(folder)
        info = json.loads((root / "meta/info.json").read_text())
        measurement_file = root / "donor_geometry/measurements.jsonl"
        item = {"episode": episode, "original_frames": n, "excluded": bool(excluded),
                "image_features": sorted(k for k in info["features"] if k.startswith("observation.images.")),
                "overview_measurements_archived": measurement_file.is_file()}
        if measurement_file.is_file():
            item["visibility"] = visibility(distinct_views(read_rows(measurement_file)))
        alternatives.append(item)
    return alternatives


def contact_sheet(root, rows, path):
    fontdir = Path("/usr/share/fonts/truetype/dejavu")
    title = ImageFont.truetype(str(fontdir / "DejaVuSans-Bold.ttf"), 23)
    font = ImageFont.truetype(str(fontdir / "DejaVuSans.ttf"), 16)
    card_w, card_h = 280, 207
    sheet = Image.new("RGB", (3 * card_w, 55 + len(PHASES) * card_h), "#f5f4ef")
    draw = ImageDraw.Draw(sheet)
    draw.text((10, 8), "SO-101  ·  Фазы показа  ·  предложение, не допущено", font=title, fill="#1e2830")
    draw.text((10, 36), "Фрагменты одной обзорной камеры. Время от первого кадра. Рамка по месту съёмки постоянна.",
              font=font, fill="#35424a")
    for line, (_, label, _, _, indices, _) in enumerate(PHASES):
        for col, index in enumerate(indices):
            row = rows[index]
            x, y = card_w * col, 55 + card_h * line
            with Image.open(root / "donor_geometry" / row["image"]) as im:
                # Same crop and scale for all frames, including frames where the tag detector failed.
                patch = im.crop((498, 240, 968, 535))
                patch.thumbnail((card_w - 10, card_h - 42), Image.Resampling.LANCZOS)
            sheet.paste(patch, (x + 5, y + 4))
            draw.text((x + 6, y + card_h - 36),
                      f"{label}  ·  № {index}  ·  {time_s(row, rows[0]['camera_timestamp_ns']):.2f} с",
                      font=font, fill="#13212e")
            valid = row["visual"].get("valid") is True
            reason = ("поворот различим" if unambiguous(row) else "неоднозначный поворот") if valid else "метка не распознана"
            draw.text((x + 6, y + card_h - 18), reason, font=font, fill="#46525b")
    sheet.save(path, quality=91)


def html_report(report):
    vis = report["visibility"]
    best = vis["longest_uninterrupted_unambiguous"]
    items = []
    alternatives_html = []
    for item in report["other_catalogued_successes"]:
        flag = "Исключён" if item["excluded"] else "Включён"
        alternate = "Только видео запястья, независимых измерений обзорной камеры нет."
        if item["overview_measurements_archived"]:
            span = item["visibility"]["longest_uninterrupted_unambiguous"]["seconds"]
            alternate = f"Самая длинная непрерывная серия однозначных наблюдений — {span:.3f} с."
        alternatives_html.append(f"<li><code>{item['episode'][:8]}</code> · {flag} в каталоге: "
                                 f"{item['original_frames']} кадров. {alternate}</li>")
    for (_, label, a, b, _, note), phase in zip(PHASES, report["proposed_intervals"]):
        seen = phase["visibility"]
        items.append(f"<tr><th>{label}</th><td>{a}–{b}</td>"
                     f"<td>{phase['first_camera_time_s']:.2f}–{phase['last_camera_time_s']:.2f}</td>"
                     f"<td>{seen['unambiguous']} / {seen['distinct_views']}</td><td>{note}</td></tr>")
    return f"""<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SO-101 · разбор фаз показа</title><style>body{{font:17px/1.45 system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#202c35}}
td,th{{border-bottom:1px solid #c9cdd0;text-align:left;padding:.45rem}}th{{vertical-align:top}} table{{border-collapse:collapse}}
img{{max-width:100%;height:auto}} li{{margin:.4rem 0}}.flag{{color:#812b22}}@media(max-width:700px){{.table{{overflow-x:auto}}}}</style>
<h1>SO-101 · разбор четырёх фаз</h1><p class="flag"><strong>Предложение, не допущено.</strong> Подписи оператора и подтверждённого переноса навыка нет.</p>
<p>Запись {EPISODE}. Проверены {report['measurement_rows']} сохранённых JPEG и их связь с энкодерами человеческого показа.
После удаления повторных временных меток остаётся {vis['distinct_views']} кадров. Архивный детектор распознал метку на {vis['marker_detected']}, однозначно оценил её поворот на {vis['unambiguous']}.</p>
<div class="table"><table><thead><tr><th>Фаза</th><th>Кадры включительно</th><th>Время камеры, с</th><th>Однозначных / разных</th><th>Основание и неопределённость</th></tr></thead><tbody>{''.join(items)}</tbody></table></div>
<p>Кадры 279–409: на верхнюю метку заходит корпус захвата. Детектор перестаёт узнавать её. Номер кадра первого контакта определить нельзя. Кадры 503–504 оставлены между подъёмом и почти неподвижной позой. Даже без проверки высоты самая длинная непрерывная серия однозначных измерений во всём показе — {best['seconds']:.3f} с (кадры {best['first_frame']}–{best['last_frame']}). Для допуска требуется 1 с.</p>
<a href="contact.jpg"><img src="contact.jpg" width="840" height="883" alt="Двенадцать кадров. В момент смыкания губки перекрывают метку, затем кубик снова виден."></a>
<details><summary>Проверены остальные пять помеченных успешными записей</summary><ul>{''.join(alternatives_html)}</ul></details>
<h2>Один дополнительный донорский показ SO-101</h2><ol>
<li>В архиве на кубике 29 × 29 × 29 мм по центру верхней грани закреплён AprilTag 36h11 №1, чёрная сторона 20 мм. Расположение по центру верхней грани зашито в привязке к кубику. Сохраните его. Направьте губки сбоку, чтобы корпус не закрывал углы метки. Проверьте в кадре все четыре позы. Наклон обзора должен позволять различать поворот метки. При смене положения камеры заново измерьте её привязку. Отдельная красная метка на белом фоне на подвижной губке должна остаться в откалиброванном месте.</li>
<li>Подтвердите привязку камеры и задержку, рабочую точку захвата и раскрытие губок. Для пилота нужны три независимые контрольные позиции и три независимых размера раскрытия, отдельно от подгонки. Зарегистрируйте неопределённость измерений. Для положения допустимо 5 мм, для раскрытия 3 мм с учётом ошибки измерения.</li>
<li>Запишите один непрерывный показ. При видимой метке поднимите <strong>сам кубик</strong> минимум на 50 мм от его начальной высоты и держите рядом с рабочей точкой захвата (менее 60 мм) не менее 1 с. Оставьте временной запас. Программа проверяет измеренную высоту кубика и время по разным последовательным обзорным кадрам, с промежутком не более 150 мс. Энкодер измеряет состояние руки.</li>
<li>Просмотрите четыре перехода и укажите границы подхода, смыкания, подъёма и удержания вручную. В начале каждой фазы нужна полностью читаемая метка с однозначным поворотом. Подпишите собственный замер и отметки только после просмотра. Пять имеющихся учебных показов целевого ROSMASTER остаются пригодными для своего разбиения.</li>
</ol><p><a href="result.json">Покадровые интервалы, контрольные суммы и ведомость альтернатив (JSON)</a> · <a href="../result.json">Исходная проверка экземпляра</a></p></html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path.home() / ".local/share/explorer3")
    parser.add_argument("--summary", type=Path, help="Optional sanitized JSON copy")
    args = parser.parse_args()
    root = args.data / "datasets/so101_pick_place" / EPISODE
    rows, report = review_episode(root)
    report["other_catalogued_successes"] = alternatives(args.data)
    output = args.data / "simlab/reports/so101-instance-replay-v3/donor-phases"
    output.mkdir(parents=True, exist_ok=True)
    contact_sheet(root, rows, output / "contact.jpg")
    report["lan_contact_sheet_sha256"] = sha(output / "contact.jpg")
    summary = json.dumps(report, indent=2, allow_nan=False) + "\n"
    (output / "result.json").write_text(summary)
    (output / "index.html").write_text(html_report(report))
    if args.summary:
        args.summary.write_text(summary)


if __name__ == "__main__":
    main()
