"""Operator page for measured stationary points; all network reads follow a user click."""

import json

import httpx

from . import grasp_calibration as capture


def install():
    from fastapi import HTTPException
    from nicegui import app, run, ui

    from .grasp_admission import resume_pending
    from .grasp_native_evidence import verified_native
    from .sensor_pages import jpeg

    app.on_startup(resume_pending)

    @app.get("/api/rosmaster/grasp-calibration")
    def recent_calibrations():
        return {"roles": capture.ROLES, "sessions": capture.list_sessions(), "motion_commands_sent": 0}

    @app.get("/api/rosmaster/grasp-calibration/{ident}")
    def one_calibration(ident: str):
        try:
            return capture.summary(capture.open_session(ident))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/rosmaster/grasp-calibration/{ident}/admission")
    def admission_report(ident: str):
        from .grasp_admission import EVIDENCE

        try:
            path = capture.open_session(ident) / EVIDENCE
            if not path.is_file():
                raise ValueError("Отчёт появится после трёх проверочных показов")
            return json.loads(path.read_text())
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/rosmaster/grasp-calibration/{ident}/offline-plans")
    def read_plans(ident: str):
        from fastapi.responses import FileResponse

        try:
            file = capture.open_session(ident) / "offline-plans.json"
            if not file.is_file():
                raise ValueError("Сначала рассчитайте цели по архивным снимкам")
            return FileResponse(file, media_type="application/json")
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @ui.page("/rosmaster/grasp-calibration")
    def calibration_page(session: str = ""):
        import cv2

        ui.dark_mode().enable()
        ui.add_css("""
        body{background:#0e151e;color:#e8eff5;font-family:Inter,system-ui,sans-serif}
        .nicegui-content{width:100%;max-width:950px;margin:auto;padding:24px 16px}
        .grasp-card{background:#18232e;border:1px solid #334556;border-radius:14px;width:100%;padding:20px}
        .grasp-muted{color:#b6c4d1;max-width:75ch}.grasp-error{color:#ffb9ad;white-space:pre-wrap}
        .grasp-table{width:100%;overflow:auto}a{color:#83dfcb}
        """)
        ui.link("← Рабочая панель", "/workspace")
        ui.label("Проверка камеры ROSMASTER для захвата").classes("text-h4 text-weight-bold")
        ui.label(
            "Проверяем, где замороженная модель видит центр кубика. Шасси и рука неподвижны. Страница читает штатные датчики по кнопке."
        ).classes("grasp-muted")
        with ui.card().classes("grasp-card"):
            ui.label("Подготовка").classes("text-h6")
            ui.label(
                "Закрепите основание и сохраните положение камеры. Рука в позе обзора: 90°, 57°, 24°, 0°, 75°, 30° по порядку сервоприводов. Требуются включённый режим наблюдения ROSMASTER и телеметрия шести суставов штатного ROS-моста."
            )
            ui.label(
                "Отмеряйте центр кубика от начала системы base_link. X вперёд, Y влево, в миллиметрах. Расставьте 3 точки треугольником и ещё 2 отдельные контрольные точки. Рабочая область показов примерно X 173–249 мм, Y −45…46 мм. Для всех пяти снимков условия и модель одинаковы."
            )
            ui.label(
                "Измерьте ширину кубика и свободное расстояние между внутренними губками при подходе. Допустимая ошибка центра равна половине разницы этих размеров."
            )
        with ui.card().classes("grasp-card"):
            ui.label("Готовность одной пробы на роботе").classes("text-h6")
            ui.label(
                "Допуск относится к одному пробному захвату в четвёртой измеренной точке. Кубик должен целиком находиться в кадре, а его положение по модели — внутри области показов. Порог MuJoCo — удержание в конце 360 команд минимум в 10 из первых 20 подходящих сцен. Дополнительно нужны проверенная камера и три независимые записи реальных движений."
            )
            try:
                native = verified_native()
                verdict = "пройден" if native["pass"] else "не пройден"
                ui.label(
                    f"Порог симулятора {verdict}. Удержаний внутри проверенной области: {native['wins']} из {native['n']}. "
                    f"Подошли по видимости и положению {native['eligible_candidates']} из {native['candidate_count']} кандидатов. "
                    f"При учёте всех 20 исторических стартов: {native['historic_holds']} удержаний, "
                    f"{native['historic_eligible']} разрешённых запусков."
                )
            except (OSError, ValueError, KeyError):
                ui.label("Проверенного результата текущего исполнителя пока нет. Запуск одиночной пробы заблокирован.")
            ui.link(
                "Все исходные сцены, причины отказа и результат внутри области",
                "/simlab-media/reports/grasp-admission-native-v3/result.json",
            )
        if not session:
            with ui.card().classes("grasp-card"):
                ui.label("Новая серия").classes("text-h6")
                device = ui.input("Номер камеры с корпуса или инвентарной наклейки").classes("w-full")
                with ui.row():
                    jaw = ui.number("Раскрытие губок, мм", min=0, step=0.1)
                    cube = ui.number("Ширина кубика, мм", min=0, step=0.1)
                create_error = ui.label("").classes("grasp-error")

                def start():
                    try:
                        path = capture.new_session(device.value, jaw.value, cube.value)
                        ui.navigate.to(f"/rosmaster/grasp-calibration?session={path.name}")
                    except (OSError, ValueError) as exc:
                        create_error.set_text(str(exc))

                ui.button("Создать серию", on_click=start)
            for row in capture.list_sessions():
                ui.link(
                    f"Серия {row['session'][:8]} · {len(row['points'])}/5",
                    f"/rosmaster/grasp-calibration?session={row['session']}",
                )
            return
        try:
            path = capture.open_session(session)
        except ValueError as exc:
            ui.label(str(exc)).classes("grasp-error")
            return
        setup = json.loads((path / "session.json").read_text())
        ui.label(
            f"Серия {session[:8]} · камера {setup['device_id']} · допустимая ошибка {1000 * setup['measured_allowable_xy_error_m']:.1f} мм"
        )
        state = {"frame": None, "corners": [], "busy": False}
        ui.link("Все серии", "/rosmaster/grasp-calibration")

        @ui.refreshable
        def results():
            progress = capture.summary(path)
            titles = {
                "incomplete": "Нужны дополнительные точки",
                "positive": "Камера прошла статическую проверку",
                "negative": "Проверка выявила выход за допуск или область показов",
            }
            with ui.card().classes("grasp-card"):
                ui.label(titles[progress["status"]]).classes("text-h6")
                ui.label(
                    f"Точки проверки {progress['counts']['calibration_check']}/3 · Независимый контроль {progress['counts']['verification']}/2"
                )
                if progress["points"]:
                    columns = [
                        {"name": k, "label": l, "field": k, "align": "left"}
                        for k, l in [
                            ("role", "Роль"),
                            ("true", "Измерено X/Y, мм"),
                            ("pred", "Прогноз X/Y, мм"),
                            ("d", "Ошибка X/Y, мм"),
                            ("length", "Расстояние, мм"),
                            ("ok", "Допуск и область"),
                        ]
                    ]
                    rows = []

                    def pair(values, factor=1):
                        return " / ".join(f"{factor * v:.1f}" for v in values)

                    for point in progress["points"]:
                        rows.append(
                            {
                                "role": "Проверка" if point["role"] == "calibration_check" else "Контроль",
                                "true": pair(point["independently_measured_base_xy_m"], 1000),
                                "pred": pair(point["predicted_xy_m"], 1000),
                                "d": pair(point["residual_xy_mm"]),
                                "length": f"{point['error_mm']:.1f}",
                                "ok": "Да"
                                if point["within_measured_margin"] and point["inside_demonstration_hull"]
                                else "Нет",
                            }
                        )
                    ui.table(columns=columns, rows=rows).classes("grasp-table")
                ui.link("Сводка измерений JSON", f"/api/rosmaster/grasp-calibration/{session}")
                if progress["complete"]:
                    ui.label(
                        "Серия завершена. Проверен только прогноз положения кубика. Захват и перенос в этой серии не выполнялись."
                    )

        results()
        if capture.summary(path)["status"] == "positive":
            ui.label(
                "После проверки камеры запишите по одному успешному человеческому захвату в трёх отдельных расстановках. Начинайте в проверенной позе, на секунду удержите неподвижный кадр с целым кубиком, затем возьмите и удержите кубик. Укажите фактический исход каждой попытки. Записи попадут в диагностическую выборку."
            )
            from . import grasp_admission as admission

            @ui.refreshable
            def admitted():
                selected = admission.references(path)
                pos = min(4, len(selected) + 1)
                point = capture.session_rows(path)[pos - 1]
                x, y = point["independently_measured_base_xy_m"]
                ui.label(
                    f"Позиция {pos}: верните тот же кубик на метку X {1000 * x:.1f} мм, Y {1000 * y:.1f} мм. Исходных показов {len(selected)}/3."
                )
                report = path / admission.EVIDENCE
                if report.is_file():
                    state = json.loads(report.read_text())
                    ui.label("Решение: " + state["reason"])
                    if state.get("channel_mae_deg"):
                        ui.label(
                            "Средняя ошибка углов, °: "
                            + " / ".join(f"{v:.1f}" for v in state["channel_mae_deg"])
                        )
                    ui.link(
                        "Проверки, веса, кубик и все изученные эпизоды",
                        f"/api/rosmaster/grasp-calibration/{session}/admission",
                    )
                    if state["status"] == "ready" and not (path / "physical-trial-claimed.json").exists():
                        problem = ui.label("").classes("grasp-error")

                        async def setup_trial():
                            try:
                                plan = await run.io_bound(admission.make_plan, session)
                                ui.navigate.to(f"/rosmaster/control?trial={plan['id']}")
                            except (OSError, ValueError, PermissionError) as exc:
                                problem.set_text(str(exc))

                        ui.button("Открыть одну наблюдаемую пробу ROSMASTER", on_click=setup_trial)
                    elif (path / "physical-trial-claimed.json").is_file():
                        ui.label("Одиночная проба использована.")
                elif len(selected) == 3:
                    ui.label(
                        "Проверяются исходные записи и штатные допуски. Если панель перезапускалась, возобновите проверку."
                    )

                    async def resume_review():
                        await run.io_bound(admission.schedule, selected[0][0]["series"])

                    ui.button("Возобновить офлайн-проверку", on_click=resume_review)

            admitted()
            ui.button("Обновить статус записей и допуска", on_click=admitted.refresh)
            reference_message = ui.label("")

            def open_reference():
                from .grasp_reference import reference_series

                try:
                    series = reference_series(path)
                    ui.navigate.to(f"/recording/collect?task=rosmaster_pick_place&series={series}")
                except (OSError, ValueError) as exc:
                    reference_message.set_text(str(exc))

            ui.button("Записать отдельный проверочный показ", on_click=open_reference)
            plans_message = ui.label("")

            async def compute_plans():
                if state["busy"]:
                    return
                state["busy"] = True
                try:
                    result = await run.io_bound(capture.archived_plans, path)
                    methods = [m for point in result["points"] for m in point["methods"].values()]
                    plans_message.set_text(
                        f"Рассчитано {sum(m['status'] == 'predicted' for m in methods)} из {len(methods)} последовательностей. Отправлено роботу 0 команд."
                    )
                    ui.link(
                        "Цели шести сервоприводов и причины отказа, JSON",
                        f"/api/rosmaster/grasp-calibration/{session}/offline-plans",
                    )
                except (OSError, RuntimeError, KeyError, ValueError) as exc:
                    plans_message.set_text(str(exc))
                finally:
                    state["busy"] = False

            ui.button("Рассчитать движения только на сохранённых снимках", on_click=compute_plans)
        if capture.summary(path)["complete"]:
            return
        with ui.card().classes("grasp-card"):
            ui.label("Следующее положение кубика").classes("text-h6")
            role = ui.select(
                {"calibration_check": "Измеренная точка проверки", "verification": "Независимый контроль"},
                value="verification"
                if capture.summary(path)["independent_geometry"]
                else "calibration_check",
                label="Роль точки",
            ).classes("w-full")
            with ui.row():
                x = ui.number("Измеренный X, мм", step=0.1)
                y = ui.number("Измеренный Y, мм", step=0.1)
            error = ui.label("").classes("grasp-error")

            def mark(event):
                if state["frame"] is None:
                    return
                if len(state["corners"]) == 2:
                    state["corners"] = []
                state["corners"].append((float(event.image_x), float(event.image_y)))
                dots = "".join(
                    f'<circle cx="{px:.2f}" cy="{py:.2f}" r="4" fill="cyan"/>' for px, py in state["corners"]
                )
                if len(state["corners"]) == 2:
                    (a, b), (c, d) = state["corners"]
                    dots += f'<rect x="{min(a, c):.2f}" y="{min(b, d):.2f}" width="{abs(a - c):.2f}" height="{abs(b - d):.2f}" fill="none" stroke="cyan" stroke-width="2"/>'
                preview.content = dots

            ui.label("На полученном снимке отметьте два противоположных угла прямоугольника вокруг кубика.")
            preview = ui.interactive_image(on_mouse=mark).style("width:min(100%,640px)").set_visibility(False)
            visible = ui.checkbox("На этом снимке виден целый кубик, его центр измерен")

            async def snapshot():
                if state["busy"]:
                    return
                state.update(busy=True, frame=None)
                error.set_text("Читаем RGB, CameraInfo, положение суставов и энкодеры…")
                visible.value = False
                state["corners"] = []
                preview.content = ""
                preview.set_visibility(False)
                try:
                    frame = await run.io_bound(
                        capture.acquire_snapshot, setup["measured_allowable_xy_error_m"]
                    )
                    preview.set_source(jpeg(cv2.cvtColor(frame["rgb"], cv2.COLOR_RGB2BGR)))
                    preview.set_visibility(True)
                    state["frame"] = frame
                    error.set_text("Снимок готов. Убедитесь, что кубик виден целиком, затем сохраните точку.")
                except (httpx.HTTPError, OSError, RuntimeError, KeyError, ValueError) as exc:
                    error.set_text(f"Снимок не получен. {exc}")
                finally:
                    state["busy"] = False

            async def save():
                if state["busy"]:
                    return
                if state["frame"] is None:
                    error.set_text("Сначала получите снимок для этой позиции")
                    return
                state["busy"] = True
                try:
                    if len(state["corners"]) != 2:
                        raise ValueError("Отметьте кубик двумя щелчками на снимке")
                    (a, b), (c, d) = state["corners"]
                    await run.io_bound(
                        capture.save_point,
                        path,
                        state["frame"],
                        role.value,
                        x.value,
                        y.value,
                        visible.value,
                        (min(a, c), min(b, d), max(a, c), max(b, d)),
                    )
                    ui.navigate.to(f"/rosmaster/grasp-calibration?session={path.name}")
                except (httpx.HTTPError, OSError, RuntimeError, KeyError, ValueError) as exc:
                    error.set_text(f"Точка не сохранена. {exc}")
                finally:
                    state["busy"] = False

            with ui.row():
                ui.button("Получить снимок", on_click=snapshot)
                ui.button("Сохранить точку и проверить", on_click=save)
