"""Bounded grasp corrections in native servo coordinates, fitted on closed-loop outcomes."""

import numpy as np


def corrected_plan(policy, xy, radial_mm, roll_gain):
    """Keep the input and corrected aim inside demonstrated support; restore the carry orientation."""
    xy = np.asarray(xy, dtype=float)
    if xy.shape != (2,) or not np.isfinite(xy).all() or policy.support.find_simplex(xy) < 0:
        raise ValueError("The base-frame target must be inside the original training hull")
    if radial_mm not in (-4, 0, 4) or roll_gain not in (-1, 0, 1):
        raise ValueError("Correction exceeds the fitted motor envelope")
    aim = xy
    if radial_mm:
        direction = xy / np.linalg.norm(xy)
        offset = direction * (radial_mm / 1000)
        for scale in (1.0, 0.5, 0.25):
            candidate = xy + scale * offset
            if policy.support.find_simplex(candidate) >= 0:
                aim = candidate
                break
    plan = policy.rbf(aim[None] / .05)[0]
    if roll_gain:
        # The wrist camera mounts on arm4. J5 rotates the jaws about their own axis.
        # Apply roll through approach and lift, then return to the demonstrated carry pose.
        phase = np.arange(len(plan))
        ramp = np.interp(phase, [0, 30, 145, 185], [0., 1., 1., 0.])
        plan[:,4] += ramp * np.clip(roll_gain * (plan[:,0] - 90.), -15., 15.)
    return plan
