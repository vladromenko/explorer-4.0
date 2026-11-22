"""Verify the fixed SO-101 camera against the jaw marker and passive encoder feedback."""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .paths import DATA, ROOT
from .so101_vendor.measure import CALIBRATION, CAMERA
from .resources import ResourceLease, assert_hardware_available

PUBLIC = DATA / "simlab/reports/so101-station-check.json"


def capture():
    """Call the installed station libraries in an isolated process, with Explorer's device leases."""
    station = Path(
        os.environ.get(
            "EXPLORER4_SO101_STATION",
            Path.home() / "Projects/so101_autonomous_pick_place",
        )
    )
    target = DATA / "so101_station" / uuid.uuid4().hex
    target.mkdir(parents=True)
    result = {"ok": False, "at": time.time(), "motor_writes": 0, "folder": str(target)}
    try:
        with ResourceLease("hardware"), ResourceLease("cameras"):
            assert_hardware_available(["/dev/so101-follower", CAMERA])
            env = {
                **os.environ,
                "PYTHONPATH": os.pathsep.join(
                    map(
                        str,
                        (
                            ROOT,
                            station / "src",
                            station / "vendor/lerobot-so101-inverse-kinematics/python",
                        ),
                    )
                ),
            }
            check = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "explorer4.station_check",
                    "--capture",
                    str(target),
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=40,
            )
        if check.returncode:
            reason = check.stderr.strip().splitlines()
            raise ValueError(reason[-1] if reason else "Station control process failed")
        result.update(json.loads((target / "control.json").read_text()))
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result["reason"] = str(exc)
    temporary = PUBLIC.with_suffix("." + uuid.uuid4().hex + ".tmp")
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(PUBLIC)
    return result


def sample(folder):
    import hashlib

    import cv2
    from so101ik import Model
    from so101_pick_place.hardware.robot import ReadOnlySO101
    from so101_pick_place.vision.calibration_control import validate_overview_control
    from .hardware import JOINTS, calibration_snapshot
    from .so101_vendor import measure

    calibration = json.loads(CALIBRATION.read_text())
    snapshot = calibration_snapshot()
    follower = DATA / "calibration" / snapshot["files"]["follower"]["path"]
    feedback = ReadOnlySO101("/dev/so101-follower", follower)
    before = feedback.read()
    if any(before["torque_enabled"].values()):
        raise ValueError("SO-101 is already holding an active torque setting")
    image = folder / "overview.jpg"
    measure.capture(image)
    after = feedback.read()
    if any(after["torque_enabled"].values()) or any(
        abs(before["positions"][n] - after["positions"][n]) > 1 for n in JOINTS
    ):
        raise ValueError("The arm moved during the camera exposure")
    model = Model(calibration_file=follower, offsets=calibration["robot_offsets_deg"])
    result = validate_overview_control(
        cv2.imread(str(image)), calibration, model, after["positions"]
    )
    (folder / "control.json").write_text(
        json.dumps(
            dict(
                ok=True,
                control=result,
                image=str(image),
                image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                calibration_sha256=hashlib.sha256(CALIBRATION.read_bytes()).hexdigest(),
                scope="Single-pose independent check, same RGB frame used for the station measurement.",
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--capture":
        sample(Path(sys.argv[2]))
    else:
        print(json.dumps(capture(), indent=2, ensure_ascii=False))
