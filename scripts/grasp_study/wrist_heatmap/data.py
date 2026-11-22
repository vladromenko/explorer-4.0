"""Reconstruct training-only wrist-camera keypoints for the original archived RGB splits."""

import cv2
import numpy as np

from explorer4.conditioned_grasp import file_hash
from explorer4.paths import DATA
from scripts import recorded_start_visual_pick as original
from scripts.grasp_study.evaluate import environment, observe

OUT = DATA / "simlab/reports/wrist-cube-heatmap-v1"
SPLITS = {"training": range(921000, 922024), "validation": range(923000, 923128)}
TEST = range(982300, 982348)


def shards(split):
    files = sorted((original.RUN / split).glob("*.npz"))
    if [int(p.stem) for p in files] != list(SPLITS[split])[::32]:
        raise ValueError(f"Incomplete {split} shards")
    return files


def keypoint(env):
    cam = env.model.camera(env.camera_name).id
    if env.model.cam_sensorsize[cam].any():
        raise ValueError("This optical projection requires a vertical-fovy camera")
    xyz = env.data.body("task_cube").xpos
    camera = (xyz - env.data.cam_xpos[cam]) @ env.data.cam_xmat[cam].reshape(3, 3)
    f = 60 / np.tan(np.radians(env.model.cam_fovy[cam]) / 2)
    return np.array([79.5, 59.5]) + f * camera[:2] / -camera[2] * [1, -1]


def label():
    OUT.mkdir(parents=True, exist_ok=True)
    env = environment()
    cv2.setNumThreads(1)
    try:
        for split in SPLITS:
            paths = shards(split)
            for path in paths:
                dest = OUT / "labels" / split / path.name
                digest = file_hash(path)
                if dest.exists():
                    with np.load(dest) as saved:
                        if str(saved["shard_sha256"]) != digest:
                            raise ValueError("Original image shard changed")
                else:
                    with np.load(path) as bank:
                        ids = bank["seeds"].copy()
                        if not np.array_equal(ids, np.arange(int(path.stem), int(path.stem) + 32)):
                            raise ValueError("Wrong training IDs")
                        labels = []
                        for i, seed in enumerate(ids):
                            _, frame = observe(env, int(seed), render=(i == 0))
                            if i == 0:
                                current = cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA)
                                difference = np.abs(current.astype(np.int16) - bank["rgb"][0])
                                audit = [difference.mean(), difference.max()]
                                if audit[0] > 0.02 or audit[1] > 8:
                                    raise ValueError(f"RGB reconstruction differs for {path.name}: {audit}")
                            if not np.allclose(
                                env.data.body("task_cube").xpos[:2], bank["xy"][i], atol=1e-7, rtol=0
                            ):
                                raise ValueError(f"Wrong object pose for seed {seed}")
                            labels.append(keypoint(env))
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        tmp = dest.with_suffix(".tmp.npz")
                        np.savez(
                            tmp,
                            seeds=ids,
                            uv=np.array(labels, dtype=np.float32),
                            shard_sha256=digest,
                            parity_mean_max=audit,
                        )
                        tmp.replace(dest)
                    print(split, path.stem, flush=True)
    finally:
        env.close()


def load(split):
    images, uv, xy = [], [], []
    for path in shards(split):
        with np.load(path) as rgb, np.load(OUT / "labels" / split / path.name) as labels:
            if str(labels["shard_sha256"]) != file_hash(path) or not np.array_equal(
                labels["seeds"], rgb["seeds"]
            ):
                raise ValueError(f"Wrong labels for {path.name}")
            images.extend(rgb["rgb"])
            xy.extend(rgb["xy"])
            uv.extend(labels["uv"])
    return np.array(images), np.array(uv), np.array(xy)


if __name__ == "__main__":
    label()
