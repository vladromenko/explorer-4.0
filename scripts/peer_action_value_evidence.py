"""Bind the local action model and reconstruct realized paired costs from saved event traces."""

import argparse
import json
from pathlib import Path
from statistics import mean

from scripts import peer_action_value_pilot as pilot
from scripts.peer_dock_study import digest, frozen


def preregister(out):
    spec = {
        "schema": "peer_action_value_artifact_binding_v1",
        "scope": "pre-confirmation provenance addition",
        "original_protocol_sha256": digest(out / "protocol.json"),
        "source_sha256": digest(Path(__file__)),
        "amendment": "Embed domain, version, admissible action set and calibration scene IDs directly in the bytes hashed as forecast.model_sha256. Preserve the original numerical fit and primary protocol. The common broker must verify the digest of the actual serialized file. Confirmation uses the same forecast, controller, deadline, group and scoring functions unchanged. Verify equal numerical predicted outcomes on all development histories before evaluation.",
    }
    dest = out / "artifact-binding-protocol.json"
    if not dest.is_file() and (out / "confirmation").exists():
        raise ValueError("Cannot register a new binding after confirmation")
    frozen(dest, spec)


def bind(out):
    preregister(out)
    original = pilot.read(out / "model.json")
    content = dict(original)
    original_id = content.pop("identity")
    if (
        pilot.sha(json.dumps(content, sort_keys=True, allow_nan=False).encode())
        != original_id
    ):
        raise ValueError("Invalid original numerical fit")
    attributes = {
        "version": 1,
        "kind": "short_history_knn_action_outcomes",
        "scope": "screen_docking_with_declared_service_offer",
        "domain": "sim",
        "actions": [pilot.LOCAL, pilot.ASK],
        "calibration": {
            "ids": list(pilot.SPLITS["calibration"][1]),
            "scores": original["scores"],
            "minimum_validation_rows": 4,
            "maximum_brier": 0.35,
            "maximum_mean_abs_seconds_error": 6,
        },
        "fit_ids": list(pilot.SPLITS["fit"][1]),
        "protocol_sha256": digest(out / "protocol.json"),
        "memory_snapshot": "empty",
        "physical_trials": 0,
        "original_numeric_fit_identity": original_id,
    }
    bound = {**content, **attributes}
    raw = json.dumps(bound, sort_keys=True, allow_nan=False).encode()
    archive = out / "verified-fit.json"
    if archive.is_file():
        if archive.read_bytes() != raw:
            raise ValueError("Changed verified model")
    else:
        tmp = archive.with_suffix(".tmp")
        tmp.write_bytes(raw)
        tmp.replace(archive)
    identity = digest(archive)
    numerical = {**bound, "identity": identity}
    for case in content["neighbors"]:
        old = pilot.forecast(original, case["x"])
        new = pilot.forecast(numerical, case["x"])
        for action in attributes["actions"]:
            if any(
                new[action][k] != v
                for k, v in old[action].items()
                if k != "model_sha256"
            ):
                raise ValueError("Provenance addition changed a numerical forecast")
    card = {
        **attributes,
        "fitted_artifact": "verified-fit.json",
        "fitted_artifact_sha256": identity,
        "identity": identity,
        "calibration_accepted": content["admitted"],
        "available_neighbor_histories": len(content["neighbors"]),
        "selected_fixed_policy": content["fixed_best"],
        "original_fit_sha256": digest(out / "model.json"),
    }
    frozen(out / "model-card.json", card)
    return card


def confirm(out):
    import inspect

    import cv2
    import torch

    from explorer4.cognitive.action_value import choose_action
    from explorer4.resources import ResourceLease

    torch.set_num_threads(1)
    cv2.setNumThreads(1)
    with ResourceLease("peer-action-value-pilot"):
        pilot.register(out)
        card = bind(out)
        model = {**pilot.read(out / "verified-fit.json"), "identity": card["identity"]}
        binding = {
            "protocol_sha256": digest(out / "protocol.json"),
            "original_fit_sha256": digest(out / "model.json"),
            "model_sha256": card["identity"],
            "model_card_sha256": digest(out / "model-card.json"),
            "artifact_binding_sha256": digest(out / "artifact-binding-protocol.json"),
            "broker_sha256": digest(Path(inspect.getfile(choose_action))),
            "dev_trials_sha256": {
                s: pilot.sha(
                    b"".join(
                        bytes.fromhex(digest(p))
                        for p in sorted((out / s).glob("*/*.json"))
                    )
                )
                for s in ("fit", "calibration")
            },
        }
        if (
            not (out / "test-binding.json").is_file()
            and (out / "confirmation").exists()
        ):
            raise ValueError("Refusing late binding")
        frozen(out / "test-binding.json", binding)
        pilot.summarize(pilot.collect("confirmation", out, model), out, model)


def report(out):
    result = pilot.read(out / "result.json")
    card = bind(out)
    spec = pilot.read(out / "protocol.json")
    roster = pilot.SPLITS["confirmation"][1]
    if result["model_sha256"] != card["identity"] or result[
        "protocol_sha256"
    ] != digest(out / "protocol.json"):
        raise ValueError("Model or protocol differs")
    methods = result["method_summary"].keys()
    rows = []
    profiles = ["clean", "queued", "uncertain_transform", "unavailable"]
    for i, seed in enumerate(roster):
        scene = {}
        for name in methods:
            path = out / "confirmation" / str(seed) / (name + ".json")
            source = pilot.read(path)
            raw = source["events"]
            costs = pilot.trace_costs(raw)
            if any(source[k] != v for k, v in costs.items()):
                raise ValueError("Costs differ from observed service trace")
            now = [e["t"] for e in raw]
            if sorted(now) != now or raw[-1]["stage"] != "recipient_outcome":
                raise ValueError("Trace chronology invalid")
            events = {e["stage"]: e for e in raw}
            if "delivered" in events and (
                "consumed" not in events
                or events["delivered"]["packet_sha256"]
                != events["consumed"]["packet_sha256"]
            ):
                raise ValueError(
                    "Delivered donor packet differs from consumed waypoint"
                )
            scene[name] = {
                **costs,
                "decided": source["decision"],
                "trace_sha256": digest(path),
                "reset_sha256": source["reset"]["reset_sha256"],
                "first_rgb_sha256": source["reset"]["initial_rgb_sha256"],
            }
        if (
            len({r["reset_sha256"] for r in scene.values()}) != 1
            or len({r["first_rgb_sha256"] for r in scene.values()}) != 1
        ):
            raise ValueError(
                "Controllers did not share the frozen reset and initial pixels"
            )
        rows.append({"seed": seed, "profile": profiles[(i // 2) % 4], "methods": scene})
    outcomes = {}
    for name in methods:
        action = [r["methods"][name] for r in rows]
        local = [r["methods"]["local_only"] for r in rows]
        rescued = sum(
            bool(a["calls"]) and a["win"] and not b["win"]
            for a, b in zip(action, local, strict=True)
        )
        harmed = sum(
            bool(a["calls"]) and b["win"] and not a["win"]
            for a, b in zip(action, local, strict=True)
        )
        outcomes[name] = {
            "rescued_vs_local_when_requested": rescued,
            "harmed_vs_local_when_requested": harmed,
            "accepted_calls_ending_in_failure": sum(r["negative_help"] for r in action),
            "refusals_before_service": sum(
                bool(r["calls"]) and not r["service_s"] for r in action
            ),
            "calls": sum(r["calls"] for r in action),
            "successes": sum(r["win"] for r in action),
            "sum_service_s": sum(r["service_s"] for r in action),
            "sum_wait_s": sum(r["wait_s"] for r in action),
        }
        if outcomes[name]["successes"] != result["method_summary"][name]["win"]:
            raise ValueError("Outcome mismatch")
    by_profile = {
        key: {
            m: {
                "n": len(q),
                "docks": sum(r["methods"][m]["win"] for r in q),
                "calls": sum(r["methods"][m]["calls"] for r in q),
                "mean_utility": mean(pilot.utility(r["methods"][m]) for r in q),
            }
            for m in methods
        }
        for key in profiles
        if (q := [r for r in rows if r["profile"] == key])
    }
    conditional = []
    for row in rows:
        decision = row["methods"]["adaptive"]["decided"]
        if decision:
            conditional.append(
                {
                    "seed": row["seed"],
                    "action": decision["action"],
                    "source": decision["source"],
                    "scores": decision["scores"],
                }
            )
    result = {
        "scope": "Paired MuJoCo interventions on 16 distinct starts; human and robot travel costs are zero by design. Harm compares actual paired local-only endpoints. An unsuccessful assisted attempt alone is uninformative about negative transfer. The material contains no physical outcomes. Sensitivity revalues the same realized policies without refitting.",
        "protocol_sha256": digest(out / "protocol.json"),
        "result_sha256": digest(out / "result.json"),
        "model_card_sha256": digest(out / "model-card.json"),
        "fit_sha256": card["identity"],
        "n_unique_scenes": len(rows),
        "method_summary": result["method_summary"],
        "primary_adaptive_minus_fixed": result["primary_adaptive_minus_fixed"],
        "strongest_local_first": result["best_fixed"],
        "all_actions_were_calibrated": all(card["calibration_accepted"].values()),
        "conditional_decisions": conditional,
        "conditional_vs_local": outcomes,
        "pareto_nondominated": result["pareto_nondominated"],
        "utility_sensitivity": result["utility_sensitivity"],
        "by_offer": by_profile,
        "materials": spec["materials"],
        "scenes": rows,
    }
    frozen(out / "evidence.json", result)
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("phase", choices=("preregister", "bind", "confirm", "report"))
    args = cli.parse_args()
    {"preregister": preregister, "bind": bind, "confirm": confirm, "report": report}[
        args.phase
    ](pilot.OUT)
