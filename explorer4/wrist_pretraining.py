"""Initialize an Explorer ACT from the vision encoder of the pinned public SO-101 model."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .paths import DATA

MODEL = "Piersondong/act_so101_wrist_v1"
REVISION = "bcf73e8e84d63bb6bcfe6791d63222d9b0660fa9"
WEIGHTS = "0ef9bd3e05ed7c3ec5d13b5177e48241b38415387fddbcfdedefbde0b16441f7"


def source_path():
    cache = (
        DATA
        / "cache/huggingface/hub"
        / ("models--" + MODEL.replace("/", "--"))
        / "snapshots"
        / REVISION
    )
    previous = (
        Path.home()
        / "Projects/so101_ai_learning/models/external/Piersondong_act_so101_wrist_v1"
    )
    return next(
        (p for p in (cache, previous) if (p / "model.safetensors").is_file()), cache
    )


def recipe():
    with (source_path() / "model.safetensors").open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != WEIGHTS:
            raise ValueError("Изменились веса публичной модели SO-101")
    return {
        "repo_id": MODEL,
        "revision": REVISION,
        "sha256": WEIGHTS,
        "scope": "ACT ResNet18 backbone only",
        "license": "Apache-2.0",
    }


def initialize(dataset, destination, seed):
    import torch
    from safetensors import safe_open
    from lerobot.datasets.dataset_metadata import LeRobotDatasetMetadata
    from lerobot.policies.act.configuration_act import ACTConfig
    from lerobot.policies.factory import make_policy, make_pre_post_processors
    from .training_drafts import checkpoint_hash

    source = recipe()
    meta = LeRobotDatasetMetadata("local/" + dataset.name, root=dataset)
    spec = meta.features
    if (
        set(k for k in spec if k.startswith("observation.images."))
        != {"observation.images.wrist"}
        or tuple(spec["action"]["shape"]) != (6,)
        or meta.fps != 30
    ):
        raise ValueError("Expected one wrist camera, six arm targets and 30 Hz")
    # The caller supplies the merged training partition. Public motor layers, optimizer,
    # action statistics and camera normalizers are never copied.
    target = Path(destination)
    receipt = target.parent / (target.name + "-lineage.json")
    expected = dict(source=source, seed=seed, training_dataset=str(dataset))
    if receipt.is_file():
        saved = json.loads(receipt.read_text())
        if any(saved.get(k) != v for k, v in expected.items()) or saved[
            "bundle_sha256"
        ] != checkpoint_hash(target):
            raise ValueError("Vision initialization or its source has changed")
        return target
    config = ACTConfig(
        device="cpu", pretrained_backbone_weights=None, push_to_hub=False
    )
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        policy = make_policy(config, ds_meta=meta)
    prefix = "model.backbone."
    backbone = policy.model.backbone
    with safe_open(
        source_path() / "model.safetensors", framework="pt", device="cpu"
    ) as packed:
        tensors = {
            k[len(prefix) :]: packed.get_tensor(k)
            for k in packed.keys()
            if k.startswith(prefix)
        }
    backbone.load_state_dict(tensors, strict=True)
    pre, post = make_pre_post_processors(config, dataset_stats=meta.stats)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as folder:
        temp = Path(folder) / "bundle"
        policy.save_pretrained(temp)
        pre.save_pretrained(temp)
        post.save_pretrained(temp)
        if target.exists():
            if checkpoint_hash(temp) != checkpoint_hash(target):
                raise ValueError("Unfinished initialization has different weights")
        else:
            os.rename(temp, target)
        lineage = Path(folder) / "lineage.json"
        lineage.write_text(
            json.dumps(
                dict(
                    **expected,
                    encoder_tensors=len(tensors),
                    bundle_sha256=checkpoint_hash(target),
                ),
                indent=2,
            )
            + "\n"
        )
        os.replace(lineage, receipt)
    return target
