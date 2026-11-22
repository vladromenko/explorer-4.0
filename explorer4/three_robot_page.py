"""Start and inspect a simulation-only three-robot order in the existing Jobs worker."""
import asyncio
import json

from nicegui import ui

from .paths import DATA

NAME = 'three-robot-dock-v1'
BASE = '/simlab-media/reports/' + NAME


def install(jobs):
    @ui.page('/team/three')
    async def page():
        with ui.column().classes('w-full max-w-4xl mx-auto p-6'):
            ui.link('Команда', '/team')
            ui.label('Заказ для трёх роботов').classes('text-3xl font-bold')
            ui.label('SO‑101 считывает цвет жетона. ROSMASTER измеряет положение одноимённого дока. Tank выполняет подъезд и останавливается.')
            with ui.row():
                room=ui.select({'workshop':'Мастерская','storage':'Зона хранения','inspection':'Сборочный участок'},
                               value='workshop',label='Сцена')
                seed=ui.number('Расстановка',value=868000,min=0,max=2**31-1,precision=0)
            status=ui.label('Готово к запуску в MuJoCo')
            selected={'id':None,'shown':None}
            async def start():
                try:
                    selected['id']=await asyncio.to_thread(jobs.three_robot_docking,int(seed.value),room.value)
                    status.set_text('Проверка поставлена в очередь · '+selected['id'][:8])
                except Exception as exc:
                    ui.notify(str(exc),type='negative')
            ui.button('Выполнить в MuJoCo',icon='play_arrow',on_click=start)
            ui.label('Исходная серия').classes('text-xl font-medium')
            initial=DATA/'simlab/reports'/NAME/'result.json'
            if initial.is_file():
                report=json.loads(initial.read_text())
                ui.label(f"Правильный док — {report['successes']['intact']} из {report['scenes']}.")
                ui.link('Все условия и журналы',BASE+'/result.json',new_tab=True)
                replay=initial.parent/'868000'/'replay.mp4'
                if replay.is_file():
                    ui.video(BASE+'/868000/replay.mp4').props('preload=metadata').classes('w-full')
                for row in report['evidence']:
                    with ui.row():
                        n=str(row['seed'])
                        ui.label(n)
                        for name,file in [('SO‑101','so101-order.png'),('ROSMASTER','rosmaster-stations.png'),
                                          ('Tank','tank-final.png'),('Протокол','trace.json')]:
                            ui.link(name,BASE+'/'+n+'/'+file,new_tab=True)
            links=ui.row()
            async def refresh():
                ident=selected['id']
                if not ident or ident==selected['shown']:
                    return
                job=await asyncio.to_thread(jobs.get,ident)
                phase=job['status']
                labels={'queued':'В очереди','running':'Работает симулятор','completed':'Проверка завершена',
                        'failed':'Ошибка','interrupted':'Прервано','cancelled':'Отменено'}
                status.set_text(labels.get(phase,phase)+' · '+ident[:8])
                if phase=='completed':
                    selected['shown']=ident
                    links.clear()
                    with links:
                        ui.link('Результат этого запуска',BASE+'/jobs/'+ident+'/result.json',new_tab=True)
            ui.timer(3,refresh)
