"""One warmed grasp-localization worker with its own PyTorch CUDA precision settings."""
import atexit
import socket
import subprocess
import sys
import threading

import numpy as np

from .paths import ROOT, offline_environment

SHAPE = (1, 120, 160, 3)
INPUT_BYTES = int(np.prod(SHAPE)) * 4
_LOCK = threading.Lock()
_worker = None


class FieldLocalizer:
    def __init__(self):
        self.lock = threading.Lock()
        self.socket, child = socket.socketpair()
        try:
            self.process = subprocess.Popen(
                [sys.executable, "-m", "explorer4.grasp_localizer", str(child.fileno())],
                pass_fds=(child.fileno(),), cwd=ROOT, env=offline_environment(),
            )
        except BaseException:
            self.socket.close()
            raise
        finally:
            child.close()
        try:
            self.socket.settimeout(60)
            if self.socket.recv(1) != b"R":
                raise RuntimeError("CUDA-локализатор не прошёл прогрев FP32")
            self.socket.settimeout(1)
        except BaseException:
            self.close()
            raise

    def __call__(self, pixels):
        import torch

        if pixels.shape != (1, 3, 120, 160) or pixels.dtype != torch.float32 or pixels.device.type != "cpu":
            raise ValueError("Expected one normalized CPU FP32 wrist image")
        # The original preprocessing lays pixels out in RGB (channels-last) order.
        frame = pixels.permute(0, 2, 3, 1).contiguous().numpy()
        with self.lock:
            try:
                self.socket.sendall(frame.data)
                reply = bytearray()
                while len(reply) < 8:
                    part = self.socket.recv(8 - len(reply))
                    if not part:
                        raise RuntimeError("CUDA-локализатор завершился без координат")
                    reply.extend(part)
            except (OSError, RuntimeError):
                self.close()
                raise
        xy = np.frombuffer(reply, dtype=np.float32)
        if not np.isfinite(xy).all():
            raise ValueError("CUDA-локализатор вернул недопустимые координаты")
        return torch.from_numpy(xy).reshape(1, 2)

    def close(self):
        self.socket.close()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)


def prewarm_field():
    global _worker
    with _LOCK:
        if _worker is None or _worker.process.poll() is not None:
            if _worker is not None:
                _worker.close()
            _worker = FieldLocalizer()
        return _worker


@atexit.register
def close_field():
    global _worker
    with _LOCK:
        if _worker is not None:
            _worker.close()
            _worker = None


def serve(fd):
    import torch
    from .grasp_admission import prewarm

    # These flags are process-global. Other models and the web process retain their own settings.
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.set_num_threads(1)
    estimator = prewarm()
    with socket.socket(fileno=fd) as channel, channel.makefile("rb") as stream, torch.inference_mode():
        estimator(torch.zeros(SHAPE[1:], dtype=torch.float32).permute(2, 0, 1)[None])
        torch.cuda.synchronize()
        # A failed launcher or abandoned session cannot retain GPU memory indefinitely.
        channel.settimeout(90)
        channel.sendall(b"R")
        while True:
            try:
                frame = stream.read(INPUT_BYTES)
            except TimeoutError:
                return
            if len(frame) != INPUT_BYTES:
                return
            image = np.frombuffer(frame, dtype=np.float32).reshape(SHAPE[1:]).copy()
            prediction = estimator(torch.from_numpy(image).permute(2, 0, 1)[None])
            channel.sendall(prediction.contiguous().numpy().data)


if __name__ == "__main__":
    serve(int(sys.argv[1]))
