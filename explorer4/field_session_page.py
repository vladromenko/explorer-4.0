"""One preparation list for the physical session and its metric print targets."""

from fastapi.responses import FileResponse
from nicegui import app, run, ui

from .paths import ROOT
from . import field_time


def time_panel():
    with ui.expansion("Время работы участников", icon="timer").classes("w-full"):
        ui.label(
            "Отмечайте только наблюдаемое время одного человека. Для общего ресурса укажите только работу, общую для условий сравнения показов."
        )
        person = ui.input("Участник (имя или постоянный код)", value="оператор")
        activity = ui.select(field_time.CATEGORIES, value="preparation", label="Вид работы").classes("w-full")
        selected = {"resource": "common"}

        async def handle(function, *args, **kwargs):
            try:
                result = await run.io_bound(function, *args, **kwargs)
                if isinstance(result, dict) and "origin_resource" in result:
                    selected["resource"] = result["origin_resource"]
                view.refresh()
            except (KeyError, ValueError, OSError) as error:
                ui.notify(str(error), type="negative")

        @ui.refreshable
        def view():
            state = field_time.read()
            choices = field_time.labels(state)
            resource = ui.select(choices, value=selected["resource"], label="Ресурс").classes("w-full")
            ui.button(
                "Начать отсчёт",
                on_click=lambda: handle(field_time.start, person.value, activity.value, resource.value),
            )
            for ident, event in state["active"].items():
                with ui.row().classes("items-center"):
                    ui.label(
                        f"{event['person_id']} · {field_time.CATEGORIES[event['activity']]} · {choices.get(event['origin_resource'], event['origin_resource'])}"
                    )
                    ui.button("Завершить", on_click=lambda _, key=ident: handle(field_time.stop, key))
                    ui.button(
                        "Закрыть без замера",
                        on_click=lambda _, key=ident: handle(field_time.stop, key, unmeasured=True),
                    ).props("flat")
            report = field_time.summary(state)
            ui.label(
                f"Засечено {report['known_minutes']:.2f} чел.-мин, включая подготовку {report['known_preparation_minutes']:.2f}. Полные затраты с историческими показами неизвестны."
            )
            pending = {
                k: label
                for k, label in choices.items()
                if k.startswith("pending-donor:") and not state["bindings"].get(k)
            }
            donors = {k: label for k, label in choices.items() if k.startswith("donor:")}
            used = {e["origin_resource"] for e in [*state["active"].values(), *state["intervals"]]}
            used.update(k for children in state["bindings"].values() for k in children)
            used_donors = {k: v for k, v in donors.items() if k in used}
            if pending and donors:
                with ui.row().classes("items-center"):
                    waiting = ui.select(pending, label="Засеченный показ", value=next(iter(pending)))
                    take = ui.select(donors, label="Сохранённая запись SO-101")
                    ui.button(
                        "Связать с записью",
                        on_click=lambda: handle(
                            field_time.bind, waiting.value, take.value or "", person.value
                        ),
                    )
            if used_donors:
                candidates = sorted(p.stem for p in (field_time.DATA / "world/skill_packets").glob("*.json"))
                for k, label in used_donors.items():
                    links = list(state["bindings"].get(k, {}))
                    ui.label(
                        label + (" · SkillPacket " + ", ".join(links) if links else " · пока без SkillPacket")
                    )
                if candidates:
                    donor = ui.select(used_donors, label="Измеренный показ", value=next(iter(used_donors)))
                    packet = ui.select(candidates, label="SHA пакета")
                    ui.button(
                        "Связать с проверенным пакетом",
                        on_click=lambda: handle(
                            field_time.bind, donor.value, packet.value or "", person.value
                        ),
                    )
            if pending and not donors:
                ui.label("Ожидается сохранённая измеренная запись SO-101 для привязки.")
            ui.button("Обновить список записей", on_click=view.refresh).props("flat")
            ui.link("Журнал для расчёта человеко-минут", "/api/workspace/field-time-ledger.json")

        view()


def install():
    @app.get("/api/workspace/field-time-ledger.json")
    def time_ledger():
        return field_time.read()

    @app.get("/api/workspace/field-targets.pdf")
    def print_pack():
        return FileResponse(
            ROOT / "assets/field-targets-A4.pdf",
            media_type="application/pdf",
            filename="Explorer-4-field-targets-A4.pdf",
        )

    @ui.page("/field-session")
    def page():
        ui.dark_mode().enable()
        with ui.column().classes("w-full max-w-3xl mx-auto p-5 gap-3"):
            ui.link("Центр экспериментов", "/workspace")
            ui.label("Подготовка к физической проверке").classes("text-3xl font-bold")
            ui.label(
                "Для симуляции, очереди обучения и просмотра записей подготовка площадки не требуется."
            )
            ui.label("Что взять за один раз").classes("text-xl font-medium")
            ui.label(
                "Линейка или рулетка, малярная лента, угольник или транспортир, кубик и материал для ширмы. Для настольной перекладки также понадобится коробка."
            )
            ui.link(
                "Один PDF для печати · A4, 100%, односторонняя печать",
                "/api/workspace/field-targets.pdf",
            )
            ui.label(
                "Для совместного подъезда используйте страницу 1 или неподвижный вертикальный экран. Линейкой проверьте чёрную сторону большой метки №7 (180 мм) и нижней №43 (36 мм). Страница 2 с меткой 20 мм пригодится только для отдельного опыта с меченым кубиком."
            )
            ui.link("Мишень на экране с настройкой масштаба", "/peer-dock-real/screen")
            ui.label("1. Совместный подъезд Tank и ROSMASTER").classes(
                "text-xl font-medium"
            )
            ui.label(
                "Когда обе машины включены и стоят при STOP, откройте страницу двух камер. Если Tank уже на общей карте, а ROSMASTER ещё не локализован, измерьте смещение ROSMASTER вперёд и влево от центра Tank и угол между передними осями. Панель проверит введённую позу по лидарам. Закрепите мишень вертикально в поле зрения обеих камер. Снимите кадры и сохраните первое измерение для каждой камеры. Сдвиньте мишень вдоль той же стены минимум на 10 см и подтвердите обе камеры во второй измеренной точке."
            )
            ui.label(
                "Отметьте лентой исходные положения и направления машин, крест для центра Tank в 277 мм от мишени и ось курса к стене. В расстановке A откройте обзор Tank, в B закройте его ширмой, сохранив обзор ROSMASTER и свободный путь. Для каждой назначенной попытки восстановите расстановку и запустите её из ручного пульта Tank. В новой серии к восьми исходным назначениям добавлены четыре с запросом к ROSMASTER после собственного поиска. По завершении нажмите STOP. Через 0,5 с неподвижности измерьте ошибки центра и курса, пока Tank стоит на месте."
            )
            ui.link("Две камеры, разметка и полевой журнал", "/peer-dock-real")
            ui.label("2. Подъём кубика рукой ROSMASTER").classes("text-xl font-medium")
            ui.label(
                "Для трёх захватов достаточно того же кубика без дополнительной метки. Зафиксируйте шасси и установите руку с камерой в позу обзора из мастера. Измерьте ширину кубика и открытого захвата. Сделайте три неподвижных снимка для настройки и два для проверки. Для каждого снимка измерьте центр кубика относительно основания."
            )
            ui.label(
                "После успешной проверки камеры мастер покажет первые три измеренные точки по очереди. В каждой начните из позы обзора, оставьте целый кубик неподвижным в кадре на секунду, затем вручную возьмите и удержите его. Укажите фактический исход каждой попытки. Для допуска нужен успешный показ в каждой точке. Старые учебные показы уже сохранены."
            )
            ui.label(
                "Когда мастер подтвердит допуск, он откроет одну автоматическую пробу в четвёртой точке. Наблюдайте подъём и время удержания. Введите замер после завершения пробы и подтверждённого STOP. Критерий успеха — отрыв более 50 мм с непрерывным удержанием не меньше секунды."
            )
            ui.link(
                "Мастер камеры и регистрации показов", "/rosmaster/grasp-calibration"
            )
            ui.label("3. Настольная рука SO-101 · дополнительный опыт").classes(
                "text-xl font-medium"
            )
            ui.label(
                "Проверьте верхнюю камеру по существующей красной метке на белом фоне на подвижной губке в её откалиброванном месте. Для повтора архивного опыта используйте кубик 29 мм с AprilTag 36h11 №1 в центре верхней грани. Измерьте чёрную сторону метки — в исходной регистрации 20 мм."
            )
            ui.link("Параметры метки кубика SO-101", "/recording/collect?task=so101_pick_place")
            ui.link("Проверка камеры SO-101", "/workspace#field-checks")
            ui.link(
                "Четыре фазы архивного показа · кадры и список для одной новой записи",
                "/simlab-media/reports/so101-instance-replay-v3/donor-phases/index.html",
            )
            ui.label(
                "В архиве непрерывный однозначный обзор метки длится максимум 0,30 с. Для донорского показа подводите губки сбоку, сохраняя все четыре угла метки в кадре. После проверки калибровки поднимите кубик минимум на 50 мм и удерживайте минимум секунду. По видео отметьте подход, смыкание, подъём и удержание."
            )
            ui.label(
                "Если проверяете узнавание одного кубика двумя роботами, оставьте AprilTag №1 на том же 29-мм кубике. При STOP покажите его камере ROSMASTER и проверьте №1 на сохранённом кадре. Исходный кадр SO-101 уже есть."
            )
            ui.link("Метрическая калибровка захвата SO-101", "/recording/so101-calibration")
            ui.link("Проверить метку кубика на ROSMASTER", "/rosmaster/sensors?object_marker=true")
            time_panel()
