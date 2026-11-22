"""Drive to a pose on the shared map (e.g. the hand-over spot) along a planned path, then turn to
the taught heading. Same goal interface as GoTo/Explore: command(rgb) -> [v, w]."""
import math
import time

from . import navigation
from .episodes import Episode
from .explore import pose_now
from .fleet_map import FLEET


class DriveTo:
    def __init__(self, robot, pose, *, text='к месту', tol=.10, heading_tol=.08, v_max=.12, w_max=.6,
                 time_limit_s=180, record=False):
        self.robot, self.goal = robot, tuple(pose)
        self.text, self.prompt = text, 'drive'
        self.tol, self.heading_tol, self.v_max, self.w_max = tol, heading_tol, v_max, w_max
        self.time_limit = time_limit_s
        self.started = time.monotonic()
        self.active = True
        self.state, self.message = 'start', f'Еду {text}'
        self.path, self.planned_at = None, 0.
        self.last_cmd = (0., 0.)
        self.distance = None
        self.endpoint = navigation.path_endpoint(self.goal[:2], None)
        self.observed_pose = None
        self.blocked_since = None
        self.aligning = False            # inside the tolerance: turn to the heading (with hysteresis)
        self.episode = Episode(robot, 'drive', text) if record else None

    def set_camera(self, cam):
        pass

    def command(self, rgb):
        if not self.active:
            return [0., 0.]
        cmd = self._command()
        self.last_cmd = (cmd[0], cmd[1])
        if self.episode is not None:
            self.episode.step(pose_now(self.robot, (0., 0.)), cmd, self.state, rgb)
        return cmd

    def _command(self):
        now = time.monotonic()
        if now - self.started > self.time_limit:
            self.finish('timeout', f'Не доехал {self.text} за отведённое время')
            return [0., 0.]
        pose = pose_now(self.robot, self.last_cmd)
        self.observed_pose = pose_now(self.robot, (0., 0.))
        if pose is None:
            self.state, self.message = 'localizing', 'Жду своё место на общей карте…'
            return [0., 0.]
        dist = math.dist(pose[:2], self.goal[:2])
        self.distance = dist
        if dist < self.tol or (self.aligning and dist < 2 * self.tol):
            # turning in place shifts the measured position by a few cm: keep aligning until it
            # really drifts away (2x tolerance), otherwise it alternates drive/turn forever
            self.aligning = True
            err = navigation.wrap(self.goal[2] - pose[2])
            if abs(err) >= self.heading_tol:
                self.state, self.message = 'align', f'Разворачиваюсь {self.text}: {math.degrees(err):+.0f}°'
                return [0., max(-.4, min(.4, 1.2 * err))]
            if dist < self.tol:
                observed = self.observed_pose
                if (observed is not None and math.dist(observed[:2], self.goal[:2]) < self.tol and
                    abs(navigation.wrap(self.goal[2] - observed[2])) < self.heading_tol):
                    self.finish('arrived', f'На месте {self.text}')
                else:
                    self.state, self.message = 'localizing', 'Жду подтверждения исходной цели по локализации'
                return [0., 0.]
        self.aligning = False
        if dist < 3 * self.tol + .1:
            # last centimetres: straight at the point (the planned path may already be «finished»
            # while the robot is still just outside the tolerance)
            b = navigation.wrap(math.atan2(self.goal[1] - pose[1], self.goal[0] - pose[0]) - pose[2])
            if abs(b) > math.pi / 2:                     # just past it: back up a little instead of a U-turn
                b = navigation.wrap(b + math.pi)
                v = -min(.06, .5 * dist + .02)
            else:
                v = min(.06, .5 * dist + .02) if abs(b) < .5 else 0.
            w = max(-.5, min(.5, 1.5 * b))
            v, w, why = navigation.guard(FLEET.scan(self.robot), self.robot, v, w)
            if why:
                self.blocked_since = self.blocked_since or now
                if now - self.blocked_since > 3:
                    self.finish('blocked', f'Цель {self.text} не достигнута: до неё {dist*100:.0f} см. {why}')
                    return [0., 0.]
            else:
                self.blocked_since = None
            self.state = 'blocked' if why else 'drive'
            self.message = f'Объезжаю: {why}' if why else f'Подъезжаю точно {self.text}: {dist * 100:.0f} см'
            return [v, w]
        if self.path is None or now - self.planned_at > 2.:
            self.planned_at = now
            path = navigation.plan(FLEET.grid, self.robot, pose[:2], self.goal[:2], allow_unknown=True)
            self.endpoint = navigation.path_endpoint(self.goal[:2], path)
            if path is None:
                self.finish('no_path', f'Нет пути {self.text} по карте')
                return [0., 0.]
            self.path = path
            FLEET.track.setdefault(self.robot, {})['path'] = list(path)
        v, w, remaining = navigation.follow(pose, self.path, self.v_max, self.w_max, lookahead=min(.12, self.tol))
        if remaining < self.tol:
            if self.endpoint['goal_cell_relocated']:
                self.finish('blocked', f'Конец обходного пути достигнут. До исходной цели {dist*100:.0f} см')
                return [0., 0.]
            v = 0.
        v, w, why = navigation.guard(FLEET.scan(self.robot), self.robot, v, w)
        self.state = 'blocked' if why else 'drive'
        self.message = f'Объезжаю: {why}' if why else f'Еду {self.text}: {remaining:.1f} м'
        return [v, w]

    def finish(self, state, message):
        self.state, self.message, self.active = state, self.route_message(message), False
        FLEET.track.setdefault(self.robot, {})['path'] = None
        if self.episode is not None:
            self.episode.extra.update(planner_endpoint=self.endpoint, requested_pose=self.goal,
                                      last_observed_pose=self.observed_pose, position_tolerance_m=self.tol,
                                      yaw_tolerance_rad=self.heading_tol)
            self.episode.finish(state, self.message)

    def cancel(self, reason='Отменено'):
        if self.active:
            self.finish('cancelled', reason)

    def route_message(self, message):
        if self.endpoint['goal_cell_relocated']:
            x, y = self.goal[:2]
            px, py = self.endpoint['planned_xy_m']
            return f'{message} · цель ({x:.2f}, {y:.2f}) м, конец маршрута ({px:.2f}, {py:.2f}) м'
        return message

    def status(self):
        message = self.route_message(self.message) if self.active else self.message
        return {'state': self.state, 'message': message, 'prompt': self.prompt, 'active': self.active,
                'planner_endpoint': self.endpoint, 'requested_pose': self.goal, 'last_observed_pose': self.observed_pose,
                'distance': self.distance, 'bearing': None, 'box': None, 'score': None, 'detect_ms': None}
