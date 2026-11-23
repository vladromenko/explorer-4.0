"""Resume an ACT checkpoint with its optimizer in a separate Explorer job."""

import hashlib
import json
from pathlib import Path
import shutil
import time

from explorer4 import catalog, training_drafts
from explorer4.fleet_config import atomic_write
from explorer4.paths import DATA


def stage_checkpoint(source, new_root, base_job):
    previous = Path(source["checkpoint"]).resolve().parent
    original = json.loads((previous / "pretrained_model/train_config.json").read_text())
    step = json.loads((previous / "training_state/training_step.json").read_text())["step"]
    if step != 1000 or original["steps"] != step:
        raise ValueError("Expected a complete optimizer checkpoint at update 1000")
    if (previous.parent / "last").resolve() != previous:
        raise ValueError("The source job's final checkpoint changed")
    dataset = DATA / "jobs" / base_job / "train"
    if Path(original["dataset"]["root"]).resolve() != dataset.resolve() or not dataset.is_dir():
        raise ValueError("Resume must use the exact original consolidated dataset")
    seed = new_root / "checkpoints" / previous.name
    config_path = seed / "pretrained_model/train_config.json"
    changed = {**original, "output_dir": str(new_root), "steps": 3000, "save_freq": 1000}
    if not seed.exists():
        temp = seed.with_name(seed.name + ".staging")
        if temp.exists():
            shutil.rmtree(temp)
        shutil.copytree(previous, temp)
        atomic_write(temp / "pretrained_model/train_config.json", changed)
        temp.rename(seed)
    if json.loads(config_path.read_text()) != changed:
        raise ValueError("Inconsistent local resume configuration")
    return seed / "pretrained_model", original["batch_size"]


def enqueue(source, study):
    old = json.loads(source["config"])
    if source["policy"] != "act" or source["status"] != "completed" or old["steps"] != 1000:
        raise ValueError("Only completed initial ACT trials qualify")
    ident = hashlib.sha256(f"{study}:3000:{source['id']}".encode()).hexdigest()[:32]
    with catalog.connect() as db:
        existing = db.execute("SELECT id FROM jobs WHERE id=?", (ident,)).fetchone()
    if existing is not None:
        return ident
    batch = old["batch_size"]
    root = DATA / "checkpoints" / f"{ident}-b{batch}"
    resume, saved_batch = stage_checkpoint(source, root, source["id"])
    if batch != saved_batch:
        raise ValueError("The original effective batch changed")
    draft_id, draft = training_drafts.prepare(
        source["profile"], "act", steps=3000, batch=batch, device=old["device"],
        train_seed=old["train_seed"], plan_id=old["plan_id"],
    )
    cfg = {
        **draft, "draft_id": draft_id, "preparation_only": False, "training_requested": True,
        "resume_checkpoint": str(resume), "resume_of_existing_job": ident,
        "continuation_source": source["id"], "continuation_study": study,
        "memory_limit_mib": old.get("memory_limit_mib", 8192),
    }
    cfg.pop("training_started", None)
    with catalog.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO jobs(id,profile,policy,status,config,created) VALUES(?,?,?,?,?,?)",
            (ident, source["profile"], "act", "queued", json.dumps(cfg), time.time()),
        )
        db.execute("INSERT INTO training_starts(job_id,not_before) VALUES(?,?)", (ident, time.time()))
    return ident
