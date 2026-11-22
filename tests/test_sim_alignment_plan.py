"""An explicit physical partition fixes which measurements may shape the simulation."""

import json

import numpy as np
import pytest

from explorer4 import alignment_lineage, datasets
from explorer4.training_drafts import save_content
from scripts import sim_align


def test_alignment_uses_train_only_with_frozen_measurements_and_refuses_diagnostic_apply(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(datasets, "DATA", tmp_path)
    root = tmp_path / "datasets" / "train"
    root.mkdir(parents=True)
    raw = {
        "domain": "real",
        "synthetic": False,
        "category": "demonstration",
        "outcome": "success",
        "profile": {"task": "pick up the cube"},
    }
    (root / "provenance.json").write_text(json.dumps(raw))
    (root / "research.jsonl").write_text(
        json.dumps({"observation.state": [1] * 6, "action": [2] * 6}) + "\n"
    )
    sha = datasets.fingerprint(root)
    entry = {
        "id": "training",
        "profile": "rosmaster_pick_place",
        "sha256": sha,
        "dataset": str(root),
    }
    unavailable = {
        "id": "held",
        "dataset": str(tmp_path / "never_open_this"),
        "sha256": "0" * 64,
    }
    plan = {
        "domain": "real",
        "profile": "rosmaster_pick_place",
        "smoke": False,
        "splits": {
            "train": [entry],
            "validation": [unavailable],
            "test": [{**unavailable, "id": "reserved"}],
        },
    }
    ident = save_content(tmp_path / "plans", plan)
    name, found = sim_align.demos(ident)
    assert name == "rosmaster_pick_place" and found[0][0] == {
        "id": "training",
        "sha256": sha,
    }
    np.testing.assert_array_equal(found[0][1], np.ones((1, 6)))
    with pytest.raises(ValueError, match="Choose one frozen"):
        sim_align.demos()
    (root / "research.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="changed after freeze"):
        sim_align.demos(ident)
    monkeypatch.setattr(
        "sys.argv", ["align", "--all-data-pilot", "rosmaster_pick_place", "--apply"]
    )
    with pytest.raises(SystemExit):
        sim_align.main()
    assert (
        alignment_lineage.configuration_record({"source": "measured, parents unknown"})[
            "mode"
        ]
        == "unknown"
    )
