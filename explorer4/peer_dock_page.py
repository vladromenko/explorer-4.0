"""Operator view and explicit handoff to the existing Tank session."""
import asyncio
import json
import logging
import math
import re

from fastapi import HTTPException
from fastapi.responses import FileResponse,HTMLResponse
from nicegui import app,ui

from . import peer_dock_real as study
from .paths import ROOT
from . import peer_dock_series_page as series_page


def install(control=None):
    series_page.install_api()

    @app.get('/peer-dock-real/screen', response_class=HTMLResponse)
    def screen():
        from .peer_dock_screen import target_html
        return target_html()

    @app.get('/api/peer-dock/board.pdf')
    def board():
        return FileResponse(ROOT/'assets/peer_dock_180mm_A4.pdf',media_type='application/pdf',filename='Explorer-dock-180mm-A4.pdf')

    @app.get('/api/peer-dock/latest')
    def latest():
        path = study.RUNS/'latest.json'
        return json.loads(path.read_text()) if path.is_file() else {'status':'awaiting_capture'}

    @app.post('/api/peer-dock/observe')
    async def observe():
        return await asyncio.to_thread(study.record)

    @app.get('/api/peer-dock/evidence/{ident}/{filename}')
    def evidence(ident:str,filename:str):
        if filename not in ('result.json','tank.npz','rosmaster.npz','tank.jpg','rosmaster.jpg'):
            raise HTTPException(404)
        try:
            study.recent_report(ident)
        except (OSError,ValueError):
            raise HTTPException(404)
        path = study.RUNS/ident/filename
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.get('/api/peer-dock/survey/{ident}')
    @app.get('/api/peer-dock/survey/{ident}/{filename}')
    def survey_receipt(ident: str, filename: str = 'receipt.json'):
        suffix = {'receipt.json':'.json','inputs.npz':'.npz','confirmation.json':'-confirmation.json',
                  'confirmation.npz':'-confirmation.npz'}.get(filename)
        if not suffix or not re.fullmatch('[0-9a-f]{32}', ident):
            raise HTTPException(404)
        base = study.RUNS/'surveys'
        path = base/(ident+suffix)
        if not (base/(ident+'.json')).is_file() or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path,media_type='application/json' if suffix.endswith('.json') else 'application/octet-stream')

    @app.get('/api/peer-dock/shelf-readiness')
    async def shelf_readiness():
        from . import peer_shelf_run, peer_dock_survey
        try:
            if control is not None:
                peer_dock_survey.require_stopped(control)
            previous = await asyncio.to_thread(peer_shelf_run.resumable_shelf_run)
            if previous is not None:
                receipt, _ = await asyncio.to_thread(peer_shelf_run.probe_resume, previous)
                return {'ready': True, 'resume': previous['id'], 'goal_relative': receipt['pose'],
                        'scan_overlap': receipt['scan_overlap'], 'replay': receipt['shadow_replay'],
                        'no_motion': True}
            receipt, shelf_map = await asyncio.to_thread(peer_shelf_run.probe)
            return {'ready': True, 'receipt': receipt['id'],
                    'goal_disagreement_m': receipt['donor_local_disagreement_m'],
                    'no_motion': True}
        except (ValueError, KeyError, OSError) as exc:
            return {'ready': False, 'reason': str(exc)}

    @ui.page('/peer-dock-real')
    async def page():
        ui.dark_mode().enable()
        ui.label('Подъезд Tank с помощью камеры ROSMASTER').classes('text-h5')
        ui.link('Центр экспериментов','/workspace')
        ui.label('Распечатайте лист в масштабе 100%, проверьте чёрную сторону 180 мм и закрепите его вертикально. Нужны основной №7 и нижний №43 на одном листе.')
        ui.label('Можно закрепить неподвижный монитор вместо листа. Выведите обе метки, настройте размер по линейке (180 мм), уберите отражения. Проверьте положение камер по двум измеренным точкам.')
        ui.link('Открыть метку для монитора','/peer-dock-real/screen',new_tab=True)
        ui.link('Скачать лист A4','/api/peer-dock/board.pdf',new_tab=True)
        ui.label('Наблюдение записывает изображения и калибровки двух камер. Оно доступно при выключенном управлении приводами.')
        displayed = {}
        @ui.refreshable
        def status():
            state = displayed.get('report',{})
            if not state.get('id'):
                ui.label('Снимков пока нет.')
                return
            for robot,obs in state['observations'].items():
                if obs.get('preview_file'):
                    ui.image(f"/api/peer-dock/evidence/{state['id']}/{robot}.jpg").style('width:min(100%,480px)')
                with ui.row():
                    ui.label(robot.upper()+(' · лист найден' if obs['board_valid'] else ' · лист не найден'))
                    ui.label('ID в кадре '+str(obs.get('detected_ids',[])))
                    if obs.get('payload_file'):
                        ui.link('Исходный пакет',f"/api/peer-dock/evidence/{state['id']}/{robot}.npz",new_tab=True)
            ui.label('Запрос помощнику: '+('да' if state['help_requested'] else 'нет'))
            ui.label(state.get('reason') or 'Координата доступна для пульта Tank. Перед движением камера обновляется.')
            ui.link('Исход наблюдения',f"/api/peer-dock/evidence/{state['id']}/result.json",new_tab=True)
        async def capture():
            button.disable()
            try:
                displayed['report'] = await asyncio.to_thread(study.record)
                status.refresh()
            except Exception as exc:
                ui.notify(str(exc),type='negative')
            finally:
                button.enable()
        button = ui.button('Получить кадры двух машин',on_click=capture)
        displayed['report'] = latest()
        status()
        if control is not None:
            donor_survey(control)
        with ui.expansion('Измерить положение камеры').classes('w-full'):
            ui.label('Для каждого робота зафиксируйте камеру. На общей карте измерьте центр большой метки и направление её лицевой стороны. После первого снимка передвиньте лист по стене минимум на 10 см, измерьте новое положение и получите второй снимок.')
            robot = ui.select(['tank','rosmaster'],value='tank',label='Камера')
            with ui.row():
                x = ui.number('X на карте, м')
                y = ui.number('Y на карте, м')
                z = ui.number('Высота центра, м')
                yaw = ui.number('Направление от стены, °')
                hours = ui.number('Срок проверки, ч',value=8,min=.1)
            def measure(validate):
                try:
                    values = [field.value for field in (x,y,z,yaw)]
                    if any(v is None for v in values):
                        raise ValueError('Введите все измеренные координаты и направление.')
                    entry = study.calibrate(displayed['report']['id'],robot.value,values[:3],values[3],validate=validate,valid_hours=hours.value)
                    if validate:
                        ui.notify(f"Ошибка {100*entry['position_residual_m']:.1f} см, угол {entry['heading_residual_deg']:.1f}°. "+
                                  ('Проверка пройдена.' if entry['verified'] else 'Повторите измерение.'))
                    else:
                        ui.notify('Первое положение сохранено. Снимите лист в следующей точке.')
                except (ValueError,KeyError,OSError) as exc:
                    ui.notify(str(exc),type='negative')
            ui.button('Сохранить первое положение',on_click=lambda:measure(False))
            ui.button('Проверить по второму положению',on_click=lambda:measure(True))
        if control is not None:
            series_page.controls(control)
        ui.link('Пульт оператора Tank','/')


def donor_survey(control):
    from .fleet_map import FLEET
    from .peer_dock_survey import anchor_donor
    with ui.expansion('Общая карта: привязать неподвижный ROSMASTER').classes('w-full'):
        ui.link('Открыть общую карту и состояние лидаров', '/swarm', new_tab=True)
        @ui.refreshable
        def positions():
            for robot in study.ROBOTS:
                pose, _, frame = study.real_pose(FLEET,robot)
                ui.label(f'{robot.upper()} · ' + (f'X {pose[0]:.2f} м, Y {pose[1]:.2f} м, '
                         f'курс {math.degrees(pose[2]):.0f}°, карта {frame[:8]}' if pose is not None
                         else 'нет актуальной позиции на общей карте'))
            with FLEET.lock:
                ref = (FLEET.track.get('rosmaster') or {}).get('floor_survey',{}).copy()
            if ref.get('status') == 'confirmed':
                ui.link('Независимый скан: локальное подтверждение измеренной позы',
                        '/api/peer-dock/survey/'+ref['id']+'/confirmation.json',new_tab=True)
            elif ref.get('status') == 'rejected':
                ui.label('Лидар не подтвердил измеренную опору. Проверьте отметки или дождитесь общей локализации по комнате.')
        positions()
        ui.button('Обновить позиции', on_click=positions.refresh).props('flat')
        ui.label('Если Tank уже виден на карте, а ROSMASTER строит свою карту, нажмите STOP. Отметьте '
                 'центры обеих баз и их передние оси на полу. Измерьте положение центра ROSMASTER '
                 'от центра Tank вдоль двух осей Tank и угол между передними осями. '
                 'Положительные направления — вперёд, влево и против часовой стрелки при взгляде сверху.')
        with ui.row():
            forward = ui.number('Вперёд от центра Tank, мм')
            left = ui.number('Влево от центра Tank, мм')
            angle = ui.number('Курс ROSMASTER относительно Tank, °')
        ui.label('Кнопка сохраняет результат замера и даёт лидарному трекеру стартовую подсказку. '
                 'Калибровка камер и начало попытки доступны отдельными действиями.')
        measured = ui.checkbox('Обе базы стоят на отметках. Смещения и угол измерены на полу')
        result = ui.column()
        async def register():
            button.disable()
            try:
                if any(v.value is None for v in (forward,left,angle)):
                    raise ValueError('Введите оба смещения и измеренный угол')
                evidence = await asyncio.to_thread(anchor_donor,control,FLEET,forward.value/1000.,left.value/1000.,
                                                   angle.value,measured.value)
                measured.value = False
                result.clear()
                with result:
                    ui.label('Стартовая подсказка сохранена. Локальную привязку должен подтвердить следующий независимый '
                             'пакет обоих лидаров. Обновите позиции и дождитесь координат '
                             'обеих машин, затем снимите мишень на двух положениях для проверки камер.')
                    ui.link('Исходные измерения и согласование с картой', '/api/peer-dock/survey/'+evidence['id'],new_tab=True)
                positions.refresh()
            except Exception as exc:
                ui.notify(str(exc),type='negative')
            finally:
                button.enable()
        button = ui.button('Проверить измерение по двум сканам ROSMASTER',on_click=register)


def add_operator_action(control,session,owner):
    """The parent control page owns the browser heartbeat, manual override and STOP."""
    ui.link('Подготовить совместный подъезд','/peer-dock-real',new_tab=True)
    async def accept():
        try:
            expected=study.operator_session(control,session,owner)
            from .fleet_map import FLEET
            report=await asyncio.to_thread(study.record,FLEET)
            study.handoff(control,session,owner,expected,report,FLEET)
            ui.notify('Координата передана в управление Tank. Действуют ручное прерывание и STOP.')
        except Exception as exc:
            ui.notify(str(exc),type='negative')
    ui.button('Подъехать к измеренной совместной цели',on_click=accept).props('outline no-caps')
    from . import peer_shelf_run
    previous = peer_shelf_run.resumable_shelf_run()
    with ui.expansion('Пробный подъезд к стеллажу без меток', value=True):
        ui.label('Одна проверка на сохранённой расстановке. ROSMASTER остаётся на месте.')
        supervised = ui.checkbox('Я рядом, вижу Tank и могу сразу нажать STOP')
        shelf_status = ui.label('Включите управление Tank и подтвердите наблюдение.').classes('muted')
        runner = None

        async def start_shelf():
            nonlocal runner
            if not supervised.value:
                ui.notify('Подтвердите, что видите Tank и можете его остановить', type='warning')
                return
            shelf_button.disable()
            try:
                expected = study.operator_session(control, session, owner)
                shelf_status.set_text('Проверяю свежие кадры и маршрут…')
                current = await asyncio.to_thread(peer_shelf_run.resumable_shelf_run)
                if previous is not None and current != previous:
                    raise ValueError('Журнал подъезда изменился. Обновите страницу.')
                if previous is None:
                    receipt, shelf_map = await asyncio.to_thread(peer_shelf_run.probe)
                else:
                    receipt, shelf_map = await asyncio.to_thread(peer_shelf_run.probe_resume, previous, supervised=True)
                if not supervised.value:
                    return
                runner = peer_shelf_run.handoff(control, session, owner, expected, receipt, shelf_map)
                shelf_status.set_text('Tank принял цель. Держите STOP под рукой.')
                ui.notify('Tank принял точку стеллажа от ROSMASTER. STOP останавливает попытку.')
            except Exception as exc:
                shelf_status.set_text(str(exc))
                logging.getLogger(__name__).warning('Shelf approach did not start: %s', exc)
                ui.notify(str(exc), type='negative')
            finally:
                if runner is None or not runner.active:
                    shelf_button.enable()

        action = 'Продолжить прерванный подъезд' if previous else 'Начать один пробный подъезд'
        shelf_button = ui.button(action, on_click=start_shelf).props('outline no-caps')

        def update_shelf_status():
            nonlocal runner
            if runner is None:
                return
            hold = (session.latest or {}).get('pause_reason') if runner.active else None
            shelf_status.set_text(hold or runner.message)
            if not runner.active:
                runner = None
                shelf_button.enable()

        ui.timer(.5, update_shelf_status)
    series_page.operator_button(control,session,owner)
