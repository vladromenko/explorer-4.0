"""Descriptive comparisons of assigned physical docking attempts after independent scoring."""

import math
from collections import Counter, defaultdict


def effective_order(state):
    supplement = state.get("sequential_supplement")
    return (supplement["protocol"] if supplement else state["protocol"])["order"]


def _attempt(slot, row):
    runtime = row.get("runtime") or {}
    endpoint = row.get("endpoint")
    measured = isinstance(endpoint, dict) and bool(endpoint)
    endpoint = endpoint or {}
    value = endpoint.get("success")
    success = value if isinstance(value, bool) else None
    intervention = endpoint.get("operator_intervention")
    admitted = endpoint.get("perception_admitted")
    observations = runtime.get("observations")
    observed = isinstance(observations, list)
    donor_seen = observed and any(
        e.get("source_robot") == "rosmaster" for e in observations
    )
    requests = runtime.get("peer_requests")
    exact = requests if type(requests) is int and requests in (0, 1) else None
    # A capture proves at least one consultation. Repeated exposures may belong to that same call.
    if donor_seen and exact == 0:
        exact = None
    seconds = runtime.get("seconds")
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
        seconds = None
    if success is True and (
        intervention is True or admitted is False or endpoint.get("valid_run") is False
    ):
        success = None
    status = "scheduled"
    if row:
        status = (
            "awaiting_endpoint"
            if not measured
            else "unknown"
            if success is None
            else "success"
            if success
            else "failure"
        )
    return {
        "slot": slot,
        "id": row.get("id"),
        "started": bool(row),
        "status": status,
        "measured": measured,
        "success": success,
        "peer_requests": exact,
        "observed_peer_requests_lower_bound": int(donor_seen) if row else None,
        "seconds": seconds,
        "intervention": intervention,
        "perception_admitted": admitted,
        "observation_count": len(observations) if observed else None,
        "terminal_reason": runtime.get("reason"),
        "measurement_source": endpoint.get("measurement_source"),
    }


def _method(rows):
    started = [r for r in rows if r["started"]]
    measured = [r for r in rows if r["measured"]]
    requests = [r["peer_requests"] for r in started if r["peer_requests"] is not None]
    seconds = [r["seconds"] for r in started if r["seconds"] is not None]
    return {
        "scheduled": len(rows),
        "started": len(started),
        "measured": len(measured),
        "independent_successes": sum(r["success"] is True for r in measured),
        "measured_failures": sum(r["success"] is False for r in measured),
        "unknown_outcomes": sum(r["success"] is None for r in measured),
        "awaiting_endpoint": len(started) - len(measured),
        "not_started": len(rows) - len(started),
        "interventions": sum(r["intervention"] is True for r in measured),
        "no_observations": sum(r["observation_count"] == 0 for r in started),
        "no_admitted_observation": sum(
            r["perception_admitted"] is False for r in measured
        ),
        "peer_requests": sum(requests)
        if started and len(requests) == len(started)
        else None,
        "known_peer_requests": sum(requests),
        "request_known_attempts": len(requests),
        "request_unknown_attempts": len(started) - len(requests),
        "observed_peer_requests_lower_bound": sum(
            r["observed_peer_requests_lower_bound"] for r in started
        ),
        "mean_seconds": sum(seconds) / len(seconds) if seconds else None,
        "timed_attempts": len(seconds),
    }


def _paired(groups, other):
    outcomes = {
        "both": 0,
        "sequential_only": 0,
        "comparison_only": 0,
        "neither": 0,
        "unknown": 0,
        "pending": 0,
    }
    rows = []
    for group in groups:
        methods = group["methods"]
        if "sequential" not in methods or other not in methods:
            continue
        seq, comparison = methods["sequential"], methods[other]
        if not (seq["measured"] and comparison["measured"]):
            outcome = "pending"
        elif seq["success"] is None or comparison["success"] is None:
            outcome = "unknown"
        else:
            outcome = {
                (True, True): "both",
                (True, False): "sequential_only",
                (False, True): "comparison_only",
                (False, False): "neither",
            }[(seq["success"], comparison["success"])]
        outcomes[outcome] += 1
        row = {
            "layout": group["layout"],
            "repetition": group["repetition"],
            "sequential_slot": seq["slot"],
            "comparison_slot": comparison["slot"],
            "outcome": outcome,
        }
        for key in ("peer_requests", "seconds"):
            values = (seq[key], comparison[key])
            row[key + "_difference"] = (
                values[0] - values[1] if None not in values else None
            )
        rows.append(row)
    return {
        "scheduled_pairs": len(rows),
        "measured_pairs": len(rows) - outcomes["pending"],
        "usable_pairs": len(rows) - outcomes["pending"] - outcomes["unknown"],
        "pending_pairs": outcomes.pop("pending"),
        "unknown_pairs": outcomes.pop("unknown"),
        **outcomes,
        "rows": rows,
    }


def paired_outcomes(state):
    """Pair the nth occurrence of each condition within a marked layout, using its frozen slot."""
    order = effective_order(state)
    assigned = {}
    unassigned = []
    for row in state.get("attempts", []):
        slot = row.get("slot")
        if (
            type(slot) is not int
            or not 0 <= slot < len(order)
            or list(order[slot]) != [row.get("layout"), row.get("condition")]
        ):
            unassigned.append(
                {"id": row.get("id"), "slot": slot, "reason": "assignment_mismatch"}
            )
        elif slot in assigned:
            raise ValueError(f"Duplicate physical trial for frozen slot {slot}")
        else:
            assigned[slot] = row
    repetitions = Counter()
    groups = {}
    by_method = defaultdict(list)
    for slot, (layout, method) in enumerate(order):
        repetitions[layout, method] += 1
        rep = repetitions[layout, method]
        group = groups.setdefault(
            (layout, rep), {"layout": layout, "repetition": rep, "methods": {}}
        )
        record = _attempt(slot, assigned.get(slot, {}))
        group["methods"][method] = record
        by_method[method].append(record)
    result = list(groups.values())
    for group in result:
        group["scheduled_methods"] = list(group["methods"])
        group["complete"] = all(r["measured"] for r in group["methods"].values())
    return {
        "scope": "Descriptive repeated attempts on two marked arrangements. A measured pair has both post-STOP endpoint records. A usable pair also has two known independent outcomes, including scored intervention or perception failures. Differences are sequential minus comparison. Unknown counts and unscored slots remain visible.",
        "groups": result,
        "methods": {name: _method(rows) for name, rows in by_method.items()},
        "comparisons": {
            "sequential_vs_" + other: _paired(result, other)
            for other in ("local_scan", "selective")
        },
        "unassigned_attempts": unassigned,
    }
