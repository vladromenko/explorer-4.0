"""Prospective operator time, independent of recording, robot leases and training."""

import json
import time
import uuid
from pathlib import Path

from . import catalog, datasets, fleet_config, knowledge, skill_packets
from .paths import DATA
from .sim_protocol import sha256_file
from scripts.demo_efficiency import design
from scripts.demo_efficiency.accounting import human_minutes, verify_reference

FOLDER = DATA / "demo-efficiency/field-time"
CATEGORIES = {
    "preparation": "Подготовка площадки или оборудования",
    "calibration": "Измерение калибровки",
    "annotation": "Разметка или просмотр",
    "reset": "Восстановление сцены",
    "donor_demo": "Показ SO-101",
    "target_demo": "Показ ROSMASTER",
    "correction": "Исправление ошибки",
}
STATIC = {
    "common": "Общее для сравнения показов",
    "field:docking": "Полевая серия подъезда Tank–ROSMASTER",
    "field:grasp": "Полевые проверки захвата",
    **{f"{a}-k{k}": f"Условие {a}, {k} показов" for a in design.ARMS for k in design.K},
}


def read():
    path = FOLDER / "ledger.json"
    if path.is_file():
        return json.loads(path.read_text())
    return {
        "schema": "explorer-field-person-time-v1",
        "target_plan": design.PLAN,
        "active": {},
        "intervals": [],
        "unmeasured": [],
        "coverage": [],
        "resources": {},
        "bindings": {},
    }


def options():
    targets = {}
    try:
        plan = datasets.load_plan(design.PLAN, verify=False)
        targets = {i: "Учебный показ ROSMASTER · " + i for i in design.original_takes(plan)}
    except FileNotFoundError:
        pass
    donors = {}
    episodes = catalog.rows("episodes")
    for e in episodes:
        path = Path(e["dataset"])
        if (
            e["profile"] == "so101_pick_place"
            and e["category"] in ("demonstration", "correction")
            and not e["excluded"]
            and (path / "donor_geometry/provenance.json").is_file()
        ):
            meta = json.loads((path / "provenance.json").read_text())
            if (
                meta.get("domain") == "real"
                and meta.get("synthetic") is False
                and meta.get("command_source") == "human"
            ):
                donors["donor:" + e["id"]] = path
    return targets, donors


def labels(state, choices=None):
    targets, donors = choices if choices is not None else options()
    return {
        **STATIC,
        **targets,
        **{k: "Измеренный показ SO-101 · " + k.split(":", 1)[1] for k in donors},
        **{k: v["label"] for k, v in state["resources"].items()},
        "new:donor": "Новый показ SO-101, запись ещё не сохранена",
    }


def clock():
    return {
        "utc_s": time.time(),
        "monotonic_ns": time.monotonic_ns(),
        "boot": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
    }


def receipt(identity, document):
    # A retry after an interrupted save can leave an unused receipt, never a credited interval.
    from .cognitive.store import digest

    path = FOLDER / "evidence" / (identity + "-" + digest(document) + ".json")
    if not path.is_file():
        fleet_config.atomic_write(path, document)
    elif json.loads(path.read_text()) != document:
        raise ValueError("Изменилось свидетельство хронометража")
    return {"path": str(path.resolve()), "sha256": sha256_file(path)}


def persist(state):
    fleet_config.atomic_write(FOLDER / "ledger.json", state)


def take_proof(donor, path):
    return {
        "episode_id": donor.split(":", 1)[1],
        "episode_sha256": datasets.fingerprint(path),
        "measured_geometry_sha256": sha256_file(path / "donor_geometry/provenance.json"),
    }


def start(person, activity, resource):
    person = " ".join(str(person or "").strip().casefold().split())
    if not 0 < len(person) <= 80 or activity not in CATEGORIES:
        raise ValueError("Укажите участника и вид работы")
    timestamp = clock()
    resources = options()
    donor = resources[1].get(resource)
    audited_take = take_proof(resource, donor) if donor else None
    choices = labels(read(), resources)
    if resource not in choices:
        raise ValueError("Неизвестный ресурс исследования")
    with fleet_config.locked(FOLDER):
        state = read()
        if any(x["person_id"] == person for x in state["active"].values()):
            raise ValueError("Для участника уже идёт отсчёт")
        if any(x["person_id"] == person and x["end_utc_s"] > timestamp["utc_s"] for x in state["intervals"]):
            raise ValueError("Часы вернулись назад, новый интервал пересечётся с предыдущим")
        ident = uuid.uuid4().hex
        if resource == "new:donor":
            resource = "pending-donor:" + ident
            state["resources"][resource] = {
                "label": "Новый SO-101 · " + ident[:8],
                "kind": "pending_donor_take",
            }
        event = {
            "id": ident,
            "person_id": person,
            "category": "calibration" if activity == "preparation" else activity,
            "activity": activity,
            "measured_take": audited_take,
            "origin_resource": resource,
            "start": timestamp,
        }
        state["active"][ident] = event
        persist(state)
        return event


def attributed(state, origin):
    resources = [origin]
    for resource in resources:
        for bound in state["bindings"].get(resource, {}):
            if bound not in resources:
                resources.append(bound)
    return resources


def stop(ident, *, unmeasured=False):
    with fleet_config.locked(FOLDER):
        state = read()
        if ident not in state["active"]:
            raise ValueError("Этот интервал уже закрыт")
        event = state["active"][ident]
        start_time = event["start"]
        end = clock()
        wall = end["utc_s"] - start_time["utc_s"]
        elapsed = (end["monotonic_ns"] - start_time["monotonic_ns"]) / 1e9
        if not unmeasured and (
            start_time["boot"] != end["boot"] or elapsed <= 0 or wall <= 0 or abs(elapsed - wall) > 2.0
        ):
            raise ValueError("Непрерывность часов не подтверждена. Закройте этот интервал без зачёта")
        proof = receipt(
            ident,
            {**event, "end": end, "measured": not unmeasured, "source": "operator_observed_start_and_stop"},
        )
        row = {k: event[k] for k in ("id", "person_id", "category", "activity", "origin_resource")}
        row.update(
            start_utc_s=start_time["utc_s"],
            end_utc_s=end["utc_s"],
            resources=attributed(state, event["origin_resource"]),
            evidence=proof,
        )
        state["unmeasured" if unmeasured else "intervals"].append(row)
        del state["active"][ident]
        persist(state)


def bind(source, destination, observer):
    observer = str(observer or "").strip()
    if not observer or len(observer) > 80:
        raise ValueError("Укажите участника, подтвердившего связь")
    _, donors = options()
    state = read()
    if source.startswith("pending-donor:") and source in state["resources"] and destination in donors:
        donor = destination
    elif source in donors and len(destination) == 64:
        donor = source
    else:
        raise ValueError("Выберите измеренную запись и совместимый ресурс")
    details = take_proof(donor, donors[donor])
    take, fingerprint = details["episode_id"], details["episode_sha256"]
    if donor == source:
        packet = knowledge.load_packet(destination)
        verification = packet["donor_verification"]
        evidence = (DATA / verification["evidence_ref"]).resolve()
        if (
            not evidence.is_relative_to(DATA.resolve())
            or sha256_file(evidence) != verification["evidence_sha256"]
        ):
            raise ValueError("Изменилось свидетельство проверки донорского показа")
        record = json.loads(evidence.read_text())
        if (record.get("episode_id"), record.get("episode_sha256")) != (take, fingerprint):
            raise ValueError("Проверка донорского показа относится к другой записи")
        if (
            packet["donor"]["behavior_source"] != "human"
            or not skill_packets.admission(packet, domain="real")["eligible"]
            or {"id": take, "sha256": fingerprint} not in packet["donor"]["episodes"]
        ):
            raise ValueError("Допущенный пакет должен ссылаться на эту физическую запись и отпечаток")
    with fleet_config.locked(FOLDER):
        state = read()
        previous = [
            event["measured_take"]
            for event in state["active"].values()
            if event["origin_resource"] == donor and event.get("measured_take")
        ]
        for event in state["intervals"]:
            if event["origin_resource"] == donor:
                verify_reference(event["evidence"])
                measured = json.loads(Path(event["evidence"]["path"]).read_text()).get("measured_take")
                if measured:
                    previous.append(measured)
        for links in state["bindings"].values():
            if donor in links:
                verify_reference(links[donor])
                previous.append(json.loads(Path(links[donor]["path"]).read_text()))
        if any(x["episode_sha256"] != fingerprint for x in previous):
            raise ValueError("Исходная запись изменилась после замера времени")
        existing = state["bindings"].setdefault(source, {})
        if source.startswith("pending-donor:") and existing and destination not in existing:
            raise ValueError("Время этого показа уже привязано к другой записи")
        if destination not in existing:
            existing[destination] = receipt(
                "binding",
                {"from": source, "to": destination, "verified_by": observer, "at": clock(), **details},
            )
        for row in state["intervals"]:
            row["resources"] = attributed(state, row["origin_resource"])
        persist(state)


def summary(state):
    resources = {r for row in state["intervals"] for r in row["resources"]}
    report = human_minutes(state, resources or {"common"})
    report["known_preparation_minutes"] = sum(
        (r["end_utc_s"] - r["start_utc_s"]) / 60 for r in state["intervals"] if r["activity"] == "preparation"
    )
    return report
