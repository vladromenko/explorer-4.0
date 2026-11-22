"""One-use and all-axis real development evidence must remain fail-closed."""

import json

import pytest

from explorer4 import grasp_admission as gate


def test_missing_human_sequences_never_open_single_trial(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "references", lambda path: [])
    monkeypatch.setattr(gate, "summary", lambda path: {"status": "positive"})
    result = gate.review(tmp_path)
    assert result["status"] == "blocked" and "0 из 3" in result["reason"]
    assert not result["reference_episodes"]
    monkeypatch.setattr(gate, "open_session", lambda ident: tmp_path)
    with pytest.raises(PermissionError):
        gate.make_plan(tmp_path.name)


def test_one_use_claim_is_durable_even_on_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "open_session", lambda ident: tmp_path)
    monkeypatch.setattr(gate, "require", lambda plan: None)
    plan = {"id": "one", "approval_sha256": "fixed", "session": "one-camera"}
    gate.claim(plan)
    with pytest.raises(PermissionError):
        gate.claim(plan)
    assert json.loads((tmp_path / "physical-trial-claimed.json").read_text())["decision_sha256"] == "fixed"


def test_sample_at_deadline_cannot_issue_another_action(tmp_path):
    session = object.__new__(gate.LiveGrasp)
    session.path = tmp_path
    (tmp_path / "physical-trial-claimed.json").write_text(json.dumps({"plan": "claimed"}))
    session.plan_id = "claimed"
    session.index = gate.TICKS
    with pytest.raises(StopIteration):
        session.next_sample({})
