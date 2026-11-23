"""Diagnose completed trials and run at most one matched ACT continuation."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from explorer4 import catalog, study_day
from explorer4.fleet_config import atomic_write
from explorer4.jobs import Jobs
from explorer4.paths import DATA
from explorer4.resources import ResourceLease
from explorer4.sim.factory import make
from explorer4.sim_protocol import protocol

from . import continuation
from .design import SIM, load
from .diagnose import diagnose, select_pair
from .followup_page import publish

TERMINAL_ERRORS = {"failed", "cancelled", "interrupted"}


def queue_evaluation(api, key, trained, original, all_jobs, study_id):
    for job in all_jobs:
        cfg = json.loads(job["config"])
        if cfg.get("continuation_study") == study_id and cfg.get("continuation_eval") == key:
            return job["id"]
    cfg = json.loads(original["config"])
    cfg.pop("study_plan")
    cfg.pop("study_task")
    checkpoint = trained["checkpoint"]
    saved = json.loads((Path(checkpoint).resolve().parent / "training_state/training_step.json").read_text())
    if saved["step"] != 3000:
        raise ValueError("Continuation did not produce the 3000-step checkpoint")
    geometry = {
        field: cfg["protocol"][field] for field in ("xml_sha256", "model_manifest_sha256")
    }
    cfg.update(
        checkpoint=checkpoint, source_job=trained["id"], continuation_study=study_id,
        continuation_eval=key, protocol=protocol(SIM, cfg["scene_seeds"], geometry, checkpoint),
    )
    return api._insert(trained["profile"], trained["policy"], cfg)


def run(study_id, output):
    study = study_day.read_plan(study_id)
    plan, _ = load(study["efficiency_plan"])
    if plan["arms"] != ["T0", "T1"] or plan["k"] != [1, 3, 5]:
        raise ValueError("Automatic continuation is registered for the donor-free ACT comparison")
    seeds = plan["pilot_seeds"]
    ticks = plan["ticks_per_synthetic_take"]
    tz = ZoneInfo(study["timezone"])
    keys = [key for key, task in study["tasks"].items() if task["kind"] == "train"]
    api = Jobs(None)

    with ResourceLease("demo-efficiency-followup-" + study_id), make(SIM, images=False) as env:
        state = json.loads(output.read_text()) if output.exists() else {
            "study": study_id, "status": "awaiting_initial_evaluations",
            "initial": {}, "continuations": {},
            "continuation_rule": {
                "priority_k": [3, 5, 1], "minimum_successes_in_either_arm": 2,
                "skip_if_both_perfect": True, "seeds": seeds, "maximum_total_updates": 3000,
            },
        }
        if state["study"] != study_id:
            raise ValueError("Output directory belongs to another study")
        if state["status"] in {"completed", "no_continuation", "blocked"}:
            return
        while True:
            inventory = catalog.rows("jobs")
            jobs = {row["id"]: row for row in inventory}
            base = study_day.find_jobs(study, study_id, inventory)
            for key in keys:
                eval_job = base.get(f"{key}-receiver", {})
                if key not in state["initial"] and eval_job.get("status") == "completed":
                    state["initial"][key] = diagnose(env, eval_job, seeds, ticks)
            if set(state["initial"]) == set(keys) and "selected_k" not in state:
                state["selected_k"] = select_pair(state["initial"])
                if state["selected_k"] is None:
                    state["status"] = "no_continuation"
            if state.get("selected_k"):
                state["status"] = "running_continuation"
                for arm in (0, 1):
                    key = f"T{arm}-k{state['selected_k']}"
                    current = state["continuations"].setdefault(key, {})
                    if "training" not in current:
                        current["training"] = continuation.enqueue(base[key], study_id)
                    trained = jobs.get(current["training"], {})
                    current["training_status"] = trained.get("status", "queued")
                    if trained.get("status") == "completed" and "evaluation" not in current:
                        current["evaluation"] = queue_evaluation(
                            api, key, trained, base[f"{key}-receiver"], inventory, study_id
                        )
                    eval_job = jobs.get(current.get("evaluation"), {})
                    if current.get("evaluation"):
                        current["evaluation_status"] = eval_job.get("status", "queued")
                    if "diagnosis" not in current and eval_job.get("status") == "completed":
                        current["diagnosis"] = diagnose(env, eval_job, seeds, ticks)
                        previous = state["initial"][key]
                        before = {r["scene"] for r in previous["trials"] if r["success"]}
                        after = {r["scene"] for r in current["diagnosis"]["trials"] if r["success"]}
                        current["change"] = {"gained": sorted(after - before), "lost": sorted(before - after)}
                active = state["continuations"].values()
                if all("diagnosis" in row for row in active):
                    state["status"] = "completed"
                elif any(TERMINAL_ERRORS & {r.get("training_status"), r.get("evaluation_status")} for r in active):
                    state["status"] = "blocked"
            elif state["status"] != "no_continuation":
                status_file = DATA / "runs" / f"study-{study['day']}" / study_id / "status.json"
                statuses = json.loads(status_file.read_text())["tasks"]
                if any(r["status"] in {"blocked", "expired", "dependency", "budget", "cancelled"}
                       for r in statuses.values()):
                    state["status"] = "blocked"
            state["updated_msk"] = datetime.now(tz).isoformat(timespec="seconds")
            atomic_write(output, state)
            publish(output, state, study["day"])
            if state["status"] in {"completed", "no_continuation", "blocked"}:
                return
            time.sleep(20)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study")
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    run(args.study, args.report)


if __name__ == "__main__":
    main()
