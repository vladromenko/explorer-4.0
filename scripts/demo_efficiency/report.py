"""Rescore recipient-only archived physics traces and expose matched success against k and labour."""

import hashlib
import json

import numpy as np

from explorer4 import catalog, study_day
from explorer4.paths import DATA
from explorer4.sim.floor_carry import ENDPOINT, carry_geometry, terminal_success
from explorer4.sim_protocol import sha256_file

from .accounting import human_minutes, paired_size
from .design import ARMS, SIM, load


def terminal(env, path, seed, checksum, expected_ticks=None):
    import mujoco

    raw = json.loads(path.read_text())
    if (
        raw["seed"] != seed
        or raw["profile"] != SIM
        or raw["model"] != env.manifest["xml_sha256"]
        or raw["checkpoint_sha256"] != checksum
    ):
        raise ValueError("Receiver trace is bound to a different run")
    env.reset(seed=seed)
    q = np.asarray(raw["qpos"], dtype="<f8")
    if (
        len(q) < 2
        or q.shape[1:] != env.data.qpos.shape
        or not np.array_equal(q[0], env.data.qpos)
        or raw["fps"] != env.fps
    ):
        raise ValueError("Receiver reset or telemetry differs from the registered scene")
    n = int(env.fps) + 1
    measured = []
    for row in q[-n:]:
        env.data.qpos[:] = row
        mujoco.mj_forward(env.model, env.data)
        measured.append(carry_geometry(env))
    a = np.asarray(measured)
    held = bool(
        len(a) == n
        and (a[:, 0] > 0.05).all()
        and (a[:, 1] < 0.06).all()
        and (a[:, 2] < env.cfg["carry_tolerance_deg"]).all()
    )
    if expected_ticks is not None:
        samples = raw["terminal_samples"]
        if (
            raw["endpoint"] != ENDPOINT
            or raw["carry_ticks"] != expected_ticks
            or len(samples) != min(n, len(q) - 1)
        ):
            raise ValueError("Receiver trace lost the fixed-horizon contact receipt")
        # Forward kinematics is reconstructed from joint/object positions. The
        # recorded contacts come from the actual MuJoCo substeps.
        held = len(q) == expected_ticks + 1 and held and terminal_success(
            samples, env.fps, env.cfg["carry_tolerance_deg"]
        )
        if held != (raw["outcome"] == "success"):
            raise ValueError("Receiver retained-cube outcome differs from the replay")
    return {
        "scene": seed,
        "native_outcome": raw.get("native_outcome", raw["outcome"]),
        "success": bool(held and raw["outcome"] == "success"),
        "first_terminal_frame": max(0, len(q) - n),
        "last_terminal_frame": len(q) - 1,
        "min_bottom_height_m": float(a[:, 0].min()),
        "max_tip_distance_m": float(a[:, 1].max()),
        "max_carry_error_deg": float(a[:, 2].max()),
        "trace_sha256": sha256_file(path),
        "initial_qpos_sha256": hashlib.sha256(q[0].tobytes()).hexdigest(),
    }


def summarize(ident, study_id, ledger=None):
    from explorer4.sim.factory import make

    p, _ = load(ident)
    jobs_plan = study_day.read_plan(study_id)
    if jobs_plan.get("efficiency_plan") != ident:
        raise ValueError("Unrelated job sequence")
    found = study_day.find_jobs(jobs_plan, study_id, catalog.rows("jobs"))
    arms = p.get("arms", ARMS)
    ticks = p["ticks_per_synthetic_take"] if p.get("endpoint") else None
    rows = []
    traces = {}
    with make(SIM, images=False) as env:
        for k in p["k"]:
            for arm in arms:
                key = f"{arm}-k{k}"
                run = found.get(key + "-receiver", {})
                if run.get("status") == "completed":
                    folder = DATA / "jobs" / run["id"]
                    result = json.loads((folder / "result.json").read_text())
                    cfg = json.loads(run["config"])
                    if (
                        cfg.get("demo_efficiency") != ident
                        or cfg.get("source_job") != found[key]["id"]
                        or result["protocol"] != cfg["protocol"]
                        or result["profile"] != SIM
                        or cfg.get("carry_ticks") != ticks
                        or [r["seed"] for r in result["trials"]] != p["pilot_seeds"]
                    ):
                        raise ValueError(
                            "Receiver-only evaluation lost its registered checkpoint or seed binding"
                        )
                    trials = [
                        terminal(env, folder / f"floor-trial-{s}.json", s, result["checkpoint_sha256"], ticks)
                        for s in p["pilot_seeds"]
                    ]
                    cost = human_minutes(
                        ledger,
                        [
                            "common",
                            *p["ordered_training_takes"][:k],
                            *([p["packet"]] if arm in ("T2", "T3", "G") else []),
                            key,
                        ],
                    )
                    traces[key] = trials
                    rows.append(
                        {
                            "arm": arm,
                            "k_unique_target_takes": k,
                            "successes": sum(t["success"] for t in trials),
                            "attempts": len(trials),
                            "receiver_only": True,
                            "domain": "sim",
                            "human_time": cost,
                            "trials": trials,
                        }
                    )
    pilot = []
    if "T1-k3" in traces and "T2-k3" in traces:
        for a, b in zip(traces["T1-k3"], traces["T2-k3"], strict=True):
            if a["scene"] != b["scene"] or a["initial_qpos_sha256"] != b["initial_qpos_sha256"]:
                raise ValueError("Primary comparison requires paired independent initial states")
            pilot.append(
                {
                    "scene": a["scene"],
                    "T1": a["success"],
                    "T2": b["success"],
                    "domain": "sim",
                    "partition": "pilot",
                    "evidence": [a["trace_sha256"], b["trace_sha256"]],
                }
            )
    return {
        "rows": rows,
        "scheduled": len(p["k"]) * len(arms),
        "comparison": p["primary"],
        "evaluated": len(rows),
        "size_for_new_simulation_scenes": paired_size(pilot, p["power"]["minimum_useful_gain"], domain="sim"),
        "size_for_physical_confirmation": paired_size([], domain="real"),
        "physical_trial_status": "Separate per-checkpoint hardware admission and a real independent paired pilot are required.",
    }


def plot(report, file):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not report["rows"]:
        raise ValueError("No receiver-only outcomes to plot")
    fig, axes = plt.subplots(1, 2, figsize=(9, 4), sharey=True)
    observed = 0
    for arm in ARMS:
        rr = sorted((r for r in report["rows"] if r["arm"] == arm), key=lambda r: r["k_unique_target_takes"])
        if rr:
            axes[0].plot(
                [r["k_unique_target_takes"] for r in rr],
                [r["successes"] / r["attempts"] for r in rr],
                ".-",
                label=arm,
            )
            cost = [r for r in rr if r["human_time"]["total_minutes"] is not None]
            if cost:
                axes[1].plot(
                    [r["human_time"]["total_minutes"] for r in cost],
                    [r["successes"] / r["attempts"] for r in cost],
                    ".-",
                    label=arm,
                )
                observed += len(cost)
    if not observed:
        axes[1].text(0.5, 0.5, "Complete human time unavailable", ha="center", transform=axes[1].transAxes)
    axes[0].legend()
    axes[0].set(
        xlabel="Unique target demonstrations", ylabel="Receiver-only simulation success", ylim=(0, 1.05)
    )
    axes[1].set_xlabel("Cumulative observed person-minutes")
    fig.tight_layout()
    fig.savefig(file)
    plt.close(fig)
