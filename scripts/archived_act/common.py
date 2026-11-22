import hashlib
import json
import os
from pathlib import Path

import numpy as np

from explorer4.paths import DATA, ROOT
from scripts.audit_floor_checkpoints import ORIGINAL, PHYSICS, PROFILE, PUBLIC, SEEDS, STEPS

QUEUE_LENGTH = 100
UNUSED_RGB = np.zeros((1, 1, 3), dtype=np.uint8)


def array_hash(values):
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes(order="C")).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def guard(step):
    if step not in STEPS:
        raise ValueError("Checkpoint outside the archived audit")
    if (os.environ.get("GALLIUM_DRIVER"), os.environ.get("LIBGL_ALWAYS_SOFTWARE"), os.environ.get("MUJOCO_GL")) != ("llvmpipe", "1", "glfw"):
        raise ValueError("Archived replay requires GLFW with Mesa llvmpipe")
    if (os.environ.get("__GLX_VENDOR_LIBRARY_NAME"), os.environ.get("PYOPENGL_PLATFORM"), os.environ.get("LP_NUM_THREADS")) != ("mesa", "glx", "1"):
        raise ValueError("Use the same single-threaded GLX Mesa backend as the full-renderer reference")
    if os.environ.get("CUDA_VISIBLE_DEVICES") or os.environ.get("EXPLORER_N_ACTION_STEPS"):
        raise ValueError("Archived replay requires CPU and the original execution horizon")
    plan = read(PUBLIC / "protocol.json")
    if (plan["source_job"], plan["seeds"], plan["physics_xml_sha256"]) != (ORIGINAL, SEEDS, PHYSICS):
        raise ValueError("Archival protocol mismatch")
    bank = DATA / "checkpoints" / (ORIGINAL + "-b8") / "checkpoints" / f"{step:06d}" / "pretrained_model"
    cfg = read(bank / "config.json")
    if (cfg["type"], cfg["n_obs_steps"], cfg["n_action_steps"], cfg["chunk_size"], cfg.get("temporal_ensemble_coeff")) != ("act", 1, QUEUE_LENGTH, QUEUE_LENGTH, None):
        raise ValueError("Only the original deterministic 100-action ACT queue is eligible")
    allowed = {"pre": ["rename_observations_processor", "to_batch_processor", "device_processor", "normalizer_processor"],
               "post": ["unnormalizer_processor", "device_processor"]}
    for side, expected in allowed.items():
        if [s["registry_name"] for s in read(bank / f"policy_{side}processor.json")["steps"]] != expected:
            raise ValueError("Unknown or stateful processor")
    return bank, plan["checkpoints"][str(step)]


def source_ids():
    import sysconfig
    from scripts.audit_floor_checkpoints import digest
    source = ROOT / ".venv/lib" / ("python" + sysconfig.get_python_version()) / "site-packages/lerobot/policies/act/modeling_act.py"
    paths = [ROOT / "scripts/archived_act" / s for s in ("common.py", "run.py", "parity.py")]
    paths += [ROOT / "explorer4" / s for s in ("act_client.py", "policy_runtime.py", "sim/policy_worker.py", "sim/evaluate.py")]
    paths.append(source)
    return {str(p.relative_to(ROOT)): digest(p) for p in paths}
