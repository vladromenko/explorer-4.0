"""Register and run a retrospective Tank PPO versus visual servo comparison without training."""

import argparse
import hashlib
import json
import math
import os
import resource
import time
from pathlib import Path
from statistics import mean
from types import SimpleNamespace

import numpy as np

from explorer4.paths import DATA, ROOT
from explorer4.simlab import contract, scenario
from explorer4.simlab.artifact import Policy
from scripts.peer_dock_study import frozen

OUT = DATA / "simlab/reports/tank-ppo-camera-v1"
POLICY = DATA / "simlab/policies/tank_dock_smoke2"
SEEDS = list(range(100000, 100050))
ARMS = ("proxy_ppo", "rgb_ppo", "rgb_geometry", "offset_ppo", "offset_geometry")
SOURCES = (
    "scripts/tank_ppo_camera.py",
    "explorer4/simlab/artifact.py",
    "explorer4/simlab/contract.py",
    "explorer4/simlab/dock_gpu.py",
    "explorer4/simlab/dock_mujoco.py",
    "explorer4/simlab/perception.py",
    "explorer4/simlab/scenario.py",
    "explorer4/sim/peer_dock.py",
    "explorer4/sim/mobile.py",
    "explorer4/sim/tank_model.py",
    "explorer4/sim/scene.py",
    "configs/scene_measurements.yaml",
    "configs/scenarios/dock_v1.yaml",
    "configs/tank-hardware-evidence.json",
)


def read(path):
    return json.loads(path.read_text())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    return sha(path.read_bytes())


def protocol():
    historical = read(POLICY / "eval-0.5.json")
    info = read(POLICY / "policy.json")
    if (
        [r["seed"] for r in historical["episodes"]] != SEEDS
        or info["weights_sha256"] != file_sha(POLICY / "policy.npz")
        or info["contract_hash"] != contract.contract_hash("tank")
        or info["train"]["actor_dim"] != 141
    ):
        raise ValueError("Unexpected historical seeds, weights or actor contract")
    ranges = DATA / "simlab/sysid/tank.json"
    return {
        "name": "tank-ppo-camera-v1",
        "phase": "retrospective on previously opened starts; new comparisons fixed before any new rollouts",
        "seeds": SEEDS,
        "arms": list(ARMS),
        "curriculum": 0.5,
        "training_updates": 0,
        "physical_trials": 0,
        "current_scenario_sha256": scenario.fingerprint("dock_v1"),
        "policy_scenario_sha256": info["scenario_fingerprint"],
        "historical_reference": "Archived 37/50 is a reference from the older simulator, whose registered board had a 100 mm marker. The current scenario specifies 150 mm. Historical XML and other simulator components were not guaranteed identical. proxy_ppo reruns the current upstream surrogate with the same weights.",
        "primary": "rgb_ppo minus rgb_geometry paired stable docking success. Both use the same measurement-to-observation pipeline, seeded full MuJoCo starts, two normalized actions, robot safety and termination. Their trajectories and later camera images may diverge.",
        "secondary": "For each controller corrupt only the delivered measured target bearing by +30 degrees on even seeds and -30 on odd seeds throughout the rollout; leave physical target, distance, yaw, visibility and safety unchanged. Compare correct versus offset successes, collisions, timeout, time, terminal pose. Exact paired two-sided binomial test on discordant successes; exploratory secondary contrasts.",
        "inputs": "Tank actor stacks 3 x 47: 6 target fields, 36 lidar sectors, 3 IMU channels, 2 previous normalized actions. The 53-dimensional training critic is never passed to either actor. proxy_ppo receives the native noisy simulator-pose target, FOV/occlusion/dropout. RGB arms obtain targets only from OpenCV ArUco/IPPE on actual rendered front camera pixels. Lidar and inertial channels are simulated. No donor or physical camera is tested.",
        "camera": "Every fourth 20 Hz control tick including tick 0 (5 Hz), 320x200 scaled factory pinhole, zero distortion as rendered, native CAD mounting. ID 0, 150 mm black square; white border and black cells on the board are render-only visual geometry with explicit front-facing orientation. Preserve full native physics and lidar. Between images the tracker ages the last measurement, visibility indicates a detection on that tick. Rotate noisy-PnP normals from optical to body frame. Report missing detections. Different sensor/noise schedule for native proxy versus RGB.",
        "controller": "Saved deterministic PPO mean action or existing DockSensors.action on a robot-frame goal reconstructed from the same six fields with the registered 0.25 m standoff. Original controller gains (0.18 m/s, 0.5 rad/s); same outer clamps and lidar/safety on both. Geometry scans at +0.4 rad/s after 0.4 s without a valid measurement. No simulator pose, reward, ID of seed, or collision oracle enters the motion controller.",
        "outcomes": scenario.load_scenario("dock_v1")["success"],
        "yaw_speed_limit_rad_s": 0.05,
        "deadline_s": 20,
        "paired_start": "Reset seeded PyTorch generator before each reset for every arm. Persist 50 starting snapshots (planar qpos, obstacle boxes/activation, dynamics parameters and RNG checksum) first; require equality before any control.",
        "sources": {n: file_sha(ROOT / n) for n in SOURCES},
        "actor_artifacts": {
            n: file_sha(POLICY / n)
            for n in ("policy.json", "policy.npz", "eval-0.5.json")
        },
        "cad_manifest_sha256": file_sha(
            DATA / "cache/source/mentorpi-t1-cad/manifest.json"
        ),
        "sysid_ranges_sha256": file_sha(ranges) if ranges.is_file() else None,
    }


class Camera:
    def __init__(self, env):
        import cv2
        import mujoco

        from explorer4.sim.peer_dock import OPTICAL_TO_MUJOCO
        from explorer4.simlab.perception import MarkerDetector

        spec = scenario.load_measurements()["dock_target"]["marker"]
        intrinsics = read(ROOT / "configs/tank-hardware-evidence.json")[
            "installed_camera"
        ]["intrinsics"]
        k = np.asarray(intrinsics["k"]).reshape(3, 3).copy()
        k[:2] *= 0.5
        self.detector = MarkerDetector(
            k, side=spec["side"], dictionary=spec["family"], marker_id=spec["id"]
        )
        neutral = mujoco.MjData(env.model)
        mujoco.mj_forward(env.model, neutral)
        mount = neutral.camera("front_cam")
        self.origin = mount.xpos.copy()
        self.axes = mount.xmat.reshape(3, 3) @ OPTICAL_TO_MUJOCO
        self.renderer = mujoco.Renderer(env.model, height=200, width=320)
        self.option = mujoco.MjvOption()
        self.option.geomgroup[:] = 1
        self.spec = spec
        pattern = cv2.aruco.generateImageMarker(
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), spec["id"], 6
        )
        pitch = spec["side"] / len(pattern)
        height = spec["center_height"]
        self.tiles = [
            (
                [0.0002, 0.625 * spec["side"], 0.625 * spec["side"]],
                [0.003, 0, height],
                [1, 1, 1, 1],
            )
        ]
        for row, col in np.argwhere(pattern == 0):
            self.tiles.append(
                (
                    [0.0001, pitch / 2, pitch / 2],
                    [0.0035, (col - 2.5) * pitch, height + (2.5 - row) * pitch],
                    [0.005, 0.005, 0.005, 1],
                )
            )

    def measure(self, env):
        import cv2
        import mujoco

        self.renderer.update_scene(
            env.data, camera="front_cam", scene_option=self.option
        )
        scene = self.renderer.scene
        scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 0
        for size, pos, rgba in self.tiles:
            g = scene.geoms[scene.ngeom]
            mujoco.mjv_initGeom(
                g,
                mujoco.mjtGeom.mjGEOM_BOX,
                np.asarray(size, float),
                np.asarray(pos, float),
                np.eye(3).ravel(),
                np.array(rgba, np.float32),
            )
            scene.ngeom += 1
        rgb = self.renderer.render()
        found = self.detector.detect(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        if found is None:
            return rgb, None
        point = self.origin + self.axes @ found["translation_optical_m"]
        dx = point[0] - env.cam_forward
        normal = self.axes @ found["normal_optical"]
        return rgb, {
            "distance": math.hypot(dx, point[1]),
            "bearing": math.atan2(point[1], dx),
            "yaw": -math.atan2(-normal[1], -normal[0]),
            "corners_px": found["corners_px"],
            "reprojection_error_px": found["reprojection_error_px"],
        }


def reset(env, seed):
    import torch

    env.g.manual_seed(seed)
    env.reset(torch.ones(1, dtype=torch.bool))
    return {
        "seed": seed,
        "qpos": env.data.qpos[:3].tolist(),
        "boxes": env.boxes[0].tolist(),
        "active_boxes": env.box_active[0].tolist(),
        "dynamics": {k: float(v[0]) for k, v in env.params.items()},
        "rng_sha256": sha(env.g.get_state().numpy().tobytes()),
    }


def geometric(obs, env):
    from explorer4.sim.peer_dock import DockSensors

    distance, sz, cz, heading, _, age = obs[:6]
    if age * contract.AGE_CLIP_S > 0.4:
        return np.array([0.0, 0.4], np.float32)
    yaw = -float(heading) * math.pi
    # Point from robot centre to marker, then back out along the measured wall normal.
    marker_xy = np.array(
        [
            env.cam_forward + distance * contract.TARGET_SCALE_M * cz,
            distance * contract.TARGET_SCALE_M * sz,
        ]
    )
    target = marker_xy - env.standoff * np.array([math.cos(yaw), math.sin(yaw)])
    v, w = DockSensors.action(
        SimpleNamespace(odometry=np.zeros(3)),
        {"target_xy_m": target, "target_yaw_rad": yaw},
    )
    return np.array([v, w], np.float32) / np.asarray(
        contract.ROBOTS["tank"]["policy_limits"], np.float32
    )


def trial(env, camera, actor, seed, arm, out):
    import cv2
    import torch

    from explorer4.simlab.perception import TargetTracker

    actor.reset()
    tracker = TargetTracker()
    found_count = 0
    frames = 0
    stops = 0
    initial_obs = None
    detections = hashlib.sha256()
    trace = hashlib.sha256()
    first_found = None
    folder = out / "scenes" / str(seed)
    folder.mkdir(parents=True, exist_ok=True)
    for step in range(env.deadline_steps):
        if arm == "proxy_ppo":
            obs = env.observe()[0][0].numpy()
        else:
            found = None
            if step % 4 == 0:
                rgb, found = camera.measure(env)
                frames += 1
                detections.update(hashlib.sha256(rgb.tobytes()).digest())
                detections.update(
                    json.dumps(found, sort_keys=True, allow_nan=False).encode()
                )
                if found:
                    found_count += 1
                if step == 0 or (found and first_found is None):
                    name = f"{arm}-{'initial' if step == 0 else 'first-detected'}.png"
                    if not cv2.imwrite(
                        str(folder / name), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                    ):
                        raise OSError("Cannot preserve the camera evidence")
                    if found and first_found is None:
                        first_found = {
                            "step": step,
                            "image": name,
                            "rgb_sha256": sha(rgb.tobytes()),
                            "packet": found,
                        }
            target = tracker.update(found, env.dt)
            if arm.startswith("offset") and target["distance"] > 0:
                target["bearing"] += math.radians(30 if seed % 2 == 0 else -30)
            obs = contract.build(
                "tank",
                target,
                env.lidar_bins()[0].numpy(),
                env.imu()[0].numpy(),
                env.prev_action[0].numpy(),
            )
        if initial_obs is None:
            initial_obs = obs.tolist()
        action = geometric(obs, env) if arm.endswith("geometry") else actor.act(obs)
        trace.update(obs.tobytes())
        trace.update(action.tobytes())
        command = env.command(torch.tensor(action)[None], env.lidar_bins(noisy=True))
        collision = env.integrate()
        _, _, truncated, info = env.finish(command, collision, auto_reset=False)
        stops += int(info["safety_stop"][0])
        if bool(info["success"][0]) or bool(info["collision"][0]) or bool(truncated[0]):
            break
    outcome = (
        "success"
        if bool(info["success"][0])
        else "collision"
        if bool(info["collision"][0])
        else "timeout"
    )
    return {
        "seed": seed,
        "arm": arm,
        "outcome": outcome,
        "steps": step + 1,
        "elapsed_s": (step + 1) * env.dt,
        "safety_stops": stops,
        "final_distance_m": float(info["distance"][0]),
        "final_yaw_error_rad": float(info["yaw_error"][0]),
        "rgb_frames": frames,
        "detections": found_count,
        "first_detection": first_found,
        "camera_trace_sha256": detections.hexdigest() if frames else None,
        "observation_action_sha256": trace.hexdigest(),
        "initial_observation": initial_obs,
    }


def calibration_check(env, camera, out):
    import cv2
    import mujoco

    # An external frontal fixture with known pose verifies image orientation/metric range before scoring.
    env.data.qpos[:3] = [0.9, 0.0, math.pi]
    for mid in env.obstacle_bodies:
        env.data.mocap_pos[mid] = [0, 0, -5]
    mujoco.mj_forward(env.model, env.data)
    rgb, reading = camera.measure(env)
    cv2.imwrite(str(out / "camera-fixture.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if (
        reading is None
        or abs(reading["distance"] - (0.9 - env.cam_forward)) > 0.05
        or abs(reading["bearing"]) > 0.08
        or abs(reading["yaw"]) > 0.4
    ):
        raise ValueError(f"Known frontal camera fixture failed: {reading}")
    frozen(
        out / "camera-fixture.json",
        {
            "pose": [0.9, 0, math.pi],
            "rgb_sha256": sha(rgb.tobytes()),
            "detection": reading,
        },
    )


ACTIVE_PROTOCOL = "execution-protocol.json"


def sample_resources():
    memory = Path("/proc/meminfo").read_text().splitlines()
    available = (
        int(
            next(line.split()[1] for line in memory if line.startswith("MemAvailable:"))
        )
        / 1024
    )
    gpu_load = Path("/sys/class/devfreq/17000000.gpu/device/load")
    return {
        "unix_s": time.time(),
        "process_cpu_s": time.process_time(),
        "peak_process_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        / 1024,
        "mem_available_mib": round(available),
        "system_load1": os.getloadavg()[0],
        "system_gpu_percent": float(gpu_load.read_text()) / 10
        if gpu_load.is_file()
        else None,
    }


def register(out):
    original = out / "protocol.json"
    spec = protocol()
    if original.is_file():
        initial = read(original)
        # Runtime admission/measurement was amended before any scene was opened. Preserve the original protocol.
        only_runner = "scripts/tank_ppo_camera.py"
        if any(initial.get(k) != v for k, v in spec.items() if k != "sources") or {
            k: v for k, v in spec["sources"].items() if k != only_runner
        } != {k: v for k, v in initial["sources"].items() if k != only_runner}:
            raise ValueError("Scientific setup differs from original registration")
    else:
        frozen(original, spec)
    spec["initial_protocol_sha256"] = file_sha(original)
    spec["runtime"] = (
        "Study-specific exclusive lock, low-priority CPU actor, one Torch/OpenCV/BLAS thread. Save per-arm outcomes. Sample process RSS, process CPU, available RAM, load and shared Jetson GPU use at each completed arm. This scheduling amendment preserves the previously registered methods and endpoints."
    )
    target = out / ACTIVE_PROTOCOL
    if not target.exists() and (out / "starts.json").exists():
        raise ValueError("Cannot amend after the first states have been opened")
    frozen(target, spec)
    return spec


def run(out):
    import cv2
    import torch

    from explorer4.resources import ResourceLease
    from explorer4.simlab.dock_mujoco import DockMujoco

    cv2.setNumThreads(1)
    torch.set_num_threads(1)
    if not (out / ACTIVE_PROTOCOL).is_file():
        raise ValueError("Register the experiment before execution")
    register(out)
    with ResourceLease("tank-ppo-camera-evaluation"):
        usage = out / "resource-samples.jsonl"

        def sample(phase):
            row = {
                "phase": phase,
                "cpu_affinity": sorted(os.sched_getaffinity(0)),
                **sample_resources(),
            }
            with usage.open("a") as log:
                log.write(json.dumps(row) + "\n")

        sample("start")
        env = DockMujoco("tank", curriculum=0.5)
        camera = Camera(env)
        try:
            starts = [reset(env, seed) for seed in SEEDS]
            frozen(out / "starts.json", starts)
            calibration_check(env, camera, out)
            actor = Policy(POLICY)
            rows = []
            for initial in starts:
                seed = initial["seed"]
                for arm in ARMS:
                    if reset(env, seed) != initial:
                        raise ValueError("Pairing failed at reset")
                    path = out / "scenes" / str(seed) / (arm + ".json")
                    if not path.exists():
                        row = trial(env, camera, actor, seed, arm, out)
                        row.update(protocol_sha256=file_sha(out / ACTIVE_PROTOCOL))
                        sample(f"{seed}/{arm}")
                        frozen(path, row)
                    row = read(path)
                    if (
                        row["arm"] != arm
                        or row["seed"] != seed
                        or row["protocol_sha256"] != file_sha(out / ACTIVE_PROTOCOL)
                    ):
                        raise ValueError(
                            "Saved scene differs from registered experiment"
                        )
                    rows.append(row)
                print(
                    f"Completed {len(rows) // len(ARMS)} / {len(SEEDS)} matched starts",
                    flush=True,
                )
            summarize(out, rows)
        finally:
            camera.renderer.close()


def summarize(out, rows):
    from scipy.stats import binomtest

    groups = {arm: [r for r in rows if r["arm"] == arm] for arm in ARMS}
    for arr in groups.values():
        if [r["seed"] for r in arr] != SEEDS:
            raise ValueError("Incomplete seed pairing")
    for a, b in (("rgb_ppo", "rgb_geometry"), ("offset_ppo", "offset_geometry")):
        if any(
            x["initial_observation"] != y["initial_observation"]
            for x, y in zip(groups[a], groups[b], strict=True)
        ):
            raise ValueError(
                "Controllers received different initial camera/sensor inputs"
            )
    stats = {
        k: {
            **{
                s: sum(r["outcome"] == s for r in arr)
                for s in ("success", "collision", "timeout")
            },
            "scenes": len(arr),
            "mean_s": mean(r["elapsed_s"] for r in arr),
            "mean_terminal_distance_m": mean(r["final_distance_m"] for r in arr),
            "mean_abs_terminal_heading_rad": mean(
                abs(r["final_yaw_error_rad"]) for r in arr
            ),
            "safety_stops": sum(r["safety_stops"] for r in arr),
            "frames_detected": sum(r["detections"] for r in arr),
            "frames_rendered": sum(r["rgb_frames"] for r in arr),
        }
        for k, arr in groups.items()
    }
    comparisons = {}
    for a, b in (
        ("rgb_ppo", "rgb_geometry"),
        ("rgb_ppo", "offset_ppo"),
        ("rgb_geometry", "offset_geometry"),
        ("rgb_ppo", "proxy_ppo"),
    ):
        pairs = list(zip(groups[a], groups[b], strict=True))
        wins = sum(
            x["outcome"] == "success" and y["outcome"] != "success" for x, y in pairs
        )
        losses = sum(
            y["outcome"] == "success" and x["outcome"] != "success" for x, y in pairs
        )
        comparisons[a + "_minus_" + b] = {
            "wins": wins,
            "losses": losses,
            "success_rate_difference": (wins - losses) / len(pairs),
            "exact_p": binomtest(wins, wins + losses).pvalue if wins + losses else 1.0,
        }
    historical = read(POLICY / "eval-0.5.json")["episodes"]
    slim = [
        {
            k: v
            for k, v in r.items()
            if k not in ("initial_observation", "first_detection")
        }
        for r in rows
    ]
    frozen(
        out / "result.json",
        {
            "status": "completed",
            "domain": "MuJoCo simulation",
            "physical_trials": 0,
            "training_updates": 0,
            "protocol_sha256": file_sha(out / ACTIVE_PROTOCOL),
            "initial_protocol_sha256": file_sha(out / "protocol.json"),
            "starting_states_sha256": file_sha(out / "starts.json"),
            "actor_weights_sha256": file_sha(POLICY / "policy.npz"),
            "historical_successes": sum(r["outcome"] == "success" for r in historical),
            "proxy_vs_historical_outcomes_matching": sum(
                x["outcome"] == y["outcome"]
                for x, y in zip(groups["proxy_ppo"], historical, strict=True)
            ),
            "methods": stats,
            "paired": comparisons,
            "seeds": SEEDS,
            "rows": slim,
        },
    )


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("phase", choices=("register", "run"))
    args.add_argument("--output", type=Path, default=OUT)
    cli = args.parse_args()
    if cli.phase == "register":
        cli.output.mkdir(parents=True, exist_ok=True)
        register(cli.output)
    else:
        run(cli.output)
