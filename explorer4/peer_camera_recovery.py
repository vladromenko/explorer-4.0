"""Recover an image-byte pairing failure while preserving the original trials and their strict score."""

import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from scripts.peer_dock_study import frozen

from . import catalog
from . import peer_confirmation as original
from .peer_confirmation import digest, read, require
from .sim.state_codec import encode

REPAIR = "shared-initial-v1"


def job(ident):
    with catalog.connect() as db:
        _, cfg = original.job(db, ident)
    return cfg, original.primary(cfg), original.directory(cfg["peer_confirmation"])


def audit(cfg, primary, out):
    original_key = cfg["peer_confirmation"]
    original_spec = read(out / "protocol.json")
    require(
        original_key == digest(out / "protocol.json")
        and original_spec == original.protocol(original_spec["job_id"], cfg),
        "Original protocol differs",
    )
    scenes, rows, receipt = original.original_rows(primary, original_spec)
    require(
        receipt == read(out / "primary-evidence.json"),
        "Original primary receipts differ",
    )
    passed = []
    misses = []
    preserved = {}
    for scene, row in zip(scenes, rows, strict=True):
        seed = scene["seed"]
        folder = out / str(seed)
        source = primary / "test" / str(seed)
        seq = read(folder / "result.json")
        preserved[str(seed)] = digest(folder / "result.json")
        if seq["initial_rgb_identical"]:
            passed.append(
                original.paired(scene, row, out, original_key, original_spec["utility"])
            )
            continue
        first = cv2.imread(str(source / "recipient-before.png"))
        rerender = cv2.imread(str(folder / "initial.png"))
        require(
            first is not None
            and rerender is not None
            and first.shape == rerender.shape,
            "Cannot compare original pictures",
        )
        delta = np.abs(first.astype(np.int16) - rerender)
        require(
            seq["initial_state_sha256"] == scene["initial_state_sha256"]
            and digest(source / "recipient-before.png") == scene["initial_rgb_sha256"]
            and seq["initial_rgb_sha256"] == digest(folder / "initial.png"),
            "The original input chain differs",
        )
        misses.append(
            {
                "seed": seed,
                "primary_png_sha256": scene["initial_rgb_sha256"],
                "original_sequential_png_sha256": seq["initial_rgb_sha256"],
                "original_sequential_result_sha256": preserved[str(seed)],
                "initial_state_sha256": scene["initial_state_sha256"],
                "image_shape": list(first.shape),
                "pixels_different": int(np.any(delta, axis=2).sum()),
                "channels_different": int(np.count_nonzero(delta)),
                "maximum_channel_difference": int(delta.max()),
                "absolute_difference_sum": int(delta.sum()),
            }
        )
    require(
        len(misses) == 1 and len(passed) == 15,
        "This recovery covers exactly one failed image pairing",
    )
    return (
        scenes,
        rows,
        passed,
        {
            "scope": "Original preregistered all-16 comparison failed strict image identity; report the unmodified comparable subset separately.",
            "matched_scenes": len(passed),
            "total_scenes": len(rows),
            "unmatched": misses,
            "original_sequential_results": preserved,
            **original.summarize(passed),
        },
    )


def register(ident):
    cfg, primary, out = job(ident)
    _, _, _, strict = audit(cfg, primary, out)
    folder = out / REPAIR
    folder.mkdir(exist_ok=True)
    frozen(folder / "original-strict.json", strict)
    fixed = {
        "phase": "post hoc technical recovery, specified before repeating the unmatched scene; original primary and all 16 original sequential outcomes preserved",
        "job": ident,
        "original_protocol_sha256": cfg["peer_confirmation"],
        "primary_evidence_sha256": digest(out / "primary-evidence.json"),
        "original_strict_sha256": digest(folder / "original-strict.json"),
        "seeds_to_replay": [item["seed"] for item in strict["unmatched"]],
        "source_sha256": digest(Path(__file__)),
        "method": "Restore and hash the complete frozen simulator snapshot and clock. Before the first command deliver the exact original Tank RGB array once to the unchanged camera detector. Require the identical saved PNG and the same independently computed detection and screen measurement. All later camera reads, actions, stops and outcomes are live within the original simulation. Keep all original thresholds, branches and utility checks. Report primary 16, originally comparable 15, and amended paired 16 separately. No retries selected by outcome.",
    }
    frozen(folder / "protocol.json", fixed)
    key = digest(folder / "protocol.json")
    with catalog.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row, db_cfg = original.job(db, ident)
        require(
            row["status"] in ("failed", "interrupted", "queued", "running", "completed")
            and db_cfg.get("peer_frame_repair", key) == key,
            "Different job or recovery registration",
        )
        if "peer_frame_repair" not in db_cfg:
            require(
                row["status"] in ("failed", "interrupted"),
                "New post hoc recovery can only attach after the primary failure",
            )
            db.execute(
                "UPDATE jobs SET config=json_set(config,'$.peer_frame_repair',?) WHERE id=?",
                (key, ident),
            )
    return key


def replay(scenes, primary, folder, key):
    from scripts import peer_sequential_control as sequential

    from .peer_primary_recovery import preserve_confirmation
    from .sim.cooperation import CooperationWorld

    camera = CooperationWorld.camera
    used = {}

    def shared_frame(world, robot, label):
        if label != "initial":
            return camera(world, robot, label)
        seed = world.seed
        require(
            robot == "tank" and seed not in used and world.world.data.time == 0,
            "Archived RGB permitted only before the first decision",
        )
        source = primary / "test" / str(seed)
        snap = world.world.snapshot()
        current = json.dumps(
            encode(snap), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        require(
            hashlib.sha256(current).hexdigest()
            == digest(source / "initial-state.json"),
            "Full restored state differs before first exposure",
        )
        initial = cv2.cvtColor(
            cv2.imread(str(source / "recipient-before.png")), cv2.COLOR_BGR2RGB
        )
        with patch.object(
            world.world,
            "render",
            side_effect=lambda robot_name: (
                np.copy(initial) if robot_name == "tank" else None
            ),
        ):
            result = camera(world, robot, label)
        decision = read(source / "decision.json")
        require(
            result["packet"] == decision["local_packet"]
            and result["measurement"] == decision["local_measurement"]
            and digest(Path(result["image"]))
            == digest(source / "recipient-before.png"),
            "Shared camera frame or its detector differs",
        )
        used[seed] = {
            "seed": seed,
            "initial_state_sha256": hashlib.sha256(current).hexdigest(),
            "png_sha256": digest(source / "recipient-before.png"),
            "delivery_time_s": result["simulation_time_s"],
            "substitution_count": 1,
            "detector_matches_original": True,
        }
        frozen(folder / f"shared-input-{seed}.json", used[seed])
        return result

    with (
        patch.object(sequential, "SOURCE", primary),
        patch.object(CooperationWorld, "camera", shared_frame),
    ):
        preserve_confirmation(sequential.run_room, {"scenes": scenes}, folder, "test")
    for scene in scenes:
        seed = scene["seed"]
        proof = read(folder / f"shared-input-{seed}.json")
        require(
            proof["initial_state_sha256"] == scene["initial_state_sha256"]
            and proof["png_sha256"] == scene["initial_rgb_sha256"]
            and proof["substitution_count"] == 1
            and proof["delivery_time_s"] == 0
            and proof["detector_matches_original"],
            "Missing time-zero camera delivery proof",
        )


def run(ident):
    cfg, primary, out = job(ident)
    folder = out / REPAIR
    key = cfg["peer_frame_repair"]
    costs = read(out / "protocol.json")["utility"]
    spec = read(folder / "protocol.json")
    require(
        digest(folder / "protocol.json") == key
        and digest(Path(__file__)) == spec["source_sha256"]
        and cfg["peer_confirmation"] == spec["original_protocol_sha256"],
        "Amendment identity differs",
    )
    scenes, rows, passed, strict = audit(cfg, primary, out)
    require(
        strict == read(folder / "original-strict.json")
        and digest(folder / "original-strict.json") == spec["original_strict_sha256"],
        "Original trials changed during recovery",
    )
    failed = spec["seeds_to_replay"]
    repeat = [s for s in scenes if s["seed"] in failed]
    replay(repeat, primary, folder, key)
    all_rows = {r["seed"]: r for r in passed}
    for scene, row in zip(scenes, rows, strict=True):
        if scene["seed"] in failed:
            all_rows[scene["seed"]] = original.paired(scene, row, folder, key, costs)
    ordered = [all_rows[s["seed"]] for s in scenes]
    receipt = read(out / "primary-evidence.json")
    result = {
        "status": "completed",
        "scope": "Post hoc shared-first-image technical recovery in held-out MuJoCo; original preregistered strict image pairing completed for 15/16.",
        "protocol_sha256": key,
        "original_protocol_sha256": cfg["peer_confirmation"],
        "original_strict_scenes": 15,
        "shared_first_image_seeds": failed,
        "model_sha256": receipt["model_sha256"],
        "primary_evidence_sha256": digest(out / "primary-evidence.json"),
        "original_registration_sha256": digest(out / "registration.json"),
        "original_strict_report": REPAIR + "/original-strict.json",
        "rows": ordered,
        **original.summarize(ordered),
        "training_updates_in_confirmation": 0,
        "physical_robot_commands": 0,
    }
    frozen(folder / "summary.json", result)
    frozen(out / "summary.json", result)
    return out / "summary.json"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=("register", "run"))
    p.add_argument("job")
    args = p.parse_args()
    print(register(args.job) if args.phase == "register" else run(args.job))
