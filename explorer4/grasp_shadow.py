"""Archive-only ROSMASTER action provider for compiled RGB-conditioned skills."""

from pathlib import Path

import numpy as np
from scipy.interpolate import RBFInterpolator
from scipy.spatial import Delaunay
from scipy.spatial.transform import Rotation

from .conditioned_grasp import (
    LOOK_COMMAND,
    MOTOR_SHA256,
    SLEW_DEGREES_PER_SECOND,
    VISION_SHA256,
    TrajectoryPolicy,
    file_hash,
    load_localizer,
    locate_cube,
)
from .sim.vendor_rosmaster.arm_model import SERVO_LIMITS, ArmModel


def close_to_look_state(state):
    # One 20 Hz slew interval is the allowed mismatch from the fixed starting posture.
    return bool(np.all(np.abs(np.asarray(state) - LOOK_COMMAND) <= SLEW_DEGREES_PER_SECOND / 20))


def look_distance(state):
    """Camera translation (m) and rotation (deg) relative to the study look pose."""
    arm = ArmModel()
    camera = arm.camera_pose(state)
    reference = arm.camera_pose(LOOK_COMMAND)
    rotation = Rotation.from_matrix(reference[:3, :3].T @ camera[:3, :3]).magnitude()
    return float(np.linalg.norm(reference[:3, 3] - camera[:3, 3])), float(np.rad2deg(rotation))


class ArchiveGraspActions:
    """Match ReplayActions.next/reset without acquiring a robot or sending commands.

    A caller provides a measured, camera-specific calibration and its individual
    reference-frame errors. A replay should retain the reason when we abstain.
    """

    input_domain = "archived_real"

    def __init__(self, bundle, source, vision, method, calibration, *, localizer=None):
        import json

        if file_hash(source) != MOTOR_SHA256 or file_hash(vision) != VISION_SHA256:
            raise ValueError("Planner training data or RGB weights changed")
        self.calibration = calibration
        self.method = method
        self.localizer = load_localizer(vision) if localizer is None else localizer
        with np.load(source, allow_pickle=False) as bank:
            xy, actions = bank["xy"], bank["action"]
        self.support = Delaunay(xy)
        if method == "rbf":
            self.rbf = RBFInterpolator(xy / 0.05, actions, smoothing=0.005, kernel="thin_plate_spline")
        elif method in ("act", "diffusion"):
            root = Path(bundle)
            metrics = json.loads((root / f"{method}-training.json").read_text())
            if (
                metrics["source_sha256"] != MOTOR_SHA256
                or metrics["weights_sha256"] != file_hash(root / method / "model.safetensors")
                or metrics["decoder_sha256"] != file_hash(root / "decoder.npz")
            ):
                raise ValueError("Unverified motor bundle")
            self.planner = TrajectoryPolicy(root, method)
        else:
            raise ValueError("Unknown archive planner")
        self.reset()

    def reset(self):
        self.plan = None
        self.index = 0
        self.last = None
        self.clipped_steps = 0
        self.max_projection_deg = np.zeros(6)

    def next(self, observation):
        if observation.get("domain") != self.input_domain or observation.get("robot_id") != "rosmaster":
            raise ValueError("This action provider requires its verified ROSMASTER observation domain")
        state = np.asarray(observation["observation.state"], dtype=float)
        if state.shape != (6,) or not np.isfinite(state).all():
            raise ValueError("Incomplete native six-servo state")
        if self.plan is None:
            self._start(observation, state)
        if self.index >= len(self.plan):
            raise StopIteration
        self.last += np.clip(
            self.plan[self.index] - self.last, -SLEW_DEGREES_PER_SECOND / 20, SLEW_DEGREES_PER_SECOND / 20
        )
        self.index += 1
        # MuJoCo clips the slew-limited target in SO101PickPlace.prepare_action.
        # Apply the documented native limits here, preserving the same pre-clip
        # slew state. Report every correction for offline physical review.
        lower, upper = np.asarray(SERVO_LIMITS).T
        bounded = np.clip(self.last, lower, upper)
        delta = np.abs(bounded - self.last)
        if np.any(delta > 1e-6):
            self.clipped_steps += 1
            self.max_projection_deg = np.maximum(self.max_projection_deg, delta)
        return bounded.tolist()

    def _start(self, observation, state):
        proof = self.calibration
        if (
            proof is None
            or not proof.get("device_id")
            or proof["device_id"] != observation.get("device_id")
            or proof["camera_calibration_sha256"] != observation.get("camera_calibration_sha256")
        ):
            raise ValueError("The archived camera lacks a matching localization calibration")
        position, angle = look_distance(state)
        if position > 0.02 or angle > 5 or not close_to_look_state(state):
            raise ValueError("Camera pose differs from the trained look window")
        image = np.asarray(observation["images"]["front"])
        if image.shape != (480, 640, 3):
            raise ValueError("Expected native 640 by 480 RGB")
        box = observation.get("confirmed_cube_bbox_xyxy_px")
        if box is None or len(box) != 4 or not 0 < box[0] < box[2] < 640 or not 0 < box[1] < box[3] < 480:
            raise ValueError("A full initial target inside the recorded image is required")
        xy = self.locate(observation, image)
        if self.support.find_simplex(xy) < 0:
            raise ValueError("Predicted cube is outside the motor demonstration hull")
        self.plan = self.rbf(xy[None] / 0.05)[0] if self.method == "rbf" else self.planner.trajectory(xy)
        self.last = state.copy()

    def locate(self, observation, image):
        return locate_cube(self.localizer, image)
