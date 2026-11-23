"""Measure simulated retention without an unloaded jaw-angle threshold."""

import numpy as np


ENDPOINT = "bilateral_floor_carry_v2"


def carry_geometry(env):
    cube = env.data.body("task_cube")
    bottom = cube.xpos[2] - np.abs(cube.xmat.reshape(3, 3)[2]) @ env.object_half()
    distance = np.linalg.norm(cube.xpos - env.data.site("gripperframe").xpos)
    pose_error = np.max(
        np.abs(env.from_radians(env.data.qpos[:6])[:5] - env.cfg["carry_pose"])
    )
    return float(bottom), float(distance), float(pose_error)


class FloorCarry:
    def __init__(self, env):
        self.env = env
        self.cube = env.model.body("task_cube").id
        self.jaws = {
            env.model.body(prefix + str(i)).id: prefix
            for prefix in ("llink", "rlink")
            for i in (1, 2, 3)
        }
        self.samples = []

    def measure(self):
        env = self.env
        touching = set()
        for contact in env.data.contact:
            a, b = env.model.geom_bodyid[[contact.geom1, contact.geom2]]
            other = b if a == self.cube else a if b == self.cube else None
            if other in self.jaws:
                touching.add(self.jaws[other])
        # Include both endpoint samples of a complete second at the control cadence.
        row = (*carry_geometry(env), len(touching) == 2)
        self.samples.append(row)

    @property
    def success(self):
        return terminal_success(self.samples, self.env.fps, self.env.cfg["carry_tolerance_deg"])


def terminal_success(samples, fps, tolerance):
    count = int(fps) + 1
    end = samples[-count:]
    return len(end) == count and all(
        height > .05 and distance < .06 and pose_error < tolerance and bilateral
        for height, distance, pose_error, bilateral in end
    )
