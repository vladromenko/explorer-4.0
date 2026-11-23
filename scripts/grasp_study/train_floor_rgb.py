"""Fit Explorer's existing wrist keypoint model at the corrected floor look pose."""

import json
from pathlib import Path

import cv2
import mujoco
import numpy as np
import torch

from explorer4.conditioned_grasp import SLEW_DEGREES_PER_SECOND
from explorer4.floor_cube_localization import cube_center, top_surface
from explorer4.paths import DATA, ROOT
from explorer4.resources import ResourceLease
from explorer4.sim.factory import make
from explorer4.sim_protocol import scene_revision, sha256_file

from .depth_floor_recovery import LOOKS, PROFILE, SIZE, capture
from .evaluate import save_json
from .wrist_heatmap.model import WristKeypoint

OUT = DATA / "simlab/reports/floor-rgb-keypoint-pilot-v1"
BACKBONE = DATA / "cache/torch/hub/checkpoints/resnet18-f37072fd.pth"
BANKS = {"train": list(range(988100, 988228)), "validation": list(range(988300, 988332)),
         "test": list(range(988400, 988432))}
SEED = 1000
EPOCHS = 8
BATCH = 16


def collect(seeds):
    rows = []
    with make(PROFILE, images=False) as env:
        depth_renderer = mujoco.Renderer(env.model, height=240, width=320)
        depth_renderer.enable_depth_rendering()
        pose, ticks = LOOKS[0]
        slew = SLEW_DEGREES_PER_SECOND * env.dt
        try:
            for seed in seeds:
                env.close()
                env.reset(seed=seed)
                command = env.observation()["state"].astype(float)
                for _ in range(ticks):
                    command += np.clip(np.asarray(pose) - command, -slew, slew)
                    env.step(command)
                depth, camera, transform = capture(env, depth_renderer)
                bounds = env.cfg["object_x_m"], env.cfg["object_y_m"]
                xy = cube_center(top_surface(depth, camera, transform, SIZE, bounds), SIZE, bounds)
                if xy is None:
                    rows.append({"seed": seed, "visible_top": False})
                    continue
                q = transform[:3, :3].T @ (np.r_[xy, SIZE] - transform[:3, 3])
                fx, fy, cx, cy = camera
                uv = .5 * np.array([fx * q[0] / q[2] + cx + .5, fy * q[1] / q[2] + cy + .5]) - .5
                rgb = cv2.resize(env.render(), (160, 120), interpolation=cv2.INTER_AREA)
                actual = env.data.body("task_cube").xpos[:2].copy()
                rows.append({"seed": seed, "visible_top": True, "rgb": rgb, "uv": uv, "xy": xy, "actual": actual})
        finally:
            depth_renderer.close()
    return rows


def arrays(rows):
    observed = [row for row in rows if row["visible_top"]]
    return tuple(torch.from_numpy(np.stack([row[k] for row in observed]))
                 for k in ("rgb", "uv", "xy", "actual"))


def predict(model, frames):
    model.eval()
    with torch.inference_mode():
        return torch.cat([model(x)[0] for x in frames.split(BATCH)]).numpy()


def main():
    torch.set_num_threads(2)
    torch.manual_seed(SEED)
    protocol = {
        "scene_revision": scene_revision(PROFILE), "banks": BANKS, "training_seed": SEED,
        "epochs": EPOCHS, "batch": BATCH,
        "measurement": "Existing RGB keypoint network after the corrected first look. Independent simulator position is reserved for scoring; synthetic metric depth labels the complete visible top.",
        "pretrained_sha256": sha256_file(BACKBONE),
        "sources": {name: sha256_file(path) for name, path in {
            "trainer": Path(__file__),
            "model": ROOT / "scripts/grasp_study/wrist_heatmap/model.py",
            "camera": ROOT / "scripts/grasp_study/depth_floor_recovery.py",
            "labels": ROOT / "explorer4/floor_cube_localization.py",
        }.items()},
    }
    with ResourceLease("floor-rgb-keypoint-fit"):
        manifest = OUT / "protocol.json"
        if manifest.exists() and json.loads(manifest.read_text()) != protocol:
            raise ValueError("RGB comparison already froze another protocol")
        save_json(manifest, protocol)
        train_bank, val_bank = (collect(BANKS[key]) for key in ("train", "validation"))
        x, uv, y, _ = arrays(train_bank)
        val_x, _, _, val_truth = arrays(val_bank)
        if len(x) < 64 or len(val_x) < 12:
            raise ValueError("Insufficient independent complete tops for RGB labeling")
        homography, _ = cv2.findHomography(uv.numpy(), y.numpy(), 0)
        model = WristKeypoint(homography)
        weights = torch.load(BACKBONE, map_location="cpu", weights_only=True)
        for prefix, module in (("conv1", model.stem[0]), ("bn1", model.stem[1]),
                               ("layer1", model.stem[4]), ("layer2", model.context)):
            module.load_state_dict({k.removeprefix(prefix + "."): v
                                    for k, v in weights.items() if k.startswith(prefix + ".")})
        for module in (model.stem, model.context):
            module.requires_grad_(False)
        optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=.001)
        history = []
        best = float("inf")
        updates = 0
        for epoch in range(1, EPOCHS + 1):
            model.train()
            model.stem.eval()
            model.context.eval()
            for ids in torch.randperm(len(x)).split(BATCH):
                optimizer.zero_grad(set_to_none=True)
                loss = model.loss(x[ids], uv[ids].float(), y[ids].float())
                loss.backward()
                optimizer.step()
                updates += 1
            error = np.linalg.norm(predict(model, val_x) - val_truth.numpy(), axis=1)
            metric = float(np.quantile(error, .9))
            history.append({"epoch": epoch, "validation_p90_m": metric})
            if metric < best:
                best = metric
                torch.save(model.state_dict(), OUT / "weights.pt")
            print("epoch", epoch, "validation p90 mm", round(1000 * metric, 2), flush=True)
        model.load_state_dict(torch.load(OUT / "weights.pt", map_location="cpu", weights_only=True))
        test = collect(BANKS["test"])
        images, _, depth_xy, true_xy = arrays(test)
        rgb_error = np.linalg.norm(predict(model, images) - true_xy.numpy(), axis=1)
        depth_error = np.linalg.norm(depth_xy.numpy() - true_xy.numpy(), axis=1)
        compare = iter(zip(rgb_error, depth_error, strict=True))
        rows = []
        for row in test:
            result = {"seed": row["seed"], "visible_top": row["visible_top"]}
            if row["visible_top"]:
                rgb, depth = next(compare)
                result.update(rgb_error_m=float(rgb), depth_error_m=float(depth))
            rows.append(result)
        save_json(OUT / "result.json", {
            "training_frames": len(x), "validation_frames": len(val_x), "optimizer_updates": updates,
            "test_total": len(test), "test_labelled": len(images), "rgb_p90_m": float(np.quantile(rgb_error, .9)),
            "depth_p90_m": float(np.quantile(depth_error, .9)), "history": history, "test": rows,
            "weights_sha256": sha256_file(OUT / "weights.pt"),
            "purpose": "Conditional localization comparison; not a new robot grasp rollout",
        })


if __name__ == "__main__":
    main()
