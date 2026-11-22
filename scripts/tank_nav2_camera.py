"""Paired RGB docking with frozen Tank PPO and the pinned ROS 2 Nav2 control law."""

import argparse
import ctypes
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean

import numpy as np

from explorer4.paths import DATA, ROOT
from explorer4.simlab import contract
from explorer4.simlab.artifact import Policy
from explorer4.simlab.perception import TargetTracker
from scripts import tank_ppo_camera as original
from scripts.nav2_dock.build import CACHE, LIBRARY
from scripts.peer_dock_study import frozen

OUT = DATA / "simlab/reports/tank-nav2-camera-v1"
SEEDS = list(range(104000, 104016))
DEVELOPMENT = [100001, 100003, 100006]
ARMS = ("nav2_memory", "ppo_memory", "ppo_native")
LIMITS = np.asarray(contract.ROBOTS["tank"]["policy_limits"], dtype=np.float32)
MEMORY_S = 8.0


def register(out):
    old = original.protocol()
    build = original.read(CACHE / "build.json")
    if original.file_sha(LIBRARY) != build["library_sha256"]:
        raise ValueError("Nav2 build receipt differs from the loaded ELF")
    names = (
        "scripts/tank_nav2_camera.py",
        "scripts/nav2_dock/velocity.cpp",
        "scripts/nav2_dock/build.py",
    )
    spec = {
        "study": "tank-nav2-camera-v1",
        "domain": "MuJoCo; zero hardware trials and zero training",
        "seeds": SEEDS,
        "development_only": DEVELOPMENT,
        "arms": list(ARMS),
        "fixed_video_seed": SEEDS[0],
        "design": "New prespecified paired simulator starts outside the original 100000..100099 set. Save identical complete stochastic starting manifests before action. One reset and independently observed trajectory per arm, common software, no tuning on these starts. Old diagnostic starts were previously open.",
        "primary": "nav2_memory minus ppo_memory, paired stable docking success, 16 scenes, two-sided exact binomial on discordances. Both arms receive the same measured goal adapter and scan when unlocalised. ppo_native uses the original frozen PPO with the legacy held RGB target and its own blind behaviour; secondary context. Scene time includes initial search and all subsequent tracking gaps.",
        "endpoint": {
            **old["outcomes"],
            "yaw_speed_limit_rad_s": 0.05,
            "deadline_s": 20,
        },
        "sensor": old["camera"],
        "actor": old["actor_artifacts"],
        "build": build,
        "front_end": "Read RGB at 5 Hz, measure marker in the original calibrated camera. Store the last marker in the robot frame. Each 20-Hz tick between detections transforms the point and heading using simulated IMU gyro and previous forward request (dead reckoning, no wheel odometry or privileged pose). A fresh detection replaces the estimate; bearing, range and yaw are re-expressed in the actor camera convention. Expire after 8 s. Detection bit and age remain measured. Use the same 36 lidar bins, IMU and previous normalized actions and native downstream clamps, latency, slip, collision and safety for all arms.",
        "control": "While unlocalized, memory arms share an in-place scan at 0.6 rad/s, + for 1.5 s then alternating 3 s sweeps about the starting heading. Once localized, PPO uses its frozen mean action. Nav2 uses the pinned Opennav docking law in the current robot frame with the measured 0.25-m standoff goal. The published law produces forward motion even near a point; Explorer switches to a terminal turn within 0.055 m (0.75 rad/s cap, unit gain, minimum 0.20 rad/s), then zero request at measured yaw within 0.12 rad. No map, Nav2 server/planner/costmap, simulator true pose, or critic is passed to controllers. Internal Nav2 approach limits 0.25 m/s and 0.75 rad/s, native PPO limits 0.30 and 1.00, shared outer safety. Scalar gyro/previous action and two measured offsets are the only dead-reckoning inputs.",
        "evidence": "Log all 5-Hz packet hashes, actions, tracking age/mode and outcomes, initial sensory vector and first RGB hash. Secondary collision, time, residuals and sensor coverage. First seed video at real simulator speed (frozen last frame after an arm ends). Separate previously opened diagnostic seeds use the old reactive logic. Allow resume only with matching digests.",
        "sources": {
            **old["sources"],
            **{n: original.file_sha(ROOT / n) for n in names},
        },
        "environment": {
            k: old[k]
            for k in (
                "current_scenario_sha256",
                "cad_manifest_sha256",
                "sysid_ranges_sha256",
            )
        },
    }
    out.mkdir(parents=True, exist_ok=True)
    frozen(out / "protocol.json", spec)


def wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


class VisualMemory:
    """Dead-reckon the last observed marker in the moving base frame."""

    def __init__(self, offset):
        self.offset = offset
        self.point = None
        self.heading = 0.0
        self.age = math.inf

    def update(self, packet, gyro, previous_forward, dt):
        if packet is not None:
            angle = packet["bearing"]
            self.point = (
                self.offset + packet["distance"] * math.cos(angle),
                packet["distance"] * math.sin(angle),
            )
            self.heading = -packet["yaw"]
            self.age = 0.0
        elif self.point is not None:
            rotation = float(gyro) * dt
            travel = float(previous_forward) * dt
            x = self.point[0] - travel * math.cos(rotation / 2)
            y = self.point[1] - travel * math.sin(rotation / 2)
            c, s = math.cos(rotation), math.sin(rotation)
            self.point = (c * x + s * y, -s * x + c * y)
            self.heading = wrap(self.heading - rotation)
            self.age += dt
            if self.age > MEMORY_S:
                self.point = None
        if self.point is None:
            return {
                "distance": 0.0,
                "bearing": 0.0,
                "yaw": 0.0,
                "age_s": contract.AGE_CLIP_S,
                "visible": 0,
            }
        x, y = self.point
        return {
            "distance": math.hypot(x - self.offset, y),
            "bearing": math.atan2(y, x - self.offset),
            "yaw": -self.heading,
            "age_s": self.age,
            "visible": int(packet is not None),
        }

    def goal(self, standoff):
        if self.point is None:
            return None
        return (
            self.point[0] - standoff * math.cos(self.heading),
            self.point[1] - standoff * math.sin(self.heading),
            self.heading,
        )


class Nav2:
    def __init__(self):
        self.velocity = ctypes.CDLL(str(LIBRARY)).explorer_nav2_velocity
        pointer = ctypes.POINTER(ctypes.c_double)
        self.velocity.argtypes = [ctypes.c_double] * 3 + [pointer, pointer]
        self.velocity.restype = ctypes.c_int

    def action(self, goal):
        x, y, heading = goal
        if math.hypot(x, y) < 0.055:
            if abs(heading) < 0.12:
                return np.zeros(2, dtype=np.float32), "hold"
            turn = math.copysign(min(0.75, max(0.20, abs(heading))), heading)
            return np.array([0.0, turn], dtype=np.float32) / LIMITS, "align"
        v, w = ctypes.c_double(), ctypes.c_double()
        if not self.velocity(x, y, heading, ctypes.byref(v), ctypes.byref(w)):
            raise ValueError("Pinned upstream Nav2 returned no finite command")
        return np.array([v.value, w.value], dtype=np.float32) / LIMITS, "nav2"


def action_for(arm, obs, memory, fallback_ticks, env, actor, nav):
    if arm == "legacy_geometry":
        return original.geometric(obs, env), "legacy_scan" if obs[
            5
        ] * contract.AGE_CLIP_S > 0.4 else "legacy_servo"
    if arm == "ppo_native":
        return actor.act(obs), "ppo"
    actor_action = actor.act(obs) if arm == "ppo_memory" else None
    goal = memory.goal(env.standoff)
    if goal is None:
        phase = math.floor((fallback_ticks * env.dt + 1.5) / 3.0)
        return np.array(
            [0.0, 0.60 * (-1 if phase % 2 else 1)], dtype=np.float32
        ) / LIMITS, "search"
    return (actor_action, "ppo") if actor_action is not None else nav.action(goal)


def run_scene(env, camera, actor, nav, seed, arm, folder, protocol_sha):
    import cv2
    import torch

    folder.mkdir(parents=True, exist_ok=True)
    actor.reset()
    native = TargetTracker()
    memory = VisualMemory(env.cam_forward)
    frames = []
    trace_hash = hashlib.sha256()
    first_vector = None
    fallback_ticks = stops = 0
    modes = Counter()
    for tick in range(env.deadline_steps):
        packet = None
        if tick % 4 == 0:
            rgb, packet = camera.measure(env)
            image_sha = original.sha(rgb.tobytes())
            if seed == SEEDS[0]:
                path = folder / f"{arm}-{tick:03}.png"
                if not cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)):
                    raise OSError("Could not preserve preregistered clip frame")
        lidar = env.lidar_bins()[0].numpy()
        imu = env.imu()[0].numpy()
        previous = env.prev_action[0].numpy()
        if arm in ("ppo_native", "legacy_geometry"):
            target = native.update(packet, env.dt)
        else:
            target = memory.update(packet, imu[0], previous[0] * LIMITS[0], env.dt)
        obs = contract.build("tank", target, lidar, imu, previous)
        if first_vector is None:
            first_vector = obs.tolist()
        action, mode = action_for(arm, obs, memory, fallback_ticks, env, actor, nav)
        fallback_ticks = fallback_ticks + 1 if mode == "search" else 0
        trace_hash.update(obs.tobytes())
        trace_hash.update(action.tobytes())
        modes[mode] += 1
        if tick % 4 == 0:
            frames.append(
                {
                    "tick": tick,
                    "rgb_sha256": image_sha,
                    "packet": packet,
                    "age_s": float(target["age_s"]),
                    "target": {k: float(v) for k, v in target.items()},
                    "mode": mode,
                    "action": action.tolist(),
                }
            )
        command = env.command(torch.tensor(action)[None], env.lidar_bins(noisy=True))
        collision = env.integrate()
        _, _, truncated, info = env.finish(command, collision, auto_reset=False)
        stops += int(info["safety_stop"][0])
        if bool(info["success"][0] | info["collision"][0] | truncated[0]):
            break
    outcome = (
        "success"
        if info["success"][0]
        else "collision"
        if info["collision"][0]
        else "timeout"
    )
    digest = original.sha(json.dumps(frames, sort_keys=True, allow_nan=False).encode())
    frozen(folder / f"{arm}-trace.json", frames)
    return {
        "seed": seed,
        "arm": arm,
        "protocol_sha256": protocol_sha,
        "outcome": outcome,
        "steps": tick + 1,
        "time_s": (tick + 1) * env.dt,
        "terminal_distance_m": float(info["distance"][0]),
        "absolute_terminal_yaw_rad": abs(float(info["yaw_error"][0])),
        "safety_stop_ticks": stops,
        "mode_ticks": dict(modes),
        "detections": sum(x["packet"] is not None for x in frames),
        "frames": len(frames),
        "initial_rgb_sha256": frames[0]["rgb_sha256"],
        "initial_observation": first_vector,
        "sampled_frames_sha256": digest,
        "observation_action_sha256": trace_hash.hexdigest(),
    }


def make_video(out, rows):
    import av
    import cv2

    folder = out / "scenes" / str(SEEDS[0])
    ordered = [r for r in rows if r["seed"] == SEEDS[0]]
    streams = [original.read(folder / (r["arm"] + "-trace.json")) for r in ordered]
    with av.open(str(out / "comparison.tmp.mp4"), "w") as video:
        encoder = video.add_stream("libx264", rate=5)
        encoder.width, encoder.height = 320 * len(ordered), 250
        encoder.pix_fmt = "yuv420p"
        encoder.thread_count = 1
        for t in range(max(map(len, streams)) + 5):
            parts = []
            for row, frames in zip(ordered, streams, strict=True):
                f = frames[min(t, len(frames) - 1)]
                image = cv2.imread(str(folder / f"{row['arm']}-{f['tick']:03}.png"))
                if f["packet"]:
                    corners = np.rint(f["packet"]["corners_px"]).astype(np.int32)
                    cv2.polylines(image, [corners], True, (129, 244, 120), 1)
                tile = cv2.copyMakeBorder(
                    image, 0, 50, 0, 0, cv2.BORDER_CONSTANT, value=(23, 23, 23)
                )
                label = row["arm"].replace("_", " ").upper()
                status = f"{t / 5:.1f} s   {f['mode']}   ID {'seen' if f['packet'] else 'missing'}"
                if t * 0.2 >= row["time_s"]:
                    status = f"{row['outcome'].upper()}  at {row['time_s']:.2f} s  |  last frame"
                for ypos, txt in ((218, label), (239, status)):
                    cv2.putText(
                        tile,
                        txt,
                        (8, ypos),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.48,
                        (245, 245, 245),
                        1,
                        cv2.LINE_AA,
                    )
                parts.append(tile)
            frame = av.VideoFrame.from_ndarray(np.hstack(parts), format="bgr24")
            for packet in encoder.encode(frame):
                video.mux(packet)
        for packet in encoder.encode():
            video.mux(packet)
    (out / "comparison.tmp.mp4").replace(out / "comparison.mp4")


def summarize(out, rows, diagnostics):
    from itertools import combinations

    from scipy.stats import binomtest

    groups = {arm: [r for r in rows if r["arm"] == arm] for arm in ARMS}
    for group in groups.values():
        if [r["seed"] for r in group] != SEEDS:
            raise ValueError("Incomplete pairing")
    paired = {}
    for a, b in combinations(ARMS, 2):
        pair = list(zip(groups[a], groups[b], strict=True))
        if any(
            x["initial_rgb_sha256"] != y["initial_rgb_sha256"]
            or x["initial_observation"] != y["initial_observation"]
            for x, y in pair
        ):
            raise ValueError("Initial RGB or observation differs between arms")
        wins = sum(
            x["outcome"] == "success" and y["outcome"] != "success" for x, y in pair
        )
        losses = sum(
            x["outcome"] != "success" and y["outcome"] == "success" for x, y in pair
        )
        paired[a + "_minus_" + b] = {
            "wins": wins,
            "losses": losses,
            "success_rate_difference": (wins - losses) / len(pair),
            "paired_exact_p": float(binomtest(wins, wins + losses).pvalue)
            if wins + losses
            else 1.0,
        }
    methods = {
        a: {
            "scenes": len(group),
            **{
                o: sum(r["outcome"] == o for r in group)
                for o in ("success", "collision", "timeout")
            },
            **{
                "mean_" + k: mean(r[k] for r in group)
                for k in ("time_s", "terminal_distance_m", "absolute_terminal_yaw_rad")
            },
            **{
                k: sum(r[k] for r in group)
                for k in ("detections", "frames", "safety_stop_ticks")
            },
        }
        for a, group in groups.items()
    }
    frozen(
        out / "result.json",
        {
            "status": "completed",
            "domain": "simulation",
            "training_updates": 0,
            "physical_trials": 0,
            "protocol_sha256": original.file_sha(out / "protocol.json"),
            "starts_sha256": original.file_sha(out / "starts.json"),
            "nav2_library_sha256": original.file_sha(LIBRARY),
            "ppo_weights_sha256": original.file_sha(original.POLICY / "policy.npz"),
            "seeds": SEEDS,
            "methods": methods,
            "paired": paired,
            "development_old_controller": diagnostics,
            "rows": [
                {k: v for k, v in row.items() if k != "initial_observation"}
                for row in rows
            ],
            "video_seed": SEEDS[0],
            "video_sha256": original.file_sha(out / "comparison.mp4"),
        },
    )


def run(out):
    import cv2
    import torch

    from explorer4.resources import ResourceLease
    from explorer4.simlab.dock_mujoco import DockMujoco

    if not (out / "protocol.json").is_file():
        raise ValueError("Register before execution")
    register(out)
    cv2.setNumThreads(1)
    torch.set_num_threads(1)
    protocol_sha = original.file_sha(out / "protocol.json")
    with ResourceLease("tank-nav2-camera-comparison"):
        env = DockMujoco("tank", curriculum=0.5)
        camera = original.Camera(env)
        actor = Policy(original.POLICY)
        nav = Nav2()
        try:
            original.calibration_check(env, camera, out)
            starts = [original.reset(env, s) for s in SEEDS]
            frozen(out / "starts.json", starts)
            rows, diagnostics = [], []
            for initial in [original.reset(env, s) for s in DEVELOPMENT] + starts:
                seed = initial["seed"]
                dev = seed in DEVELOPMENT
                folder = out / ("development" if dev else "scenes") / str(seed)
                for arm in ("legacy_geometry",) if dev else ARMS:
                    if original.reset(env, seed) != initial:
                        raise ValueError("Full MuJoCo reset differs")
                    path = folder / (arm + ".json")
                    if not path.is_file():
                        row = run_scene(
                            env, camera, actor, nav, seed, arm, folder, protocol_sha
                        )
                        frozen(path, row)
                        with (out / "resources.jsonl").open("a") as log:
                            print(
                                json.dumps(
                                    {
                                        "phase": f"{seed}/{arm}",
                                        **original.sample_resources(),
                                    }
                                ),
                                file=log,
                            )
                    row = original.read(path)
                    if (row["seed"], row["arm"], row["protocol_sha256"]) != (
                        seed,
                        arm,
                        protocol_sha,
                    ):
                        raise ValueError(
                            "Existing evidence inconsistent with frozen protocol"
                        )
                    if dev:
                        archived = original.read(
                            original.OUT / "scenes" / str(seed) / "rgb_geometry.json"
                        )
                        diagnostics.append(
                            {
                                "seed": seed,
                                "matched_archived_outcome": row["outcome"]
                                == archived["outcome"],
                                "outcome": row["outcome"],
                                "mode_ticks": row["mode_ticks"],
                                "terminal_distance_m": row["terminal_distance_m"],
                                "absolute_terminal_yaw_rad": row[
                                    "absolute_terminal_yaw_rad"
                                ],
                                "detections": row["detections"],
                                "frames": row["frames"],
                            }
                        )
                    else:
                        rows.append(row)
                print(
                    f"Completed {'development' if dev else 'paired'} seed {seed}",
                    flush=True,
                )
            if not (out / "comparison.mp4").is_file():
                make_video(out, rows)
            summarize(out, rows, diagnostics)
        finally:
            camera.renderer.close()


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("phase", choices=("register", "run"))
    cli.add_argument("--output", type=Path, default=OUT)
    args = cli.parse_args()
    (register if args.phase == "register" else run)(args.output)
