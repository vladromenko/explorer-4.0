"""Distinct resource costs and paired outcomes must not become extra demonstrations or physical evidence."""

import pytest

from explorer4.sim_protocol import sha256_file
from scripts.demo_efficiency import design
from scripts.demo_efficiency.accounting import COSTS, human_minutes, paired_size


def test_time_deduplicates_shared_resources_and_partial_coverage_is_unknown(tmp_path):
    evidence = tmp_path / "operator_log"
    evidence.write_text("one observed calibration")
    ref = {"path": str(evidence), "sha256": sha256_file(evidence)}
    shared = ["common", "take-A"]
    event = {
        "id": "cal-1",
        "person_id": "operator",
        "category": "calibration",
        "start_utc_s": 10.0,
        "end_utc_s": 130.0,
        "resources": shared,
        "evidence": ref,
    }
    ledger = {
        "intervals": [event],
        "coverage": [
            {"resource": r, "category": c, "complete": True, "evidence": ref, "observer": "reviewer"}
            for c in COSTS
            for r in shared
        ],
    }
    assert human_minutes(ledger, shared)["total_minutes"] == 2.0
    ledger["coverage"].pop()
    assert human_minutes(ledger, shared)["total_minutes"] is None
    ledger["intervals"].append({**event, "id": "other", "category": "reset", "start_utc_s": 129.0})
    with pytest.raises(ValueError, match="Overlapping"):
        human_minutes(ledger, shared)
    assert paired_size([], domain="real")["required_pairs"] is None
    paired = [
        {
            "scene": i,
            "domain": "sim",
            "partition": "pilot",
            "evidence": "bound-by-replay",
            "T1": i % 3 != 0,
            "T2": i % 4 != 0,
        }
        for i in range(12)
    ]
    size = paired_size(paired, domain="sim")
    assert 12 < size["required_pairs"] < 1000 and size["design_power"] >= 0.8
    with pytest.raises(ValueError):
        paired_size(paired, domain="real")


def test_freeze_rejects_simulated_donor_before_dataset_or_training(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(design, "preflight", lambda _: {"motor_comparison_ready": False})
    monkeypatch.setattr(
        design, "datasets", SimpleNamespace(load_plan=lambda *a: pytest.fail("opened target corpus"))
    )
    with pytest.raises(ValueError, match="real human"):
        design.freeze("sim-packet")


def test_queue_materializes_all_five_arms_for_the_same_nested_physical_takes(tmp_path, monkeypatch):
    import json

    from explorer4 import datasets, study_day, training_drafts
    from explorer4.profiles import profile
    from scripts.demo_efficiency import prepare as queue

    ident = "d" * 64
    contract = {**profile(design.TARGET), "task": "pick up the cube"}
    base = {
        "domain": "real",
        "smoke": False,
        "profile": design.TARGET,
        "profile_contract": contract,
        "recorded_instruction": contract["task"],
        "seed": 1000,
        "sim_model_hash": None,
    }
    real = [{"id": str(i), "sha256": str(i) * 64, "frames": 70, "profile": design.TARGET} for i in range(5)]
    base["splits"] = {
        "train": real,
        "validation": [{"id": "v", "frames": 20}],
        "test": [{"id": "t", "frames": 20}],
    }
    plan = {
        "k": design.K,
        "paired_aux_scenes": 2,
        "ticks_per_synthetic_take": 360,
        "target_plan_id": "1" * 64,
        "training": {"policy": "act", "steps": 1000, "batch": 8, "train_seed": 1000, "device": "cuda"},
        "ordered_training_takes": [e["id"] for e in real],
        "pilot_seeds": list(design.PILOT_SEEDS),
    }
    pool = {e["id"]: e for e in real}
    (tmp_path / "imports").mkdir()
    (tmp_path / "selection.json").write_text(json.dumps({"matched": True, "seeds": [1, 2]}))
    for s in (1, 2):
        for arm in design.AUX:
            key = arm + str(s)
            ep = tmp_path / key
            ep.mkdir()
            pool[key] = {
                "id": key,
                "profile": design.SIM,
                "dataset": str(ep),
                "frames": 360,
                "outcome": "success",
            }
            (ep / "provenance.json").write_text(
                json.dumps(
                    {
                        "domain": "sim",
                        "synthetic": True,
                        "profile": contract,
                        "hardware": {
                            "model": {"xml_sha256": "f" * 64},
                            "efficiency": {"plan": ident, "arm": arm, "seed": s},
                        },
                    }
                )
            )
            (tmp_path / "imports" / f"{s}-{arm}.json").write_text(
                json.dumps({"episode_id": key, "dataset_sha256": "a" * 64})
            )
    for m in (queue, study_day, training_drafts, datasets):
        monkeypatch.setattr(m, "DATA", tmp_path)
    monkeypatch.setattr(queue, "load", lambda _: (plan, tmp_path))
    monkeypatch.setattr(queue.catalog, "rows", lambda _: list(pool.values()))
    monkeypatch.setattr(queue, "relatives", lambda e, *a, **kw: {("episode", e["id"])})
    monkeypatch.setattr(queue, "probe_geometry", lambda _: {"xml_sha256": "f" * 64})
    monkeypatch.setattr(queue, "target_statistics", lambda real: ({}, str(len(real)) * 64))
    monkeypatch.setattr(datasets, "fingerprint", lambda _: "a" * 64)

    def load_plan(key, verify=True):
        return (
            base
            if key == plan["target_plan_id"]
            else json.loads((tmp_path / "plans" / (key + ".json")).read_text())
        )

    monkeypatch.setattr(datasets, "load_plan", load_plan)
    sid = queue.prepare(ident, "2026-11-25")
    result = study_day.read_plan(sid)
    assert len(result["tasks"]) == 30 and not (tmp_path / "jobs").exists()
    for k in design.K:
        for arm in design.ARMS:
            draft = training_drafts.load(result["tasks"][f"{arm}-k{k}"]["draft"])
            d = load_plan(draft["plan_id"])
            assert d["receiver_normalization"]["target_ids"] == [e["id"] for e in real[:k]]
            assert d["synthetic_frames"] == (0 if arm == "T0" else 720)
            assert (draft["steps"], draft["batch_size"], draft["train_seed"]) == (1000, 8, 1000)
            assert result["tasks"][f"{arm}-k{k}-receiver"]["seeds"] == list(design.PILOT_SEEDS)
