"""Replay development frames with and without chroma through the same Tank observation interface."""
import hashlib
import json
from collections import defaultdict

import cv2
import numpy as np

from explorer4.paths import DATA, ROOT
from explorer4.peer_dock_config import MARKER_ID, MARKER_SIDE_M
from explorer4.peer_request_policy import local_features
from explorer4.sim.peer_screens import screen_fraction
from explorer4.simlab.perception import MarkerDetector


def features(detector, bgr):
    detection = detector.detect(bgr)
    if detection and detection["reprojection_error_px"] > 2.5:
        detection = None
    measurement = {"screen_fraction": screen_fraction(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))}
    return local_features(detection, measurement)


def replay():
    root = DATA / "runs/peer-screen-dock-v2"
    metadata = json.loads((root / "development.json").read_text())
    if metadata["phase"] != "development_only" or metadata["test_outcomes_read"]:
        raise ValueError("Expected development-only outcomes")
    hardware = json.loads((ROOT / "configs/tank-hardware-evidence.json").read_text())
    intrinsics = hardware["installed_camera"]["intrinsics"]["k"]
    detector = MarkerDetector(np.asarray(intrinsics).reshape(3, 3), side=MARKER_SIDE_M, marker_id=MARKER_ID)
    groups = defaultdict(list)
    records = []
    for row in metadata["rows"]:
        if row["split"] not in ("train", "calibration"):
            raise ValueError("Unreleased phase")
        frame = root / row["split"] / str(row["seed"]) / "recipient-before.png"
        if hashlib.sha256(frame.read_bytes()).hexdigest() != row["image_sha256"]:
            raise ValueError("Frame differs from the development evidence")
        colour = cv2.imread(str(frame), cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(colour, cv2.COLOR_BGR2GRAY)
        mono = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        original = features(detector, colour)
        altered = features(detector, mono)
        np.testing.assert_allclose(original, row["x"], rtol=0, atol=1e-8)
        # The PnP target coordinates do not enter the selector. Its first four values
        # come from a marker detector which itself already consumes luminance.
        np.testing.assert_array_equal(original[:4], altered[:4])
        gain = int(row["peer"]) - int(row["local"])
        groups[tuple(altered)].append(gain)
        records.append({"seed": row["seed"], "image_sha256": row["image_sha256"],
                        "rgb_features": original, "monochrome_features": altered,
                        "archived_peer_minus_local_success": gain})
    unresolved = [
        {"input": list(values), "n": len(gains), "rescued": gains.count(1),
         "unchanged": gains.count(0), "harmed": gains.count(-1)}
        for values, gains in groups.items() if len(set(gains)) > 1
    ]
    return {
        "protocol": "Post-hoc paired chroma ablation of pre-decision recipient images. "
                    "Recompute all five selector features; preserve original branch labels.",
        "colour_conversion": "OpenCV BGR2GRAY followed by GRAY2BGR",
        "development_sha256": hashlib.sha256((root / "development.json").read_bytes()).hexdigest(),
        "source": "https://arxiv.org/abs/1703.06907",
        "read_held_out_scenes": 0, "trained_models": 0, "new_motor_rollouts": 0,
        "distinct_rgb_inputs": len({tuple(r["rgb_features"]) for r in records}),
        "distinct_monochrome_inputs": len(groups),
        "identical_monochrome_inputs_with_conflicting_branch_labels": unresolved, "rows": records,
    }


if __name__ == "__main__":
    cv2.setNumThreads(1)
    report = replay()
    target = ROOT / "docs/results/peer-camera-docking/colour-ablation.json"
    target.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print({k: v for k, v in report.items() if k not in ("rows", "protocol", "source")})
