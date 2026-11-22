"""Freeze camera observations for fitting and confirming a bounded native grasp correction."""

from unittest.mock import patch

from explorer4.paths import DATA
from scripts.grasp_study import admission_native as baseline
from scripts.grasp_study.admission_native_v3 import IntegerVisibility
from scripts.grasp_study.coverage_design import frozen, read


OUT = DATA / "simlab/reports/grasp-native-residual-v1"
BLOCKS = {"train": range(979000, 979080), "confirmation": range(979200, 979360)}
QUOTAS = {"train": 16, "confirmation": 32}


def inputs():
    import torch
    import cv2

    torch.set_num_threads(1)
    cv2.setNumThreads(1)
    design = {
        "study": "Bounded residual motor-policy search after inspection of native field errors",
        "source_study": "grasp-admission-native-v3",
        "selection": "All candidates recorded in order, using the original field camera, its full visibility requirement, and original demonstration hull. Take first eligible up to the quota. No replacement after seeing outcomes.",
        "banks": {k: list(v) for k, v in BLOCKS.items()},
        "quotas": QUOTAS,
        "training": "Nine combinations, radial correction -4, 0 or 4 mm and wrist-roll gain -1, 0 or 1 on the planned base angle. All settings run on the same eligible training starts. Select by count of independent terminal retentions, then count passing both independent and historical strict tests, then smallest normalized correction. Zero wins ties. No confirmation motor trial until fit is frozen.",
        "endpoint": "Final 20 consecutive 20-Hz samples of the 360 commands. Independent retention requires simultaneous contact with both sets of jaw links, lift above support >50 mm, and the original measured five-joint carry predicate at every sample. Preserve the original closed-jaw strict endpoint as a separate score. Initial RGB and native guard settings are identical in paired comparisons.",
        "report": "Report all outcomes, refusals, qualified-start counts, discordances and exact two-sided paired binomial tests. Individual confirmation scenes provide independence within this simulated distribution. This is a fixed-size axis-aligned cube.",
        "physical_trials": 0,
        "source_sha256": {n: baseline.file_hash(baseline.ROOT/n) for n in (
            "scripts/grasp_study/residual_inputs.py","scripts/grasp_study/admission_native.py",
            "scripts/grasp_study/admission_native_v3.py","explorer4/conditioned_grasp.py")},
        "vision_weights": baseline.VISION_SHA256,
        "motor_demonstrations": baseline.MOTOR_SHA256,
        "physics": baseline.PHYSICS_SHA256,
    }
    design_path = OUT / "design.json"
    if design_path.exists():
        prior_sha = read(design_path)["source_sha256"]["scripts/grasp_study/residual_inputs.py"]
        if prior_sha == "63c9720edd0cd9f42361085dee1896d31702551773abb63b7a599a7eb08b1cbf":
            # This registered version used the same selection with an early loop skip.
            design["source_sha256"]["scripts/grasp_study/residual_inputs.py"] = prior_sha
    frozen(design_path, design)
    model=baseline.SimulatedActions(None, baseline.SOURCE, baseline.VISION, "rbf", None)
    env=baseline.environment()
    scorer=IntegerVisibility()
    try:
        for group,seeds in BLOCKS.items():
            directory=OUT/group
            if not (directory/"selection.json").exists():
                frozen(directory/"protocol.json", {"design_sha256": baseline.file_hash(OUT/"design.json"), "group":group})
                with patch.multiple(baseline, OUT=directory, BANK=tuple(seeds), HISTORY=(), visibility=scorer):
                    candidates=baseline.collect(env,model,{})
                selected=[r["seed"] for r in candidates if r["eligible"]][:QUOTAS[group]]
                frozen(directory/"selection.json", {"selected":selected,"candidates":len(candidates),
                                                    "eligible":sum(r["eligible"] for r in candidates),
                                                    "protocol_sha256":baseline.file_hash(directory/"protocol.json")})
                print(group,len(selected),"selected",flush=True)
    finally:
        scorer.close()
        env.close()


if __name__ == "__main__":
    inputs()
