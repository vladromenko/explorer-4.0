"""Matched active-sensing policies under a common deadline and an explicitly priced donor."""

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from statistics import mean, median

import cv2
import numpy as np

from explorer4.paths import DATA, ROOT
from explorer4.sim.state_codec import dump
from scripts.peer_dock_study import digest, frozen

OUT = DATA / "simlab/reports/peer-action-value-v1"
SPLITS = {
    "fit": ("workshop_screen", range(894000, 894024)),
    "calibration": ("storage_screen", range(894100, 894116)),
    "confirmation": ("inspection_screen", range(894200, 894216)),
}
FIXED = {"local_0.8": 16, "local_1.6": 32, "local_3.0": 60}
LOCAL = "local_observe"
ASK = "ask:rosmaster"
TIME_PRICE = 0.005
HELP_PRICE = 0.10
SENSING = 120  # 20 Hz, including all local frames, donor wait and service
SERVICE = 60
FIRST = 16
FEATURES = [
    "initial_abs_surveyed_heading_rad",
    "current_abs_heading_rad",
    "measured_yaw_change_rad",
    "mean_abs_recent_velocity_rad_s",
    "camera_samples",
    "quoted_wait_s",
    "quoted_help_units",
    "declared_bad_packet_probability",
]
MATERIAL = (
    "scripts/peer_action_value_pilot.py",
    "explorer4/sim/peer_dock.py",
    "explorer4/sim/peer_screens.py",
    "explorer4/sim/cooperation.py",
    "explorer4/sim/fleet.py",
    "explorer4/sim/state_codec.py",
    "explorer4/peer_dock_config.py",
)
QUOTES = [
    (True, 0, 1, 0.0),
    (True, 32, 2, 0.0),
    (True, 8, 1.5, 0.5),
    (False, 0, 0, 0.0),
]


def read(p):
    return json.loads(p.read_text())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def register(out):
    out.mkdir(parents=True, exist_ok=True)
    frozen(
        out / "protocol.json",
        {
            "name": "peer-action-value-v1",
            "groups": {
                k: {"room": r, "seeds": list(seeds)} for k, (r, seeds) in SPLITS.items()
            },
            "intervention": "Per room preset, each consecutive open/screened pair cycles independently through one of four declared service offers: clean (0s wait, 1 unit), queued (1.6s wait, 2 units), uncertain transform (0.4s wait, 1.5 units, advertised 50% chance of error), unavailable. In the uncertain tier a hidden prespecified balanced crossing displaces the delivered waypoint 0.24 m sideways on one member of each assigned pair, alternating hidden screen parity across blocks. All methods on one scene receive the same offer and hidden outcome. The world and recipient are stepped during wait/service; target poses and hidden faults never enter policy selection.",
            "primary": "Adaptive action value minus the best fixed local-first sequence selected on the calibration set by registered mean utility, then fewer calls, then longer local scan. Report all fixed-time variants and paired gains/losses, calls, simulated elapsed and utility. Same starts/no post hoc tuning. Clean, queued, unreliable and unavailable cases included. Local only and immediate peer when available are controls. Equal sensing cap 6 s including wait/service and common native 20 s episode cutoff. Fixed comparators shorten their planned search if required to preserve the quoted service opportunity. After 0.8 s of initially fruitless local inspection, the adaptive policy may ask now or finish the selected fixed search-then-ask rule. An initial/early local success is acted upon immediately. The local-only control can scan a full 3 s and never ask.",
            "history": FEATURES,
            "scope": "Only returning a measured pose and driving are supported here. Unavailable donors, human corrections, travel and extra skills cannot be dispatched by this simulator. Donor base travel zero; three-second arm/camera motion counts as service. Independent stable docking endpoint incl. causal failure from erroneous messages. Turn encoders use the simulator body velocity and gyro. Neither policy receives colour, pixels, seed, hidden screen, future detection or outcome. Short history includes camera negative observations and measured turns.",
            "estimator": "For each of two admissible continuations, find the six nearest paired training histories after a missed 0.8 s inspection in standardized feature space, using training scales only. Predict terminal probability with (successes+1)/(n+2), mean measured total mission seconds and help units; uncertainty is the Bernoulli posterior standard deviation. Action-wise validation requires >=4 support queries, Brier <=0.35 and mean absolute elapsed error <=6s on independent calibration scenes; otherwise fall back to the best fixed rule. No test updates. The binary predictor is a small conditional outcome model, not an exact POMDP solver.",
            "costs": {
                "time_weight": TIME_PRICE,
                "help_weight": HELP_PRICE,
                "sensitivity_time": [0, 0.005, 0.02],
                "sensitivity_help": [0, 0.10, 0.25],
            },
            "materials": {n: digest(ROOT / n) for n in MATERIAL},
            "scoring": "Carry the same measured initial RGB through detection for every policy in a reset. Verify reset hash before motion. Score task completion independently with the original MuJoCo verifier, shared 20s from initial reset. No physical trials, no human labour. An early stop is an outcome. Publish all 16 scenes and reward allocation; repeats do not add independent scenes.",
            "trace": "Record requested, accepted/refused, observed, delivered, consumed, recipient_outcome with actual simulator timestamps and the geometry packet or its hash; reconstruct wait/service/travel and costs. One published paired comparison of hyperparameter-frozen policies; sensitivity revalues realized trajectories only.",
            "sources": [
                "https://doi.org/10.1109/LRA.2026.3703246",
                "https://arxiv.org/abs/2602.22474",
            ],
            "fresh_test_gate": "Before opening any confirmation reset, require model/calibration/checksummed broker source binding. Frozen memory is empty. No future fields may enter predict().",
        },
    )


def context(index):
    avail, wait, fee, risk = QUOTES[(index // 2) % len(QUOTES)]
    # Hidden draw is available only to the world intervention.
    fault = risk > 0 and index % 2 == (index // 8) % 2
    return {
        "available": avail,
        "wait_ticks": wait,
        "help_units": fee,
        "risk": risk,
    }, fault


def sense(world, robot, image):
    return world.sensors.packet(robot, image)


def frozen_start(world, seed, folder):
    world.reset(seed)
    candidate = folder / "checking-state.json"
    folder.mkdir(parents=True, exist_ok=True)
    checksum = dump(candidate, world.initial)
    first = folder / "initial-state.json"
    if first.is_file():
        if digest(first) != checksum:
            raise ValueError("Unmatched MuJoCo reset")
        candidate.unlink()
    else:
        candidate.replace(first)
    path = folder / "initial.png"
    if not path.is_file():
        rgb = world.world.render("tank")
        if not cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)):
            raise OSError(path)
    raw = cv2.imread(str(path))
    if raw is None:
        raise ValueError("Missing common initial RGB")
    rgb = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
    receipt = {
        "reset_sha256": checksum,
        "initial_rgb_sha256": sha(rgb.tobytes()),
        "camera_sha256": digest(path),
        "world_xml_sha256": world.world.manifest["xml_sha256"],
    }
    frozen(folder / "reset.json", receipt)
    return rgb, receipt


def yaw_abs(x):
    return abs(math.atan2(math.sin(x), math.cos(x)))


def history(angles, quote):
    return [
        yaw_abs(angles[0]),
        yaw_abs(angles[-1]),
        angles[-1] - angles[0],
        float(np.mean(np.abs(np.diff(angles[-4:]))) / 0.2) if len(angles) > 1 else 0,
        len(angles),
        0.05 * quote["wait_ticks"],
        quote["help_units"],
        quote["risk"],
    ]


def episode(world, common, quote, fault, method, fixed_best=None, model=None):
    world.rewind()
    local = sense(world, "tank", common)
    now = lambda: float(world.world.data.time)
    angles = [float(world.sensors.odometry[2])]
    tick = 0
    events = []
    query = None
    decision = None
    delivered_from = None

    def event(stage, **details):
        events.append({"stage": stage, "t": round(now(), 6), **details})

    def scan(until):
        nonlocal tick, local
        while local is None and tick < until:
            turn = float(
                np.clip(
                    -2 * math.atan2(math.sin(angles[-1]), math.cos(angles[-1])),
                    -0.5,
                    0.5,
                )
            )
            world.world.step({"tank": [0.0, turn]})
            world.sensors.integrate(0.05)
            tick += 1
            if tick % 4 == 0:
                image = world.world.render("tank")
                local = sense(world, "tank", image)
                angles.append(float(world.sensors.odometry[2]))
        # Subsequent services and docking must start from the live robot pose.

    eligible = quote["available"]

    def deadline(limit):
        return (
            min(limit, SENSING - SERVICE - quote["wait_ticks"]) if eligible else limit
        )

    if method == "immediate_peer" and eligible:
        local = None
        ask = True
    elif method == "local_only" or (method == "immediate_peer" and not eligible):
        scan(60)
        ask = False
    else:
        scan(deadline(FIRST))
        if local is None:
            query = history(angles, quote)
        if method == "adaptive" and local is None and eligible:
            from explorer4.cognitive.action_value import choose_action

            estimates = forecast(model, query)
            decision = choose_action(
                admissible=[LOCAL, ASK],
                forecasts=estimates,
                fallback=LOCAL,
                time_weight=TIME_PRICE,
                help_weight=HELP_PRICE,
                domain="sim",
                model_sha256=model["identity"],
            )
            limit = FIRST if decision["action"] == ASK else FIXED[fixed_best]
        else:
            limit = FIXED[fixed_best if method == "adaptive" else method]
        scan(deadline(limit))
        ask = local is None and eligible
    packet = local
    if ask:
        event(
            "requested",
            donor="rosmaster",
            fee=quote["help_units"],
            advertised_wait_s=0.05 * quote["wait_ticks"],
        )
        if tick + quote["wait_ticks"] + SERVICE > SENSING:
            event("refused", reason="sensing_deadline")
        else:
            event("accepted", donor="rosmaster")
            while now() + 1e-8 < (tick + quote["wait_ticks"]) * 0.05:
                world.world.step({"tank": [0.0, 0.0]})
                world.sensors.integrate(0.05)
            event("service_start", travel_m=0.0)
            from explorer4.sim.cooperation import OBSERVE_POSE

            for _ in range(SERVICE):
                world.world.step({"tank": [0.0, 0.0], "rosmaster": OBSERVE_POSE})
                world.sensors.integrate(0.05)
            world.world.hold_agent("rosmaster")
            image = world.world.render("rosmaster")
            measured = sense(world, "rosmaster", image)
            event(
                "observed",
                frame_sha256=sha(image.tobytes()),
                valid=measured is not None,
            )
            if measured:
                packet = dict(measured)
                if fault:
                    packet["target_xy_m"] = [
                        packet["target_xy_m"][0],
                        packet["target_xy_m"][1] + 0.24,
                    ]
                packet_sha = sha(json.dumps(packet, sort_keys=True).encode())
                event("delivered", packet_sha256=packet_sha)
                delivered_from = "rosmaster"
                world.received = packet
            else:
                event("refused", reason="donor_no_valid_packet")
    if now() > 6.00001:
        raise ValueError("Hard sensing budget exceeded")
    sensing = now()
    outcome = world.dock(packet, save=False)
    # dock verifies freshness and records the true consumed message.
    if outcome["consumed_packet"] is not None:
        event_record = {
            "stage": "consumed",
            "t": round(sensing, 6),
            "source": delivered_from or "tank",
            "packet_sha256": sha(
                json.dumps(outcome["consumed_packet"], sort_keys=True).encode()
            ),
        }
        events.append(event_record)
    if now() > 20.0001:
        raise ValueError("Hard task clock exceeded")
    event(
        "recipient_outcome",
        success=outcome["task"] == "success",
        reason=outcome["reason"],
    )
    result = {
        "method": method,
        "history": query,
        "decision": decision,
        "events": events,
        "terminal": outcome,
        "sensing_s": sensing,
    }
    result.update(trace_costs(events))
    return result


def trace_costs(events):
    by = {e["stage"]: e for e in events}
    end = by["recipient_outcome"]
    accepted = by.get("accepted")
    start = by.get("service_start")
    seen = by.get("observed")
    wait = start["t"] - accepted["t"] if start else 0.0
    service = seen["t"] - start["t"] if seen and start else 0.0
    return {
        "win": int(end["success"]),
        "calls": int("requested" in by),
        "help_units": float(by.get("requested", {}).get("fee", 0.0)),
        "wait_s": wait,
        "service_s": service,
        "travel_m": float((start or {}).get("travel_m", 0.0)),
        "human_s": 0.0,
        "seconds": end["t"],
        "expired_or_refused": int("refused" in by),
        "negative_help": bool(accepted and not end["success"]),
        "deadline_miss": end["t"] >= 20 - 1e-5 and not end["success"],
    }


def utility(row, t=TIME_PRICE, h=HELP_PRICE):
    return row["win"] - t * row["seconds"] - h * row["help_units"]


def forecast(model, history_vector):
    rows = model["neighbors"]
    distance = np.linalg.norm(
        (np.asarray([r["x"] for r in rows]) - history_vector)
        / np.asarray(model["scale"]),
        axis=1,
    )
    close = np.argsort(distance, kind="stable")[:6]
    result = {}
    for action in (LOCAL, ASK):
        adjacent = [rows[i][action] for i in close]
        n = len(adjacent)
        s = sum(r["win"] for r in adjacent)
        p = (s + 1) / (n + 2)
        result[action] = {
            "model_sha256": model.get("identity", ""),
            "domain": "sim",
            "verified": model["admitted"].get(action, False),
            "p_success": p,
            "elapsed_s": mean(r["seconds"] for r in adjacent),
            "help_cost": mean(r["help_units"] for r in adjacent),
            "uncertainty": math.sqrt(p * (1 - p) / (n + 3)),
            "support": n,
        }
    return result


def collect(stage, out, model=None):
    from explorer4.sim.cooperation import CooperationWorld

    room, seeds = SPLITS[stage]
    world = CooperationWorld(out / "scratch" / room, seeds[0], room)
    rows = []
    try:
        for index, seed in enumerate(seeds):
            folder = out / stage / str(seed)
            world.output = folder
            common, reset = frozen_start(world, seed, folder)
            quote, fault = context(index)
            methods = (
                list(FIXED)
                if stage != "confirmation"
                else [model["fixed_best"], "adaptive", "local_only", "immediate_peer"]
            )
            row = {
                "seed": seed,
                "quote": quote,
                "methods": {},
                "hidden_fault_scoring_only": fault,
            }
            for method in methods:
                path = folder / (method + ".json")
                if not path.is_file():
                    start = time.process_time()
                    result = episode(
                        world,
                        common,
                        quote,
                        fault,
                        method,
                        model["fixed_best"] if model else None,
                        model,
                    )
                    result.update(
                        reset=reset,
                        method=method,
                        protocol_sha256=digest(out / "protocol.json"),
                        model_sha256=model["identity"] if model else None,
                        process_cpu_s=time.process_time() - start,
                    )
                    frozen(path, result)
                trial = read(path)
                if (
                    trial["reset"] != reset
                    or trial["protocol_sha256"] != digest(out / "protocol.json")
                    or trial["model_sha256"] != (model["identity"] if model else None)
                ):
                    raise ValueError("Different trial registration")
                if any(trial[k] != v for k, v in trace_costs(trial["events"]).items()):
                    raise ValueError("Trace does not reconstruct costs")
                row["methods"][method] = trial
            rows.append(row)
            print(stage, seed, flush=True)
    finally:
        world.close()
    return rows


def fit(train, cal, out):
    costs = {
        method: mean(utility(r["methods"][method]) for r in cal) for method in FIXED
    }
    best = max(
        FIXED,
        key=lambda m: (costs[m], -sum(r["methods"][m]["calls"] for r in cal), FIXED[m]),
    )

    def cases(rows):
        result = []
        for r in rows:
            short = r["methods"]["local_0.8"]
            long = r["methods"][best]
            if short["history"] is not None and r["quote"]["available"]:
                if short["history"] != long["history"]:
                    raise ValueError("Different predecision histories")
                result.append(
                    {
                        "x": short["history"],
                        **{
                            a: {k: v[k] for k in ("win", "seconds", "help_units")}
                            for a, v in ((ASK, short), (LOCAL, long))
                        },
                    }
                )
        return result

    neighbors = cases(train)
    if len(neighbors) < 6:
        raise ValueError("Insufficient independent action forecasts")
    scale = np.maximum(np.std([r["x"] for r in neighbors], axis=0), 0.05).tolist()
    model = {
        "fixed_best": best,
        "calibration_fixed_mean_utility": costs,
        "neighbors": neighbors,
        "scale": scale,
        "admitted": {},
        "scores": {},
    }
    valid = cases(cal)
    for a in (ASK, LOCAL):
        predictions = [(forecast(model, r["x"])[a], r[a]) for r in valid]
        brier = mean((p["p_success"] - r["win"]) ** 2 for p, r in predictions)
        mae = mean(abs(p["elapsed_s"] - r["seconds"]) for p, r in predictions)
        model["admitted"][a] = len(predictions) >= 4 and brier <= 0.35 and mae <= 6
        model["scores"][a] = {
            "n": len(predictions),
            "brier": brier,
            "mean_abs_time_error_s": mae,
        }
    model["identity"] = sha(json.dumps(model, sort_keys=True, allow_nan=False).encode())
    frozen(out / "model.json", model)
    return model


def summarize(rows, out, model):
    from scipy.stats import binomtest

    methods = list(rows[0]["methods"])
    best = model["fixed_best"]
    record = {}
    savings = {}
    for name in methods:
        values = [r["methods"][name] for r in rows]
        record[name] = {
            "n": len(values),
            **{
                k: sum(v[k] for v in values)
                for k in (
                    "win",
                    "calls",
                    "help_units",
                    "wait_s",
                    "service_s",
                    "travel_m",
                    "human_s",
                    "expired_or_refused",
                    "negative_help",
                    "deadline_miss",
                )
            },
            "mean_sensing_s": mean(v["sensing_s"] for v in values),
            "mean_elapsed_s": mean(v["seconds"] for v in values),
            "mean_utility": mean(utility(v) for v in values),
            "mean_process_cpu_s": mean(v["process_cpu_s"] for v in values),
            "fallbacks": sum(
                (v["decision"] or {}).get("source") == "fallback" for v in values
            ),
        }
    primary = [(r["methods"]["adaptive"], r["methods"][best]) for r in rows]
    gains = sum(x["win"] and not y["win"] for x, y in primary)
    losses = sum(y["win"] and not x["win"] for x, y in primary)
    contrast = {
        "gains": gains,
        "losses": losses,
        "paired_exact_p": float(binomtest(gains, gains + losses).pvalue)
        if gains + losses
        else 1.0,
        "mean_utility_difference": mean(utility(x) - utility(y) for x, y in primary),
        "median_utility_difference": median(
            utility(x) - utility(y) for x, y in primary
        ),
    }
    sensitivity = []
    for t in (0, 0.005, 0.02):
        for h in (0, 0.10, 0.25):
            sensitivity.append(
                {
                    "time_price": t,
                    "help_price": h,
                    "mean_utility": {
                        n: mean(utility(r["methods"][n], t, h) for r in rows)
                        for n in methods
                    },
                }
            )
    for n, x in record.items():
        savings[n] = not any(
            y["win"] >= x["win"]
            and y["help_units"] <= x["help_units"]
            and y["mean_elapsed_s"] <= x["mean_elapsed_s"]
            and (
                y["win"] > x["win"]
                or y["help_units"] < x["help_units"]
                or y["mean_elapsed_s"] < x["mean_elapsed_s"]
            )
            for y in record.values()
        )
    slim = [
        {
            "seed": r["seed"],
            "offer": r["quote"],
            "simulated_fault": r["hidden_fault_scoring_only"],
            "methods": {
                n: {
                    k: v[k]
                    for k in (
                        "win",
                        "calls",
                        "help_units",
                        "seconds",
                        "sensing_s",
                        "decision",
                    )
                }
                for n, v in r["methods"].items()
            },
        }
        for r in rows
    ]
    frozen(
        out / "result.json",
        {
            "status": "completed",
            "domain": "sim",
            "physical_trials": 0,
            "n_unique_scenes": len(rows),
            "protocol_sha256": digest(out / "protocol.json"),
            "test_binding_sha256": digest(out / "test-binding.json"),
            "model_sha256": model["identity"],
            "best_fixed": best,
            "validation": model["scores"],
            "method_summary": record,
            "primary_adaptive_minus_fixed": contrast,
            "pareto_nondominated": savings,
            "utility_sensitivity": sensitivity,
            "per_scene": slim,
        },
    )


def run(out, phase):
    import torch

    from explorer4.resources import ResourceLease

    torch.set_num_threads(1)
    cv2.setNumThreads(1)
    if not (out / "protocol.json").is_file():
        raise ValueError("Registration is required")
    register(out)
    with ResourceLease("peer-action-value-pilot"):
        if phase == "develop":
            fit(collect("fit", out), collect("calibration", out), out)
        else:
            model = read(out / "model.json")
            identity = model.pop("identity")
            if (
                sha(json.dumps(model, sort_keys=True, allow_nan=False).encode())
                != identity
            ):
                raise ValueError("Model was modified")
            model["identity"] = identity
            import inspect

            from explorer4.cognitive.action_value import choose_action

            binding = {
                "protocol_sha256": digest(out / "protocol.json"),
                "model_sha256": digest(out / "model.json"),
                "broker_sha256": digest(Path(inspect.getfile(choose_action))),
                "dev_trials_sha256": {
                    s: sha(
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
                raise ValueError("Refusing late registration")
            frozen(out / "test-binding.json", binding)
            summarize(collect("confirmation", out, model), out, model)


if __name__ == "__main__":
    c = argparse.ArgumentParser(description=__doc__)
    c.add_argument("phase", choices=("register", "develop", "confirm"))
    c.add_argument("--output", type=Path, default=OUT)
    args = c.parse_args()
    if args.phase == "register":
        register(args.output)
    else:
        run(args.output, args.phase)
