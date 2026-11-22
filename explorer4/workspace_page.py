"""Fleet workspace: operator entry points, held research queue and measured outcomes."""

import asyncio
import json
import time
from pathlib import Path

from nicegui import app, ui
from . import study_queue, training_schedule
from .training_schedule_page import timing_controls
from .paths import DATA

MEDIA = DATA / "simlab"
REPORT = "reports/"
ROBOTS = (
    (
        "ROSMASTER",
        "Рука и колёсная база",
        "/rosmaster/control",
        "rosmaster_pick_place",
        "rosmaster",
        "Поднять кубик с пола",
        "/rosmaster/preparation",
    ),
    (
        "Tank",
        "Гусеничная база, RGB-D и лидар",
        "/?robot=tank",
        "tank_dock",
        "tank",
        "Подъехать к цели и остановиться",
        "/tank/sensors",
    ),
    (
        "SO-101",
        "Настольная рука и кистевая камера",
        "/?robot=so101",
        "so101_pick_place",
        "so101",
        "Переложить предмет в коробку",
        "/recording/check/so101",
    ),
)
STATES = {
    "queued": "В очереди",
    "running": "Выполняется",
    "completed": "Завершено",
    "failed": "Ошибка",
    "cancelled": "Отменено",
    "interrupted": "Прервано",
}
ARMS = {
    "local_only": "Только своё наблюдение",
    "local_scan": "Самостоятельный поиск",
    "always": "Всегда запросить",
    "selective": "Запрос по наблюдению",
    "matched_random": "Случайные запросы с тем же бюджетом",
    "stale": "Устаревший ответ",
    "shuffled": "Ответ другой сцены",
}
WORKSPACE_CSS = """
.work-head{display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:10px;width:100%}
.work-title{font-size:clamp(28px,4vw,42px);font-weight:720;letter-spacing:-.03em}
.work-section{font-size:22px;font-weight:650;margin-top:12px}
.work-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr));gap:12px;width:100%}
.work-box{border:1px solid #334151;border-radius:14px;background:#141b24;padding:16px;display:flex;flex-direction:column;gap:8px}
.work-box a{width:fit-content}.work-links{display:flex;flex-wrap:wrap;gap:14px;align-items:center}
.work-name{font-size:19px;font-weight:650}.work-muted{color:#a8b7c7}.work-row{width:100%;align-items:center;gap:12px}
"""


def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def evidence_link(title, name):
    if name and (MEDIA / name).is_file():
        ui.link(title, "/simlab-media/" + name)


def simulation_score(title, path, note, video):
    data = read(MEDIA / path)
    rows = data.get("episodes", [])
    if rows:
        count = sum(r["outcome"] == "success" for r in rows)
        ui.label(f"{title} · {count}/{len(rows)}").classes("work-name")
        ui.label(note).classes("work-muted")
        with ui.row().classes("work-links"):
            evidence_link("Исходы по сценам", path)
            evidence_link("Видео", video)


def results():
    with ui.element("div").classes("work-grid"):
        with ui.element("section").classes("work-box"):
            ui.label("ROSMASTER · подъём кубика").classes("work-name")
            base = REPORT + "recorded-start-night/"
            for description, key in [
                ("До обучения", "before"),
                ("ACT с предобучением", "after"),
                ("ACT с нуля", "control"),
            ]:
                rows = read(MEDIA / (base + key + "-result.json")).get("trials", [])
                if rows:
                    ui.label(
                        f"{description} · {sum(x['outcome'] == 'success' for x in rows)}/{len(rows)}"
                    )
            improved = read(MEDIA / (REPORT + "conditioned-grasp-v1/summary.json"))
            if improved:
                for key in ("act", "diffusion", "rbf", "ik"):
                    if key in improved["counts"]:
                        ui.label(
                            f"{key.upper()} с оценкой позиции · {improved['counts'][key]}/{improved['total']}"
                        )
            with ui.row().classes("work-links"):
                evidence_link("Сцены до и после", base + "primary-paired-scenes.csv")
                evidence_link(
                    "Новые исходы", REPORT + "conditioned-grasp-v1/summary.json"
                )
                evidence_link(
                    "Видео Diffusion",
                    REPORT + "conditioned-grasp-v1/diffusion-940200.mp4",
                )
                evidence_link(
                    "Сравнение на тех же сценах",
                    REPORT
                    + "conditioned-grasp-v1/historical_confirmation/summary.json",
                )
                evidence_link("Запись исходной серии", base + "after-seed-88300.mp4")
                evidence_link(
                    "Видео с оценкой позиции",
                    REPORT + "article-20261122/learned-motor-926000.mp4",
                )
        with ui.element("section").classes("work-box"):
            simulation_score(
                "Tank · подъезд",
                "policies/tank_dock_smoke2/eval-0.5.json",
                "Уровень сложности 0,5 в исходной серии MuJoCo.",
                "policies/tank_dock_smoke2/videos/seed100500.mp4",
            )
            simulation_score(
                "SO-101 · перекладка",
                "policies/so101_bc_v1/eval-cpu.json",
                "Разброс начальной позиции кубика ±2 см. Контроллеру доступна позиция объекта из симулятора.",
                "policies/so101_bc_v1/videos/seed200500.mp4",
            )
            so = REPORT + "so101-overhead-rgb-v1/"
            score = read(MEDIA / (so + "result.json"))
            if score:
                for method, title in (
                    ("rgb_pick_belief", "Замер по камере и энкодеры"),
                    ("constant_pick_belief", "Постоянная цель и энкодеры"),
                    ("overhead_rgb", "Последняя видимая позиция"),
                ):
                    row = score["summary"][method]
                    ui.label(f"{title} · {row['success']}/{row['episodes']} укладок")
                with ui.row().classes("work-links"):
                    evidence_link("Все шесть условий", so + "result.json")
                    evidence_link(
                        "Видео укладки", so + "rgb_pick_belief-seed200000.mp4"
                    )
                    evidence_link(
                        "Та же сцена с потерей видимости",
                        so + "overhead_rgb-seed200000.mp4",
                    )
        with ui.element("section").classes("work-box"):
            ui.label("Совместный подъезд · MuJoCo").classes("work-name")
            path = REPORT + "peer-observation-dock-v1/"
            res = read(MEDIA / (path + "result.json"))
            if res:
                for key, row in res["conditions"].items():
                    ui.label(
                        f"{ARMS.get(key, key)} · {row['successes']}/{res['scenes']} · запросов {row['calls']}"
                    )
                with ui.row().classes("work-links"):
                    evidence_link("Все сцены", path + "result.json")
                    evidence_link("Видео подъезда", path + "replay-848000.mp4")
                    if replay := next(iter(res.get("evidence", [])), None):
                        evidence_link("Кадр помощника", path + replay["donor_frame"])
                        evidence_link("Конечное положение", path + replay["overview"])
            else:
                ui.label(
                    "Итог появится после парных попыток с камерой получателя и помощника."
                )
            screen = REPORT + "peer-screen-dock-v2/"
            dev = read(MEDIA / (screen + "development.json")).get("rows", [])
            if dev:
                ui.label("Ширма · сцены подготовки").classes("work-name")
                ui.label(
                    f"Самостоятельный обзор {sum(r['local'] for r in dev)}/{len(dev)}, с напарником {sum(r['peer'] for r in dev)}/{len(dev)}."
                )
                with ui.row().classes("work-links"):
                    evidence_link("Исходы подготовки", screen + "development.json")
                    evidence_link("Видео со ширмой", screen + "replay-861000.mp4")
            ui.link("Общая сцена MuJoCo", "/sim/fleet")
            ui.link("Запуск агента помощи", "/team")
            ui.link("Заказ для трёх роботов", "/team/three")
            ui.link(
                "Доставка в 96 комнатах · журнал и парные исходы",
                "/simlab-media/reports/room-study-e1/index.html",
            )


def install(jobs, css):
    @app.get("/api/workspace/queue")
    def queue_info():
        return {**study_queue.status(), "training_jobs": training_schedule.queue()}

    @ui.page("/workspace")
    async def workspace():
        ui.add_css(css + WORKSPACE_CSS)
        ui.dark_mode().enable()
        ui.colors(primary="#238a77")
        with ui.element("header").classes("work-head"):
            ui.label("Центр экспериментов").classes("work-title")
            with ui.row().classes("work-links"):
                ui.link(
                    "Исследования и изменения в коде",
                    "/simlab-media/reports/research-register-20261122/lineage.html",
                )
                ui.link("Пульт", "/")
                ui.link("Совместное управление", "/swarm")
                ui.link("Все датчики", "/fleet/live")
        ui.label("Роботы и навыки").classes("work-section")
        with ui.element("div").classes("work-grid"):
            for name, role, remote, profile, robot, task, sensors in ROBOTS:
                with ui.element("section").classes("work-box"):
                    ui.label(name).classes("work-name")
                    ui.label(role).classes("work-muted")
                    ui.label(task)
                    with ui.row().classes("work-links"):
                        ui.link("Управление", remote)
                        ui.link("Показы", "/learn?tab=real&profile=" + profile)
                        ui.link("Подготовка", sensors)
                    if robot == "rosmaster":
                        ui.link("Ведение руки с помощью SO-101", remote)
        with ui.expansion("Что умеют отдельные машины и команда", icon="route").classes(
            "w-full"
        ):
            rows = [
                (
                    "Tank и ROSMASTER",
                    "Осмотр комнаты, поиск, подъезд по карте",
                    "Есть исполнитель и журнал полевых попыток",
                    "/swarm",
                ),
                (
                    "Tank и ROSMASTER",
                    "Распознавание объектов",
                    "YOLOE и SAM 3 на сохранённом изображении",
                    "/sim/vision",
                ),
                (
                    "Tank и ROSMASTER",
                    "Подъезд по сообщению напарника",
                    "Проверка с двумя камерами и размеченной целью",
                    "/peer-dock-real",
                ),
                (
                    "SO-101",
                    "Ручной показ, передача предмета",
                    "Запись действий и камеры, проверка датасета",
                    "/recording/collect",
                ),
                (
                    "ROSMASTER",
                    "Ручной захват и зеркальное управление",
                    "Пульт с ведущей рукой SO-101",
                    "/rosmaster/control",
                ),
                (
                    "Все три",
                    "Совместная миссия и обмен навыками",
                    "Выбор участников и журнал выполнения",
                    "/swarm",
                ),
                (
                    "Все три",
                    "Общая сцена и воспроизведение эпизода",
                    "Три робота в одном пространстве MuJoCo",
                    "/sim/fleet",
                ),
            ]
            for who, task, available, url in rows:
                with ui.row().classes("work-links"):
                    ui.label(who)
                    ui.link(task, url)
                    ui.label(available).classes("work-muted")
            ui.label(
                "Сортировка по нескольким коробкам и непрерывное сопровождение человека требуют самостоятельной проверки."
            ).classes("work-muted")
        ui.label("Очередь обучения").classes("work-section").props("id=training-queue")
        ui.label(
            "Два независимых эксперимента. Оба работают на Homebrain. Порядок задан заранее."
        ).classes("work-muted")
        with ui.element("div").classes("work-grid"):
            with ui.element("section").classes("work-box"):
                ui.label(study_queue.LABELS["grasp_replication"]).classes("work-name")
                ui.label(
                    "32 показанные траектории. Повторяем обучение с seed 1001. В одинаковых сценах сравниваем ACT, Diffusion, интерполяцию, обратную кинематику и постоянную цель."
                )
            with ui.element("section").classes("work-box"):
                ui.label(study_queue.LABELS["peer_learning"]).classes("work-name")
                ui.label(
                    "По парным попыткам учим робота решать, когда нужна камера напарника. На отдельных сценах сравниваем исходы и число запросов."
                )
        queue_box = ui.column().classes("work-row")

        def message(exc):
            ui.notify(str(exc), type="negative", multi_line=True)

        async def update_plan():
            try:
                await asyncio.to_thread(study_queue.prepare)
                queue_view.refresh()
            except (ValueError, OSError) as exc:
                message(exc)

        async def enqueue_plan(plan):
            try:
                await asyncio.to_thread(study_queue.stage, plan)
                queue_view.refresh()
            except (ValueError, OSError) as exc:
                message(exc)

        async def retry(ident):
            try:
                await asyncio.to_thread(jobs.resume, ident)
                queue_view.refresh()
            except (ValueError, OSError) as exc:
                message(exc)

        @ui.refreshable
        def queue_view():
            snapshot = study_queue.status()
            key = snapshot["plan"]
            with ui.row().classes("work-links"):
                if not key:
                    ui.button("Подготовить очередь", on_click=update_plan)
                elif not snapshot["tracks"]:
                    ui.label("План двух экспериментов готов").classes("work-name")
                    ui.label("Версия " + key[:12]).classes("work-muted")
                    ui.button(
                        "Обновить подготовленный план", on_click=update_plan
                    ).props("flat")
                    ui.button(
                        "Поставить в очередь",
                        on_click=lambda: enqueue_plan(key),
                    )
                else:
                    for job in snapshot["tracks"]:
                        ui.label(
                            study_queue.LABELS[job["track"]]
                            + " · "
                            + STATES.get(job["status"], job["status"])
                        )
                        ui.link("Журнал", "/jobs/" + job["id"])
                        if job["status"] == "completed":
                            evidence_link(
                                "Результат",
                                f"reports/workspace/{key}/{job['track']}/result.json",
                            )
                        if job["status"] in ("failed", "cancelled", "interrupted"):
                            ui.button(
                                "Продолжить", on_click=lambda i=job["id"]: retry(i)
                            ).props("flat")
                            if job["error"]:
                                ui.label(job["error"])
                ui.link("Все задания", "/learn?tab=jobs")
            pending = training_schedule.queue()
            for job in pending:
                title = study_queue.LABELS.get(
                    job["track"], job["profile"] + " · " + job["policy"].upper()
                )
                when = job["not_before"]
                if when is None:
                    detail = "ждёт команды"
                elif when > time.time():
                    detail = "старт " + training_schedule.local_label(when)
                else:
                    detail = "ожидает свободного исполнителя"
                ui.label(title + " · " + detail).classes("work-muted")

        with queue_box:
            queue_view()
            timing_controls(queue_view.refresh)
            ui.label(
                "Назначенное время указано по Москве. Если Homebrain выключен, очередь сможет стартовать при следующем включении. Новые задания ожидают отдельной команды."
            ).classes("work-muted")
        ui.timer(15, queue_view.refresh)
        ui.label("Результаты в симуляции").classes("work-section")
        results()
        ui.label("Проверка на реальных роботах").classes("work-section").props(
            "id=field-checks"
        )
        ui.link("Единый список подготовки и файлы печати", "/field-session")
        bridge = read(DATA / "ros2-hub/status.json")
        age = time.time() - bridge.get("updated_at", 0)
        if age < 10 and bridge.get("running"):
            pairing = (
                "совпала" if bridge.get("pairing", {}).get("matched") else "вне допуска"
            )
            ui.label(
                f"При открытии панели пара RGB-D {pairing}. Общая система координат "
                + (
                    "подтверждена."
                    if bridge.get("shared_map_ready")
                    else "требует измерения."
                )
            )
        else:
            ui.label("Нет свежего статуса моста ROS 2.")
        ui.label(
            "Для проверки помощи в комнате нужны метка на цели, измеренное взаимное положение камер и наблюдаемая конечная позиция. Захват на полу проверяется отдельной физической попыткой."
        )
        station_note = ui.label().classes("work-muted")

        async def check_station():
            from .station_check import capture

            reading = await asyncio.to_thread(capture)
            station_note.set_text(
                ("Камера SO-101 · ошибка %.2f px" % reading["control"]["error_px"])
                if reading["ok"]
                else "Камера SO-101 · " + reading["reason"]
            )

        with ui.row().classes("work-links"):
            ui.button(
                "Проверить камеру SO-101 без движения", on_click=check_station
            ).props("outline no-caps")
            ui.link("Совместный подъезд и лист-мишень", "/peer-dock-real")
            ui.link("Подготовить физическую проверку", "/team/real")
            ui.link("Записать показ", "/recording/collect")
            ui.link(
                "Камера и положение кубика ROSMASTER", "/rosmaster/grasp-calibration"
            )
            evidence_link(
                "Перенос новых политик ROSMASTER",
                REPORT + "conditioned-grasp-v1/physical-shadow.json",
            )
            evidence_link(
                "Состояние сенсоров и привязок камер",
                REPORT + "research-register-20261122/fleet-sensor-readiness.json",
            )
            evidence_link(
                "Проверка ACT на записях ROSMASTER",
                REPORT + "research-register-20261122/deployment-shadow-orin.json",
            )
            evidence_link(
                "Проверка внешнего ACT на записях SO-101",
                REPORT + "so101-external-shadow.json",
            )
            evidence_link(
                "Привязка верхней камеры SO-101", REPORT + "so101-station-check.json"
            )
            evidence_link(
                "Перенос зрительного энкодера SO-101",
                REPORT + "so101-encoder-initialization.json",
            )
            evidence_link(
                "Реестр методов и источников",
                REPORT + "research-register-20261122/index.html",
            )
