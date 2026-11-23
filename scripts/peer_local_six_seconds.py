"""Post-hoc six-second onboard observation controls on the 16 opened action-value starts."""

import argparse
import json
import math
from pathlib import Path
from statistics import mean
from unittest.mock import patch

import cv2
import numpy as np

from explorer4.paths import ROOT
from explorer4.sim.state_codec import encode, load
from scripts import peer_action_value_pilot as pilot
from scripts.peer_dock_study import digest, frozen

SOURCE = pilot.OUT
OUT = SOURCE.parent / "peer-local-six-seconds"
METHODS = ("repeat_3s", "extend_heading", "arc_left", "arc_right")


def canonical(value):
    return pilot.sha(
        json.dumps(encode(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def prepare():
    design = pilot.read(SOURCE / "protocol.json")
    versions = pilot.read(SOURCE / "runtime-environment.json")
    for file, checksum in (design["materials"] | versions["files"]).items():
        if digest(ROOT / file) != checksum:
            raise ValueError("Changed primary simulator or controller: " + file)
    group = design["groups"]["confirmation"]
    data = {}
    for seed in group["seeds"]:
        folder = SOURCE / "confirmation" / str(seed)
        data[str(seed)] = {
            f: digest(folder / f)
            for f in ("reset.json", "initial.png", "initial-state.json", "local_only.json", "local_3.0.json")
        }
    OUT.mkdir(parents=True, exist_ok=True)
    frozen(
        OUT / "protocol.json",
        {
            "question": "Does spending the full peer policy sensing cap on local observations recover docking performance?",
            "scope": "Post-hoc on the previously opened 16 action-value confirmation starts. No new independent scenes or fit.",
            "room": group["room"],
            "scenes": group["seeds"],
            "primary_protocol": digest(SOURCE / "protocol.json"),
            "primary_summary": digest(SOURCE / "result.json"),
            "primary_runtime": digest(SOURCE / "runtime-environment.json"),
            "script_sha256": digest(Path(__file__)),
            "reference_sha256": data,
            "shared_prefix": "Rebuild the same scene model, restore the full archived simulator state and deliver the original initial RGB. Run the original local_only function for up to 3 s. On repeated branches serve exactly the RGB of the shared prefix only at the identical physical state, time and camera.",
            "controls": {
                "repeat_3s": "Replay original local_only; check the detection time, terminal win, consumed packet presence, command digest and duration against the original before using the controls.",
                "extend_heading": "Primary sensitivity. At a 3 s miss continue the exact original local heading law, same pad, speed zero, turn clamp ±0.5 rad/s, yaw feedback from the latest 5 Hz sample, for 60 further 20 Hz ticks.",
                "arc_left": "Exploratory onboard-only. At a 3 s miss: one second turn towards +0.55 rad at up to 0.65 rad/s, one second drive at 0.16 m/s with that heading target, then one second drive at 0.16 m/s while steering back towards zero. Same proportional heading law, 5 Hz odometry feedback.",
                "arc_right": "Independent mirrored exploratory policy towards -0.55 rad. Both sides run on every start. No result-dependent choice.",
            },
            "samples": "Original initial image, then every 4 native 50 ms steps of search (0.2 s). At the first valid onboard ArUco/IPPE measurement stop searching immediately and start the unchanged same-world docking controller. Stop without a packet at 6 s. No donor, map, seed, screen label, score or actual target is exposed to the action policy.",
            "endpoint": "Original independent stable docking until 20 s from reset. Compare each control to archived calibration-selected local_3.0 (first search then request if feasible). Utility = success - 0.005*total simulated seconds - 0.1*quoted help units actually consumed. Report paired gains/losses, calls, sensing, terminal seconds, utility and measured end-of-search displacement.",
            "limits": "Fixed bounded local paths on the existing open start pad in the simulator. No obstacle-aware navigation or physical permission is claimed. A negative result does not exclude other onboard views.",
        },
    )


def command(method, step, yaw):
    target, speed, limit = 0.0, 0.0, 0.5
    if method in ("arc_left", "arc_right"):
        target = (0.55 if method == "arc_left" else -0.55) if step < 40 else 0.0
        speed, limit = (0.16 if step >= 20 else 0.0), 0.65
    error = math.atan2(math.sin(target - yaw), math.cos(target - yaw))
    return [speed, float(np.clip(2 * error, -limit, limit))]


def rollout(world, method, initial, cache):
    base_dock, render = world.dock, world.world.render
    prefix, extra, actions, observed = [], [], [], {}

    def camera(robot):
        if robot != "tank":
            raise ValueError("Recipient-only control received a peer image")
        time_s = round(float(world.world.data.time), 6)
        state = world.world.snapshot()["physics"].tobytes()
        cam = world.world.model.camera("tank/" + world.world.views["tank"].env.camera_name).id
        optics = world.world.data.cam_xpos[cam].tobytes() + world.world.data.cam_xmat[cam].tobytes()
        key = pilot.sha(state + optics)
        if time_s <= 3.000001 and key in cache:
            image = cache[key]
        else:
            image = render(robot)
            if time_s <= 3.000001:
                cache[key] = image.copy()
        entry = {
            "t": time_s,
            "physics_camera_sha256": key,
            "rgb_sha256": pilot.sha(image.tobytes()),
            "odometry": world.sensors.odometry.tolist(),
        }
        (prefix if time_s <= 3.000001 else extra).append(entry)
        return image

    def continue_search(packet, **kwargs):
        origin = world.sensors.odometry.copy()
        observed["split_s"] = float(world.world.data.time)
        observed["split_state_sha256"] = canonical(world.world.snapshot())
        observed["had_packet_by_three"] = packet is not None
        yaw = float(origin[2])
        for step in range(0 if packet is not None or method == "repeat_3s" else 60):
            target = command(method, step, yaw)
            world.world.step({"tank": target})
            world.sensors.integrate(0.05)
            actions.append(target)
            if (step + 1) % 4 == 0:
                packet = pilot.sense(world, "tank", world.world.render("tank"))
                yaw = float(world.sensors.odometry[2])
                if packet is not None:
                    break
        observed.update(
            sensing_s=float(world.world.data.time),
            extra_displacement_m=float(np.linalg.norm(world.sensors.odometry[:2] - origin[:2])),
            final_sensor_odometry=world.sensors.odometry.tolist(),
            observed_local_packet=packet is not None,
        )
        return base_dock(packet, **kwargs)

    with patch.object(world, "dock", continue_search), patch.object(world.world, "render", camera):
        result = pilot.episode(world, initial, {"available": False}, False, "local_only")
    terminal = result["terminal"]
    if (
        observed["sensing_s"] > 6.00001
        or terminal["simulation_time_s"] > 20.00001
        or result["calls"]
        or any(abs(v) > 0.16000001 or abs(w) > 0.65000001 for v, w in actions)
    ):
        raise ValueError("Unexpected time, call or actuator command")
    if len(extra) != len(actions) // 4:
        raise ValueError("Incorrect camera frequency")
    return {
        "method": method,
        **observed,
        "terminal": terminal,
        "extra_frames": extra,
        "extra_commands_sha256": pilot.sha(np.asarray(actions, dtype="<f8").tobytes()),
        "extra_ticks": len(actions),
        "max_extra_speed": max((abs(a[0]) for a in actions), default=0.0),
        "max_extra_turn": max((abs(a[1]) for a in actions), default=0.0),
        "prefix": prefix,
        "initial_rgb_sha256": pilot.sha(initial.tobytes()),
        "seconds": result["seconds"],
        "calls": 0,
        "win": result["win"],
        "utility": result["win"] - pilot.TIME_PRICE * result["seconds"],
    }


def run():
    import torch
    from explorer4.sim.cooperation import CooperationWorld

    cv2.setNumThreads(1)
    torch.set_num_threads(1)
    prepare()
    spec = pilot.read(OUT / "protocol.json")
    key = digest(OUT / "protocol.json")
    rows = []
    world = CooperationWorld(OUT / "scratch", spec["scenes"][0], spec["room"])
    try:
        for seed in spec["scenes"]:
            src = SOURCE / "confirmation" / str(seed)
            dest = OUT / str(seed)
            dest.mkdir(exist_ok=True)
            original = pilot.read(src / "local_only.json")
            paired = pilot.read(src / "local_3.0.json")
            reset = pilot.read(src / "reset.json")
            rgb = cv2.cvtColor(cv2.imread(str(src / "initial.png")), cv2.COLOR_BGR2RGB)
            world.reset(seed)
            world.initial = load(src / "initial-state.json")
            world.rewind()
            if (
                canonical(world.world.snapshot()) != reset["reset_sha256"]
                or world.world.manifest["xml_sha256"] != reset["world_xml_sha256"]
                or pilot.sha(rgb.tobytes()) != reset["initial_rgb_sha256"]
                or original["reset"] != reset
                or paired["reset"] != reset
            ):
                raise ValueError(f"Changed shared reset or image {seed}")
            row = {"seed": seed, "reset": reset, "methods": {}}
            values = {}
            cache = {}
            for method in METHODS:
                path = dest / (method + ".json")
                if not path.exists():
                    result = rollout(world, method, rgb, cache)
                    result["protocol_sha256"] = key
                    frozen(path, result)
                values[method] = trial = pilot.read(path)
                if trial["protocol_sha256"] != key:
                    raise ValueError("Wrong receipt")
                if method == "repeat_3s":
                    checks = {
                        k: trial["terminal"][k] == original["terminal"][k]
                        for k in ("task", "reason", "commands_sha256", "actions_sent")
                    }
                    checks["time"] = abs(original["seconds"] - trial["seconds"]) < 1e-5
                    checks["found_time"] = abs(original["sensing_s"] - trial["sensing_s"]) < 1e-5
                    if not all(checks.values()):
                        raise ValueError(f"Original local-only reproduction failed at {seed}: {checks}")
                elif (
                    trial["prefix"] != values["repeat_3s"]["prefix"]
                    or trial["split_state_sha256"] != values["repeat_3s"]["split_state_sha256"]
                ):
                    raise ValueError(f"Different pre-intervention inputs at {seed}")
                row["methods"][method] = {
                    k: trial[k]
                    for k in (
                        "win",
                        "calls",
                        "sensing_s",
                        "seconds",
                        "utility",
                        "had_packet_by_three",
                        "observed_local_packet",
                        "extra_ticks",
                        "extra_displacement_m",
                        "max_extra_speed",
                        "max_extra_turn",
                    )
                }
                row["methods"][method]["receipt_sha256"] = digest(path)
            row["methods"]["local_first"] = {
                k: paired[k] for k in ("win", "calls", "sensing_s", "seconds", "help_units")
            }
            row["methods"]["local_first"]["utility"] = (
                paired["win"] - pilot.HELP_PRICE * paired["help_units"] - pilot.TIME_PRICE * paired["seconds"]
            )
            rows.append(row)
            print(seed, {k: v["win"] for k, v in row["methods"].items()}, flush=True)
    finally:
        world.close()
    totals = {}
    contrasts = {}
    for name in (*METHODS, "local_first"):
        group = [r["methods"][name] for r in rows]
        baseline = [r["methods"]["local_first"] for r in rows]
        totals[name] = {
            "successes": sum(t["win"] for t in group),
            "calls": sum(t["calls"] for t in group),
            **{"mean_" + k: mean(t[k] for t in group) for k in ("sensing_s", "seconds", "utility")},
        }
        contrasts[name] = {
            "control_only": sum(a["win"] and not b["win"] for a, b in zip(group, baseline)),
            "local_first_only": sum(b["win"] and not a["win"] for a, b in zip(group, baseline)),
            **{
                "mean_delta_" + k: mean(a[k] - b[k] for a, b in zip(group, baseline))
                for k in ("win", "calls", "seconds", "utility")
            },
        }
    frozen(
        OUT / "result.json",
        {
            "phase": "Post-hoc repeated controls on opened scenes",
            "n": len(rows),
            "protocol_sha256": key,
            "full_trace": "One JSON receipt per seed and local policy on Homebrain, including time, actual odometry, RGB and state digests for each added camera frame.",
            "physical_trials": 0,
            "training_updates": 0,
            "summary": totals,
            "control_minus_local_first": contrasts,
            "rows": rows,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "run"))
    if parser.parse_args().phase == "prepare":
        prepare()
    else:
        run()
