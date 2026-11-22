"""«Подъехать к …»: prompt translation and the controller, with a fake detector (no camera, no robot)."""
import time

import numpy as np
import pytest

pytest.importorskip('cv2')
from explorer4 import goto


@pytest.fixture(autouse=True)
def isolated_memory(monkeypatch, tmp_path):
    from explorer4 import world_memory
    monkeypatch.setattr(world_memory, 'MEMORY', tmp_path / 'memory.json')
    monkeypatch.setattr(world_memory, 'SNAPSHOTS', tmp_path / 'snap')
    from explorer4 import episodes
    monkeypatch.setattr(episodes, 'ROOT', tmp_path / 'episodes')
    monkeypatch.setattr(world_memory, 'beacons', lambda: {})
    for p in world_memory.POSES.values():
        p.x = p.y = p.theta = None


class FakeDetector:
    def __init__(self, boxes):
        self.boxes = boxes
    def detect(self, rgb, prompt, conf=.35):
        time.sleep(.01)
        return self.boxes, 10.0


def make(monkeypatch, boxes):
    monkeypatch.setattr(goto.Detector, 'shared', classmethod(lambda cls: FakeDetector(boxes)))
    return goto.GoTo('tank', 'к носку')


def drive(g, frames=8):
    rgb = np.zeros((400, 640, 3), np.uint8)
    out = None
    for _ in range(frames):
        out = g.command(rgb)
        time.sleep(.03)
    return out


def test_prompt_translation_any_case():
    assert goto.to_prompt('подъедь к носку') == 'sock'
    assert goto.to_prompt('к красной коробке') == 'red box'
    assert goto.to_prompt('go to the red ball') == 'red ball'


def test_turns_toward_object_on_the_right(monkeypatch):
    g = make(monkeypatch, [[520, 250, 600, 300, .9]])           # right of centre, far
    v, w = drive(g)
    assert w < 0 and v == 0                                       # rotate first (clockwise)
    g.cancel()


def test_drives_forward_when_centred_and_stops_close(monkeypatch):
    g = make(monkeypatch, [[300, 230, 340, 260, .9]])           # centred, bottom edge -> ~1 m
    v, w = drive(g)
    assert v > 0 and abs(w) < .2 and g.state == 'approach'
    assert 0.5 < g.distance < 1.6
    g.detector.boxes = [[290, 330, 350, 398, .9]]               # bottom of frame -> arrived
    time.sleep(.05)
    assert drive(g) == [0., 0.] and g.state == 'arrived' and not g.active


def test_searches_then_gives_up(monkeypatch):
    g = make(monkeypatch, [])
    g.searched = 2 * np.pi + 1
    assert drive(g, 2) == [0., 0.] and g.state == 'not_found'


@pytest.mark.parametrize("failure", ["stale_depth", "missing_scan", "camera", "depth_timeout", "fresh"])
def test_rosmaster_lease_dispatches_only_after_complete_native_observation(monkeypatch, failure):
    from types import SimpleNamespace
    from explorer4 import rosmaster_goto as runner, rosmaster_session, sensors, fleet_map
    commands = []
    goal = SimpleNamespace(active=True, message="", status=lambda: {"message": goal.message})
    def cancel(reason):
        goal.active, goal.message = False, reason
    def command(_rgb):
        goal.active = False
        return .1, 0.
    goal.cancel, goal.command = cancel, command
    now = time.monotonic_ns()
    sample = {"rgb": np.zeros((480, 640, 3), np.uint8), "camera": {"received_ns": now},
              "agent_monotonic_ns": now, "homebrain_received_ns": now, "request_duration_ns": 0,
              "base_measured_age_s": .02}
    if failure == "camera":
        sample["camera"]["received_ns"] -= 600_000_000
    scan_meta = {"age_s": .01, "angle_min": 0., "angle_increment": np.pi / 90, "range_min": .03}
    scan = {"meta": {"streams": {key: scan_meta for key in ("scan", "scan_rear")}},
            "arrays": {key: np.ones(180) for key in ("scan", "scan_rear")}, "received_ns": now, "request_elapsed_s": .01}
    if failure == "missing_scan":
        del scan["arrays"]["scan"]
    def snapshot(only):
        if failure == "depth_timeout":
            raise TimeoutError("depth unavailable")
        return {"meta": {"streams": {"depth": {"age_s": .7 if failure == "stale_depth" else 0., "unit": "m"}}},
                "arrays": {"depth": np.ones((72, 112), np.float32)}, "received_ns": now, "request_elapsed_s": .002}
    http = SimpleNamespace(get=lambda url: SimpleNamespace(json=lambda: {}), close=lambda: None)
    operator = SimpleNamespace(owner=runner.OWNER, lease="offline", input=lambda *args: None,
                               set_direct=lambda direct: commands.append(direct["base"]), stop=lambda message: None)
    monkeypatch.setattr(runner.rosmaster_control, "operator", operator)
    monkeypatch.setattr(runner.rosmaster_control, "connection", lambda _: http)
    monkeypatch.setattr(rosmaster_session, "native_sample", lambda _: sample)
    monkeypatch.setattr(fleet_map, "native_scan_packet", lambda _: scan)
    monkeypatch.setattr(sensors, "SensorClient", lambda **kw: SimpleNamespace(snapshot=snapshot, close=lambda: None))
    instance = runner.RosmasterGoTo()
    instance.goal = goal
    instance._run()
    assert commands[-1] == [0., 0., 0.]
    assert any(any(row) for row in commands) == (failure == "fresh")
    assert failure == "fresh" or goal.message
