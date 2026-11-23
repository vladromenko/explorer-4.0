"""Field entry for independent SO-101 ruler measurements. Reading saved captures only."""

import json
import math
from urllib.parse import urlencode

from nicegui import ui

from . import fleet_config
from . import so101_metric_calibration as metric
from .paths import DATA


def form_file(episode):
    metric.load_capture(episode)
    return DATA / "validation/so101-metric-survey" / (episode + ".json")


def survey(episode):
    path = form_file(episode)
    return (
        json.loads(path.read_bytes())
        if path.is_file()
        else {
            "rows": [],
            "reference_mm": None,
            "size_sigma_mm": None,
            "operator": "",
            "instrument": "",
        }
    )


def save_row(episode, source, item, common):
    path = form_file(episode)
    with fleet_config.locked():
        old = survey(episode)
        if old["rows"] and old["control_episode"] != source:
            raise ValueError("Для этого листа уже выбрана другая запись с измерениями")
        if old["rows"] and any(common[k] != old[k] for k in common):
            raise ValueError(
                "За введёнными точками уже закреплены наблюдатель, инструмент и погрешность"
            )
        # Preserve other observers' saved frames. Re-entering a frame edits only that row.
        rows = {r["frame"]: r for r in old["rows"]}
        rows[item["frame"]] = item
        fleet_config.atomic_write(
            path, {**common, "control_episode": source, "rows": list(rows.values())}
        )


def install():
    @ui.page("/recording/so101-calibration")
    def choose():
        ui.link("Подготовка к физической проверке", "/field-session")
        ui.label("Метрическая калибровка SO-101").classes("text-2xl")
        found = metric.recordings()
        if not found:
            ui.label("Нужна сохранённая запись SO-101 с обзорной камерой.")
        for episode in found:
            ui.link(
                "Измерения для записи " + episode[:12],
                "/recording/so101-calibration/" + episode,
            )

    @ui.page("/recording/so101-calibration/{episode}")
    def form(episode: str):
        ui.link("Подготовка к физической проверке", "/field-session")
        ui.label("Метрическая калибровка SO-101").classes("text-2xl")
        try:
            draft = survey(episode)
        except (KeyError, OSError, ValueError) as exc:
            ui.label(str(exc))
            return
        ui.label(
            "Снимите одной записью неподвижные положения губок. На площадке измерьте по осям основания X, Y, Z двух отмеченных точек напротив друг друга: на неподвижной и подвижной губках. Измерьте внутренний зазор штангенциркулем. Запишите номер кадра каждого положения. Проверьте, что рука надёжно зафиксирована, приводы остановлены и каждая измеряемая поза неподвижна минимум полсекунды."
        )
        ui.label(
            "Выберите три положения для калибровки с разным раскрытием и ещё три независимо выставленных для проверки. У исходных положений диапазон раскрытия должен покрывать всё движение нового показа. Калибровочные кадры сохраните отдельно от четырёх фаз захвата."
        )
        ui.label(
            "Исходный обзор и энкодеры берутся из выбранной записи. Мастер вычислит смещение точки контакта, направление смыкания и метрическую кривую раскрытия."
        ).classes("text-sm")
        choices = metric.recordings()
        source = ui.select(
            {k: k[:16] for k in choices},
            value=draft.get("control_episode", episode),
            label="Запись с неподвижными измерениями",
        ).classes("w-96 max-w-full")
        with ui.row():
            user = ui.input("Кто измерял", value=draft["operator"])
            instrument = ui.input(
                "Инструмент и система отсчёта", value=draft["instrument"]
            )
            reference = ui.number(
                "Предел ошибки XYZ (по расстоянию) и зазора, мм",
                value=draft["reference_mm"],
                min=0,
            )
            size = ui.number(
                "Погрешность размера кубика, мм", value=draft["size_sigma_mm"], min=0
            )
        with ui.row():
            frame = ui.number("Номер исходного кадра", min=0, step=1)
            group = ui.select(
                {"fit": "Калибровочное", "control": "Независимое проверочное"},
                value="fit",
                label="Положение",
            )
            opening = ui.number("Раскрытие штангенциркулем, мм", min=0)
        field = {}
        for key, name in (
            ("fixed_mm", "Неподвижная губка"),
            ("moving_mm", "Подвижная губка"),
        ):
            ui.label(name)
            with ui.row():
                field[key] = [
                    ui.number(f"{axis}, мм").classes("w-32") for axis in "XYZ"
                ]

        def remove(frame_no):
            path = form_file(episode)
            with fleet_config.locked():
                latest = survey(episode)
                latest["rows"] = [r for r in latest["rows"] if r["frame"] != frame_no]
                fleet_config.atomic_write(path, latest)
            entries.refresh()

        with ui.column().bind_visibility_from(
            group, "value", backward=lambda v: v == "control"
        ):
            ui.label(
                "Центр меченого кубика по независимому замеру в осях основания. В трёх проверочных кадрах включите положение на столе и положение на подставке высотой 50 мм или выше."
            )
            with ui.row():
                cube_fields = [
                    ui.number(f"Центр {a}, мм").classes("w-32") for a in "XYZ"
                ]

        @ui.refreshable
        def entries():
            latest = survey(episode)
            for row in sorted(latest["rows"], key=lambda r: r["frame"]):
                name = "калибровка" if row["group"] == "fit" else "проверка"
                with ui.row().classes("items-center"):
                    ui.label(
                        f"Кадр {row['frame']} · {name} · зазор {row['opening_mm']:g} мм · точки {row['fixed_mm']} и {row['moving_mm']} мм"
                    )
                    ui.button(
                        icon="close", on_click=lambda n=row["frame"]: remove(n)
                    ).props("flat round").tooltip("Убрать строку из черновика")
            ui.link(
                "Открыть кадры обзорной камеры",
                "/recording/so101-donor/" + source.value,
            )

        entries()
        source.on_value_change(lambda _: entries.refresh())

        def values():
            if (
                not user.value
                or not instrument.value
                or not reference.value
                or not size.value
            ):
                raise ValueError("Укажите наблюдателя, инструмент и обе погрешности")
            return {
                "operator": user.value.strip(),
                "instrument": instrument.value.strip(),
                "reference_mm": float(reference.value),
                "size_sigma_mm": float(size.value),
            }

        def save():
            try:
                if (
                    frame.value is None
                    or not float(frame.value).is_integer()
                    or opening.value is None
                ):
                    raise ValueError("Укажите номер кадра и действительное раскрытие")
                if any(
                    v.value is None or not math.isfinite(v.value)
                    for widgets in field.values()
                    for v in widgets
                ):
                    raise ValueError("Заполните все шесть координат обеих точек")
                common = values()
                item = {
                    "frame": int(frame.value),
                    "group": group.value,
                    "opening_mm": float(opening.value),
                    **{
                        k: [float(v.value) for v in widgets]
                        for k, widgets in field.items()
                    },
                }
                if group.value == "control":
                    if any(v.value is None for v in cube_fields):
                        raise ValueError(
                            "Нужны три независимо измеренные координаты центра кубика"
                        )
                    item["cube_mm"] = [float(v.value) for v in cube_fields]
                _, meta = metric.load_capture(episode)
                other, _ = metric.measured_points(
                    source.value, [item], common["reference_mm"]
                )
                if metric.sensor_identity(meta) != metric.sensor_identity(other):
                    raise ValueError(
                        "Настройки камеры, модель или калибровка отличаются"
                    )
                save_row(episode, source.value, item, common)
                entries.refresh()
                ui.notify("Измерение сохранено")
            except (ValueError, KeyError, TypeError, OSError) as exc:
                ui.notify(str(exc), type="negative")

        ui.button("Сохранить измерение положения", on_click=save)
        result = ui.column()

        def check():
            result.clear()
            try:
                latest = survey(episode)
                observed = values()
                if (
                    not latest["rows"]
                    or latest.get("control_episode") != source.value
                    or any(latest[k] != v for k, v in observed.items())
                ):
                    raise ValueError(
                        "Выберите запись и инструмент, сохранённые в этом листе"
                    )
                review = metric.save_calibration(
                    episode,
                    latest["control_episode"],
                    latest["rows"],
                    **{k: latest[k] for k in observed},
                )
                with result:
                    ui.label("Измерения и контролируемые ошибки сохранены.")
                    ui.link(
                        "Применить к разбору показа",
                        "/recording/so101-donor/" + episode + "?" + urlencode(review),
                    )
            except (ValueError, KeyError, TypeError, OSError) as exc:
                with result:
                    ui.label(str(exc))

        ui.button("Проверить независимые измерения", on_click=check)
        try:
            _, meta = metric.load_capture(episode)
            _, timing = metric.timing_report(meta)
            ui.label(
                f"Задержка камеры {timing['lag_s'] * 1000:.1f} мс, погрешность {timing['uncertainty_s'] * 1000:.1f} мс."
            )
        except (ValueError, KeyError, OSError) as exc:
            ui.label(str(exc))
            ui.label(
                "Для отдельного замера камера снимает независимый оптический таймкод в двух коротких сериях. Рука остаётся неподвижной. Исходные кадры с красной меткой уже проверены."
            )
            ui.link(
                "Что показали измерения C920",
                "/simlab-media/reports/so101-camera-timing-v1/result.json",
            )
            ui.link(
                "Способ измерения и загрузка результата",
                "https://github.com/vladromenko/explorer-4.0/blob/main/docs/RESEARCH_REGISTER_ROBOTS.md#physical-so-101-camera-timing",
            )
        ui.link("Разобрать четыре фазы захвата", "/recording/so101-donor/" + episode)
