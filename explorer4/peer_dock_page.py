"""Operator view and explicit handoff to the existing Tank session."""
import asyncio
import json

from fastapi import HTTPException
from fastapi.responses import FileResponse
from nicegui import app,ui

from . import peer_dock_real as study
from .paths import ROOT


def install(control=None):
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

    @ui.page('/peer-dock-real')
    async def page():
        ui.dark_mode().enable()
        ui.label('Подъезд Tank с помощью камеры ROSMASTER').classes('text-h5')
        ui.link('Центр экспериментов','/workspace')
        ui.label('Распечатайте лист в масштабе 100%, проверьте чёрную сторону 180 мм и закрепите его вертикально. Нужны основной №7 и нижний №43 на одном листе.')
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
        ui.link('Пульт оператора Tank','/')


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
