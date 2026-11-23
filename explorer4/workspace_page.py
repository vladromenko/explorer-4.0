"""Fleet workspace: operator entry points, held research queue and measured outcomes."""

import asyncio
import json
import time
from pathlib import Path

from nicegui import app, ui
from . import catalog, study_queue, training_schedule
from .training_schedule_page import timing_controls
from .paths import DATA
from .policy_catalog import SMOL_REV

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


def methods():
    register = REPORT + "research-register-20261122/"
    smol_path = register + "evidence/e3_diagnostics/smolvla_v4_state.json"
    sam_path = REPORT + "so101-instance-replay-v3/"
    with ui.element("div").classes("work-grid"):
        with ui.element("section").classes("work-box"):
            ui.label("SmolVLA · обучение управлению").classes("work-name")
            archived = read(MEDIA / smol_path)
            if archived.get("stage") == "completed":
                protocol = archived["protocol"]
                steps = format(protocol["steps"], ",").replace(",", " ")
                ui.label("ROSMASTER в MuJoCo · поднять с пола кубик, бутылку, брусок или мяч и удержать в позе переноса")
                ui.label(
                    f"{archived['successes']} пар показов симулятора с одинаковыми кадрами и действиями. "
                    f"Различается текст команды. Каждая версия прошла {steps} обновлений."
                ).classes("work-muted")
                for name, title in (("knowledge", "С размером"), ("noknowledge", "Без размера")):
                    profile = f"rosmaster_floor_pick_{name}_sim"
                    job = archived["jobs"][profile]
                    trials = job["result"]["trials"]
                    held = sum(r["outcome"] == "success" and r["reason"] == "held_in_carry_pose" for r in trials)
                    ui.link(f"{title} · {held}/{len(trials)} удержаний в позе переноса", "/jobs/" + job["evaluation"])
                object_audit = register + "evidence/smolvla-v4-objects.json"
                evidence_link("Что удалось удержать · брусок и кубик", object_audit)
                split = archived["plans"]["rosmaster_floor_pick_knowledge_sim"]["scenes"]
                ui.label(
                    f"В каждой версии {len(split['train'])} учебных, {len(split['validation'])} "
                    f"валидационных и {len(split['test'])} отложенных. Для оценки обеих моделей взяли "
                    f"одни и те же новые сцены {protocol['evaluation_seeds'][0]}–{protocol['evaluation_seeds'][1]}. "
                    "У текущего сравнения ACT и Diffusion другой набор из 32 показов."
                ).classes("work-muted")
            else:
                ui.label("Архив парного опыта с подсказкой о размере недоступен.")
            with ui.row().classes("work-links"):
                evidence_link("Показы, веса и все исходы", smol_path)
                ui.link("Исходная SmolVLA 450M", "https://huggingface.co/lerobot/smolvla_base/tree/" + SMOL_REV)
                evidence_link("Реестр обучения", register + "learning.html")
                ui.link("Задания обучения", "/learn?tab=jobs")
            with catalog.connect() as db:
                current = db.execute(
                    """SELECT id, status, json_extract(config,'$.steps') AS steps FROM jobs
                       WHERE policy='smolvla' AND json_type(config,'$.smolvla_development')='object'
                       ORDER BY created DESC LIMIT 1"""
                ).fetchone()
            if current:
                states = {"queued": "в очереди", "running": "идёт", "completed": "завершено",
                          "failed": "сбой", "interrupted": "прервано", "cancelled": "отменено"}
                state = states.get(current["status"], current["status"])
                ui.link(f"SmolVLA на 32 показах · {current['steps']} шагов · {state}", "/jobs/" + current["id"])
                path = REPORT + f"smolvla-recorded-start/{current['id']}/result.json"
                scores = read(MEDIA / path).get("results", {})
                if scores:
                    initial = scores["smolvla_0_updates"]
                    trained = scores["smolvla_finetuned"]
                    ui.label(f"Удержания на восьми сценах · исходные веса {initial['task_successes']}/{initial['scenes']}, "
                             f"после обучения {trained['task_successes']}/{trained['scenes']}.")
                evidence_link("Исходы на восьми стартовых сценах", path)
        with ui.element("section").classes("work-box"):
            ui.label("SAM 3 и YOLOE · зрение по готовым весам").classes("work-name")
            report = read(MEDIA / (sam_path + "result.json"))
            if report:
                control = report["positive_marker_box_control"]
                ui.label("Реальный кадр SO-101 · две подсказки без дообучения")
                ui.label(
                    f"По слову «{report['segmentation']['prompt']}» модель выделила другой участок кадра. "
                    f"При подсказке рамкой вокруг метки модель выдала {len(control['scores'])} маски. "
                    f"Все четыре угла метки попали в {sum(row['marker_corners_inside'] == 4 for row in control['mask_corner_coverage'])} из них."
                ).classes("work-muted")
                image_path = sam_path + "first-frame.png"
                if (MEDIA / image_path).is_file():
                    with ui.link(target="/simlab-media/" + image_path).style("width:100%;max-width:330px"):
                        ui.image("/simlab-media/" + image_path).props(
                            'fit=contain alt="Метка кубика и область, которую SAM 3 выделила по слову cube"'
                        ).style("width:100%;max-width:330px;aspect-ratio:1.6").classes("rounded")
                ui.label("Зелёный контур — зарегистрированный кубик, жёлтая рамка — ответ на текст. Захват здесь не проверялся.").classes("work-muted")
            else:
                ui.label("Архив проверки на реальном кадре недоступен.")
            comparison_path = REPORT + "cube-detector-comparison-v1/result.json"
            comparison = read(MEDIA / comparison_path).get("summary", {})
            if comparison:
                ui.label("Сравнение на 12 реальных кадрах SO-101 из одного показа")
                for prompt, label in (("cube", "Кубик"),
                                      ("cube with a black and white marker on top", "Кубик с чёрно-белой меткой сверху")):
                    counts = []
                    for method, name in (("sam3", "SAM 3"), ("yoloe", "YOLOE")):
                        score = comparison[method][prompt]
                        counts.append(f"{name} {score['top_covers_tag']}/{score['readable_tag_frames']}")
                    ui.label(f"«{label}» · " + ", ".join(counts))
                ui.label("Засчитаны кадры, где рамка с наибольшей уверенностью охватила все четыре угла читаемой метки.").classes("work-muted")
            with ui.row().classes("work-links"):
                evidence_link("Результаты обеих подсказок", sam_path + "result.json")
                if report:
                    ui.link("Веса Meta SAM 3", "https://huggingface.co/facebook/sam3/tree/" + report["sam_revision"])
                evidence_link("YOLOE и SAM 3 на 12 кадрах", comparison_path)
                ui.link("Проверка зрения", "/sim/vision")
        with ui.element("section").classes("work-box"):
            ui.label("Обучение с подкреплением · Tank").classes("work-name")
            archived_ppo = "policies/tank_dock_smoke2/eval-0.5.json"
            episodes = read(MEDIA / archived_ppo).get("episodes", [])
            if episodes:
                held = sum(row["outcome"] == "success" for row in episodes)
                ui.label(f"PPO обучалась управлять двумя командами шасси за награду. В архивной проверке — {held}/{len(episodes)} стыковок.")
                camera = read(MEDIA / (REPORT + "tank-ppo-camera-v1/result.json")).get("methods", {})
                if camera:
                    learned, offset = camera["rgb_ppo"], camera["offset_ppo"]
                    ui.label(
                        f"Камера MuJoCo и OpenCV · {learned['success']}/{learned['scenes']} стыковок, "
                        f"столкновений {learned['collision']}. При ошибке направления на 30° — "
                        f"{offset['success']}/{offset['scenes']}."
                    )
                ui.label("В архивной серии положение цели поступало от имитированного датчика с шумом.").classes("work-muted")
                evidence_link("PPO · исходы и ошибки положения", archived_ppo)
                evidence_link("PPO и геометрическое управление по одной камере", REPORT + "tank-ppo-camera-v1/result.json")
                nav = REPORT + "tank-nav2-camera-v1/"
                controllers = read(MEDIA / (nav + "result.json")).get("methods", {})
                if controllers:
                    classic, learned = controllers["nav2_memory"], controllers["ppo_memory"]
                    ui.label(f"На новых стартах с сохранением положения цели · "
                             f"Nav2 {classic['success']}/{classic['scenes']}, PPO {learned['success']}/{learned['scenes']}.")
                    evidence_link("Сравнение штатного регулятора Nav2 и PPO", nav + "result.json")
                    evidence_link("Видео подъезда на первой общей сцене", nav + "comparison.mp4")
            ui.label("Управление по показам и обратной связи").classes("work-name")
            ui.label("LeRobot ACT и Diffusion обучены на показах ROSMASTER. Внешнюю ACT для SO-101 проверяли по ранее записанным действиям оператора.")
            with ui.row().classes("work-links"):
                evidence_link("ACT и Diffusion · исходы", REPORT + "conditioned-grasp-v1/summary.json")
                evidence_link("Внешняя ACT · воспроизведение", REPORT + "so101-external-shadow.json")
                evidence_link("Коррекция по новому кадру · смещение кубика", REPORT + "grasp-look-refresh-development-v1-1/result.json")
                evidence_link("Камера после начала движения · проверка DAgger и возврата в обзор", REPORT + "grasp-dagger-v1/result.json")
                evidence_link("Выбор 32 показов по положению кубика", REPORT + "rosmaster-grasp-coverage-design-v1-1/result.json")
            ui.label("ROS 2 и Nav2 · в проверке Tank и ROSMASTER поступали лидары и одометрия. Для штатной навигации нужны привязка карты и доступный сервер NavigateToPose.")
            with ui.row().classes("work-links"):
                evidence_link("Что ответило по ROS 2", register + "nav2-readiness.json")
                evidence_link("Драйверы и контроллеры роботов", register + "robots.html")
            ui.label("NoMaD рассматривается для Tank после проверки локализации и задержки на записях. Для дообучения π0 требуется больше памяти, чем доступно на Homebrain.").classes("work-muted")
            with ui.row().classes("work-links"):
                evidence_link("Сравнение исходных работ и кода", register + "lineage.html")


def results():
    with ui.element("div").classes("work-grid"):
        with ui.element("section").classes("work-box"):
            ui.label("ROSMASTER · подъём кубика").classes("work-name")
            base = REPORT + "recorded-start-night/"
            ui.label("Исходная серия · сцены 88300–88319").classes("work-muted")
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
            comparison = REPORT + "research-register-20261122/evidence/conditioned_grasp_v1/optimizer-seed-1001.json"
            replica = read(MEDIA / comparison)
            if improved:
                ui.label("С оценкой положения из камеры · сцены 940200–940219").classes("work-muted")
                fresh = replica.get("blocks", {}).get("fresh", {})
                for key, name in (("act", "ACT"), ("diffusion", "Diffusion"), ("rbf", "Интерполяция"), ("ik", "Обратная кинематика")):
                    if key not in improved["counts"]:
                        continue
                    total = improved["total"]
                    count = improved["counts"][key]
                    matched = fresh.get("paired_counts", {}).get(key)
                    if key in ("act", "diffusion") and matched and fresh["total"] == total:
                        repeated = matched["both"] + matched["replica_only"]
                        ui.label(f"{name} · {count}/{total} при первом обучении, {repeated}/{total} при повторном")
                    else:
                        ui.label(f"{name} · {count}/{total}")
            field_report = REPORT + "grasp-admission-native-v3/result.json"
            field = read(MEDIA / field_report)
            if field:
                historic, selected = field["historical"], field["conditional"]
                ui.label("Штатное управление ROSMASTER в симуляции").classes("work-muted")
                ui.label(
                    f"На исходных {historic['denominator']} сценах удержаний {historic['terminal_holds']}. "
                    f"Для точек с видимым кубиком внутри области показов — "
                    f"{selected['terminal_holds']}/{selected['n']}. "
                    f"Критериям подходили {selected['eligible_candidates']} из {len(selected['source_bank'])} стартов."
                )
                evidence_link("Сцены, отказы и удержание в конце команды", field_report)
            watch_path = REPORT + "wrist-video-failure-watch-v1/paired-test/"
            watch = read(MEDIA / watch_path / "result.json")
            if watch.get("pairs"):
                n = len(watch["pairs"])
                original = sum(row["stale_hold"] for row in watch["pairs"])
                repeated = sum(row["recovery_hold"] for row in watch["pairs"])
                ui.label(f"Повторный взгляд перед захватом · {original}/{n} → {repeated}/{n} в MuJoCo")
                evidence_link("Видео одной и той же попытки с повторным взглядом и без", watch_path + "first-rescued.webm")
                evidence_link("Исходы и ошибки предупреждения", watch_path + "result.json")
            refresh_path = REPORT + "grasp-look-refresh-development-v1-1/result.json"
            refresh = read(MEDIA / refresh_path).get("all_scenes", {}).get("shifted")
            if refresh:
                ui.label(
                    f"Кубик смещён на 10 мм · по первому кадру {refresh['first_holds']}/{refresh['n']}, "
                    f"по повторному {refresh['refresh_holds']}/{refresh['n']} удержаний в сценах подготовки."
                )
            with ui.row().classes("work-links"):
                if refresh:
                    evidence_link("Сравнение двух кадров", refresh_path)
                evidence_link("Два обучения на одних и тех же 20 сценах", comparison)
                evidence_link("Исходные 20 сцен до и после обучения", base + "primary-paired-scenes.csv")
                evidence_link(
                    "Новые исходы", REPORT + "conditioned-grasp-v1/summary.json"
                )
                evidence_link(
                    "Видео Diffusion",
                    REPORT + "conditioned-grasp-v1/diffusion-940200.mp4",
                )
                evidence_link(
                    "Сравнение с прямым управлением по RGB · сцены 88500–88519",
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
            comparison_path = REPORT + "peer-screen-sequential-development/summary.json"
            sequential = read(MEDIA / comparison_path).get("summary", {}).get("sequential")
            if sequential:
                ui.label(
                    f"Поиск, затем запрос при промахе · {sequential['successes']}/{sequential['n']} стыковки, "
                    f"запросов {sequential['calls']}."
                )
                evidence_link("Время и запросы на тех же сценах", comparison_path)
            ui.link("Общая сцена MuJoCo", "/sim/fleet")
            ui.link("Запуск агента помощи", "/team")
            ui.link("Заказ для трёх роботов", "/team/three")
            confirmation = REPORT + "research-register-20261122/evidence/peer-camera-docking/sequential-confirmation-results.json"
            confirmed = read(MEDIA / confirmation).get("methods", {})
            if confirmed:
                ui.label("Ширма · проверка на 16 общих сценах").classes("work-name")
                for key, label in (("local_scan", "Только локальный поиск"), ("immediate_peer", "Сразу звать напарника"),
                                   ("learned", "Обученный выбор"), ("sequential", "Осмотр, затем запрос")):
                    row = confirmed[key]
                    ui.label(f"{label} · {row['successes']}/{row['scenes']} стыковок, запросов {row['calls']}")
                evidence_link("Методы, исходные сцены и восстановление кадра", confirmation)
            pilot_path = REPORT + "peer-action-value-v1/evidence.json"
            common_budget = read(MEDIA / pilot_path)
            if common_budget.get("method_summary"):
                n = common_budget["n_unique_scenes"]
                outcomes = common_budget["method_summary"]
                sequential = outcomes[common_budget["strongest_local_first"]]
                adaptive = outcomes["adaptive"]
                ui.label(f"Общий лимит времени · Tank один {outcomes['local_only']['win']}/{n}, "
                         f"после поиска с помощью {sequential['win']}/{n}, "
                         f"обученный выбор {adaptive['win']}/{n}.")
                evidence_link("Выбор помощи при ограниченном времени · парные исходы", pilot_path)
            local_path = REPORT + "peer-local-six-seconds/result.json"
            local_check = read(MEDIA / local_path)
            if local_check.get("summary"):
                n = local_check["n"]
                local = local_check["summary"]
                ui.label(
                    f"Самостоятельный поиск до 6 с на тех же {n} сценах · "
                    f"исходный поворот {local['extend_heading']['successes']}/{n}, "
                    f"дуга влево {local['arc_left']['successes']}/{n}, "
                    f"вправо {local['arc_right']['successes']}/{n}."
                )
                evidence_link("Дополнительная проверка времени и траектории поиска", local_path)
            evidence_link("Аудит, методы и практические ограничения", REPORT + "research-register-20261122/audit.html")
            evidence_link("Воспроизвести результаты и таблицы статьи", REPORT + "explorer-audit-20261123/reproduction.zip")
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
                ui.link("Модели и библиотеки", "#methods")
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
        ui.link_target("methods")
        ui.label("Модели и библиотеки").classes("work-section")
        methods()
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
                        if job["track"] == "peer_learning":
                            confirmation = json.loads(jobs.get(job["id"])["config"]).get("peer_confirmation")
                            if confirmation:
                                path = f"reports/peer-sequential-confirmation/{confirmation}/"
                                evidence_link("Протокол сравнения на 16 сценах", path + "protocol.json")
                                if (MEDIA / path / "summary.json").is_file():
                                    evidence_link("Обученный выбор и поиск до вызова", path + "summary.json")
                        if job["status"] == "completed":
                            evidence_link(
                                "Результат",
                                f"reports/workspace/{key}/{job['track']}/result.json",
                            )
                            if job["track"] == "grasp_replication":
                                path = f"reports/workspace/{key}/grasp_replication/"
                                evidence_link("Повторное обучение · видео первого захвата", path + "diffusion-940200.mp4")
                                evidence_link("Скачать движения, веса и проверочные кадры", path + "simulation-grasp-bundle.zip")
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
            if not reading['ok']:
                station_note.set_text("Камера SO-101 · " + reading['reason'])
                return
            message = "Камера SO-101 · ошибка %.2f px." % reading["control"]["error_px"]
            from . import so101_geometry
            from .so101_station import read_registered_object
            settings = so101_geometry.configuration()
            if settings.get('enabled') and settings.get('instance_id'):
                found = await asyncio.to_thread(read_registered_object, reading, settings['object_class'], settings['instance_id'])
                if found['ok']:
                    sizes = " × ".join(f"{1000 * found[k]:g}" for k in ("width_m", "length_m", "height_m"))
                    message += f" Видна метка {found['object_instance']}. Размеры по записи оператора: {sizes} мм."
                else:
                    message += " " + found['reason']
            station_note.set_text(message)

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
