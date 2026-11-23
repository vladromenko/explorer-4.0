"""Operator review of the actual C920 images in a saved human demonstration."""

from fastapi import HTTPException
from fastapi.responses import FileResponse
from nicegui import app, run, ui

from . import so101_donor_review as review
from .skill_packets import PHASES

LABELS = dict(zip(PHASES, ("Подход", "Смыкание", "Подъём", "Удержание")))
ERRORS = (OSError, ValueError, KeyError, TypeError, RuntimeError)


def install():
    @app.get("/recording/so101-donor/{episode}/frame/{index}.jpg")
    def photo(episode: str, index: int):
        try:
            root = review.episode_root(episode)
            _, rows = review.measurements(root)
            return FileResponse(review.frame(root, rows, index), media_type="image/jpeg")
        except ERRORS as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/recording/so101-donor/{episode}/signed/{key}.json")
    def export(episode: str, key: str):
        try:
            return FileResponse(
                review.signed(episode, key),
                media_type="application/json",
                filename=f"so101-review-{episode}-{key[:12]}.json",
            )
        except ERRORS as exc:
            raise HTTPException(404, str(exc)) from exc

    @ui.page("/recording/so101-donor/{episode}")
    async def page(episode: str, calibration_ref: str = "", calibration_sha256: str = ""):
        ui.dark_mode().enable()
        ui.query(".nicegui-content").classes("w-full max-w-4xl mx-auto p-4 gap-3")
        ui.link("← Сбор показов SO-101", "/recording/collect?task=so101_pick_place")
        ui.label("Разбор человеческого показа SO-101").classes("text-2xl font-bold")
        try:
            root = review.episode_root(episode)
            meta, rows = await run.io_bound(review.measurements, root)
            saved = review.draft(episode)
        except ERRORS as exc:
            ui.label(str(exc))
            return
        ui.label(f"Эпизод {episode} · {len(rows)} кадров C920 · экземпляр {meta['settings']['instance_id']}")
        counts = review.visibility(review.distinct_views(rows))
        limit = counts["longest_uninterrupted_unambiguous"]["seconds"]
        ui.label(
            f"Разных измерений камеры {counts['distinct_views']}, с однозначной меткой {counts['unambiguous']}. "
            f"Самая длинная непрерывная серия однозначной видимости — {limit:.3f} с. "
            "Высота кубика и удержание проверяются отдельно по метрической калибровке."
        )
        route = f"/recording/so101-donor/{episode}"
        image = (
            ui.image(route + "/frame/0.jpg")
            .props("fit=contain")
            .style("width:min(680px,100%);aspect-ratio:16/9")
        )
        info = ui.label()
        data = {"index": 0, "revision": saved["revision"]}

        def show(value):
            if value is None or not float(value).is_integer() or not 0 <= value < len(rows):
                return
            i = data["index"] = int(value)
            row = rows[i]
            visual = row["visual"]
            tag = (
                ("поворот однозначен" if review.unambiguous(row) else "поворот неоднозначен")
                if visual.get("valid")
                else "метка не распознана"
            )
            stamp = (row["camera_timestamp_ns"] - rows[0]["camera_timestamp_ns"]) / 1e9
            image.set_source(f"{route}/frame/{i}.jpg")
            info.set_text(
                f"Кадр {i} · {stamp:.3f} с · {tag} · энкодер губок {row['measured_native_joints'][5]:.1f}%"
            )

        with ui.row().classes("items-center"):
            position = ui.number(
                "Номер кадра", value=0, min=0, max=len(rows) - 1, step=1, on_change=lambda e: show(e.value)
            ).style("width:130px")
            ui.button("Назад", on_click=lambda: position.set_value(max(0, data["index"] - 1)))
            ui.button("Вперёд", on_click=lambda: position.set_value(min(len(rows) - 1, data["index"] + 1)))
        show(0)
        ui.label("Границы четырёх фаз").classes("text-xl")
        ui.label(
            "Оба номера включаются. Для начала каждой фазы нужна полностью распознанная метка с однозначным поворотом."
        )
        fields = {}
        for phase in PHASES:
            with ui.row().classes("items-center"):
                ui.label(LABELS[phase]).style("min-width:85px")
                ends = []
                for k, title in enumerate(("Первый", "Последний")):
                    box = ui.number(
                        title, value=saved["ranges_inclusive"][phase][k], min=0, max=len(rows) - 1, step=1
                    ).style("width:90px")
                    ui.button("Текущий", on_click=lambda b=box: b.set_value(data["index"])).props(
                        "flat dense"
                    )
                    ends.append(box)
                fields[phase] = ends
        if suggestion := review.archived_suggestion(episode, root):

            def propose():
                for p in PHASES:
                    for item, val in zip(fields[p], suggestion[p]):
                        item.set_value(val)

            ui.button("Подставить архивное предложение для этих кадров", on_click=propose).props("outline")
        ui.link(
            "Независимые измерения камеры, рабочей точки и раскрытия губок · отдельная вкладка",
            f"/recording/so101-calibration/{episode}",
            new_tab=True,
        )
        ref = ui.input(
            "Файл подтверждённой калибровки на Homebrain", value=calibration_ref or saved["calibration_ref"]
        ).classes("w-full")
        sha = ui.input("SHA256 калибровки", value=calibration_sha256 or saved["calibration_sha256"]).classes(
            "w-full"
        )
        message = ui.label().style("white-space:pre-wrap")

        async def persist():
            # NiceGUI numbers may be floats. Never round a fractional frame index.
            ranges = {
                p: [
                    (int(n.value) if n.value is not None and float(n.value).is_integer() else n.value)
                    for n in ends
                ]
                for p, ends in fields.items()
            }
            record = await run.io_bound(
                review.save_draft, episode, ranges, ref.value, sha.value, data["revision"]
            )
            data["revision"] = record["revision"]
            return record

        async def save():
            try:
                await persist()
                message.set_text("Черновик сохранён. Разметку можно снова открыть и исправить.")
            except ERRORS as exc:
                message.set_text(str(exc))

        async def check():
            try:
                record = await persist()
                score = await run.io_bound(review.inspect, episode, record)
                lines = [
                    f"{LABELS[p]}: однозначных кадров {v['unambiguous']} / {v['distinct_views']}"
                    for p, v in score["phase_visibility"].items()
                ]
                lines.append(
                    "Метрическое удержание пока не установлено."
                    if score["hold_s"] is None
                    else f"Непрерывное удержание ≥50 мм: {score['hold_s']:.3f} с."
                )
                if score["lift_m"] is not None:
                    lines.append(
                        f"Подъём на конце самого длинного удержания: {score['lift_m'] * 1000:.1f} мм."
                    )
                message.set_text("\n".join(lines + score["reasons"]))
            except ERRORS as exc:
                message.set_text(str(exc))

        with ui.row():
            ui.button("Сохранить черновик", on_click=save)
            ui.button("Проверить фазы и измерение удержания", on_click=check)

        ui.label("Подпись оператора").classes("text-xl")
        name = ui.input("Имя оператора")
        confirmed = ui.checkbox(
            "Лично проверил выбранные фазы и измерения. Разрешаю использование показа для адаптации навыка."
        )
        training = ui.checkbox("Также разрешаю использовать этот показ для обучения.")
        versions = ui.column()

        def signed_links(container, key):
            with container:
                ui.link(f"Скачать подписанный разбор {key[:12]}", f"{route}/signed/{key}.json")
                result = ui.label()

                async def register():
                    try:
                        sha = await run.io_bound(review.register, episode, key)
                        result.set_text(
                            "Донорский пакет зарегистрирован: "
                            + sha
                            + ". Перенос на другую машину проверяется отдельно."
                        )
                    except ERRORS as exc:
                        result.set_text(str(exc))

                ui.button("Зарегистрировать донорский пакет по этой версии", on_click=register).props(
                    "outline"
                )

        async def sign():
            try:
                record = await persist()
                key = await run.io_bound(
                    review.sign, episode, record["revision"], name.value, confirmed.value, training.value
                )
                message.set_text(f"Подпись сохранена для версии {key[:12]}.")
                versions.clear()
                show_versions()
            except ERRORS as exc:
                message.set_text(str(exc))

        ui.button("Подписать проверенный разбор", on_click=sign)

        def show_versions():
            for file in sorted(review.folder(episode).glob("signed-*.json")):
                signed_links(versions, file.stem.removeprefix("signed-"))

        show_versions()
