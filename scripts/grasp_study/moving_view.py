"""RGB-only floor-plane tracking and bounded Cartesian residuals for the simulated wrist."""

import cv2
import numpy as np
from scipy.linalg import lstsq

from explorer4.sim.vendor_rosmaster.arm_model import ArmModel

SIZE = (160, 120)
# Measured nominal Orbbec focal length, at one quarter of 640 x 480.
K = np.array([[120.1775, 0, 79.5], [0, 120.1775, 59.5], [0, 0, 1]])
PLANE_Z = 0.032  # top of the task's 32 mm cube
MODEL = ArmModel()
MAX_CHANGE = 0.015  # metres per observation


def clipped_delta(value):
    value = np.asarray(value, dtype=float)
    return value * min(1.0, MAX_CHANGE / max(1e-12, np.linalg.norm(value)))


def floor_to_pixel(joints):
    camera = np.linalg.inv(MODEL.camera_pose(joints))
    return K @ np.column_stack((camera[:3, 0], camera[:3, 1], camera[:3, 3] + PLANE_Z * camera[:3, 2]))


def project(transform, point):
    projected = transform @ np.r_[point, 1.0]
    return projected[:2] / projected[2]


class WristTracker:
    """Track the first RGB patch on the cube's top plane, compensating the measured wrist motion."""

    def __init__(self, rgb, joints, first_xy):
        self.first_xy = np.asarray(first_xy, float)
        self.joints = np.asarray(joints, float)
        self.ref = floor_to_pixel(joints)
        self.center = project(self.ref, first_xy)
        self.template = self._patch(cv2.resize(rgb, SIZE, interpolation=cv2.INTER_AREA), 15)

    def _patch(self, img, width):
        return cv2.getRectSubPix(img, (width, width), tuple(self.center.astype(float)))

    def read(self, rgb, joints):
        # The learner receives nominal manufacturer geometry, never the simulator camera perturbation.
        warp = self.ref @ np.linalg.inv(floor_to_pixel(joints))
        small = cv2.resize(rgb, SIZE, interpolation=cv2.INTER_AREA)
        warped = cv2.warpPerspective(small, warp, SIZE)
        mask = cv2.warpPerspective(np.full(small.shape[:2], 255, np.uint8), warp, SIZE)
        search = self._patch(warped, 47)
        scores = cv2.matchTemplate(search, self.template, cv2.TM_CCOEFF_NORMED)
        available = cv2.matchTemplate(
            self._patch(mask, 47).astype(np.float32) / 255, np.ones((15, 15), np.float32), cv2.TM_CCORR
        )
        scores[available < 0.90 * 225] = -2
        _, confidence, _, (px, py) = cv2.minMaxLoc(scores)
        # cv2 pads getRectSubPix at the border; exclude those samples as well.
        within = np.all(self.center >= 23) and np.all(self.center < np.array(SIZE) - 23)
        valid = bool(within and confidence >= 0.45 and np.max(self.template.std(axis=(0, 1))) >= 3.0)
        if not valid:
            return self.first_xy.copy(), False, float(confidence)
        # The central matching window starts at index 16. Convert relative pixel motion into metric XY.
        matched = project(np.linalg.inv(self.ref), self.center + [px - 16, py - 16])
        return matched, True, float(confidence)


def features(tracker, joints, current_xy, observed, confidence, tick):
    return np.r_[
        (observed - current_xy) * 1_000,
        (observed - tracker.first_xy) * 1_000,
        (tracker.first_xy - [0.21, 0]) * 1_000,
        np.asarray(joints[:5]) - tracker.joints[:5],
        confidence,
        tick,
    ]


def fit(rows):
    labelled = [q for scene in rows for q in scene["queries"] if q["tracking_valid"]]
    if len(labelled) < 8:
        return None
    x = np.array([q["feature"] for q in labelled])
    y = np.array([q["expert_delta_m"] for q in labelled])
    center, scale, bias = x.mean(0), x.std(0).clip(1e-6), y.mean(0)
    normalized = (x - center) / scale
    # Tikhonov/ridge least squares, with a fixed penalty and an unpenalized intercept.
    design = np.vstack([normalized, np.eye(x.shape[1])])
    targets = np.vstack([y - bias, np.zeros((x.shape[1], 2))])
    weights = lstsq(design, targets, lapack_driver="gelsd")[0]
    return {
        k: v.tolist() for k, v in {"center": center, "scale": scale, "bias": bias, "weights": weights}.items()
    }


def predict(model, feature):
    return clipped_delta((feature - model["center"]) / model["scale"] @ model["weights"] + model["bias"])
