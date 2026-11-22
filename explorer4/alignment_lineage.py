"""Record the exact task configuration used by simulated observations and audit its real-data parents."""

import hashlib
import json
from pathlib import Path


def configuration_record(config):
    ancestry = config.get("alignment_provenance")
    if ancestry is None:
        mode = "instructions" if config.get("source") == "instructions" else "unknown"
        ancestry = {"mode": mode, "source_episodes": []}
    record = {
        **ancestry,
        "parameters": {k: v for k, v in config.items() if k != "alignment_provenance"},
    }
    encoded = json.dumps(
        record, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return {**record, "configuration_sha256": hashlib.sha256(encoded).hexdigest()}


def relatives(episode, pool, *, confirm_alignment=False):
    """Resolve intermediate parents even when they are absent from the compared splits."""
    from . import datasets

    tokens, visited, active = set(), set(), set()

    def visit(e):
        ident = e["id"]
        if ident in active:
            raise ValueError("cycle in recording ancestry: " + ident)
        if ident in visited:
            return
        active.add(ident)
        tokens.add(("episode", ident))
        tokens.update((key, e[key]) for key in ("session", "scene") if e.get(key))
        raw = json.loads((Path(e["dataset"]) / "provenance.json").read_text())
        hw = raw.get("hardware", {})
        donor = hw.get("transfer_lineage", {})
        parents = set(e.get("lineage_sources", [])) | set(
            donor.get("ancestor_episode_ids", [])
        )
        parents.update(p["id"] for p in donor.get("source_episodes", []))
        parents.update(
            v
            for v in (
                raw.get("source_episode"),
                hw.get("source_episode"),
                hw.get("start_source_episode"),
            )
            if v
        )
        alignment = hw.get("model", {}).get("alignment")
        if confirm_alignment and e.get("profile") in datasets.SIM_FOR_REAL.values():
            if not isinstance(alignment, dict) or alignment.get("mode") not in {
                "instructions",
                "frozen_train",
            }:
                raise ValueError("alignment parents unrecorded or diagnostic: " + ident)
            if not isinstance(alignment.get("parameters"), dict):
                raise ValueError("missing aligned scene parameters: " + ident)
            ancestry = {
                k: v
                for k, v in alignment.items()
                if k not in ("parameters", "configuration_sha256")
            }
            expected = configuration_record(
                {**alignment["parameters"], "alignment_provenance": ancestry}
            )
            if (
                expected != alignment
                or alignment["parameters"].get("source")
                != {"instructions": "instructions", "frozen_train": "measured"}[
                    alignment["mode"]
                ]
            ):
                raise ValueError(
                    "aligned scene parameters or provenance changed: " + ident
                )
            if alignment["mode"] == "frozen_train":
                plan = datasets.load_plan(alignment["plan_id"], verify=False)
                train = {
                    p["id"]: p["sha256"]
                    for p in plan["splits"]["train"]
                    if p.get("domain", "real") == "real"
                }
                if (
                    plan["domain"] != "real"
                    or plan.get("smoke")
                    or datasets.SIM_FOR_REAL.get(plan["profile"]) != e["profile"]
                    or not alignment.get("source_episodes")
                    or any(
                        train.get(p["id"]) != p["sha256"]
                        for p in alignment["source_episodes"]
                    )
                ):
                    raise ValueError(
                        "alignment does not derive exclusively from the stated frozen training plan: "
                        + ident
                    )
            elif alignment.get("source_episodes"):
                raise ValueError("instruction scene unexpectedly lists fitted data")
        if alignment:
            parents.update(p["id"] for p in alignment.get("source_episodes", []))
        for parent in sorted(parents):
            if parent not in pool:
                raise ValueError("unresolved recording ancestor: " + parent)
            visit(pool[parent])
        active.remove(ident)
        visited.add(ident)

    visit(episode)
    return tokens
