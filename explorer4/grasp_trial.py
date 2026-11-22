"""One leased physical grasp and a separately recorded human observation of the held cube."""
from contextlib import ExitStack
import json
import math
import re
import threading
import time

from . import fleet_config
from .paths import DATA

RESULTS = DATA / "runs/conditioned-grasp-field"
LAUNCH = threading.Lock()


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


def observe_outcome(plan_id, operator, visible, lift_mm, hold_s, note):
    if not isinstance(note, str) or not note.strip() or visible not in ("held", "failed", "unobservable"):
        raise ValueError("Укажите наблюдаемый исход и источник независимого замера или записи")
    if visible == "held" and any(isinstance(x, bool) or not isinstance(x, (int, float))
                                 or not math.isfinite(x) or x < 0 for x in (lift_mm, hold_s)):
        raise ValueError("Измерьте отрыв от исходной опоры в мм и непрерывное время удержания в секундах")
    with fleet_config.locked(), operator.lock:
        record = result(plan_id)
        if not record.get("finished_at") or operator.lease:
            raise ValueError("Сначала нужна завершённая проба и STOP")
        if "endpoint" in record:
            raise ValueError("Исход уже зафиксирован")
        measured = visible == "held" and lift_mm > 50 and hold_s >= 1
        endpoint = {"visible_outcome": visible, "lift_above_support_mm": lift_mm if visible == "held" else None,
                    "continuous_hold_s": hold_s if visible == "held" else None, "measurement": note.strip(),
                    "observed_at": time.time(), "geometry_and_hold_pass": measured}
        record.update(phase="measured", endpoint=endpoint,
                      success=bool(record.get("sequence_completed") and record.get("stop_acknowledged_by_agent") and not record.get("emergency") and measured))
        fleet_config.atomic_write(result_path(plan_id), record)
        return record
