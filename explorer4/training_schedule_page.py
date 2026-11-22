"""Start-time field for the ordinary training queue."""

import time

from nicegui import ui

from . import training_schedule


def timing_controls(refresh):
    """Keep the selected date while the surrounding job list polls for changes."""
    with ui.row().classes("work-links items-center"):
        mode = ui.select(
            {
                "now": "По команде",
                "timed": "В указанное время",
                "hold": "Отложить запуск",
            },
            value="now",
            label="Запуск очереди",
        ).style("min-width:190px")
        date = ui.input(label="Дата и время по Москве").props(
            "type=datetime-local stack-label"
        )
        date.bind_visibility_from(
            mode, "value", backward=lambda value: value == "timed"
        )

        def submit():
            try:
                if mode.value == "timed":
                    when = training_schedule.local_start(date.value)
                elif mode.value == "hold":
                    when = None
                else:
                    when = time.time()
                selected = [r["id"] for r in training_schedule.queue()]
                count = training_schedule.set_start(selected, when)
                refresh()
                ui.notify(f"Обновлено заданий: {count}", type="positive")
            except (ValueError, OSError) as exc:
                ui.notify(str(exc), type="negative")

        button = ui.button("Запустить", on_click=submit)
        button.bind_text_from(
            mode,
            "value",
            backward=lambda value: "Запустить" if value == "now" else "Сохранить",
        )
