"""Physical series setup and independent human scoring on the existing camera and operator pages."""
import asyncio
import re

from fastapi import HTTPException
from fastapi.responses import FileResponse

from nicegui import app,ui

from . import peer_dock_series as series


def install_api():
    @app.get('/api/peer-dock/field-series')
    def result():
        return series.report()

    @app.get('/api/peer-dock/field-series/{ident}/{capture}/{filename}')
    def evidence(ident:str,capture:str,filename:str):
        match=re.fullmatch(r'[0-9]{3,}-(tank|rosmaster)',capture)
        if not re.fullmatch(r'[0-9a-f]{32}',ident) or not match:
            raise HTTPException(404)
        robot=match[1]
        if filename not in ('observation.json',robot+'.npz',robot+'.jpg'):
            raise HTTPException(404)
        path=series.SERIES.parent/ident/capture/filename
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)


def controls(control):
    with ui.expansion('Парная серия на реальном полу').classes('w-full'):
        ui.label('Восемь попыток в двух размеченных расстановках A и B. Порядок уже зафиксирован. '
                 'В одном условии Tank запрашивает неподвижную камеру ROSMASTER, в другом ищет сам поворотом на месте. '
                 'На получение наблюдения даётся 3 с, общий лимит 20 с.')
        ui.link('Протокол, порядок, исходы и замеры JSON','/api/peer-dock/field-series',new_tab=True)
        ui.label('Для каждой расстановки нанесите на пол метки исходных поз и курса обеих машин. '
                 'Отметьте крест для центра Tank на расстоянии 277 мм от лицевой стороны мишени и стрелку перпендикулярно к стене. '
                 'Для оценки приготовьте линейку и угломер. Обеспечьте свободный круг поворота вокруг Tank.')
        layout=ui.select(['A','B'],value='A',label='Расстановка')
        note=ui.input('Описание меток исходной позы, креста и оси цели').classes('w-full')
        start_distance=ui.number('Измеренное расстояние от начального центра Tank до целевого креста, мм',min=0)
        async def mark():
            try:
                from .fleet_map import FLEET
                await asyncio.to_thread(series.label_layout,layout.value,note.value or '',FLEET,control,
                                        None if start_distance.value is None else start_distance.value/1000.)
                ui.notify('Расстановка зафиксирована');progress.refresh()
            except Exception as exc:
                ui.notify(str(exc),type='negative')
        ui.button('Зафиксировать расстановку при STOP',on_click=mark)
        @ui.refreshable
        def progress():
            r=series.report()
            needed=[r.upper() for r,c in r['calibration'].items() if not c['verified_current']]
            if needed:
                ui.label('Измерьте камеры на двух положениях мишени в одной общей карте: '+', '.join(needed))
            ui.label('Зарегистрированные расстановки: '+(', '.join(r['fixtures']) or 'пока нет'))
            try:
                name,mode=series.next_slot(r)
                ui.label('Следующая: '+name+' · '+('запрос помощнику' if mode=='selective' else 'активный поиск только камерой Tank'))
            except ValueError as exc:
                ui.label(str(exc))
            for c,s in r['outcomes'].items():
                title='С помощью' if c=='selective' else 'Локальный поиск'
                ui.label(f"{title}: {s['independent_successes']} успехов, {s['measured']} измеренных, {s['started']} начатых.")
        progress()
        ui.button('Обновить состояние серии',on_click=progress.refresh).props('flat')
        ui.link('Начать следующую попытку из ручного пульта Tank','/',new_tab=True)
        ui.label('После завершения нажмите STOP в пульте и убедитесь, что машина физически остановилась. Не передвигая Tank, вручную измерьте ошибки '
                 'его центра относительно креста и курса относительно стрелки. Допуск 80 мм и 0,15 рад (8,6°).')
        dx=ui.number('Продольная ошибка, мм');dy=ui.number('Поперечная ошибка, мм');yaw=ui.number('Ошибка курса, °')
        stationary=ui.checkbox('После STOP Tank неподвижен не менее 0,5 с')
        intervention=ui.checkbox('Потребовалось вмешательство или досрочная остановка')
        evidence=ui.input('Источник независимого замера или идентификатор видео').classes('w-full')
        async def score():
            try:
                rows=series.state()['attempts']
                if not rows:raise ValueError('Нет начатой попытки')
                if any(v.value is None for v in (dx,dy,yaw)):raise ValueError('Заполните все три замера')
                result=await asyncio.to_thread(series.score,control,rows[-1]['id'],dx.value/1000.,dy.value/1000.,yaw.value,
                                               stationary.value,intervention.value,evidence.value or '')
                ui.notify('Замер сохранён. '+('Критерий выполнен.' if result['success'] else 'Критерий не выполнен.'))
                for v in (dx,dy,yaw):v.value=None
                stationary.value=intervention.value=False;evidence.value=''
                progress.refresh()
            except Exception as exc:
                ui.notify(str(exc),type='negative')
        ui.button('Сохранить независимый замер',on_click=score)


def operator_button(control,session,owner):
    restored=ui.checkbox('Цель, экран, Tank и ROSMASTER выставлены по меткам очередной расстановки')
    async def launch():
        try:
            from .fleet_map import FLEET
            ident=await asyncio.to_thread(series.start,control,session,owner,FLEET,fixture_restored=restored.value)
            restored.value=False
            ui.notify('Запущена размеченная попытка '+ident[:8]+'. Стрелки и STOP её прерывают.')
        except Exception as exc:
            ui.notify(str(exc),type='negative')
    ui.button('Начать очередную попытку физической серии',on_click=launch).props('outline no-caps')
