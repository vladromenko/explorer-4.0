"""Observed durations and delayed donor bindings used by the ordinary demonstration-efficiency report."""

import json
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from explorer4 import datasets, field_time as timer, knowledge
from explorer4.cognitive.store import digest
from scripts.demo_efficiency import report
from scripts.demo_efficiency.accounting import human_minutes
from test_skill_packets import packet_fixture


@pytest.fixture
def field(tmp_path, monkeypatch):
    for mod in (timer, datasets, knowledge, report):
        monkeypatch.setattr(mod, "DATA", tmp_path)
    monkeypatch.setattr(timer, "FOLDER", tmp_path / "field-time")
    root = tmp_path / "datasets/donor"
    (root / "donor_geometry").mkdir(parents=True)
    (root / "donor_geometry/provenance.json").write_text('{"frames":12}')
    originals = {"donor:episode-a": root}
    monkeypatch.setattr(timer, "options", lambda: ({"real-target": "Target training take"}, originals))
    now = {"utc_s": 1000.0, "monotonic_ns": int(1000e9), "boot": "A"}
    monkeypatch.setattr(timer, "clock", lambda: dict(now))
    return root, now


def advance(clock, seconds):
    clock["utc_s"] += seconds
    clock["monotonic_ns"] += int(seconds * 1e9)


def packet(tmp_path, source, fingerprint):
    item = packet_fixture()
    item["donor"]["episodes"] = [{"id": source, "sha256": fingerprint}]
    verify = tmp_path / "world/skill_verifications" / (source + "-control.json")
    verify.parent.mkdir(exist_ok=True, parents=True)
    verify.write_text(json.dumps({"episode_id": source, "episode_sha256": fingerprint}))
    item["donor_verification"].update(
        evidence_ref=str(verify.relative_to(tmp_path)), evidence_sha256=timer.sha256_file(verify)
    )
    ident = digest(item)
    folder = tmp_path / "world/skill_packets"
    folder.mkdir(exist_ok=True, parents=True)
    (folder / (ident + ".json")).write_text(json.dumps(item))
    return ident


def test_source_binding_and_normal_report(field, tmp_path, monkeypatch):
    root, now = field
    e = timer.start(" Operator ", "donor_demo", "new:donor")
    with pytest.raises(ValueError):
        timer.start("operator", "reset", "common")
    advance(now, 120)
    timer.stop(e["id"])
    timer.bind(e["origin_resource"], "donor:episode-a", "observer")
    p = packet(tmp_path, "episode-a", datasets.fingerprint(root))
    assert human_minutes(timer.read(), [p])["known_minutes"] == 0
    wrong = packet(tmp_path, "another-episode", datasets.fingerprint(root))
    with pytest.raises(ValueError):
        timer.bind("donor:episode-a", wrong, "observer")
    timer.bind("donor:episode-a", p, "observer")
    timer.bind("donor:episode-a", p, "observer")
    assert human_minutes(timer.read(), [p, e["origin_resource"], "donor:episode-a"])["known_minutes"] == 2
    assert len(timer.read()["bindings"]["donor:episode-a"]) == 1
    prep = timer.start("operator", "preparation", "common")
    advance(now, 60)
    timer.stop(prep["id"])
    assert timer.summary(timer.read())["known_preparation_minutes"] == 1
    plan = {
        "k": [1],
        "ordered_training_takes": ["real-target"],
        "packet": p,
        "pilot_seeds": [7],
        "power": {"minimum_useful_gain": 0.20},
    }
    monkeypatch.setattr(report, "load", lambda key: (plan, tmp_path))
    monkeypatch.setattr(report.study_day, "read_plan", lambda key: {"efficiency_plan": "protocol"})
    monkeypatch.setattr(report.catalog, "rows", lambda table: [])
    found = {}
    for a in ("T1", "T2"):
        key = a + "-k1"
        found[key] = {"id": key}
        found[key + "-receiver"] = {
            "id": key,
            "status": "completed",
            "config": json.dumps({"demo_efficiency": "protocol", "source_job": key, "protocol": "fixture"}),
        }
        folder = tmp_path / "jobs" / key
        folder.mkdir(parents=True)
        (folder / "result.json").write_text(
            json.dumps(
                {
                    "protocol": "fixture",
                    "profile": report.SIM,
                    "trials": [{"seed": 7}],
                    "checkpoint_sha256": "example",
                }
            )
        )
    monkeypatch.setattr(report.study_day, "find_jobs", lambda *args: found)
    monkeypatch.setitem(
        sys.modules, "explorer4.sim.factory", SimpleNamespace(make=lambda *a, **kw: nullcontext(None))
    )
    monkeypatch.setattr(report, "terminal", lambda *args: {"success": False})
    result = report.summarize("protocol", "day", json.loads((timer.FOLDER / "ledger.json").read_text()))
    assert [r["human_time"]["known_minutes"] for r in result["rows"]] == [1.0, 3.0]
    assert all(r["human_time"]["total_minutes"] is None for r in result["rows"])
    assert len(timer.read()["intervals"]) == 2


def test_reboot_and_source_mutation_do_not_create_minutes_or_transfer(field, tmp_path):
    root, now = field
    event = timer.start("one", "annotation", "donor:episode-a")
    advance(now, 10)
    now["boot"] = "B"
    with pytest.raises(ValueError, match="часов"):
        timer.stop(event["id"])
    timer.stop(event["id"], unmeasured=True)
    assert not timer.read()["intervals"] and len(timer.read()["unmeasured"]) == 1
    next_event = timer.start("one", "correction", "donor:episode-a")
    advance(now, 30)
    timer.stop(next_event["id"])
    (root / "donor_geometry/provenance.json").write_text('{"frames":13}')
    key = packet(tmp_path, "episode-a", datasets.fingerprint(root))
    with pytest.raises(ValueError, match="изменилась"):
        timer.bind("donor:episode-a", key, "observer")
    assert human_minutes(timer.read(), [key])["total_minutes"] is None
