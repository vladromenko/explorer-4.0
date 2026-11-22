"""Local or peer RGB measurements for a shared-world docking task."""
import hashlib
import math
import xml.etree.ElementTree as ET

import cv2
import mujoco
import numpy as np

from ..simlab.perception import MarkerDetector
from .tank_model import camera_attributes

from ..peer_dock_config import MARKER_ID, MARKER_SIDE_M, STANDOFF_M, MAX_AGE_S

OPTICAL_TO_MUJOCO = np.diag([1., -1., -1.])


def instrument_dock(root):
    """Add a printable OpenCV marker and body-frame twist sensors to the existing dock XML."""
    target = root.find(".//body[@name='target']")
    ET.SubElement(target, 'geom', name='fiducial_sheet', type='box', pos='-.021 0 0',
                  size='.001 .111 .111', rgba='1 1 1 1', contype='0', conaffinity='0')
    pattern = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), MARKER_ID, 6)
    cell = MARKER_SIDE_M / len(pattern)
    for row, col in np.argwhere(pattern == 0):
        pos = f'-.023 {(2.5-col)*cell} {(2.5-row)*cell}'
        ET.SubElement(target, 'geom', name=f'fiducial_{row}_{col}', type='box', pos=pos,
                      size=f'.0001 {cell / 2} {cell / 2}', rgba='.005 .005 .005 1',
                      contype='0', conaffinity='0')
    base = root.find(".//body[@name='base']")
    ET.SubElement(base, 'site', name='odometry', pos='0 0 0', size='.001', rgba='0 0 0 0')
    sensors = root.find('sensor')
    if sensors is None:
        sensors = ET.SubElement(root, 'sensor')
    ET.SubElement(sensors, 'velocimeter', name='body_velocity', site='odometry')
    ET.SubElement(sensors, 'gyro', name='body_gyro', site='odometry')


def yaw_matrix(yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])


class DockSensors:
    def __init__(self, world, start_xy_yaw):
        self.world = world
        self.odometry = np.asarray(start_xy_yaw, dtype=float).copy()
        tank = world.views['tank'].env
        mount = mujoco.MjData(tank.model)
        mujoco.mj_forward(tank.model, mount)
        camera = mount.camera(tank.camera_name)
        self.tank_mount = (camera.xpos.copy(), camera.xmat.reshape(3, 3).copy() @ OPTICAL_TO_MUJOCO)
        attrs = camera_attributes()
        width, height = map(int, attrs['resolution'].split())
        fx, fy = map(float, attrs['focalpixel'].split())
        ox, oy = map(float, attrs['principalpixel'].split())
        tank_k = [[fx, 0, width / 2 - ox], [0, fy, height / 2 - oy], [0, 0, 1]]
        donor = world.views['rosmaster'].env
        fovy = float(donor.model.camera(donor.camera_name).fovy[0])
        focal = 240 / math.tan(math.radians(fovy / 2))
        self.detectors = {
            'tank': MarkerDetector(tank_k, side=MARKER_SIDE_M, marker_id=MARKER_ID),
            'rosmaster': MarkerDetector([[focal, 0, 320], [0, focal, 240], [0, 0, 1]],
                                        side=MARKER_SIDE_M, marker_id=MARKER_ID),
        }

    def camera_pose(self, robot):
        if robot == 'tank':
            mount, axes = self.tank_mount
            rotation = yaw_matrix(self.odometry[2])
            origin = self.world.views['tank'].origin
            return origin + np.r_[self.odometry[:2], 0.] + rotation @ mount, rotation @ axes
        # FK on the donor's local kinematic model uses the arm encoder angles.
        # Its base is fixed at the surveyed mounting point throughout this task.
        view = self.world.views['rosmaster']
        camera = view.env.data.camera(view.env.camera_name)
        return view.origin + camera.xpos, camera.xmat.reshape(3, 3) @ OPTICAL_TO_MUJOCO

    def packet(self, robot, image):
        detection = self.detectors[robot].detect(cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
        if detection is None:
            return None
        origin, rotation = self.camera_pose(robot)
        centre = origin + rotation @ detection['translation_optical_m']
        if detection['reprojection_error_px'] > 2.5:
            return None
        # This fixture mounts every marker on a surveyed +X wall. Its origin
        # varies between trials. A monocular planar tag has two pose solutions,
        # so using its unconstrained normal as the docking yaw is ambiguous.
        outward = np.array([-1., 0.])
        goal = centre[:2] + STANDOFF_M * outward - self.world.views['tank'].origin[:2]
        return {'source_robot': robot, 'marker_id': MARKER_ID, 'frame': 'tank_start_map',
                'stamp_s': float(self.world.data.time), 'frame_sha256': hashlib.sha256(image.tobytes()).hexdigest(),
                'target_xy_m': goal.tolist(), 'target_yaw_rad': math.atan2(-outward[1], -outward[0]),
                'solved_with': 'OpenCV ArUco/IPPE position, surveyed wall heading and camera mounts',
                'reprojection_error_px': detection['reprojection_error_px'], 'corners_px': detection['corners_px']}

    def integrate(self, dt):
        velocity = self.world.data.sensor('tank/body_velocity').data
        yaw_rate = self.world.data.sensor('tank/body_gyro').data[2]
        mid_yaw = self.odometry[2] + .5 * yaw_rate * dt
        self.odometry[:2] += (yaw_matrix(mid_yaw) @ velocity)[:2] * dt
        self.odometry[2] += yaw_rate * dt

    def action(self, packet):
        delta = np.asarray(packet['target_xy_m']) - self.odometry[:2]
        error = math.atan2(delta[1], delta[0]) - self.odometry[2]
        distance = np.linalg.norm(delta)
        if distance < .035:
            error = packet['target_yaw_rad'] - self.odometry[2]
            speed = 0.
        else:
            speed = min(.18, .9 * distance) * max(0., math.cos(error))
        turn = 2 * math.atan2(math.sin(error), math.cos(error))
        return [speed, np.clip(turn, -.5, .5)]
