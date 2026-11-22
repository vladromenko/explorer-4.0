"""Select among executable actions using complete, same-domain terminal forecasts."""

import json
import math
import re
import time

from . import store


def bounded(value, maximum=math.inf):
    return type(value) in (float, int) and math.isfinite(value) and 0 <= value <= maximum


def choose_action(*, admissible, forecasts, fallback, time_weight, help_weight, domain, model_sha256):
    actions = tuple(admissible)
    if not actions or len(set(actions)) != len(actions) or fallback not in actions:
        raise ValueError("An admissible fallback and distinct actions are required")
    result = {"action": fallback, "source": "fallback", "scores": {}}
    if (domain not in {"real", "sim"} or not isinstance(model_sha256, str)
            or not re.fullmatch("[a-f0-9]{64}", model_sha256)
            or not bounded(time_weight) or not bounded(help_weight)
            or not isinstance(forecasts, dict)):
        return {**result, "reason": "unverified forecast context"}
    scores = {}
    for action in actions:
        row = forecasts.get(action)
        if (not isinstance(row, dict) or row.get("verified") is not True
                or row.get("domain") != domain or row.get("model_sha256") != model_sha256
                or type(row.get("support")) is not int or row["support"] <= 0
                or not bounded(row.get("p_success"), 1) or not bounded(row.get("uncertainty"), 1)
                or not bounded(row.get("elapsed_s")) or not bounded(row.get("help_cost"))):
            return {**result, "reason": "missing verified forecast for " + action}
        scores[action] = row["p_success"] - time_weight * row["elapsed_s"] - help_weight * row["help_cost"]
    best = max(actions, key=lambda a: (scores[a], a == fallback))
    return {"action": best, "source": "forecast", "scores": scores,
            "model_sha256": model_sha256, "reason": "highest expected terminal utility"}


def observed_choice(evidence, *, admissible, fallback, domain, scope=None):
    """Only the local, verified history monitor can supply a scoped action forecast."""
    default = {"action": fallback, "source": "fallback", "scores": {}}
    matches = [e for e in evidence if e.status == "observed" and e.source == "recorded_execution_history"
               and e.payload.get("action_value") is not None]
    if len(matches) != 1:
        return {**default, "reason": "no unique scoped history"}
    item = matches[0]
    forecast = item.payload["action_value"]
    if (not isinstance(forecast,dict) or forecast.get("domain") != domain
            or item.payload.get("domain",domain) != domain):
        return {**default, "reason": "forecast domain unavailable"}
    now = time.time()
    ref = getattr(item, "artifact_ref", None)
    digest = forecast.get("model_sha256")
    if (getattr(item, "domain", None) != domain or not item.created_at <= now < item.expires_at
            or not ref or getattr(item, "artifact_sha256", None) != digest
            or (scope is not None and forecast.get("scope") != scope)):
        return {**default, "reason": "unbound or expired history"}
    try:
        store.validate_evidence_artifact(item)
        model = (store.DATA / ref).resolve()
        fit = json.loads(model.read_bytes())
    except (ValueError, TypeError, OSError):
        return {**default, "reason": "fitted evidence or model changed"}
    if (not isinstance(fit, dict) or fit.get("domain") != domain
            or not fit.get("version") or not fit.get("calibration")
            or not isinstance(fit.get("actions"), list) or not set(admissible) <= set(fit["actions"])):
        return {**default, "reason": "fit does not cover this domain and action set"}
    result = choose_action(admissible=admissible, fallback=fallback, domain=domain,
                           forecasts=forecast.get("forecasts"), time_weight=forecast.get("time_weight"),
                           help_weight=forecast.get("help_weight"), model_sha256=forecast.get("model_sha256"))
    return {**result, "evidence_id":item.id}
