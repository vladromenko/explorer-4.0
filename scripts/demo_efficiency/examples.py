"""Generate matched simulation-only auxiliaries with Explorer's existing object-frame IK and writer."""

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

from explorer4 import knowledge
from explorer4.fleet_config import atomic_write
from explorer4.paths import ROOT, offline_environment
from explorer4.resources import ResourceLease
from explorer4.sim.capture import SimCapture
from explorer4.sim.factory import EXPERTS, make
from explorer4.sim.floor_carry import ENDPOINT, FloorCarry
from explorer4.sim.skill_transfer import (
    RetargetedGrasp,
    TransferRejected,
    TransferVerifier,
)

from .design import AUX, SIM, load


def reset(env, seed, expected=None):
    from explorer4.sim.seeded_start import (
        checked_fingerprint,
        fingerprint,
        save_reference,
    )

    # EGL render history can alter shadows on an identical reset.
    env.close()
    obs, _ = env.reset(seed=seed)
    obs["rgb"] = env.render()
    xy = env.data.body("task_cube").xpos[:2].tolist()
    if expected:
        checked_fingerprint(seed, env, obs, expected)
        if xy != expected["xy"] or env.manifest["xml_sha256"] != expected["xml_sha256"]:
            raise ValueError("Registered recipient start changed")
        return expected
    return {
        **fingerprint(seed, env, obs),
        "reference_png_sha256": save_reference(obs["rgb"]),
        "xy": xy,
        "xml_sha256": env.manifest["xml_sha256"],
    }


def teacher(env, arm, packet, delta_xy):
    if arm == "T1":
        return EXPERTS[SIM](env, knowledge="none")
    if arm == "G":
        size = np.asarray(packet["object"]["size_m"])
        axis = np.asarray(packet["measurement"]["closing_axis_object"])
        R = env.data.body("task_cube").xmat.reshape(3, 3)
        u = R @ axis
        return EXPERTS[SIM](
            env,
            knowledge={
                "height_m": float(size[2]),
                "width_m": float(np.abs(axis) @ size),
                "closing_yaw_deg": float(np.rad2deg(np.arctan2(u[1], u[0]))),
            },
        )
    expert = RetargetedGrasp(env, packet)
    if arm == "T3":
        # Change only correspondence between source motion and training scene. The packet stays immutable.
        for sample in expert.samples:
            sample["pose"][:2, 3] += delta_xy
    return expert


def rollout(env, arm, packet, plan, ident, starts, seed, *, save=False):
    reset(env, seed, starts[str(seed)])
    seeds = plan["aux_seeds"]
    wrong = seeds[(seeds.index(seed) + 1) % len(seeds)]
    offset = np.subtract(starts[str(wrong)]["xy"], starts[str(seed)]["xy"])
    carry = FloorCarry(env) if plan.get("endpoint") == ENDPOINT else None
    verify = TransferVerifier(env)
    env.physics_observer = verify
    trace = hashlib.sha256()
    observed = 0
    reason = "terminal_carry_not_verified"
    capture = None
    try:
        expert = teacher(env, arm, packet, offset)
        if save:
            capture = SimCapture(env, seed, "scripted_expert")
            parents = packet["donor"]["episodes"] if arm in ("T2", "T3", "G") else []
            capture.meta.update(
                task="pick up the cube",
                transfer_lineage={"method": arm, "source_episodes": parents},
                efficiency={"plan": ident, "arm": arm, "seed": seed},
                session=f"efficiency-{ident}-{arm}-{seed}",
            )
        frozen_action = None
        for _ in range(plan["ticks_per_synthetic_take"]):
            action = expert.action() if frozen_action is None else frozen_action
            if capture:
                capture.add(env, action)
            _, _, term, trunc, info = env.step(action)
            if carry:
                carry.measure()
            trace.update(np.asarray(action, dtype="<f8").tobytes())
            trace.update(env.data.qpos.astype("<f8").tobytes())
            observed += 1
            if term and info["outcome"] == "success" and carry is None:
                frozen_action = np.asarray(action).copy()
            if trunc or (term and info["outcome"] != "success"):
                reason = info["termination_reason"]
                break
        passed = bool(
            observed == plan["ticks_per_synthetic_take"]
            and (carry.success if carry else info["success"] and verify.held_s >= 1.0)
            and verify.report()["accepted"]
        )
        if passed:
            reason = "terminal_carry"
    except TransferRejected as exc:
        passed = False
        reason = str(exc)
    except ValueError as exc:
        if "Recipient object dimensions outside first-transfer scope" not in str(exc):
            raise
        passed = False
        reason = str(exc)
    finally:
        env.physics_observer = None
    row = {
        "arm": arm,
        "seed": seed,
        "passed": passed,
        "reason": reason,
        "frames": observed,
        "trace_sha256": trace.hexdigest(),
        "terminal_held_s": verify.held_s,
        "verification": verify.report(),
        "shuffled_seed": wrong if arm == "T3" else None,
    }
    if carry:
        row.update(endpoint=ENDPOINT, terminal_samples=carry.samples[-(env.fps + 1):])
    if capture:
        spool = capture.finish("success" if passed else "failure", reason)
        return row, spool
    return row, None


def collect(ident):
    plan, root = load(ident)
    root.mkdir(parents=True, exist_ok=True)
    packet = knowledge.load_packet(plan["packet"]) if plan["packet"] else None
    auxiliaries = [arm for arm in plan["arms"] if arm in AUX]
    with ResourceLease("demo-efficiency-" + ident), make(SIM) as env:
        start_file = root / "training-starts.json"
        old = json.loads(start_file.read_text()) if start_file.exists() else {}
        bank = {str(s): reset(env, s, old.get(str(s))) for s in plan["aux_seeds"]}
        if old and bank != old:
            raise ValueError("Frozen training bank changed")
        if not old:
            atomic_write(start_file, bank)
        rows = []
        for seed in plan["aux_seeds"]:
            for arm in auxiliaries:
                path = root / "screen" / f"{seed}-{arm}.json"
                if not path.exists():
                    atomic_write(path, rollout(env, arm, packet, plan, ident, bank, seed)[0])
                rows.append(json.loads(path.read_text()))
        selected = [s for s in plan["aux_seeds"] if all(r["passed"] for r in rows if r["seed"] == s)][
            : plan["paired_aux_scenes"]
        ]
        decision = {"matched": len(selected) == plan["paired_aux_scenes"], "seeds": selected, "rows": rows}
        receipt = root / "selection.json"
        if receipt.exists() and json.loads(receipt.read_text()) != decision:
            raise ValueError("Training selection changed on resume")
        atomic_write(receipt, decision)
        if decision["matched"]:
            for s in selected:
                for arm in auxiliaries:
                    p = root / "imports" / f"{s}-{arm}.json"
                    spool_file = p.with_suffix(".spool.json")
                    if not p.exists():
                        if not spool_file.exists():
                            row, spool = rollout(env, arm, packet, plan, ident, bank, s, save=True)
                            if row != next(r for r in rows if r["seed"] == s and r["arm"] == arm):
                                raise ValueError("Replay differs from the screened trajectory")
                            atomic_write(spool_file, {"spool": str(spool)})
                        spool = Path(json.loads(spool_file.read_text())["spool"])
                        subprocess.run(
                            [
                                str(ROOT / ".venv/bin/python"),
                                "-m",
                                "explorer4.sim.import_episode",
                                str(spool),
                            ],
                            cwd=ROOT,
                            env=offline_environment(),
                            check=True,
                        )
                        result = json.loads((spool / "imported.json").read_text())
                        if (
                            result["readback"] != "PASS"
                            or result["frames"] != plan["ticks_per_synthetic_take"]
                        ):
                            raise ValueError("Imported auxiliary failed frame or readback receipt")
                        atomic_write(p, result)
    return decision
