"""Independent field-policy replication with an integer-ID visibility measurement."""

from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np

from scripts.grasp_study import admission_native as v2

BANK = tuple(range(976100, 976228))
OUT = v2.DATA / "simlab/reports/grasp-admission-native-v3"
V2_PROTOCOL = "d6a96dd50bce73ae6c617d7a1d139217f2118aaaab9a6fcdef8a30f08f76fa26"
SOURCE = "scripts/grasp_study/admission_native_v3.py"


class IntegerVisibility:
    """Dedicated single-sample ID buffer. Policy RGB uses the unchanged four-sample renderer."""

    def __init__(self):
        self.renderer = None

    def close(self):
        if self.renderer is not None:
            self.renderer.close()

    def __call__(self, env):
        m = env.model
        if self.renderer is None:
            original = m.vis.quality.offsamples
            try:
                m.vis.quality.offsamples = 0
                self.renderer = mujoco.Renderer(m, height=480, width=640)
            finally:
                m.vis.quality.offsamples = original
            self.renderer.enable_segmentation_rendering()
        option = mujoco.MjvOption()
        cube = m.geom("cube").id

        def target_mask():
            self.renderer.update_scene(env.data, camera=env.camera_name, scene_option=option)
            ids = self.renderer.render()
            return (ids[:, :, 0] == cube) & (ids[:, :, 1] == int(mujoco.mjtObj.mjOBJ_GEOM))

        observed = target_mask()
        groups = m.geom_group.copy()
        try:
            m.geom_group[:] = 4
            m.geom_group[[cube, m.geom("floor").id]] = 0
            option.geomgroup[:] = 0
            option.geomgroup[0] = 1
            expected = target_mask()
        finally:
            m.geom_group[:] = groups
        ys, xs = np.nonzero(expected)
        box = [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)] if xs.size else None
        full = bool(
            box
            and 0 < box[0] < box[2] < 640
            and 0 < box[1] < box[3] < 480
            and np.array_equal(observed, expected)
        )
        return {
            "full": full,
            "box": box,
            "visible_pixels": int(observed.sum()),
            "unoccluded_pixels": int(expected.sum()),
        }


def main():
    base_protocol, save = v2.protocol, v2.save_json

    def protocol():
        result = base_protocol()
        result["measurement_revision"] = {
            "previous_protocol": V2_PROTOCOL,
            "validation_seeds": list(range(976000, 976006)),
            "v2_missing_pixels": [25, 46, 38, 224, 71, 68],
            "single_sample_with_support_missing_pixels": [0, 46, 38, 191, 0, 0],
            "cause": "Mixed multisample ID colours at boundaries do not represent a unique MuJoCo object. A dedicated single-sample ID renderer and a cube-on-support silhouette remove the false edge labels. True partial occlusions remain excluded, and the provider receives only the full-target box and RGB prediction. Physics and the original RGB renderer stay unchanged.",
        }
        result["source_sha256"][SOURCE] = v2.file_hash(Path(__file__))
        result["selection"] = (
            "Freeze all 148 first RGBs, 20 historical and 128 new candidates, before motor evaluation. Historical seeds 88300-88319 use the full denominator. Select the first 20 eligible ordered seeds from 976100-976227 without replacement after failure. Retain all 128 eligibility decisions. Fewer than 20 opens no admission. The previously screened 973000-973063 are excluded."
        )
        result["eligibility"] = (
            "Known simulated native wrist camera, measured look, every pixel of the cube-on-floor silhouette visible and strictly inside the frame, predicted RGB XY inside the frozen 32-demonstration hull. Compare exact, single-sample integer ID masks solely to supply the initial object box. Truth and localization error are reserved for scoring. Zero tolerance for a missing mask pixel."
        )
        return result

    def write(path, data):
        if path == OUT / "result.json":
            data["conditional"]["eligible_candidates"] = data["conditional"].pop("eligible_all_64")
            data["measurement_revision"] = "single_sample_cube_on_support_visibility"
        save(path, data)

    assert v2.file_hash(v2.OUT / "protocol.json") == V2_PROTOCOL
    scorer = IntegerVisibility()
    try:
        with patch.multiple(
            v2,
            BANK=BANK,
            OUT=OUT,
            SCHEMA="rosmaster.bound-rbf-native.v3",
            protocol=protocol,
            visibility=scorer,
            save_json=write,
        ):
            v2.main()
    finally:
        scorer.close()


if __name__ == "__main__":
    main()
