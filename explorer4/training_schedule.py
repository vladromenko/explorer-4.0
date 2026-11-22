"""Release only the selected batch of queued training jobs at the operator's chosen time."""

import json
import math
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import catalog

MOSCOW = ZoneInfo("Europe/Moscow")
TRAINING_KINDS = frozenset(
    (
        "train",
        "sim_ppo",
        "workspace_study",
        "branch_gain_train",
        "simlab_pipeline",
        "research",
    )
)


def is_training(job):
    return json.loads(job["config"]).get("kind", "train") in TRAINING_KINDS


def local_start(value):
    if not value:
        raise ValueError("Укажите дату и время старта по Москве")
    try:
        instant = datetime.strptime(value, "%Y-%m-%dT%H:%M").replace(tzinfo=MOSCOW)
    except ValueError as exc:
        raise ValueError(
            "Укажите дату и время по Москве с точностью до минуты"
        ) from exc
    if instant.timestamp() <= time.time():
        raise ValueError("Время старта уже прошло")
    return instant.timestamp()


def local_label(instant):
    return datetime.fromtimestamp(instant, MOSCOW).strftime("%d.%m.%Y %H:%M МСК")


def permits(db):
    return dict(db.execute("SELECT job_id, not_before FROM training_starts"))


def allowed(job, starts, now):
    if not is_training(job):
        return True
    instant = starts.get(job["id"])
    return instant is not None and instant <= now


def queue():
    with catalog.connect() as db:
        starts = permits(db)
        rows = db.execute(
            "SELECT id,profile,policy,config FROM jobs WHERE status='queued' ORDER BY created,id"
        )
        return [
            dict(
                id=row["id"],
                profile=row["profile"],
                policy=row["policy"],
                track=json.loads(row["config"]).get("track"),
                not_before=starts.get(row["id"]),
            )
            for row in rows
            if is_training(row)
        ]


def set_start(identifiers, instant):
    """A null time holds a selection. A new job never inherits a previous batch's permission."""
    if instant is not None and (not math.isfinite(instant) or instant < 0):
        raise ValueError("Некорректное время старта")
    ids = tuple(dict.fromkeys(identifiers))
    if not ids:
        raise ValueError("В очереди нет ожидающих обучений")
    with catalog.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        count = 0
        for ident in ids:
            row = db.execute(
                "SELECT id,status,config FROM jobs WHERE id=?", (ident,)
            ).fetchone()
            if row is None or not is_training(row):
                raise ValueError("В очереди нет указанного обучения")
            if row["status"] != "queued":
                continue
            if instant is None:
                db.execute("DELETE FROM training_starts WHERE job_id=?", (ident,))
            else:
                db.execute(
                    """INSERT INTO training_starts(job_id,not_before) VALUES(?,?)
                              ON CONFLICT(job_id) DO UPDATE SET not_before=excluded.not_before""",
                    (ident, instant),
                )
            count += 1
    return count
