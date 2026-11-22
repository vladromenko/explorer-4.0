"""Interpret only the support-qualified ROSMASTER simulation evidence that matches the field executor."""

import hashlib
import json

from .conditioned_grasp import MOTOR_SHA256, PHYSICS_SHA256, VISION_SHA256, file_hash
from .grasp_measured import TRIAL_TICKS
from .paths import ROOT

REPORT = ROOT / "docs/results/conditioned_grasp_v1/field-admission-v3.json"
PROTOCOL_SHA256 = "1299c3aaafe2c5e95f18523c55bb0c2495d5566f34ab1c038f8a57d348fe6a65"
SELECTION_SHA256 = "9faf751a28ed84f71e8f755aa0653240e836037bc7db6537277759fa2b0f6160"
FIELD_FILES = (
    "explorer4/grasp_measured.py",
    "explorer4/grasp_shadow.py",
    "explorer4/conditioned_grasp.py",
    "agents/rosmaster/runtime.py",
)


def verified_native(path=REPORT):
    data = json.loads(path.read_text())
    history, bank = list(range(88300, 88320)), list(range(976100, 976228))
    if (
        data.get("schema") != "rosmaster.bound-rbf-native.v3"
        or data.get("status") != "completed"
        or data.get("profile") != "rosmaster_floor_pick_recorded_start_sim"
        or data.get("protocol_sha256") != PROTOCOL_SHA256
        or data.get("motor_sha256") != MOTOR_SHA256
        or data.get("vision_sha256") != VISION_SHA256
        or data.get("physics_sha256") != PHYSICS_SHA256
        or data.get("measurement_revision") != "single_sample_cube_on_support_visibility"
        or data.get("physical_trials") != 0
        or data.get("command_budget") != TRIAL_TICKS
        or data.get("field_source_sha256") != {name: file_hash(ROOT / name) for name in FIELD_FILES}
    ):
        raise ValueError("Нет сопоставимого отчёта MuJoCo для текущей политики и штатных ограничений руки")
    candidates = data["candidates"]
    if [r["seed"] for r in candidates] != history + bank:
        raise ValueError("Нарушен порядок исходных сцен")
    for row in candidates:
        if row["eligible"] and not (
            row["inside_motor_hull"] is True
            and row["visibility"]["full"] is True
            and row["reason"] == "eligible"
            and row["camera"]["device_id"] == "mujoco:front_cam"
        ):
            raise ValueError("В допущенную выборку попала сцена с неподтверждённым положением кубика")
    eligible = [r["seed"] for r in candidates[20:] if r["eligible"]]
    selected = eligible[:20]
    cohort = data["conditional"]
    intake = {"protocol_sha256": PROTOCOL_SHA256, "candidates": candidates, "selected": selected}
    intake_bytes = (json.dumps(intake, indent=2, allow_nan=False) + "\n").encode()
    if (
        data.get("selection_sha256") != SELECTION_SHA256
        or hashlib.sha256(intake_bytes).hexdigest() != SELECTION_SHA256
    ):
        raise ValueError("Изменился список кандидатов, зафиксированный до первого испытания")
    trials = data["trials"]
    if (
        cohort["source_bank"] != bank
        or cohort["eligible_candidates"] != len(eligible)
        or cohort["selected"] != selected
        or cohort["n"] != len(selected)
        or [r["seed"] for r in trials] != history + selected
    ):
        raise ValueError("Результаты не соответствуют первым допущенным сценам")
    for row in trials:
        if row["terminal_success"] and not (
            row["executed_ticks"] == TRIAL_TICKS
            and row["termination"] == "field_sequence_complete"
            and row.get("terminal_qualified_hold_s", 0) >= 1
            and row.get("bilateral_contact") is True
            and isinstance(row.get("first_stable_hold_tick"), int)
            and 0 < row["first_stable_hold_tick"] <= TRIAL_TICKS
        ):
            raise ValueError("Успех без удержания кубика в конце ограниченной последовательности")
    wins = sum(r["terminal_success"] is True for r in trials[20:])
    if (
        cohort["minimum_holds"] != 10
        or wins != cohort["terminal_holds"]
        or cohort["pass"] != (len(selected) == 20 and wins >= 10)
    ):
        raise ValueError("Итог допуска не совпадает с исходами отдельных сцен")
    return {
        "wins": wins,
        "n": len(selected),
        "pass": cohort["pass"],
        "eligible_candidates": len(eligible),
        "candidate_count": len(bank),
        "historic_holds": sum(r["terminal_success"] is True for r in trials[:20]),
        "historic_eligible": sum(r["eligible"] for r in candidates[:20]),
    }
