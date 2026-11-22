"""The physical comparison retains scheduled slots, unknown evidence and failed attempts."""

import hashlib
import json
import threading
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from explorer4 import peer_dock_series as series
from explorer4.peer_field_outcomes import paired_outcomes


def recorded_series():
    raw = series.CONFIG.read_bytes()
    return {
        "protocol": json.loads(raw),
        "protocol_sha256": hashlib.sha256(raw).hexdigest(),
        "fixtures": {},
        "attempts": [],
    }


def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(series, "SERIES", tmp_path / "series.json")
    monkeypatch.setattr(series.fleet_config, "locked", nullcontext)


@pytest.mark.parametrize("prior", ["empty", "fixture", "attempt"])
def test_register_only_before_a_fixture_or_attempt(tmp_path, monkeypatch, prior):
    isolated(monkeypatch, tmp_path)
    original = recorded_series()
    if prior == "fixture":
        original["fixtures"]["A"] = {"note": "marked"}
    if prior == "attempt":
        original["attempts"].append(
            {"slot": 0, "id": "old", "layout": "A", "condition": "selective"}
        )
    series.SERIES.write_text(json.dumps(original))
    before = series.SERIES.read_bytes()
    got = series.prepare()
    assert (
        got["protocol"] == original["protocol"]
        and got["protocol_sha256"] == original["protocol_sha256"]
    )
    result = paired_outcomes(got)
    assert len(result["groups"]) == 4
    if prior == "empty":
        supplement = got["sequential_supplement"]
        assert (
            supplement["sha256"] == series.SUPPLEMENT_SHA256
            and supplement["registered_at"] > 0
        )
        schedule = series.checked_order(got)
        assert (
            len(schedule) == 12
            and [a for a in schedule if a[1] != "sequential"]
            == original["protocol"]["order"]
        )
        assert all(
            x["scheduled_pairs"] == 4
            and x["pending_pairs"] == 4
            and x["usable_pairs"] == 0
            for x in result["comparisons"].values()
        )
        preserved = series.SERIES.read_bytes()
        assert (
            series.state() == series.prepare() == got
            and preserved == series.SERIES.read_bytes()
        )
        supplement["protocol"]["order"].reverse()
        with pytest.raises(ValueError, match="порядка"):
            series.next_slot(got)
    else:
        assert (
            "sequential_supplement" not in got and before == series.SERIES.read_bytes()
        )
        assert len(series.checked_order(got)) == 8
        assert all(x["scheduled_pairs"] == 0 for x in result["comparisons"].values())


def test_failures_unknowns_and_calls_have_separate_denominators(tmp_path, monkeypatch):
    isolated(monkeypatch, tmp_path)
    state = series.prepare()
    order = series.checked_order(state)

    def add(slot, endpoint, runtime):
        layout, condition = order[slot]
        row = {
            "id": str(slot),
            "layout": layout,
            "condition": condition,
            "slot": slot,
            "runtime": runtime,
        }
        if endpoint is not None:
            row["endpoint"] = endpoint
        state["attempts"].append(row)

    add(
        0,
        {"success": False, "operator_intervention": True},
        {
            "seconds": 2,
            "observations": [
                {"source_robot": "rosmaster"},
                {"source_robot": "rosmaster"},
            ],
        },
    )
    add(
        1,
        {"success": False, "perception_admitted": False},
        {"peer_requests": 0, "seconds": 0, "observations": []},
    )
    add(
        2,
        {"success": True, "perception_admitted": True},
        {"peer_requests": 1, "seconds": 4},
    )
    add(3, {"success": False}, {"peer_requests": 1, "seconds": 12})
    add(4, {"operator_intervention": False}, {"seconds": 8})
    add(5, None, {"reason": "arrived"})
    add(6, {"success": True}, {"peer_requests": 0})
    add(7, {"success": False}, {"peer_requests": 0})
    add(8, {"success": False}, {"peer_requests": 1})
    add(9, {"success": True}, {"peer_requests": 0})
    add(10, {"success": True}, {"peer_requests": 0})
    add(11, {"success": True}, {"peer_requests": 0})
    state["attempts"].reverse()  # Pair frozen slots even if exported out of order.
    result = paired_outcomes(state)
    a1 = result["groups"][0]
    assert a1["complete"] and a1["layout"] == "A" and a1["repetition"] == 1
    old = a1["methods"]["selective"]
    assert (
        old["peer_requests"] is None and old["observed_peer_requests_lower_bound"] == 1
    )
    assert (
        result["methods"]["selective"]["interventions"] == 1
        and result["methods"]["selective"]["request_unknown_attempts"] == 2
    )
    assert (
        result["methods"]["local_scan"]["no_observations"] == 1
        and result["methods"]["local_scan"]["unknown_outcomes"] == 1
    )
    pair = result["comparisons"]["sequential_vs_local_scan"]
    assert (
        pair["scheduled_pairs"],
        pair["measured_pairs"],
        pair["usable_pairs"],
        pair["pending_pairs"],
        pair["unknown_pairs"],
    ) == (4, 4, 3, 0, 1)
    assert (
        pair["sequential_only"],
        pair["comparison_only"],
        pair["both"],
        pair["neither"],
    ) == (1, 1, 1, 0)
    assert (
        pair["rows"][0]["seconds_difference"] == 4
        and pair["rows"][0]["peer_requests_difference"] == 1
    )
    pair = result["comparisons"]["sequential_vs_selective"]
    assert (
        pair["scheduled_pairs"],
        pair["measured_pairs"],
        pair["usable_pairs"],
        pair["pending_pairs"],
    ) == (4, 3, 3, 1)
    assert (
        pair["sequential_only"],
        pair["comparison_only"],
        pair["both"],
        pair["neither"],
    ) == (1, 0, 1, 1)
    assert pair["rows"][0]["peer_requests_difference"] is None


def test_third_slot_uses_donor_budget_and_existing_operator_path(tmp_path, monkeypatch):
    isolated(monkeypatch, tmp_path)
    state = series.prepare()
    for slot, (layout, condition) in enumerate(series.checked_order(state)[:2]):
        state["attempts"].append(
            {
                "id": str(slot),
                "slot": slot,
                "layout": layout,
                "condition": condition,
                "endpoint": {"success": False},
            }
        )
    series.SERIES.write_text(json.dumps(state))
    monkeypatch.setattr(series.field, "operator_session", lambda *a: 123)
    monkeypatch.setattr(series, "check_position", lambda *a: {"verified": "fixture"})
    received = []
    monkeypatch.setattr(series, "PairedAttempt", lambda *a: received.append(a))
    control = SimpleNamespace(lock=threading.RLock())
    ident = series.start(
        control,
        None,
        None,
        SimpleNamespace(scan=lambda robot: [1]),
        fixture_restored=True,
    )
    assert received[0][0:2] == (ident, "sequential")
    assert received[0][2]["donor_budget_s"] == received[0][2]["sensing_budget_s"] == 3
    assert (
        received[0][2]["total_budget_s"] == 20
        and "donor_budget_s" not in series.state()["protocol"]
    )
