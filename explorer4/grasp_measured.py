"""Action sequence shared by the observed field trial and its simulator counterpart."""

import numpy as np

from .grasp_shadow import ArchiveGraspActions

PLAN_TICKS = 220
TRIAL_TICKS = 360


class MeasuredActions(ArchiveGraspActions):
    input_domain = "bound_rosmaster_reference"

    def locate(self, observation, image):
        return np.asarray(observation["predicted_xy_m"], dtype=np.float32)


def next_target(model, observation, index, last):
    """At 20 Hz, advance the bounded plan, then hold its last native target through STOP."""
    if not 0 <= index < TRIAL_TICKS:
        raise StopIteration
    return model.next(observation) if index < PLAN_TICKS else last
