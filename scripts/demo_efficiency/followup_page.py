"""Publish the paired continuation and failure-stage counts through the existing report route."""

from html import escape

from explorer4.study_day import write_atomic

STAGES = {
    "retained": "Удержание подтверждено",
    "never_reached_cube": "Рука не дошла до кубика",
    "near_cube_without_bilateral_contact": "Рядом с кубиком, захвата двумя губками нет",
    "grasped_without_lift": "Контакт двумя губками, подъёма на 5 см нет",
    "dropped_after_lift": "Кубик опустился после подъёма",
    "outside_carry_pose": "Кубик поднят, рука вне позы переноса",
    "insufficient_terminal_hold": "Удержание в конце не подтверждено",
}
STATUS = {
    "awaiting_initial_evaluations": "Идёт исходная серия",
    "running_continuation": "Идёт продолжение до 3 000 шагов",
    "no_continuation": "Исходная серия закончена, продление не выбрано",
    "completed": "Разбор и повторная проверка завершены",
    "blocked": "Есть незавершённое задание, см. журнал",
}


def table(rows):
    if not rows:
        return "<p>Ожидаются завершённые проверки.</p>"
    rendered = []
    for key, row in sorted(rows.items()):
        steps, outcomes = row
        counts = ", ".join(f"{STAGES[s]} — {n}" for s, n in outcomes["stages"].items())
        rendered.append(
            f"<tr><td>{escape(key)}</td><td>{steps}</td>"
            f"<td>{outcomes['successes']}/{outcomes['attempts']}</td><td>{escape(counts)}</td></tr>"
        )
    return "<table><thead><tr><th>Вариант</th><th>Шагов</th><th>Удержания</th><th>Что произошло</th></tr></thead><tbody>" + "".join(rendered) + "</tbody></table>"


def publish(path, state, day):
    rows = {key + " · исходный": (1000, row) for key, row in state["initial"].items()}
    rows.update({key + " · продолжение": (3000, row["diagnosis"])
                 for key, row in state["continuations"].items() if "diagnosis" in row})
    change = []
    for key, row in state["continuations"].items():
        if "change" in row:
            moves = row["change"]
            change.append(f"<li>{escape(key)} · добавилось {len(moves['gained'])}, потеряно {len(moves['lost'])} сцен.</li>")
    detail = "<ul>" + "".join(change) + "</ul>" if change else ""
    status = STATUS[state["status"]]
    if state.get("selected_k"):
        status += f" · {state['selected_k']} показов"
    write_atomic(path.with_suffix(".html"),
                 '<!doctype html><html lang="ru"><meta charset="utf-8"><meta http-equiv="refresh" content="60">'
                 '<title>Explorer · Разбор захватов ACT</title><style>body{font:16px system-ui;margin:2em;line-height:1.55}'
                 'td,th{padding:.35em .8em;border-bottom:1px solid #ccc;text-align:left}</style>'
                 f'<h1>Разбор захватов ACT</h1><p>{escape(status)} · {escape(state["updated_msk"])}</p>'
                 '<p>Продлевается одна пара, если хотя бы одна модель удержала кубик на двух из 12 сцен '
                 'и есть запас для улучшения. Приоритет у сравнения на трёх показах, затем на пяти и одном.</p>'
                 f'{table(rows)}{detail}<p><a href="../study-{escape(day)}.html">Очередь исходной серии</a> · '
                 f'<a href="{escape(path.name)}">Все сцены и контрольные суммы</a></p></html>')
