"""Run an explicitly authorized demo-efficiency Study Day and release its training jobs."""

import argparse
import json
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from explorer4 import catalog, study_day, training_schedule
from explorer4.jobs import Jobs
from explorer4.paths import DATA
from explorer4.resources import ResourceLease

from .design import load


def run(study_id):
    plan = study_day.read_plan(study_id)
    protocol, _ = load(plan["efficiency_plan"])
    expected = {f"{arm}-k{k}" for arm in protocol["arms"] for k in protocol["k"]}
    tasks = plan["tasks"]
    if {key for key, task in tasks.items() if task["kind"] == "train"} != expected:
        raise ValueError("Study training keys differ from the frozen comparison")
    tz = ZoneInfo(plan["timezone"])
    if datetime.now(tz).date() != date.fromisoformat(plan["day"]):
        raise ValueError("Explicit training release must start on the registered date")
    label = "study-" + plan["day"]
    root = DATA / "runs" / label / study_id
    root.mkdir(parents=True, exist_ok=True)
    with ResourceLease(label):
        path = root / "state.json"
        state = json.loads(path.read_text()) if path.exists() else dict(
            metrics={}, errors={}, admitted=[], retried=[]
        )
        api = Jobs(None)
        while True:
            now = datetime.now(tz)
            done = study_day.cycle(study_id, plan, root, state, api, now)
            if done:
                break
            if now.date() == date.fromisoformat(plan["day"]):
                with catalog.connect() as db:
                    permitted = training_schedule.permits(db)
                jobs = study_day.find_jobs(plan, study_id, catalog.rows("jobs"))
                release = [
                    row["id"] for key, row in jobs.items()
                    if key in expected and row["status"] == "queued" and row["id"] not in permitted
                ]
                if release:
                    training_schedule.set_start(release, time.time())
                    print("Released study training:", ", ".join(release), flush=True)
            time.sleep(10)
    summary = json.loads((root / "status.json").read_text())
    if not all(row["status"] == "completed" for row in summary["tasks"].values()):
        raise RuntimeError("Demo-efficiency study ended with incomplete tasks")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study")
    args = parser.parse_args()
    run(args.study)


if __name__ == "__main__":
    main()
