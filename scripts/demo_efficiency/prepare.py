"""Prepare ordinary offline ACT drafts and Study Day tasks; preparation never starts a trainer."""

import json
from pathlib import Path

from explorer4 import catalog, datasets, study_day, training_drafts
from explorer4.alignment_lineage import relatives
from explorer4.paths import DATA
from explorer4.sim_protocol import probe_geometry

from .design import ARMS, SIM, TARGET, load


def target_statistics(originals):
    from lerobot.datasets.compute_stats import aggregate_stats
    from lerobot.datasets.io_utils import load_stats
    from lerobot.datasets.utils import serialize_dict

    from explorer4.cognitive.store import digest

    stats = serialize_dict(aggregate_stats([load_stats(Path(e["dataset"])) for e in originals]))
    return stats, digest(stats)


def install_target_statistics(plan, train_dir):
    from explorer4.fleet_config import atomic_write

    spec = plan["receiver_normalization"]
    originals = [e for e in plan["splits"]["train"] if e.get("domain", "real") == "real"]
    stats, checksum = target_statistics(originals)
    if [e["id"] for e in originals] != spec["target_ids"] or checksum != spec["sha256"]:
        raise ValueError("Unique physical sources or upstream normalization statistics changed")
    atomic_write(train_dir / "meta/stats.json", stats)


def prepare(ident, day):
    from datetime import date

    date.fromisoformat(day)
    p, root = load(ident)
    selection = json.loads((root / "selection.json").read_text())
    if not selection["matched"] or len(selection["seeds"]) != p["paired_aux_scenes"]:
        raise ValueError("Matched generation budget not reached; no comparison can be queued")
    physical = datasets.load_plan(p["target_plan_id"])
    pool = {e["id"]: e for e in catalog.rows("episodes")}
    held = set().union(
        *(relatives(e, pool) for role in ("validation", "test") for e in physical["splits"][role])
    )
    sim_geometry = probe_geometry(SIM)
    train = {e["id"]: e for e in physical["splits"]["train"]}
    tasks, groups = {}, []
    fit = p["training"]
    for k in p["k"]:
        real = [train[i] for i in p["ordered_training_takes"][:k]]
        _, stats_sha = target_statistics(real)
        train_keys = []
        eval_keys = []
        for arm in ARMS:
            aux = []
            if arm != "T0":
                for seed in selection["seeds"]:
                    data = json.loads((root / "imports" / f"{seed}-{arm}.json").read_text())
                    e = pool[data["episode_id"]]
                    raw = json.loads((Path(e["dataset"]) / "provenance.json").read_text())
                    hw = raw["hardware"]
                    contract = training_drafts.semantic_contract(raw["profile"])
                    tokens = relatives(e, pool, confirm_alignment=True)
                    target_lineage = {
                        v for key, v in tokens if key == "episode" and pool[v]["profile"] == TARGET
                    }
                    if not target_lineage.issubset({take["id"] for take in real}):
                        raise ValueError(
                            "Synthetic geometry or ancestry consumes extra target demonstrations at this k"
                        )
                    if (
                        hw["efficiency"] != {"plan": ident, "arm": arm, "seed": seed}
                        or hw["model"]["xml_sha256"] != sim_geometry["xml_sha256"]
                        or e.get("excluded")
                        or e["outcome"] != "success"
                        or raw["domain"] != "sim"
                        or raw["synthetic"] is not True
                        or contract != training_drafts.semantic_contract(physical["profile_contract"])
                        or e["frames"] != p["ticks_per_synthetic_take"]
                        or tokens & held
                    ):
                        raise ValueError("Auxiliary source, geometry, contract or held-out lineage mismatch")
                    sha = datasets.fingerprint(e["dataset"])
                    if sha != data["dataset_sha256"]:
                        raise ValueError("Auxiliary changed since verified capture")
                    aux.append({**e, "domain": "sim", "sha256": sha})
            splits = {**physical["splits"], "train": [*real, *aux]}
            plan = {
                **physical,
                "splits": splits,
                "comparison": ident,
                "arm": arm,
                "k_unique_target_takes": k,
                "physical_source_plan": p["target_plan_id"],
                "receiver_normalization": {"target_ids": [e["id"] for e in real], "sha256": stats_sha},
                "synthetic_frames": sum(e["frames"] for e in aux),
            }
            pid = training_drafts.save_content(DATA / "plans", plan)
            draft, _ = training_drafts.prepare(
                TARGET,
                fit["policy"],
                plan_id=pid,
                steps=fit["steps"],
                batch=fit["batch"],
                train_seed=fit["train_seed"],
                device=fit["device"],
            )
            key = f"{arm}-k{k}"
            test_key = key + "-receiver"
            tasks[key] = {"kind": "train", "steps": fit["steps"], "draft": draft}
            tasks[test_key] = {
                "kind": "simulation",
                "source": key,
                "profile": SIM,
                "physics": sim_geometry["xml_sha256"],
                "seeds": p["pilot_seeds"],
                "demo_efficiency": ident,
                "geometry": sim_geometry,
            }
            train_keys.append(key)
            eval_keys.append(test_key)
        groups.extend(
            [
                {"title": f"k={k}: train", "needs": [], "keys": train_keys},
                {"title": f"k={k}: recipient alone", "needs": train_keys, "keys": eval_keys},
            ]
        )
    value = {
        "day": day,
        "timezone": "Europe/Moscow",
        "study": "demonstration-efficiency",
        "comparison": "T2 vs T1 at k=3; simulation development; recipient ACT only",
        "limits": "Five matched treatments at k=1,3,5; human minutes require separately measured intervals",
        "efficiency_plan": ident,
        "tasks": tasks,
        "groups": groups,
    }
    sid = training_drafts.save_content(DATA / "study-days", value)
    study_day.read_plan(sid)
    return sid
