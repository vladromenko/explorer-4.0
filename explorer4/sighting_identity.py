"""Bind the registered cube ID to a unique detection in the recipient's own image."""

import hashlib
import json

import cv2
import numpy as np

from .so101_geometry import MARKERS, configuration


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def bind_cube(rgb, prompt, boxes):
    """Return the matching box index and its pixel evidence, or None for ambiguity."""
    if prompt != "cube" or not len(boxes):
        return None
    card = configuration()
    dictionary, marker_id = card.get("marker_dictionary", "DICT_4X4_50"), card.get("marker_id")
    if (
        not card.get("enabled")
        or card.get("object_class") != prompt
        or not card.get("instance_id")
        or dictionary not in MARKERS
        or type(marker_id) is not int
    ):
        return None
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary)))
    corners, ids, _ = detector.detectMarkers(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    if ids is None or np.count_nonzero(ids == marker_id) != 1:
        return None
    polygon = corners[np.flatnonzero(ids.ravel() == marker_id)[0]].reshape(4, 2)
    owners = [
        i
        for i, box in enumerate(boxes)
        if np.all(polygon >= np.asarray(box[:2])) and np.all(polygon < np.asarray(box[2:4]))
    ]
    if len(owners) != 1:
        return None
    index = owners[0]
    return index, {
        "instance_id": card["instance_id"],
        "source": "unique_registered_tag_in_one_detected_box",
        "dictionary": dictionary,
        "marker_id": marker_id,
        "corners_px": polygon.tolist(),
        "box_xyxy_px": np.asarray(boxes[index][:4]).astype(float).tolist(),
        "rgb_sha256": hashlib.sha256(np.ascontiguousarray(rgb)).hexdigest(),
        "registration_sha256": digest(card),
    }
