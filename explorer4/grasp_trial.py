"""One leased physical grasp and a separately recorded human observation of the held cube."""
from contextlib import ExitStack
import json
import re
import threading
import time
from pathlib import Path

from . import catalog, fleet_config, grasp_terminal
from .paths import DATA

RESULTS = DATA / "runs/conditioned-grasp-field"
LAUNCH = threading.Lock()
ENDPOINT_VERSION = grasp_terminal.VERSION
PENDING_OBSERVATION = "awaiting_measurement"


def result_path(plan_id):
    if not isinstance(plan_id, str) or not re.fullmatch(r"[a-f0-9]{32}", plan_id):
        raise ValueError("Неверный номер одиночной пробы")
    return RESULTS / (plan_id + ".json")


def result(plan_id):
    path = result_path(plan_id)
    return json.loads(path.read_text()) if path.exists() else {}


def amend(ident, **fields):
    with fleet_config.locked():
        path = result_path(ident)
        record = result(ident)
        record.update(fields)
        fleet_config.atomic_write(path, record)
        return record


def sync_recorded_outcome(record, *, recover_missing=False):
    """A capture keeps its original label. The catalogue can receive the later independent verdict."""
    endpoint = record.get("endpoint") or {}
    measured = record.get("pending_at_capture_close") and endpoint.get("version") == ENDPOINT_VERSION

    if not record.get("episodes") or not (measured or recover_missing):
        return
    base = (DATA / "datasets/rosmaster_pick_place").resolve()
    with catalog.connect() as db:
        for episode in record["episodes"]:
            root = (base / episode).resolve()
            if root.parent != base or root.name != episode:
                raise ValueError("Путь записи не соответствует эпизоду наблюдаемой пробы")
            row = db.execute("SELECT profile,category,dataset,outcome FROM episodes WHERE id=?", (episode,)).fetchone()
            if row is None and (not recover_missing or not (root / "provenance.json").is_file()):
                continue
            if row is not None:
                if row["profile"] != "rosmaster_pick_place" or row["category"] != "rollout" or Path(row["dataset"]).resolve() != root:
                    raise ValueError("Каталог указывает на другую запись пробы")
                if not measured or row["outcome"] != PENDING_OBSERVATION:
                    continue
            raw = json.loads((root / "provenance.json").read_text())
            plan = raw["hardware"]["trial_plan"]
            if (raw["domain"] != "real" or raw["command_source"] != "policy" or plan["id"] != record["plan_id"]
                    or plan["kind"] != "conditioned_grasp"):
                raise ValueError("Сохранённый эпизод не соответствует наблюдению")
            if row is None:
                from .recording import finalized_grasp_frames
                frames = finalized_grasp_frames(root, record, raw)
                db.execute("""INSERT INTO episodes
                    (id,profile,dataset,episode_index,session,scene,category,outcome,frames,created)
                    VALUES(?,'rosmaster_pick_place',?,0,?,?,'rollout',?,?,?) ON CONFLICT(id) DO NOTHING""",
                    (episode, str(root), raw["session_id"], raw["scene_id"], raw["outcome"], frames, raw["closed_at"]))
            if measured:
                if raw["outcome"] != PENDING_OBSERVATION:
                    raise ValueError("Оценка не соответствует исходной метке записи")
                label = grade_status(record)
                db.execute("UPDATE episodes SET outcome=? WHERE id=? AND outcome=?", (label, episode, PENDING_OBSERVATION))


def recover_observed_outcomes():
    for path in RESULTS.glob("*.json"):
        try:
            record = json.loads(path.read_text())
            if record.get("episodes") and record.get("plan_id") != path.stem:
                raise ValueError("Номер пробы не совпадает с именем файла")
            if (record.get("pending_at_capture_close") and record.get("capture_protocol") == ENDPOINT_VERSION
                    and not record.get("recording_saved_at")):
                root = capture_root(record)
                if (root / "provenance.json").is_file():
                    from .recording import finalized_grasp_frames
                    finalized_grasp_frames(root, record, json.loads((root / "provenance.json").read_text()))
                    record = amend(path.stem, recording_saved_at=time.time(), recovered_finalized_capture=True)
            if record.get("recording_saved_at"):
                record = certify(record)
            sync_recorded_outcome(record, recover_missing=True)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            catalog.event("error", f"Восстановление записи пробы {path.stem}: {exc}")


def same_lease(operator, owner, generation, lease):
    return operator.owner == owner and operator.generation == generation and operator.lease == lease and bool(lease)


def check_heartbeat(operator, owner):
    stamp, intent = operator.inputs.get(owner, (0, {}))
    if time.monotonic() - stamp > operator.INPUT_HOLD_S:
        raise InterruptedError("Нет свежего heartbeat наблюдающего оператора")
    if getattr(operator, "mirror", False) or intent.get("free"):
        raise InterruptedError("Идёт ручное вмешательство в режим управления")
    if any(abs(v) > 1e-3 for v in [*intent.get("arm", []), *intent.get("drive", []),
                                   intent.get("pitch", 0), intent.get("roll", 0), intent.get("grip", 0)]):
        raise InterruptedError("Ручное вмешательство. Одиночная проба остановлена")


def start(plan, owner, generation, recorder, operator, scene, confirmed):
    from . import grasp_admission as admission
    from . import rosmaster_control, rosmaster_session
    from .trials import require_physical

    if not confirmed or not scene.strip():
        raise ValueError("Подтвердите неподвижную базу, присутствие у STOP и обозначьте расстановку")
    with LAUNCH, ExitStack() as startup:
        require_physical(plan)
        with operator.lock:
            if recorder.active() or operator.lease or operator.generation != generation:
                raise PermissionError("Для одиночной пробы нужен STOP и свободный пульт")
            check_heartbeat(operator, owner)
        from .grasp_localizer import close_field
        startup.callback(close_field)
        admission.prewarm_field()
        rosmaster_control.ensure_agent()
        if not rosmaster_control.request("/health").get("hardware_open"):
            if operator.generation != generation:
                raise PermissionError("Подготовка отменена последним STOP")
            rosmaster_control.request("/acquire", {}, 45)
        with rosmaster_session.agent_client() as http:
            clock = rosmaster_session.ClockMap(http)
            clock.probe()
            sample = recorder.sample(http, clock)
            initial = admission.preflight(plan, sample)
        with operator.lock:
            if recorder.active() or operator.lease or operator.generation != generation:
                raise PermissionError("Проба отменена последним STOP")
            check_heartbeat(operator, owner)
        admission.claim(plan)
        amend(plan["id"], plan_id=plan["id"], calibration_session=plan["session"], method=plan["method"],
              approval_sha256=plan["approval_sha256"], prearm_observation=initial, scene=scene, started_at=time.time(), phase="claimed",
              success=None)
        try:
            operator.enable(owner, "rosmaster_pick_place", "joint", True, "policy", expected_generation=generation)
            with operator.lock:
                if not same_lease(operator, owner, generation, operator.lease):
                    raise InterruptedError("STOP до запуска записи")
                recorder.start(owner, "rosmaster_pick_place", scene, plan=plan, conditioned_lease=(generation, operator.lease))
                startup.pop_all()  # The recording loop now owns shutdown.
        except Exception as exc:
            with operator.lock:
                ours = same_lease(operator, owner, generation, operator.lease)
            if ours:
                operator.stop("Одиночная проба отменена до начала записи")
            amend(plan["id"], phase="failed_to_start", finished_at=time.time(), sequence_completed=False, error=str(exc))
            raise


def capture_root(record):
    episodes = record.get("episodes", [])
    if len(episodes) != 1 or not re.fullmatch(r"[a-f0-9]{32}", episodes[0]):
        raise ValueError("Нет связанного эпизода терминальной пробы")
    return DATA / "datasets/rosmaster_pick_place" / episodes[0]


def grade_status(record):
    endpoint = record.get("endpoint") or {}
    if not endpoint:
        return "pending"
    if endpoint.get("version") != ENDPOINT_VERSION or endpoint.get("visible_outcome") == "unobservable":
        return "unconfirmed"
    return "success" if record.get("success") else "failure"


def certify(record):
    # This receipt can be rebuilt after a crash without rewriting an earlier operator verdict.
    if record.get("capture_protocol") != ENDPOINT_VERSION or record.get("endpoint") or record.get("terminal_review"):
        return record
    try:
        timing = grasp_terminal.window(capture_root(record), record)
        review = {"status": "available", "window": timing}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        review = {"status": "unconfirmed", "reason": str(exc)}
    return amend(record["plan_id"], terminal_review=review)


def side_video(plan_id):
    return result_path(plan_id).with_suffix(".mp4")


def observe_outcome(plan_id, operator, visible, lift_mm, hold_s, note, *, source=None, stop_s=None, confirmed=False):
    if not isinstance(note, str) or not note.strip() or visible not in ("held", "failed", "unobservable"):
        raise ValueError("Укажите наблюдаемый исход и источник независимого замера или записи")
    record = result(plan_id)
    if not record.get("finished_at") or operator.lease:
        raise ValueError("Сначала нужна завершённая проба и STOP")
    if "endpoint" in record:
        raise ValueError("Исход уже зафиксирован")
    measured = False
    endpoint = {"version": ENDPOINT_VERSION, "visible_outcome": visible, "measurement": note.strip(),
                "observed_at": time.time(), "geometry_and_hold_pass": False}
    if visible == "held":
        if (record.get("terminal_review") or {}).get("status") != "available":
            raise ValueError("Терминальная поза и доступная запись пока не подтверждены. При отсутствии доказательств выберите «Исход не видно».")
        # Re-read the original video, timestamps, feedback and final still on the scoring path.
        window = grasp_terminal.window(capture_root(record), record)
        if window != record["terminal_review"]["window"]:
            raise ValueError("Изменились сохранённые измерения или видеозапись")
        if hold_s is not None:
            raise ValueError("Длительность подтверждает запись, ввод вручную не используется")
        clip = side_video(plan_id) if source == "side_video" else None
        visual = grasp_terminal.bind_height(window, source, stop_s, clip, lift_mm, confirmed)
        measured = lift_mm > 50
        endpoint.update(lift_above_support_mm=lift_mm, continuous_hold_s=window["duration_s"],
                        terminal_window=window, height_evidence=visual, geometry_and_hold_pass=measured)
    with operator.lock, fleet_config.locked():
        if operator.lease:
            raise ValueError("Сначала нужен STOP")
        if result(plan_id) != record:
            raise ValueError("Запись пробы изменилась во время проверки. Обновите журнал")
        record.update(phase="measured", endpoint=endpoint,
                      success=None if visible == "unobservable" else bool(record.get("sequence_completed") and record.get("stop_acknowledged_by_agent")
                                   and not record.get("emergency") and measured))
        fleet_config.atomic_write(result_path(plan_id), record)
    sync_recorded_outcome(record)
    return record
