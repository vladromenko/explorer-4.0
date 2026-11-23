"""Shared world memory for the fleet: what was seen, by whom, when and — when the robot knows
where it is — where in the room. Room frame comes from printed ArUco «beacons» on the walls
(configs/room_beacons.yaml); between beacon sightings each robot dead-reckons (ROSMASTER from
wheel odometry, Tank from its own commands). One robot's sighting becomes another robot's goal.
"""
import hashlib
import json
import math
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

from .paths import DATA, ROOT
from .sighting_identity import bind_cube, digest
from .so101_geometry import configuration as registered_object

LOCK = threading.Lock()
MEMORY = DATA / 'world' / 'memory.json'
LISTENERS = []                     # called with every new sighting
SNAPSHOTS = DATA / 'world' / 'snapshots'


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


# ------------------------------------------------------------------ beacons and robot poses
def beacons():
    """{id: {'x','y','z','facing'}} — facing = direction the printed side looks (radians, room frame)."""
    path = ROOT / 'configs' / 'room_beacons.yaml'
    try:
        value = yaml.safe_load(path.read_text()) or {}
    except OSError:
        return {}
    out = {}
    for item in value.get('beacons') or []:
        try:
            out[int(item['id'])] = {'x': float(item['x']), 'y': float(item['y']), 'z': float(item.get('z', .3)),
                                    'facing': math.radians(float(item['facing_deg'])), 'side': float(item.get('side', .20))}
        except (KeyError, TypeError, ValueError):
            continue
    return out


class Pose:
    """Robot pose in the room frame: beacon fixes + dead reckoning between them."""

    def __init__(self, robot):
        self.robot = robot
        self.x = self.y = self.theta = None
        self.fixed_at = None
        self.source = 'unknown'
        self.frame_id = None
        self.drift_m = 0.

    def known(self):
        return self.x is not None

    def fix(self, x, y, theta, source='beacon', *, frame_id=None):
        self.frame_id = frame_id or ('beacon_room:' + digest(beacons()) if source == 'beacon' else None)
        self.x, self.y, self.theta = x, y, theta
        self.fixed_at, self.source, self.drift_m = time.time(), source, 0.

    def move(self, vx, vy, w, dt):
        if not self.known():
            return
        c, s = math.cos(self.theta), math.sin(self.theta)
        self.x += (c * vx - s * vy) * dt
        self.y += (s * vx + c * vy) * dt
        self.theta = wrap(self.theta + w * dt)
        self.drift_m += math.hypot(vx, vy) * dt * .1 + abs(w) * dt * .05
        self.source = 'dead_reckoning'

    def as_dict(self):
        return {'robot': self.robot, 'x': self.x, 'y': self.y, 'theta': self.theta, 'source': self.source,
                'fixed_at': self.fixed_at, 'frame_id': self.frame_id, 'drift_m': round(self.drift_m, 2)}


POSES = {'tank': Pose('tank'), 'rosmaster': Pose('rosmaster')}


class BeaconLocalizer:
    """Every ArUco beacon in view gives the camera pose; the robot centre follows from the
    camera mounting (same camera dicts as explorer4.goto)."""

    def __init__(self):
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self.detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), params)

    def locate(self, rgb, cam):
        table = beacons()
        if not table:
            return None
        corners, ids, _ = self.detector.detectMarkers(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
        if ids is None:
            return None
        K = np.array([[cam['fx'], 0, cam['cx']], [0, cam['fy'], cam['cy']], [0, 0, 1.]])
        fixes = []
        for c, i in zip(corners, ids.ravel()):
            b = table.get(int(i))
            if b is None:
                continue
            h = b['side'] / 2
            obj = np.array([[-h, h, 0], [h, h, 0], [h, -h, 0], [-h, -h, 0]], dtype=np.float64)
            n, rvecs, tvecs, errs = cv2.solvePnPGeneric(obj, c.reshape(4, 2).astype(np.float64), K, np.zeros(5),
                                                        flags=cv2.SOLVEPNP_IPPE_SQUARE)
            if not n:
                continue
            best = None
            for rvec, tvec, err in zip(rvecs, tvecs, np.ravel(errs)):
                R, _ = cv2.Rodrigues(rvec)
                into = -R[:, 2]
                score = abs(into[1]) + (0. if into @ tvec.ravel() > 0 else 10.) + .01 * float(err)
                if best is None or score < best[0]:
                    best = (score, R, tvec.ravel())
            _, R, t = best
            into = -R[:, 2]
            d = math.hypot(t[0], t[2])                     # camera -> beacon, ground plane
            bearing_cam = math.atan2(-t[0], t[2])           # beacon left of the optical axis = +
            facing_into_cam = math.atan2(-into[0], into[2])  # direction into the wall, camera frame
            # Room frame: «into the wall» is facing + pi. Camera heading follows.
            cam_heading = wrap(b['facing'] + math.pi - facing_into_cam)
            cx = b['x'] - d * math.cos(cam_heading + bearing_cam)
            cy = b['y'] - d * math.sin(cam_heading + bearing_cam)
            theta = wrap(cam_heading - cam.get('yaw', 0.))
            x = cx - (cam['forward'] * math.cos(theta) - cam.get('lateral', 0.) * math.sin(theta))
            y = cy - (cam['forward'] * math.sin(theta) + cam.get('lateral', 0.) * math.cos(theta))
            fixes.append((d, x, y, theta, int(i)))
        if not fixes:
            return None
        d, x, y, theta, beacon = min(fixes)                  # the closest beacon is the most accurate
        return {'x': x, 'y': y, 'theta': theta, 'beacon': beacon, 'distance': d}


# ------------------------------------------------------------------ object memory
def _load():
    try:
        return json.loads(MEMORY.read_text())
    except (OSError, ValueError):
        return []


def _save(items):
    MEMORY.parent.mkdir(parents=True, exist_ok=True)
    tmp = MEMORY.with_suffix('.tmp')
    tmp.write_text(json.dumps(items[-500:], ensure_ascii=False, indent=1))
    tmp.replace(MEMORY)


def record_boxes(robot, text, prompt, boxes, rgb, camera, frame):
    """Keep the highest score for ordinary scouting and the independently identified box for named lookup."""
    from .goto import ground_geometry

    if not len(boxes):
        return None
    top = max(range(len(boxes)), key=lambda index: boxes[index][4])
    match = bind_cube(rgb, prompt, boxes)
    selected = [top] if match is None or match[0] == top else [top, match[0]]
    best = None
    for index in selected:
        box = boxes[index]
        distance, bearing, _ = ground_geometry(camera, box[:4], rgb.shape[0])
        binding = match[1] if match and match[0] == index else None
        metric_available = math.isfinite(distance) and distance <= 5
        if metric_available or binding:
            item = _record(
                robot,
                text,
                prompt,
                distance if metric_available else None,
                bearing,
                rgb,
                box[:4],
                box[4],
                frame,
                binding,
            )
            if index == top and metric_available:
                best = item
    return best


def record(robot, text, prompt, distance, bearing, rgb=None, box=None, score=None):
    return _record(robot, text, prompt, distance, bearing, rgb, box, score, None, None)


def _record(robot, text, prompt, distance, bearing, rgb, box, score, frame, identity):
    """Save the observation with the pose and receipt time of its input frame."""
    captured = time.time_ns()
    if frame is None:
        frame = {
            "received_timestamp_ns": captured,
            "timing_basis": "world_memory_record",
            "pose": POSES[robot].as_dict() if POSES[robot].known() else None,
        }
    pose = frame["pose"]
    at = frame.get("receipt_wall_estimate_ns", frame["received_timestamp_ns"]) / 1e9
    bounds = None if box is None else [float(v) for v in box[:4]]
    item = {
        "at": at,
        "recorded_at": captured / 1e9,
        "robot": robot,
        "text": text,
        "prompt": prompt,
        "distance": round(distance, 2) if distance is not None else None,
        "bearing": round(bearing, 3),
        "bbox_xyxy_px": bounds,
        "score": None if score is None else round(float(score), 2),
        "room_xy": None,
        "robot_pose": pose,
        "frame_id": (pose or {}).get("frame_id"),
        "observation": {k: v for k, v in frame.items() if k != "pose"},
        "object_instance": None,
    }
    if pose and pose["x"] is not None and distance is not None:
        a = pose["theta"] + bearing
        item["room_xy"] = [
            round(pose["x"] + distance * math.cos(a), 2),
            round(pose["y"] + distance * math.sin(a), 2),
        ]
        item["uncertainty_m"] = round(0.05 + 0.1 * distance + pose["drift_m"], 2)
        item["uncertainty_source"] = "nominal range and drift heuristic"
        item["measured_error_bound_m"] = None
    if rgb is not None:
        raw_sha = hashlib.sha256(np.ascontiguousarray(rgb)).hexdigest()
        item["observation"]["rgb_sha256"] = raw_sha
        if identity is not None:
            if identity["rgb_sha256"] != raw_sha or identity["box_xyxy_px"] != bounds:
                raise ValueError("Marker, detected box and image must refer to the same observation")
            item["identity"] = identity
            item["object_instance"] = identity["instance_id"]
        item["sample_id"] = digest([robot, prompt, frame["received_timestamp_ns"], raw_sha, bounds])
        SNAPSHOTS.mkdir(parents=True, exist_ok=True)
        name = item["sample_id"] + (".png" if identity else ".jpg")
        img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        if bounds is not None and identity is None:
            x1, y1, x2, y2 = [int(v) for v in bounds]
            cv2.rectangle(img, (x1, y1), (x2, y2), (120, 230, 180), 3)
        if not cv2.imwrite(str(SNAPSHOTS / name), img):
            raise OSError(f"Could not save sighting image {name}")
        item["snapshot"] = name
        item["snapshot_sha256"] = hashlib.sha256((SNAPSHOTS / name).read_bytes()).hexdigest()
    with LOCK:
        items = _load()
        items.append(item)
        _save(items)
    for listener in list(LISTENERS):  # e.g. the swarm's SceneObserver (evidence records)
        try:
            listener(item)
        except Exception:
            pass
    return item


def known_objects(max_age_s=3600, *, frame_id=None):
    """Latest sighting per class and verified instance in the requested map."""
    latest = {}
    now = time.time()
    for item in _load():
        age = now - item["at"]
        if 0 <= age <= max_age_s and (frame_id is None or item.get("frame_id") == frame_id):
            key = (item["prompt"], item.get("object_instance"))
            prior = latest.get(key)
            if prior is None or item["at"] > prior["at"] or (item["room_xy"] and not prior["room_xy"]):
                latest[key] = item
    return sorted(latest.values(), key=lambda i: -i["at"])


def forget(prompt=None):
    with LOCK:
        _save([] if prompt is None else [i for i in _load() if i["prompt"] != prompt])


def recent_instance(robot, prompt, instance, max_age_s):
    """Only the recipient's latest class observation can establish current single-frame identity."""
    now = time.time()
    recent = [
        item
        for item in _load()
        if item["robot"] == robot and item["prompt"] == prompt and 0 <= now - item["at"] <= max_age_s
    ]
    if not recent:
        return None

    def receipt_ns(item):
        evidence = item.get("observation") or {}
        return evidence.get("receipt_wall_estimate_ns", int(item["at"] * 1e9))

    last = max(map(receipt_ns, recent))
    registration = digest(registered_object())
    for item in recent:
        proof = item.get("identity") or {}
        if (
            receipt_ns(item) == last
            and item.get("object_instance") == instance
            and proof.get("source") == "unique_registered_tag_in_one_detected_box"
            and proof.get("registration_sha256") == registration
            and proof.get("rgb_sha256") == (item.get("observation") or {}).get("rgb_sha256")
        ):
            snapshot = SNAPSHOTS / (item.get("snapshot") or "")
            if snapshot.is_file() and hashlib.sha256(snapshot.read_bytes()).hexdigest() == item.get(
                "snapshot_sha256"
            ):
                return item
    return None


def target_for(robot, prompt, max_age_s=3600, *, object_instance=None):
    """Find a compatible mapped observation. A named request requires matching recipient pixels."""
    current = POSES.get(robot)
    frame = current.frame_id if current and current.known() else None
    if object_instance:
        item = recent_instance(robot, prompt, object_instance, max_age_s)
        return item if item and frame and item.get("frame_id") == frame and item["room_xy"] else None
    for item in known_objects(max_age_s, frame_id=frame):
        if item["prompt"] == prompt and item["room_xy"]:
            return item
    return None
