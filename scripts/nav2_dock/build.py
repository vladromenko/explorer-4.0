"""Build the upstream Nav2 Jazzy docking law for offline arm64 simulation."""

import ctypes
import fcntl
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.request import urlopen

from explorer4.paths import DATA

CACHE = DATA / "cache/nav2-dock-jazzy"
IMAGE = "ros@sha256:00b8d47a6e6384a2834e3d01fa87ae767876543baa574f2d64a75c04ea33c698"
NAV2 = "ros-navigation/navigation2/c7046550547d382a5186d106b0895eda02485d7c"
ANGLES = "ros/angles/a96224f9ab3ac51fe8fd981c1e1554528dc4345a"
FILES = {
    "nav2_graceful_controller/src/smooth_control_law.cpp": "1bf61f320d7cd5091d2a31af601a3616e994b0e01c2b7760a8de18568c3ebcda",
    "nav2_graceful_controller/include/nav2_graceful_controller/smooth_control_law.hpp": "87a3e0c4db58f51d97a4773cdbf1c329d6dcac9c74a1b3c884b22519490c6a3d",
    "nav2_graceful_controller/include/nav2_graceful_controller/ego_polar_coords.hpp": "c7ad82fe944424d5ad8b00363951c6e16d61befce760f2bd4b602652aa0f8b35",
    "nav2_util/include/nav2_util/geometry_utils.hpp": "a5e65e398dd2559b2e1cac8a7b4aaa8199b94af77ac873a0d883ba5af123edad",
    "angles/include/angles/angles.h": "6972d2fd0fda27ca42ab9271859004256f55dd58521711138b30df581ab9c5cf",
}
LIBRARY = CACHE / "libexplorer_nav2_dock.so"
WRAPPER = Path(__file__).with_name("velocity.cpp").resolve()
COMPILE = """
set -euo pipefail
includes=()
for directory in /opt/ros/jazzy/include/*; do includes+=("-I$directory"); done
g++ -std=c++17 -O2 -shared -fPIC -Wl,-z,defs \
    "${includes[@]}" -I/usr/include/eigen3 -Iangles/include \
    -Inav2_util/include -Inav2_graceful_controller/include \
    nav2_graceful_controller/src/smooth_control_law.cpp /wrapper.cpp \
    -o /output/libexplorer_nav2_dock.so
"""


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    source = CACHE / "source"
    for name, expected in FILES.items():
        path = source / name
        if not path.exists():
            repo = ANGLES if name.startswith("angles/") else NAV2
            with urlopen(
                f"https://raw.githubusercontent.com/{repo}/{name}", timeout=30
            ) as stream:
                body = stream.read()
            if hashlib.sha256(body).hexdigest() != expected:
                raise ValueError(f"Unexpected upstream source {name}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        if sha(path) != expected:
            raise ValueError(f"Cached upstream source differs at {name}")
    with tempfile.TemporaryDirectory(dir=CACHE) as temp:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network=none",
                "--read-only",
                "--tmpfs",
                "/tmp",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "-v",
                f"{source}:/src:ro",
                "-v",
                f"{WRAPPER}:/wrapper.cpp:ro",
                "-v",
                f"{temp}:/output",
                "-w",
                "/src",
                "--entrypoint",
                "bash",
                IMAGE,
                "-c",
                COMPILE,
            ],
            check=True,
        )
        binary = Path(temp) / LIBRARY.name
        fn = ctypes.CDLL(str(binary)).explorer_nav2_velocity
        ptr = ctypes.POINTER(ctypes.c_double)
        fn.argtypes = [ctypes.c_double] * 3 + [ptr, ptr]
        for left, sign in ((0.0, 0), (0.1, 1), (-0.1, -1)):
            v, w = ctypes.c_double(), ctypes.c_double()
            if (
                not fn(0.8, left, 0.0, ctypes.byref(v), ctypes.byref(w))
                or not 0 < v.value <= 0.25
            ):
                raise ValueError("Upstream controller failed the forward fixture")
            if not (abs(w.value) < 1e-9 if sign == 0 else 0 < sign * w.value <= 0.75):
                raise ValueError("Upstream controller failed the left/right fixture")
        binary.replace(LIBRARY)
    receipt = {
        "ros_image": IMAGE,
        "nav2": NAV2,
        "angles": ANGLES,
        "sources": FILES,
        "wrapper_sha256": sha(WRAPPER),
        "library_sha256": sha(LIBRARY),
    }
    temporary = CACHE / "build.json.tmp"
    temporary.write_text(json.dumps(receipt, indent=2) + "\n")
    temporary.replace(CACHE / "build.json")
    print(LIBRARY, receipt["library_sha256"])


if __name__ == "__main__":
    CACHE.mkdir(parents=True, exist_ok=True)
    with (CACHE / ".build.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        build()
