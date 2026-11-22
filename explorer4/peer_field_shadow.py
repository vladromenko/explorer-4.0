"""Score saved initial Tank RGB independently of the physical docking protocol and its outcomes."""

import fcntl
import hashlib
import json
import logging
import re
import threading
import time

import cv2
import numpy as np

from . import peer_dock_real as field
from . import peer_request_policy as policy
from .paths import DATA, ROOT
from .peer_dock_config import MARKER_ID, MARKER_SIDE_M, MAX_AGE_S
from .sensors import decode_packet
from .sim.peer_screens import screen_fraction
from .simlab.perception import MarkerDetector

CANONICAL = (640, 400)
FIELD = DATA / "peer-dock-field"
CALIBRATION_KEYS = ("width", "height", "k", "d", "frame_id", "distortion_model")
LOG = logging.getLogger(__name__)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_text())


def image_features(rgb, camera):
    """The simulation uses normalized image positions and a 640 x 400 pixel reprojection residual."""
    w, h = camera["width"], camera["height"]
    if (
        type(w) is not int
        or type(h) is not int
        or min(w, h) <= 0
        or rgb.dtype != np.uint8
        or rgb.shape != (h, w, 3)
        or w * CANONICAL[1] != h * CANONICAL[0]
    ):
        raise ValueError("RGB and calibrated 8:5 image dimensions required; unknown crop or aspect ratio")
    if camera["distortion_model"] not in ("plumb_bob", "rational_polynomial") or not camera.get("frame_id"):
        raise ValueError("Missing optical frame or unsupported lens distortion")
    K = np.asarray(camera["k"], dtype=float).reshape(3, 3)
    dist = np.asarray(camera["d"], dtype=float)
    if (
        not np.isfinite(K).all()
        or min(K[0, 0], K[1, 1]) <= 0
        or not np.array_equal(K[2], [0, 0, 1])
        or not (0 <= K[0, 2] < w and 0 <= K[1, 2] < h)
        or dist.shape not in ((4,), (5,), (8,), (12,), (14,))
        or not np.isfinite(dist).all()
    ):
        raise ValueError("Unusable intrinsic matrix or distortion coefficients")
    if (w, h) != CANONICAL:
        # An isotropic resize maps pixel centres to (u+0.5)*scale-0.5.
        scale = CANONICAL[0] / w
        rgb = cv2.resize(rgb, CANONICAL, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        K = K.copy()
        K[:2] *= scale
        K[:2, 2] += (scale - 1) / 2
    detector = MarkerDetector(K, dist, side=MARKER_SIDE_M, marker_id=MARKER_ID)
    detection = detector.detect(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if detection and detection["reprojection_error_px"] > 2.5:
        detection = None
    vector = policy.local_features(detection, {"screen_fraction": screen_fraction(rgb)})
    return {
        "features": vector,
        "feature_names": list(policy.FEATURES),
        "native_camera_size": [w, h],
        "feature_camera_size": list(CANONICAL),
        "feature_camera_k": K.tolist(),
        "feature_rgb_sha256": digest(rgb.tobytes()),
        "corners_px": detection["corners_px"] if detection else [],
        "marker_bearing_rad": detection["bearing"] if detection else None,
        "monochrome_features": policy.local_features(detection, {"screen_fraction": 0.0}),
    }


def load_input(source, kind):
    metadata = source / ("observation.json" if kind == "series" else "result.json")
    doc = read(metadata)
    if kind == "series" and (source.name != "001-tank" or doc.get("id") != source.parent.name + "/001-tank"):
        raise ValueError("Expected the initial Tank capture")
    obs = doc["observations"]["tank"]
    raw = (source / "tank.npz").read_bytes()
    checksum = digest(raw)
    if (
        obs.get("payload_sha256") != checksum
        or obs.get("source_robot") != "tank"
        or obs.get("read_only") is not True
    ):
        raise ValueError("Archived payload or Tank identity differs from the capture receipt")
    packet = decode_packet(raw)
    meta = packet["meta"]
    sensor = meta["streams"]["rgb"]
    info = meta["streams"]["rgb_info"]
    camera = {k: info.get(k) for k in CALIBRATION_KEYS}
    camera_sha = digest(json.dumps(camera, sort_keys=True).encode())
    stamp = sensor.get("source_timestamp_ns")
    if (
        meta["robot"] != "tank"
        or meta.get("read_only") is not True
        or meta.get("motion_commands_sent") != 0
        or meta.get("clock_pair", {}).get("use_sim_time") is not False
        or camera != obs.get("camera")
        or camera_sha != obs.get("camera_sha256")
        or sensor.get("frame_id") != info.get("frame_id")
        or (sensor.get("width"), sensor.get("height")) != (info["width"], info["height"])
        or sensor.get("encoding") not in ("bgr8", "rgb8")
        or type(stamp) is not int
        or stamp <= 0
        or stamp != obs.get("source_rgb_stamp_ns")
        or type(info.get("source_timestamp_ns")) is not int
        or abs(info["source_timestamp_ns"] - stamp) > MAX_AGE_S * 1e9
        or not 0 <= obs["rgb_age_s"] <= MAX_AGE_S
    ):
        raise ValueError(
            "Original RGB time, encoding, camera calibration or physical identity could not be verified"
        )
    rgb = packet["arrays"]["rgb"]
    features = image_features(rgb, camera)
    return {
        **features,
        "decoded_rgb_sha256": digest(rgb.tobytes()),
        "source_payload_sha256": checksum,
        "camera_sha256": camera_sha,
        "camera": camera,
        "rgb_age_s_at_capture": obs["rgb_age_s"],
        "source_rgb_stamp_ns": stamp,
        "received_at": obs["received_at"],
        "source_metadata_sha256": digest(metadata.read_bytes()),
    }


def record(source, kind, phase, models=None):
    ident = source.parent.name if kind == "series" else source.name
    if not re.fullmatch("[0-9a-f]{32}", ident):
        raise ValueError("Invalid physical capture ID")
    dest = FIELD / "shadows" / kind / ident
    dest.mkdir(parents=True, exist_ok=True)
    receipt = dest / "input.json"
    with (dest / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if receipt.exists():
            item = read(receipt)
        else:
            try:
                item = {"status": "available", **load_input(source, kind)}
            except (OSError, ValueError, KeyError, TypeError, cv2.error) as exc:
                item = {"status": "unavailable", "reason": str(exc)}
            item.update(kind=kind, capture=ident, schema=1, recorded_at=time.time())
            field.write_json(receipt, item)
        pending = policy.available_models() if models is None else models
        if item["status"] == "available":
            if any(not (dest / (sha + ".json")).is_file() for sha in pending):
                checked = load_input(source, kind)
                if any(item.get(k) != value for k, value in checked.items()):
                    raise ValueError("Archived input or extracted features changed before scoring")
            for sha, entry in pending.items():
                path = dest / (sha + ".json")
                if path.exists():
                    continue
                actual, model = policy.verified_model(entry["folder"])
                if actual != sha:
                    raise ValueError("Peer selector changed while scoring")
                value = policy.score(model, item["features"])
                gray = policy.score(model, item["monochrome_features"])
                decision = {
                    "capture": ident,
                    "kind": kind,
                    "phase": phase,
                    "computed_at": time.time(),
                    "model_sha256": actual,
                    "plan_sha256": model["plan_sha256"],
                    "input_sha256": digest(receipt.read_bytes()),
                    "source_rgb_sha256": item["decoded_rgb_sha256"],
                    "features": item["features"],
                    "score": value,
                    "threshold": model["threshold"],
                    "request": value >= model["threshold"],
                    "monochrome_score": gray,
                    "monochrome_request": gray >= model["threshold"],
                    "consumed_by_controller": False,
                }
                field.write_json(path, decision)
        decisions = [read(p) for p in sorted(dest.glob("*.json")) if re.fullmatch("[0-9a-f]{64}", p.stem)]
        if phase == "before_independent_measurement" and not (dest / "seal.json").exists():
            field.write_json(
                dest / "seal.json",
                {
                    "sealed_at": time.time(),
                    "input_sha256": digest(receipt.read_bytes()),
                    "decision_sha256": {
                        d["model_sha256"]: digest((dest / (d["model_sha256"] + ".json")).read_bytes())
                        for d in decisions
                    },
                },
            )
        seal = read(dest / "seal.json") if (dest / "seal.json").exists() else None
        fingerprint = digest(receipt.read_bytes())
        if any(d["input_sha256"] != fingerprint for d in decisions):
            raise ValueError("Shadow input digest differs from a saved decision")
        if seal and (
            seal["input_sha256"] != fingerprint
            or any(
                digest((dest / (sha + ".json")).read_bytes()) != expected
                for sha, expected in seal["decision_sha256"].items()
            )
        ):
            raise ValueError("Pre-measurement shadow receipt changed")
        return {"input": item, "decisions": decisions, "pre_measurement_seal": seal}


def capture_hook(folder, *, before_endpoint=False):
    """Shadow computation cannot delay camera admission, drive the robot or veto a manual score."""

    def compute():
        try:
            record(folder, "series", "before_independent_measurement" if before_endpoint else "initial_capture")
        except Exception:
            LOG.exception("Could not save independent Tank shadow at %s", folder)

    if before_endpoint:
        if (folder / "observation.json").is_file():
            compute()
    else:
        threading.Thread(target=compute, name="tank-field-shadow", daemon=True).start()


def report():
    models = policy.available_models()
    rows = []
    for kind, base, filename in [
        ("series", FIELD, "001-tank/observation.json"),
        ("passive_archive", field.RUNS, "result.json"),
    ]:
        for path in sorted(base.glob("*/" + filename)):
            ident = path.parent.parent.name if kind == "series" else path.parent.name
            if re.fullmatch("[0-9a-f]{32}", ident):
                try:
                    rows.append(record(path.parent, kind, "archive_replay", models))
                except (OSError, ValueError, KeyError, TypeError, cv2.error) as exc:
                    rows.append(
                        {
                            "input": {
                                "status": "unavailable",
                                "reason": str(exc),
                                "kind": kind,
                                "capture": ident,
                            },
                            "decisions": [],
                            "pre_measurement_seal": None,
                        }
                    )
    evidence = read(ROOT / "docs/results/peer-camera-docking/colour-ablation.json")
    return {
        "schema": 1,
        "models": sorted(models),
        "records": rows,
        "training_started": False,
        "motor_commands": 0,
        "scope": "Initial Tank RGB only. The fixed field rule controls both physical conditions. Passive archives have no paired physical endpoint.",
        "detector_contract": "The simulated selector detects single ID 7 with measured Tank CameraInfo. The field docking controller separately requires both IDs 7 and 43 and surveyed map geometry. One executed field condition gives one observed outcome per capture.",
        "timing_rule": "Only model decision digests in the pre-measurement seal precede the independent endpoint. Later archived inferences remain retrospective. No endpoint enters feature extraction.",
        "colour_evidence_source": "docs/results/peer-camera-docking/colour-ablation.json",
        "colour_replay": {
            k: evidence[k]
            for k in (
                "distinct_rgb_inputs",
                "distinct_monochrome_inputs",
                "identical_monochrome_inputs_with_conflicting_branch_labels",
            )
        },
    }
