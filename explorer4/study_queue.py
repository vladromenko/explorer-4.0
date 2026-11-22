"""Freeze the research queue without execution, then release it to the existing Jobs worker."""

import argparse
import hashlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

from . import catalog, training_schedule
from .paths import DATA, ROOT, offline_environment

QUEUE = DATA / "runs" / "workspace-queue"
TRACKS = ("grasp_replication", "peer_learning")
LABELS = {
    "grasp_replication": "ROSMASTER · воспроизведение ACT и Diffusion",
    "peer_learning": "Tank и ROSMASTER · обучение выбору помощи",
}
SOURCES = (
    "scripts/grasp_study/protocol.json",
    "scripts/grasp_study/train.py",
    "docs/results/conditioned_grasp_v1/development.json",
    "docs/results/conditioned_grasp_v1/fresh.json",
    "docs/results/conditioned_grasp_v1/historical_confirmation.json",
    "explorer4/cognitive/three_robot_cards.py",
    "scripts/grasp_study/evaluate.py",
    "scripts/grasp_study/run.py",
    "explorer4/conditioned_grasp.py",
    "scripts/peer_dock_policy.py",
    "scripts/peer_dock_study.py",
    "explorer4/sim/peer_dock.py",
    "explorer4/sim/fleet.py",
    "explorer4/sim/cooperation.py",
    "explorer4/simlab/perception.py",
    "explorer4/sim/mobile.py",
    "explorer4/sim/room.py",
    "explorer4/sim/tank_model.py",
    "explorer4/sim/state_codec.py",
    "explorer4/study_queue.py",
    "explorer4/peer_request_policy.py",
    "explorer4/peer_dock_config.py",
    "explorer4/sim/peer_screens.py",
    "scripts/peer_screen_evidence.py",
    "explorer4/cognitive/registry.py",
    "explorer4/cognitive/run.py",
    "explorer4/cognitive/protocol.py",
    "explorer4/cognitive/schemas.py",
)
MOTOR = "runs/article-closeout-20261122/learned-trajectories/motor.npz"
VISION = "runs/recorded-start-cube-20261121/night/visual-pick-v1/weights.pt"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    os.replace(temporary, path)


def manifest():
    protocol = json.loads((ROOT / SOURCES[0]).read_text())
    datasets = {MOTOR: protocol["motor_sha256"], VISION: protocol["vision_sha256"]}
    for name, expected in datasets.items():
        if digest(DATA / name) != expected:
            raise ValueError(f"Изменился входной набор {name}")
    reports = DATA / "simlab/reports/conditioned-grasp-v1"
    frozen = {}
    for block in ("development", "fresh", "historical_confirmation"):
        for filename in ("summary.json", "observations.json"):
            path = reports / block / filename
            frozen[str(path.relative_to(DATA))] = digest(path)
    peer = DATA / "runs/peer-screen-dock-v2"
    for path in (peer / "protocol.json", peer / "development.json"):
        frozen[str(path.relative_to(DATA))] = digest(path)
    return {
        "version": 1,
        "frozen_evidence": frozen,
        "scope": "offline_only",
        "tracks": list(TRACKS),
        "training_seed": 1001,
        "sources": {name: digest(ROOT / name) for name in SOURCES},
        "datasets": datasets,
        "grasp_protocol": protocol,
    }


def prepare():
    value = manifest()
    key = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    write_json(QUEUE / (key + ".json"), value)
    write_json(QUEUE / "prepared.json", {"key": key})
    return key


def prepared():
    try:
        return json.loads((QUEUE / "prepared.json").read_text())["key"]
    except FileNotFoundError:
        return None


def verify(key):
    if not key or len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise ValueError("Очередь ещё не подготовлена")
    value = json.loads((QUEUE / (key + ".json")).read_text())
    if (
        hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest() != key
        or value != manifest()
    ):
        raise ValueError(
            "После подготовки изменились код или входы. Подготовьте новую версию очереди."
        )
    return value


def entries(db, key):
    return list(
        db.execute(
            """SELECT id,status,error,config FROM jobs
        WHERE json_extract(config,'$.kind')='workspace_study'
        AND json_extract(config,'$.study_plan')=? ORDER BY created,id""",
            (key,),
        )
    )


def stage(key):
    verify(key)
    with catalog.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = entries(db, key)
        if existing:
            return [r["id"] for r in existing]
        other = db.execute("""SELECT id FROM jobs WHERE json_extract(config,'$.kind')='workspace_study'
                            AND status IN ('queued','running') LIMIT 1""").fetchone()
        if other:
            raise ValueError("В очереди уже есть другая версия серии")
        ids = []
        for track in TRACKS:
            ident = uuid.uuid4().hex
            cfg = {
                "kind": "workspace_study",
                "track": track,
                "study_plan": key,
                "device": "cuda" if track == "grasp_replication" else "cpu",
                "memory_limit_mib": 7168,
            }
            db.execute(
                "INSERT INTO jobs(id,profile,policy,status,config,created) VALUES(?,?,?,?,?,?)",
                (
                    ident,
                    "rosmaster_floor_pick_recorded_start_sim"
                    if track == TRACKS[0]
                    else "tank_dock_sim",
                    "act+diffusion" if track == TRACKS[0] else "peer_policy",
                    "queued",
                    json.dumps(cfg),
                    time.time(),
                ),
            )
            ids.append(ident)
    return ids


def release(key):
    ids = stage(key)
    training_schedule.set_start(ids, time.time())
    return ids


def status():
    key = prepared()
    with catalog.connect() as db:
        rows = entries(db, key) if key else []
        starts = training_schedule.permits(db)
    return dict(
        plan=key,
        disposition=(
            "awaiting_release"
            if all(r["status"] == "queued" and r["id"] not in starts for r in rows)
            else "released"
        )
        if key
        else "unprepared",
        prepared_tracks=[{"track": name, "label": LABELS[name]} for name in TRACKS]
        if key
        else [],
        tracks=[
            dict(
                track=json.loads(r["config"])["track"],
                id=r["id"],
                status=r["status"],
                not_before=starts.get(r["id"]),
                error=r["error"],
            )
            for r in rows
        ],
    )


def execute(cfg, work):
    plan = verify(cfg["study_plan"])
    track = cfg["track"]
    if track not in TRACKS:
        raise ValueError("Unknown study track")
    public = DATA / "simlab/reports/workspace" / cfg["study_plan"] / track
    public.mkdir(parents=True, exist_ok=True)
    env = {**offline_environment(), "MUJOCO_GL": "egl", "MPLBACKEND": "Agg"}

    def run(module, args, sim=False):
        python = ROOT / (".venv-sim" if sim else ".venv") / "bin/python"
        cmd = [str(python), "-m", module, *map(str, args)]
        print(" ".join(cmd), flush=True)
        subprocess.run(cmd, cwd=ROOT, env=env, check=True)

    if track == "grasp_replication":
        bundle = DATA / "checkpoints" / "workspace" / cfg["study_plan"] / track
        run(
            "scripts.grasp_study.run",
            [
                "--seed",
                plan["training_seed"],
                "--checkpoint-dir",
                bundle,
                "--report-dir",
                public,
                "--reference-observations",
                DATA / "simlab/reports/conditioned-grasp-v1",
            ],
        )
        development = json.loads((public / "development/summary.json").read_text())
        final = public / "fresh/summary.json"
        result = dict(
            development=development["counts"],
            optimizer_seed=plan["training_seed"],
            counts=json.loads(final.read_text())["counts"] if final.exists() else {},
            confirmation_completed=final.exists(),
        )
    else:
        for stage in ("prepare", "fit", "evaluate"):
            run(
                "scripts.peer_dock_policy",
                [stage, "--output", public],
                sim=stage == "evaluate",
            )
        result = json.loads((public / "evaluation.json").read_text())
    result.update(
        study_plan=cfg["study_plan"],
        track=track,
        physical_trials=0,
        report="/simlab-media/"
        + str(public.relative_to(DATA / "simlab") / "result.json"),
    )
    write_json(public / "result.json", result)
    write_json(work / "result.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "stage", "status", "start"))
    args = parser.parse_args()
    if args.action == "prepare":
        answer = prepare()
    elif args.action == "stage":
        answer = stage(prepared())
    elif args.action == "start":
        answer = release(prepared())
    else:
        answer = status()
    print(json.dumps(answer, ensure_ascii=False, indent=2))
