"""Measure and admit at most one operator-observed ROSMASTER interpolation trial."""

import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from . import catalog, datasets, grasp_reference
from .conditioned_grasp import (
    MOTOR_SHA256,
    VISION_SHA256,
    file_hash,
    load_localizer,
    locate_cube,
)
from .deploy_gate import thresholds
from .grasp_calibration import (
    MOTOR,
    VISION,
    json_write,
    open_session,
    session_rows,
    summary,
)
from .grasp_shadow import ArchiveGraspActions
from .paths import DATA, ROOT, offline_environment

NATIVE = ROOT / "docs/results/conditioned_grasp_v1/native-execution.json"
TICKS = 360
TASK = "pick up the cube"
EVIDENCE = "physical-admission.json"


def digest(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def identity(path):
    proof = path / "localization-calibration.json"
    record = json.loads(proof.read_text())
    # The immutable object description binds the operator's physical measurements and five images.
    obj = {
        "width_mm": record["cube_width_mm"],
        "jaw_opening_mm": record["jaw_opening_mm"],
        "reference_stills": [r["sha256"] for r in record["reference_frames"]],
    }
    sources = (
        "explorer4/conditioned_grasp.py",
        "explorer4/grasp_shadow.py",
        "explorer4/grasp_admission.py",
        "explorer4/grasp_reference.py",
        "explorer4/grasp_calibration.py",
        "agents/rosmaster/runtime.py",
        "explorer4/rosmaster_session.py",
        "explorer4/rosmaster_console.py",
        "explorer4/rosmaster_control.py",
        "explorer4/grasp_trial.py",
        "agents/rosmaster/leased_core.py",
        "agents/rosmaster/control_adapter.py",
        "explorer4/trials.py",
        "configs/deploy-gate.json",
    )
    if file_hash(MOTOR) != MOTOR_SHA256 or file_hash(VISION) != VISION_SHA256:
        raise ValueError("Изменилась модель локализации или банк демонстраций")
    if file_hash(path / record["camera_info"]) != record["camera_calibration_sha256"]:
        raise ValueError("Изменились параметры камеры")
    for r in record["reference_frames"]:
        if file_hash(path / r["file"]) != r["sha256"]:
            raise ValueError("Изменилась фотография измеренной позиции")
    return {
        "method": "rbf",
        "motor_sha256": MOTOR_SHA256,
        "vision_sha256": VISION_SHA256,
        "calibration_sha256": file_hash(proof),
        "object_sha256": digest(obj),
        "object": obj,
        "native_evidence_sha256": file_hash(NATIVE),
        "implementation": {n: file_hash(ROOT / n) for n in sources},
        "instruction": TASK,
        "trial_point": 4,
        "trial_ticks": TICKS,
    }


def references(path):
    """First eligible success per independent, explicitly reserved development placement."""
    selected = []
    for f in sorted(grasp_reference.LINKS.glob("*.json")):
        link = json.loads(f.read_text())
        if link["session"] != path.name:
            continue
        with catalog.connect() as db:
            hit = db.execute(
                "SELECT * FROM episodes WHERE session=? AND scene=? AND profile='rosmaster_pick_place' AND category='demonstration' AND outcome='success' AND excluded=0 ORDER BY created,id LIMIT 1",
                (link["series"], link["layout"]),
            ).fetchone()
        if hit:
            selected.append((link, dict(hit)))
    selected.sort(key=lambda pair: pair[0]["placement"])
    if [p[0]["placement"] for p in selected] != list(range(1, len(selected) + 1)) or len(selected) > 3:
        raise ValueError("Нарушен зафиксированный порядок трёх проверочных расстановок")
    return selected


def initial_target(path, placement, rgb, estimator):
    """Confirm a full visible cube by matching the operator's measured, annotated reference."""
    ref = session_rows(path)[placement - 1]
    bgr = cv2.imread(str(path / ref["file"]))
    ref_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    x0, y0, x1, y1 = np.rint(ref["confirmed_cube_bbox_xyxy_px"]).astype(int)
    # Include measured context so a flat cube face cannot match any patch of the same colour.
    l, t, r, b = max(0, x0 - 4), max(0, y0 - 4), min(640, x1 + 4), min(480, y1 + 4)
    x, y = max(0, l - 18), max(0, t - 18)
    patch = ref_rgb[t:b, l:r]
    area = rgb[y : min(480, b + 18), x : min(640, r + 18)]
    if patch.shape[0] < 4 or patch.shape[1] < 4 or max(np.std(patch, axis=(0, 1))) < 5:
        raise ValueError("На эталонном снимке недостаточно фактуры по краям кубика")
    corr = cv2.matchTemplate(area, patch, cv2.TM_CCOEFF_NORMED)
    _, score, _, (dx, dy) = cv2.minMaxLoc(corr)
    box = [x + dx + x0 - l, y + dy + y0 - t, x + dx + x1 - l, y + dy + y1 - t]
    if (
        not np.isfinite(score)
        or score < 0.90
        or not (0 < box[0] < box[2] < 640 and 0 < box[1] < box[3] < 480)
    ):
        raise ValueError("Кубик или фон не совпали с проверенным эталоном этой точки")
    predicted = locate_cube(estimator, rgb)
    error = float(np.linalg.norm(predicted - ref["independently_measured_base_xy_m"]))
    tolerance = json.loads((path / "session.json").read_text())["measured_allowable_xy_error_m"]
    if not np.isfinite(error) or error > tolerance:
        raise ValueError("Кубик находится вне измеренного допуска выбранной позиции")
    return {
        "confirmed_cube_bbox_xyxy_px": [int(i) for i in box],
        "template_correlation": float(score),
        "xy_error_m": error,
        "predicted_xy_m": predicted.tolist(),
    }


class InferenceLocalizer:
    """Same frozen FP32 network and preprocessing as the study, with warmed CUDA inference."""

    def __init__(self, network):
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("Для решения за 40 мс нужен проверенный CUDA-исполнитель Homebrain")
        self.network = network.to("cuda").eval()
        with torch.inference_mode():
            self(torch.zeros((1, 3, 120, 160), dtype=torch.float32))

    def __call__(self, pixels):
        return self.network(pixels.to("cuda")).cpu()


class MeasuredActions(ArchiveGraspActions):
    input_domain = "bound_rosmaster_reference"

    def locate(self, observation, image):
        # The position was computed from this very image while checking the matched
        # physical point. The observation is constructed locally, never taken from a client.
        return np.asarray(observation["predicted_xy_m"], dtype=np.float32)


def observation(sample, binding, target):
    return {
        "domain": MeasuredActions.input_domain,
        "robot_id": "rosmaster",
        "device_id": binding["device_id"],
        "camera_calibration_sha256": binding["camera_info_sha256"],
        "observation.state": sample["arm_measured"],
        "images": {"front": sample["rgb"]},
        **target,
    }


@lru_cache(maxsize=1)
def prewarm():
    return InferenceLocalizer(load_localizer(VISION))


def policy(path):
    proof = json.loads((path / "localization-calibration.json").read_text())
    return MeasuredActions(None, MOTOR, VISION, "rbf", proof, localizer=prewarm())


def replay(path, link, ep, model):
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    root = Path(ep["dataset"])
    meta = json.loads((root / "provenance.json").read_text())
    hw = meta["hardware"]
    binding = hw.get("rgb_camera_identity", {})
    if (
        meta.get("domain") != "real"
        or meta.get("synthetic") is not False
        or meta.get("command_source") != "human"
        or binding.get("role") != "validation"
        or binding.get("series") != link["series"]
        or binding.get("layout") != ep["scene"]
        or binding.get("session") != path.name
        or binding.get("calibration_sha256") != file_hash(path / "localization-calibration.json")
        or hw.get("collection", {}).get("instruction") != TASK
        or hw.get("emergency_intervention")
    ):
        raise ValueError(
            "Эпизод не был зафиксирован как независимый успешный человеческий показ этого кубика"
        )
    journal = [json.loads(s) for s in (root / "research.jsonl").read_text().splitlines()]
    required = thresholds()["frames_per_episode"]
    if len(journal) < required or len(journal) != ep["frames"]:
        raise ValueError("Неполный журнал показа")
    ds = LeRobotDataset(repo_id="local/" + ep["id"], root=root, video_backend="pyav")
    image = ds[0]["observation.images.front"].permute(1, 2, 0).numpy()
    rgb = np.rint(np.clip(image, 0, 1) * 255).astype(np.uint8)
    start = {"rgb": rgb, "arm_measured": journal[0]["observation.state"]}
    if journal[0]["camera"].get("source_timestamp_ns") != binding[
        "recording_start_rgb_source_ns"
    ] or not np.allclose(start["arm_measured"], binding["recording_start_arm_deg"], atol=0.001):
        raise ValueError("Первый кадр и измеренная поза не совпали с первичным журналом")
    hold = np.asarray(start["arm_measured"])
    commands = np.asarray([r["action"] for r in journal], float)
    moving = np.flatnonzero(np.max(abs(commands - hold), axis=1) > 2.25)
    if not len(moving):
        raise ValueError("В показе не обнаружено начала действия")
    begin = int(moving[0])
    n = min(len(journal) - begin, TICKS)
    if n < required:
        raise ValueError("Слишком короткий отрезок от начала движения")
    # Use the registered initial view and align by a fixed motor-onset rule, never by minimum error.
    model.reset()
    t0 = time.monotonic()
    target = initial_target(path, link["placement"], rgb, model.localizer)
    obs = observation(start, binding, target)
    indices = set(np.linspace(0, n - 1, required, dtype=int).tolist())
    errors = []
    jumps = []
    latencies = []
    last = None
    for i in range(n):
        row = journal[begin + i]
        state = np.asarray(row["observation.state"])
        ages = np.asarray(row.get("measured_response_age_s"), dtype=float)
        cam = row.get("camera") or {}
        timestamp = row.get("observation_timestamp_ns", 0)
        previous_ns = (
            journal[begin + i - 1].get("observation_timestamp_ns", 0) if begin + i else timestamp - 50_000_000
        )
        timely = (
            0 < timestamp - previous_ns < 250_000_000
            and 0 <= timestamp - cam.get("timestamp_ns", 0) <= 500_000_000
        )

        if (
            not timely
            or row.get("measured_response_kind") != "servo_position_readback"
            or ages.shape != (6,)
            or not np.all((ages >= 0) & (ages <= 0.6))
            or row.get("command_source") != "human"
            or not all(row.get("arm_measured_valid", []))
            or len(row.get("arm_measured_valid", [])) != 6
            or not np.isfinite(state).all()
            or state.shape != (6,)
            or not np.all(np.abs(row.get("base_requested", [100])) <= 0.01)
        ):
            raise ValueError("Показ содержит неподтверждённое движение, обратную связь или источник команд")
        now = time.monotonic()
        if i < 220:
            last = np.asarray(model.next(obs))
        latency = time.monotonic() - now
        if i == 0:
            latencies.append(time.monotonic() - t0)
        if i in indices:
            errors.append(abs(last - commands[begin + i]).tolist())
            jumps.append(abs(last - state).tolist())
            if i:
                latencies.append(latency)
    return {
        "episode": ep["id"],
        "series": ep["session"],
        "scene": ep["scene"],
        "sha256": datasets.fingerprint(root),
        "frames_scored": len(errors),
        "motion_onset_frame": begin,
        "initial_localization": target,
        "first_step_latency_s": latencies[0],
        "p95_tick_latency_s": float(np.percentile(latencies, 95)),
        "error": errors,
        "jump": jumps,
    }


def review(path):
    with (path / ".review.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        selected = references(path)
        result = {
            "session": path.name,
            "method": "rbf",
            "status": "blocked",
            "physical_trials": 0,
            "reason": "",
            "reference_episodes": [],
        }
        try:
            if summary(path)["status"] != "positive":
                raise ValueError("Статическая проверка камеры не пройдена")
            if len(selected) != 3:
                raise ValueError(f"Готовых независимых показов {len(selected)} из 3")
            ident = identity(path)
            result["identity"] = ident
            model = policy(path)
            rows = []
            for link, ep in selected:
                rows.append(replay(path, link, ep, model))
            lim = thresholds()
            errors = np.concatenate([r.pop("error") for r in rows])
            jumps = np.concatenate([r.pop("jump") for r in rows])
            result["reference_episodes"] = rows
            mae = errors.mean(axis=0)
            p95 = np.percentile(jumps, 95, axis=0)
            native = json.loads(NATIVE.read_text())
            if native["source_sha256"]["native_executor"] != file_hash(
                ROOT / "agents/rosmaster/runtime.py"
            ) or [r["seed"] for r in native["trials"]] != list(range(940200, 940220)):
                raise ValueError("Штатный исполнитель или исходные сцены отличаются от проверенных")
            n = len(native["trials"])
            wins = sum(
                r["methods"]["rbf"]["outcome"] == "success"
                and r["methods"]["rbf"]["executed_control_steps"] <= TICKS
                for r in native["trials"]
            )
            latency = max(r["first_step_latency_s"] for r in rows)
            result.update(
                channel_mae_deg=mae.tolist(),
                p95_jump_deg=p95.tolist(),
                slowest_initial_decision_s=latency,
                native_sim_success=wins,
                native_sim_trials=n,
            )
            checks = {
                "native_mujoco": n >= lim["mujoco_min_episodes"] and wins / n >= lim["mujoco_min_success"],
                "independent_recordings": len(rows) >= lim["min_real_holdout_episodes"],
                "joint_and_grip_mae": bool(np.all(mae <= [lim["joint_mae_deg"]] * 5 + [lim["gripper_mae"]])),
                "p95_command_jump": bool(
                    np.all(p95 <= [lim["first_step_jump_deg_p95"]] * 5 + [lim["gripper_first_step_p95"]])
                ),
                "latency": max(latency, max(r["p95_tick_latency_s"] for r in rows))
                <= lim["latency_budget_fraction"] / 20,
            }
            result["checks"] = checks
            if not all(checks.values()):
                raise ValueError("Не пройдены проверки: " + ", ".join(k for k, v in checks.items() if not v))
            result.update(status="ready", reason="Одна наблюдаемая проба на четвёртой измеренной позиции")
        except (KeyError, OSError, ValueError, RuntimeError) as exc:
            result["reason"] = str(exc)
        result["decision_sha256"] = digest(result)
        # Preserve the first published verdict; subsequent rescoring never silently opens a consumed permit.
        json_write(path / EVIDENCE, result)
        return result


def schedule(series):
    if not isinstance(series, str) or not re.fullmatch(r"rosmaster_pick_place-s\d+", series):
        return
    link = grasp_reference.LINKS / (series + ".json")
    if not link.is_file():
        return
    path = open_session(json.loads(link.read_text())["session"])
    if len(references(path)) != 3 or (path / EVIDENCE).exists():
        return
    env = {**offline_environment(), "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
    with (path / "admission.log").open("ab") as log:
        subprocess.Popen(
            [str(ROOT / ".venv/bin/python"), "-m", "explorer4.grasp_admission", path.name],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )


def resume_pending():
    # A UI restart can interrupt an offline review. This only restarts measured-data
    # processing. No trial is claimed and no robot endpoints are touched here.
    for f in grasp_reference.LINKS.glob("*.json"):
        link = json.loads(f.read_text())
        if link["placement"] == 3:
            schedule(link["series"])


def make_plan(session_id):
    path = open_session(session_id)
    decision = json.loads((path / EVIDENCE).read_text())
    if decision.get("status") != "ready":
        raise PermissionError(decision.get("reason", "Нет допуска"))
    ident = digest([session_id, decision["decision_sha256"], "one_trial"])[:32]
    plan = {
        "id": ident,
        "session": session_id,
        "kind": "conditioned_grasp",
        "profile": "rosmaster_pick_place",
        "approval_sha256": decision["decision_sha256"],
        "method": "rbf",
        "instruction": TASK,
        "max_duration_s": 22.0,
        "source_id": session_id,
        "object_sha256": decision["identity"]["object_sha256"],
        "point": 4,
    }
    require(plan)
    plan_file = DATA / "trials" / (ident + ".json")
    plan_file.parent.mkdir(exist_ok=True)
    with (path / ".lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if plan_file.exists() and json.loads(plan_file.read_text()) != plan:
            raise ValueError("Изменился план попытки")
        if not plan_file.exists():
            json_write(plan_file, plan)
    return plan


def require(plan):
    path = open_session(plan["session"])
    if (path / "physical-trial-claimed.json").exists():
        raise PermissionError("Эта единственная попытка уже использована")
    decision = json.loads((path / EVIDENCE).read_text())
    key = decision.pop("decision_sha256")
    if (
        key != digest(decision)
        or plan.get("approval_sha256") != key
        or decision.get("status") != "ready"
        or plan.get("id") != digest([path.name, key, "one_trial"])[:32]
        or plan.get("kind") != "conditioned_grasp"
        or plan.get("source_id") != path.name
        or plan.get("method") != "rbf"
        or plan.get("instruction") != TASK
        or plan.get("point") != 4
        or plan.get("profile") != "rosmaster_pick_place"
        or plan.get("max_duration_s") != 22.0
        or decision["identity"] != identity(path)
        or plan.get("object_sha256") != decision["identity"]["object_sha256"]
    ):
        raise PermissionError("Допуск не соответствует кубику, контроллеру или сохранённому решению")
    selected = references(path)
    if len(selected) != 3 or [(e["id"], datasets.fingerprint(e["dataset"])) for _, e in selected] != [
        (r["episode"], r["sha256"]) for r in decision["reference_episodes"]
    ]:
        raise PermissionError("Изменились независимые записи после решения")
    return {**decision, "decision_sha256": key}


def claim(plan):
    require(plan)
    path = open_session(plan["session"]) / "physical-trial-claimed.json"
    try:
        with path.open("x") as f:
            json.dump(
                {"plan": plan["id"], "decision_sha256": plan["approval_sha256"], "claimed_at": time.time()}, f
            )
            f.flush()
            os.fsync(f.fileno())
    except FileExistsError as exc:
        raise PermissionError("Единственная попытка уже занята") from exc


def live_binding(plan):
    path = open_session(plan["session"])
    return grasp_reference.current_camera(
        {
            "session": path.name,
            "calibration_sha256": file_hash(path / "localization-calibration.json"),
            "placement": 4,
        }
    )


def checked_sample(path, sample, binding, model):
    verified = grasp_reference.verify_start(sample, binding)
    target = initial_target(path, 4, sample["rgb"], model.localizer)
    return observation(sample, verified, target), target


def preflight(plan, sample):
    path = open_session(plan["session"])
    binding = live_binding(plan)
    # This sample precedes the CameraInfo request. Verify sensor/robot ROS times are within the same 0.5 s window.
    difference = abs(sample["camera"]["source_timestamp_ns"] - binding["camera_sample_source_ns"]) / 1e9
    if difference > 0.5:
        raise ValueError("RGB и CameraInfo не относятся к свежему общему окну")
    binding["camera_sample_source_ns"] = min(
        binding["camera_sample_source_ns"], sample["camera"]["source_timestamp_ns"]
    )
    obs, target = checked_sample(path, sample, binding, policy(path))
    received = sample.get("homebrain_received_ns", 0)
    if not 0 <= time.monotonic_ns() - received <= 500_000_000:
        raise ValueError("К моменту проверки исходный кадр устарел; повторите после STOP")
    return {"target": target, "device_id": obs["device_id"], "object_sha256": plan["object_sha256"]}


class LiveGrasp:
    def __init__(self, plan):
        self.path = open_session(plan["session"])
        self.model = policy(self.path)
        self.binding = live_binding(plan)
        self.plan_id = plan["id"]
        self.decision_budget = thresholds()["latency_budget_fraction"] / 20
        self.reset()

    def reset(self):
        self.model.reset()
        self.index = 0
        self.last = None
        self.obs = None
        self.pending = None
        self.last_stamp = None
        self.decision_info = {}

    def next_sample(self, sample):
        claimed = json.loads((self.path / "physical-trial-claimed.json").read_text())
        if claimed["plan"] != self.plan_id:
            raise PermissionError("Попытка принадлежит другому плану")
        if self.index >= TICKS:
            raise StopIteration
        stamp = sample["agent_monotonic_ns"]
        camera = sample["camera"]
        if (
            (self.last_stamp is not None and not 0 < stamp - self.last_stamp < 250_000_000)
            or not 0 <= stamp - camera["received_ns"] <= 500_000_000
            or sample.get("preparing")
            or np.shape(sample.get("arm_measured")) != (6,)
            or not all(sample.get("arm_measured_valid", []))
            or len(sample.get("arm_measured_valid", [])) != 6
            or np.shape(sample.get("base_measured")) != (3,)
            or not np.all(np.abs(sample["base_measured"]) <= 0.01)
            or not np.all(np.isfinite(sample["arm_measured"]))
            or np.shape(sample.get("arm_measured_ages_s")) != (6,)
            or not np.all(np.asarray(sample["arm_measured_ages_s"], float) >= 0)
            or not np.all(np.asarray(sample["arm_measured_ages_s"], float) <= 0.6)
            or sample.get("base_measured_age_s") is None
            or not 0 <= sample["base_measured_age_s"] <= 0.5
        ):
            raise ValueError("Остановлено: кадр, положение шасси или обратная связь руки недостоверны")
        self.last_stamp = stamp
        decision_started = time.monotonic()
        if self.obs is None:
            self.obs, target = checked_sample(self.path, sample, self.binding, self.model)
            self.decision_info = {"method": "rbf", "target": target, "command_tick": 0}
        if self.index < 220:
            self.last = self.model.next(self.obs)
        self.index += 1
        self.decision_info["command_tick"] = self.index
        decision_seconds = time.monotonic() - decision_started
        if decision_seconds > self.decision_budget:
            raise RuntimeError("Превышено допустимое время решения политики")
        self.decision_info["decision_seconds"] = decision_seconds
        return list(self.last)


if __name__ == "__main__":
    import torch

    torch.set_num_threads(1)
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m explorer4.grasp_admission CALIBRATION_SESSION")
    from .resources import ResourceBusy, ResourceLease

    session_path = open_session(sys.argv[1])
    with (session_path / ".offline-worker.lock").open("a+") as worker:
        try:
            fcntl.flock(worker, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(0)
        while not (session_path / EVIDENCE).exists():
            try:
                with ResourceLease("compute"):
                    print(review(session_path))
                break
            except ResourceBusy:
                time.sleep(5)
