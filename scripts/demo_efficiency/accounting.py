"""Paired pilot sizing and separately observable person-time in the donor/recipient comparison."""

import itertools
import math
from pathlib import Path

import numpy as np
from scipy.stats import beta, binom

from explorer4.sim_protocol import sha256_file

COSTS = ("donor_demo", "target_demo", "calibration", "annotation", "reset", "correction")


def verify_reference(value):
    if not isinstance(value, dict) or not value.get("path") or len(value.get("sha256", "")) != 64:
        raise ValueError("An auditable source requires a local file path and SHA256")
    if sha256_file(Path(value["path"])) != value["sha256"]:
        raise ValueError("Measurement or reviewer receipt changed")
    return True


def human_minutes(ledger, resources):
    """A shared interval is charged once per counterfactual arm, never once per use."""
    if ledger is None:
        return {"total_minutes": None, "known_minutes": 0.0, "unknown_categories": list(COSTS)}
    records = ledger["intervals"]
    by_person = {}
    ids = set()
    for event in records:
        start, end = event["start_utc_s"], event["end_utc_s"]
        if (
            event["id"] in ids
            or not event["person_id"]
            or not event["evidence"]
            or not event.get("resources")
            or event["category"] not in COSTS
            or not all(math.isfinite(v) for v in (start, end))
            or not end > start
        ):
            raise ValueError("Invalid human interval or missing source")
        verify_reference(event["evidence"])
        ids.add(event["id"])
        by_person.setdefault(event["person_id"], []).append((start, end))
    for events in by_person.values():
        ordered = sorted(events)
        if any(b[0] < a[1] for a, b in itertools.pairwise(ordered)):
            raise ValueError("Overlapping intervals for one person would double-count labour")
    seconds = {cat: 0.0 for cat in COSTS}
    resources = set(resources)
    for event in records:
        if resources.intersection(event["resources"]):
            seconds[event["category"]] += event["end_utc_s"] - event["start_utc_s"]
    # A measured zero requires a signed coverage record with a source; no intervals alone means unknown.
    covered = {
        (r["resource"], r["category"])
        for r in ledger.get("coverage", [])
        if r.get("complete") is True
        and r.get("observer")
        and r["category"] in COSTS
        and verify_reference(r["evidence"])
    }
    unknown = [c for c in COSTS if any((r, c) not in covered for r in resources)]
    minutes = {c: v / 60 for c, v in seconds.items()}
    return {
        "total_minutes": None if unknown else sum(minutes.values()),
        "known_minutes": sum(minutes.values()),
        "by_category_minutes": minutes,
        "unknown_categories": unknown,
    }


def paired_size(pairs, delta=0.20, *, domain, alpha=0.05, power=0.8):
    """Exact positive-tail rejection of a two-sided McNemar test under a matched alternative."""
    if not pairs:
        return {"required_pairs": None, "domain": domain, "reason": "No independent paired pilot"}
    if not (0 < delta <= 1 and 0 < alpha < 1 and 0 < power < 1):
        raise ValueError("Invalid design parameters")
    if len({p["scene"] for p in pairs}) != len(pairs) or any(
        p.get("partition") != "pilot"
        or p.get("domain") != domain
        or type(p.get("T1")) is not bool
        or type(p.get("T2")) is not bool
        or not p.get("evidence")
        for p in pairs
    ):
        raise ValueError("Each independent pilot layout needs a paired binary endpoint in the same domain")
    n0 = len(pairs)
    discordant = sum(p["T1"] != p["T2"] for p in pairs)
    # Higher discordance gives lower power for the same useful net gain. Protect the small pilot with
    # a prespecified one-sided exact 90% upper confidence bound, capped at the feasible alternative.
    q = max(delta, float(beta.ppf(0.90, discordant + 1, n0 - discordant)) if discordant < n0 else 1.0)
    p_plus = (1 + delta / q) / 2
    m = np.arange(2001)
    upper = binom.isf(alpha / 2, m, 0.5).astype(int) + 1
    conditional = binom.sf(upper - 1, m, p_plus)
    result = {
        "domain": domain,
        "pilot_pairs": n0,
        "discordant": int(discordant),
        "discordance_upper_used": q,
        "minimum_useful_net_gain": delta,
        "target_power": power,
        "two_sided_alpha": alpha,
        "required_pairs": None,
    }
    for n in range(2, len(m)):
        achieved = float(binom.pmf(m[: n + 1], n, q) @ conditional[: n + 1])
        if achieved >= power:
            return {
                **result,
                "required_pairs": n,
                "design_power": achieved,
                "confirmation_must_exclude_pilot_scenes": True,
            }
    return {**result, "reason": "More than 2000 independent pairs required under the pilot assumption"}
