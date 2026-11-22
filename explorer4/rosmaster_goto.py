"""«Подъехать к …» on ROSMASTER: the same controller as Tank (explorer4.goto), driving the base
through the existing leased operator session with source='policy' (agent clamps and STOP
apply). The camera is on the arm, so its pose is recomputed from the measured servos."""
import threading
import time

import numpy as np

from . import rosmaster_control
from .goto import GoTo, rosmaster_camera
from .sensors import stream_age

OWNER = 'goto'


class RosmasterGoTo:
    def __init__(self):
        self.goal = None
        self.thread = None
        self.error = None
        self.stop_event = threading.Event()

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def status(self):
        if self.goal is None:
            return {'message': self.error or '', 'active': False}
        return {**self.goal.status(), 'message': self.error or self.goal.status()['message']}

    def start(self, text=None, task=None):
        """text: «подъехать к …»; task: any goal object with command(rgb) (e.g. explore.Explore)."""
        operator = rosmaster_control.operator
        if self.running():
            raise RuntimeError('ROSMASTER уже выполняет задание')
        if operator.lease:
            raise RuntimeError('Сначала выключите ручное управление ROSMASTER (STOP в его панели)')
        rosmaster_control.ensure_agent()
        goal = task if task is not None else GoTo('rosmaster', text)
        operator.input(OWNER, rosmaster_control.ZERO)
        try:
            operator.enable(OWNER, 'rosmaster_dock', 'cartesian', True, source='policy')
        except Exception:
            goal.cancel('Не удалось включить управление')
            raise
        self.goal, self.error = goal, None
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return goal

    def cancel(self, reason='Отменено оператором'):
        self.stop_event.set()
        if self.goal is not None:
            self.goal.cancel(reason)

    def _run(self):
        operator, goal = rosmaster_control.operator, self.goal
        lease = operator.lease
        client = None
        last_health = 0.
        slide_end = 0.
        slide_direction = 0
        blocked_since = None
        last_cmd = (0., 0.)
        from .sensors import SensorClient
        from .fleet_map import native_scan_packet, scan_points
        from .rosmaster_session import base_hold_reason, native_sample
        sensors = None
        alive = threading.Event()

        def heartbeat():
            # The session watchdog needs a sign of life every <3 s. The control loop can stall (the
            # first SAM 3 load takes ~20 s): direct commands then expire after 0.3 s and the base
            # stands still, but the session is kept.
            while not alive.wait(.1):
                operator.input(OWNER, rosmaster_control.ZERO)
        threading.Thread(target=heartbeat, daemon=True, name='rosmaster-goto-heartbeat').start()
        try:
            sensors = SensorClient(robot="rosmaster")
            client = rosmaster_control.connection(1)
            while goal.active and not self.stop_event.is_set():
                started = time.monotonic()
                operator.input(OWNER, rosmaster_control.ZERO)          # keeps the session alive
                if operator.owner != OWNER or not operator.lease:
                    goal.cancel(operator.error or 'Сессия ROSMASTER завершена')
                    break
                if started - last_health > 1.:
                    health = client.get('/health').json()
                    last_health = started
                    st = health.get('status') or {}
                    pinned = bool(st.get('guard')) and not any(abs(v) > 1e-3 for v in (st.get('base_command') or [0.]))
                    blocked_since = (blocked_since or started) if pinned and any(abs(v) > 1e-3 for v in last_cmd) else None
                    if blocked_since is not None and started - blocked_since > 2.:
                        slide_direction = None
                        slide_end = started + 1.5
                        blocked_since = None
                sample = native_sample(client)
                packet = sensors.snapshot(only=["depth"])
                scan_packet = native_scan_packet(client)
                camera_on_arm = hasattr(goal, 'set_camera')
                reason = base_hold_reason(sample, scan_packet, camera_on_arm=camera_on_arm)
                if reason:
                    goal.cancel(reason)
                    break
                rgb = sample["rgb"]
                if camera_on_arm:
                    goal.set_camera(rosmaster_camera(sample["arm_measured"]))
                depth_m = metric_depth(packet)
                near = front_clearance(depth_m) if depth_m is not None else None
                if near is None:
                    goal.cancel('Нет достоверного расстояния перед камерой')
                    break
                goal.depth = (time.monotonic(), depth_m)
                goal.depth_rgb_size = (rgb.shape[1], rgb.shape[0])
                scan = scan_points('rosmaster', scan_packet)
                if slide_direction is None:
                    slide_direction = slide_side(scan)
                if started < slide_end and slide_direction:
                    dx, dy, yaw = 0., .08 * slide_direction, 0.
                else:
                    dx, yaw = goal.command(rgb)
                    dy = 0.
                reason = base_hold_reason(sample, scan_packet, camera_on_arm=camera_on_arm)
                if reason or not 0 <= stream_age(packet, "depth") <= .5:
                    goal.cancel(reason or 'Нет свежей глубины ROSMASTER')
                    break
                if dy and slide_side(scan) != slide_direction:
                    dy, slide_end = 0., 0.
                if near < CAMERA_STOP_M and dx > 0:
                    dx = 0.
                    goal.message = f'Перед камерой препятствие в {near:.2f} м'
                last_cmd = (dx, yaw)
                with operator.lock:
                    if operator.owner != OWNER or operator.lease != lease or self.stop_event.is_set() or not goal.active:
                        break
                    operator.set_direct({'base': [float(dx), float(dy), float(yaw)]})
                time.sleep(max(0., 1 / 15 - (time.monotonic() - started)))
        except Exception as exc:
            self.error = 'ROSMASTER: ' + str(exc)
            goal.cancel(self.error)
        finally:
            alive.set()
            with operator.lock:
                if operator.owner == OWNER and operator.lease == lease:
                    operator.set_direct({'base': [0., 0., 0.]})
            if sensors is not None:
                sensors.close()
            if client is not None:
                client.close()
            if operator.owner == OWNER and operator.lease == lease:
                operator.stop('Подъезд завершён: ' + goal.status()['message'])


CAMERA_STOP_M = .30


def metric_depth(packet):
    depth = packet['arrays'].get('depth')
    if depth is None or depth.ndim != 2:
        return None
    unit = packet["meta"]["streams"]["depth"].get("unit")
    if depth.dtype.kind == "u" and depth.dtype.itemsize == 2 and unit == "mm":
        return depth.astype(np.float32) / 1000.
    if depth.dtype.kind == "f" and unit == "m":
        return depth
    return None


def front_clearance(depth_m):
    """Nearest surface in the central part of the arm camera view (3rd percentile: a small near
    object still counts, single noisy pixels do not), metres."""
    h, w = depth_m.shape
    centre = depth_m[h // 4: 3 * h // 4, w // 4: 3 * w // 4]
    valid = centre[(centre > .05) & (centre < 4.)]
    return float(np.percentile(valid, 3)) if valid.size > 200 else None


def slide_side(points, reach=.35):
    """+1 = slide left, -1 = right: away from the side with the nearest returns beside the body."""
    if points is None or len(points) == 0:
        return 0
    near = points[(np.abs(points[:, 0]) < reach) & (np.abs(points[:, 1]) < reach)]
    if len(near) == 0:
        return 0
    left = near[near[:, 1] > 0]
    right = near[near[:, 1] < 0]
    dl = float(np.abs(left[:, 1]).min()) if len(left) else 9.
    dr = float(np.abs(right[:, 1]).min()) if len(right) else 9.
    return 1 if dr < dl else -1


runner = RosmasterGoTo()
