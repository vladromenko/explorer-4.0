"""Room inventory while driving: every robot's camera frames go through SAM 3 with a list of
household objects (configs/inventory.yaml, several prompts per vision pass). Everything found is
written to the shared fleet memory with its room position, so «принеси печенье» already knows
where the cookie is. Runs in the background next to any task; never commands motion."""
import threading
import time

import yaml

from .paths import ROOT
from . import world_memory

DEFAULT = [('cookie', 'печенье'), ('cup', 'кружка'), ('bottle', 'бутылка'), ('sock', 'носок'), ('shoe', 'обувь'),
           ('toy', 'игрушка'), ('box', 'коробка'), ('cube', 'кубик')]


def inventory():
    """[(prompt, russian name)]"""
    try:
        items = yaml.safe_load((ROOT / 'configs' / 'inventory.yaml').read_text()).get('objects') or []
        out = [(str(i['prompt']), str(i.get('name') or i['prompt'])) for i in items if i.get('prompt')]
        return out or DEFAULT
    except (OSError, ValueError, AttributeError, TypeError):
        return DEFAULT


class Scout:
    """Feed frames with feed(rgb); a background thread inventories the newest one."""

    BATCH = 6               # prompts per vision pass (~2.3 s on the Orin)

    def __init__(self, robot, cam=None, priority=None, on_found=None, min_score=.5):
        from .goto import CAMERAS, Detector
        self.robot = robot
        self.cam = dict(cam or CAMERAS[robot])
        self.priority = priority            # prompt checked on every pass (the thing being searched for)
        self.on_found = on_found
        self.min_score = min_score
        self.items = inventory()
        self.names = dict(self.items)
        self.cursor = 0
        self.frame = None
        self.frame_at = 0.
        self.frame_context = None
        self.last_source = None
        self.seen = {}                       # prompt -> last record time
        self.found = []                      # (prompt, item) found during this run
        self.passes = 0
        self.error = None
        self.detector = Detector.shared()
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, daemon=True, name=f'scout-{robot}')
        self.thread.start()

    def set_camera(self, cam):
        with self.lock:
            self.cam = dict(cam)

    def feed(self, rgb, *, camera_info=None, received_monotonic_ns=None):
        """Keep the transport's clocks distinct from the SAM worker's processing time."""
        if rgb is None:
            return
        info = camera_info or {}
        if info.get("reused") or info.get("source_clock") == "missing":
            return
        stamp = info.get("source_timestamp_ns")
        source_clock = info.get("source_clock")
        stamp = stamp if type(stamp) is int and stamp > 0 and source_clock else None
        sequence = info.get("sequence")
        exposure = (
            (info.get("boot_id"), sequence, stamp) if sequence is not None or stamp is not None else None
        )
        with self.lock:
            if exposure is not None and exposure == self.last_source:
                return
            self.last_source = exposure
            mono = time.monotonic_ns()
            wall = time.time_ns()
            receipt = mono if received_monotonic_ns is None else received_monotonic_ns
            if not 0 < receipt <= mono:
                raise ValueError("Invalid Homebrain monotonic receipt")
            camera = self.cam.copy()
            pose = world_memory.POSES[self.robot]
            self.frame_context = (
                camera,
                {
                    "received_timestamp_ns": receipt,
                    "receipt_clock": "homebrain_monotonic",
                    "receipt_wall_estimate_ns": wall - (mono - receipt),
                    "timing_basis": "scout_intake" if received_monotonic_ns is None else "transport_receipt",
                    "source_timestamp_ns": stamp,
                    "source_clock": source_clock,
                    "sequence": sequence,
                    "boot_id": info.get("boot_id"),
                    "optical_frame": info.get("frame_id"),
                    "agent_received_ns": info.get("agent_receive_timestamp_ns", info.get("received_ns")),
                    "camera_model": camera,
                    "camera_model_sha256": world_memory.digest(camera),
                    "source_arm_native": info.get("arm_measured"),
                    "source_arm_received_ns": info.get("arm_received_ns"),
                    "image_shape": list(rgb.shape),
                    "calibration_sha256": info.get("calibration_sha256"),
                    "pose_at": "scout_intake",
                    "pose": pose.as_dict() if pose.known() else None,
                },
            )
            self.frame, self.frame_at = rgb, mono / 1e9

    def stop(self):
        self.done.set()

    def next_prompts(self):
        prompts = [p for p, _ in self.items]
        batch = []
        if self.priority:
            batch.append(self.priority)
        while len(batch) < min(self.BATCH, len(prompts) + (1 if self.priority else 0)):
            p = prompts[self.cursor % len(prompts)]
            self.cursor += 1
            if p not in batch:
                batch.append(p)
        return batch

    def _run(self):
        while not self.done.is_set():
            with self.lock:
                frame, at, context = self.frame, self.frame_at, self.frame_context
                self.frame = None
            if frame is None or time.monotonic() - at > 1.5:
                self.done.wait(.1)
            else:
                self._inventory_frame(frame, context)

    def _inventory_frame(self, frame, context):
        try:
            results, _ = self.detector.detect_many(frame, self.next_prompts(), conf=self.min_score)
            self.error = None
        except Exception as exc:
            self.error = str(exc)
            self.done.wait(2)
            return
        self.passes += 1
        for prompt, boxes in results.items():
            boxes = [b for b in boxes if b[4] >= self.min_score]
            ready = time.monotonic() - self.seen.get(prompt, 0) >= 4 or prompt == self.priority
            if boxes and ready:
                camera, info = context
                name = self.names.get(prompt, prompt)
                try:
                    item = world_memory.record_boxes(self.robot, 'к ' + name, prompt, boxes, frame, camera, info)
                    if item:
                        self.seen[prompt] = time.monotonic()
                        self.found.append((prompt, item))
                        if self.on_found is not None:
                            self.on_found(self.robot, prompt, item)
                except Exception as exc:
                    self.error = str(exc)
