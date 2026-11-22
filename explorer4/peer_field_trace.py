"""Physical consultation events and costs, aligned with the paired simulation stage names."""

import hashlib
import json
import math


def goal_receipt(goal):
    raw = json.dumps(
        goal, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return {
        "packet_sha256": hashlib.sha256(raw).hexdigest(),
        "evidence": goal.get("evidence"),
        "source_robot": goal.get("source_robot"),
        "map_frame_id": goal.get("map_frame_id"),
    }


def seconds(value):
    return (
        value
        if type(value) in (float, int) and math.isfinite(value) and value >= 0
        else None
    )


def consultation(attempt):
    runtime = attempt.get("runtime") or {}
    logged = runtime.get("communication_events")
    events = list(logged) if isinstance(logged, list) else []
    requests = runtime.get("peer_requests")
    if type(requests) is not int or requests not in (0, 1):
        requests = None
    donor_reads = [
        r
        for r in runtime.get("observations", [])
        if r.get("source_robot") == "rosmaster"
    ]
    if logged is None:
        # A legacy completed capture is only a lower bound on consultations.
        phase = next(
            (e for e in runtime.get("phase_events", []) if e.get("phase") == "peer"),
            None,
        )
        if phase:
            events.append(
                {
                    "stage": "requested",
                    "t": seconds(phase.get("at_s")),
                    "capture": phase.get("capture"),
                    "source": "archived peer phase",
                }
            )
    lower_bound = int(
        bool(donor_reads) or any(e["stage"] == "requested" for e in events)
    )
    if lower_bound and requests == 0:
        requests = None
    endpoint = attempt.get("endpoint") or {}
    geometry = [
        endpoint.get(k) for k in ("x_error_m", "y_error_m", "heading_error_deg")
    ]
    if (
        type(endpoint.get("success")) is bool
        and endpoint.get("measurement_source")
        and all(type(x) in (int, float) and math.isfinite(x) for x in geometry)
        and type(endpoint.get("stationary_half_second")) is bool
        and type(endpoint.get("operator_intervention")) is bool
    ):
        events.append(
            {
                "stage": "recipient_outcome",
                "t": None,
                "recorded_unix_s": seconds(endpoint.get("at")),
                "success": endpoint["success"],
                "source": "independent_post_stop_measurement",
                "measurement": endpoint["measurement_source"],
                "geometry": {
                    key: endpoint[key]
                    for key in ("x_error_m", "y_error_m", "heading_error_deg")
                },
                "stationary_half_second": endpoint["stationary_half_second"],
                "operator_intervention": endpoint["operator_intervention"],
            }
        )
    stages = {e["stage"] for e in events}
    expected = {"recipient_outcome"}
    if requests != 0:
        expected.add("requested")
        if not stages.intersection({"accepted", "refused"}):
            expected.add("accepted_or_refused")
        if "refused" not in stages:
            expected.update(("observed", "delivered", "consumed"))
    return {
        "attempt_id": attempt["id"],
        "condition": attempt["condition"],
        "domain": "physical",
        "events": events,
        "unobserved_stages": sorted(expected - stages),
        "controller_stop_reason": runtime.get("reason"),
        "unconsumed_capture": runtime.get("unconsumed_capture"),
        "costs": {
            "calls": requests,
            "observed_calls_lower_bound": lower_bound,
            "elapsed_s": seconds(runtime.get("seconds")),
            "wait_s": 0.0 if requests == 0 else None,
            "service_s": 0.0 if requests == 0 else None,
            "travel_m": None,
            "human_s": None,
        },
    }


def report(attempts):
    return {
        "scope": "Elapsed time is measured by the Homebrain monotonic clock. Request acceptance describes the local read-only sensor service queue. A camera receipt identifies an actual RGB packet; controller consumption identifies a submitted measured waypoint. Donor-side queue, service, physical travel and operator labour require separate measurements. Post-STOP scoring uses independent geometry and its own wall-clock timestamp.",
        "physical_attempts": len(attempts),
        "traces": [consultation(a) for a in attempts],
    }
