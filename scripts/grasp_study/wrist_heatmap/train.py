"""Fit one fixed heatmap recipe on the archived split; select only by validation p90."""

import json

import cv2
import numpy as np
import torch
import torchvision
from torch.optim import AdamW

from explorer4.conditioned_grasp import file_hash
from scripts.grasp_study.evaluate import save_json
from .data import OUT, load
from .model import WristKeypoint


def write_pt(path, value):
    temp = path.with_suffix(".tmp")
    torch.save(value, temp)
    temp.replace(path)


def errors(values):
    v = np.asarray(values, dtype=float)
    return {
        "n": len(v),
        "p50_mm": float(np.median(v)),
        "p90_mm": float(np.percentile(v, 90)),
        "mean_mm": float(v.mean()),
        "max_mm": float(v.max()),
        "above_10_mm": int((v > 10).sum()),
        "above_20_mm": int((v > 20).sum()),
    }


def fit():
    from .study import verify_protocol

    spec = verify_protocol()
    protocol_sha = file_hash(OUT / "protocol.json")
    weights, completion, resume = (OUT / name for name in ("heatmap.pt", "fit.json", "last-training.pt"))
    if completion.exists():
        record = json.loads(completion.read_text())
        if record["protocol_sha256"] != protocol_sha or record["weights_sha256"] != file_hash(weights):
            raise ValueError("Completed fit differs from the registered artifacts")
        return
    device = torch.device("cuda")
    torch.set_num_threads(1)
    torch.manual_seed(1000)
    torch.cuda.manual_seed_all(1000)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    train_rgb, train_uv, train_xy = load("training")
    valid_rgb, valid_uv, valid_xy = load("validation")
    homography, _ = cv2.findHomography(train_uv, train_xy, method=0)
    model = WristKeypoint(homography, pretrained=True).to(device)
    trunk = [*model.stem.parameters(), *model.context.parameters()]
    remaining = [p for n, p in model.named_parameters() if not n.startswith(("stem.", "context."))]
    optimizer = AdamW(
        [{"params": trunk, "lr": 0.00015}, {"params": remaining, "lr": 0.001}], weight_decay=0.0001
    )
    rgb, uv, xy, valid = [torch.from_numpy(a).to(device) for a in (train_rgb, train_uv, train_xy, valid_rgb)]
    best_p90, best_epoch, best_state = float("inf"), None, None
    history = []
    if resume.exists():
        state = torch.load(resume, weights_only=True, map_location="cpu")
        if state["protocol_sha256"] != protocol_sha:
            raise ValueError("Wrong fit checkpoint")
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        best_state, best_epoch, best_p90 = state["best"], state["best_epoch"], state["best_p90"]
        history = state["history"]
        torch.set_rng_state(state["cpu_rng"])
        torch.cuda.set_rng_state(state["cuda_rng"])
    for epoch in range(len(history) + 1, spec["epochs"] + 1):
        model.train()
        total_loss = 0.0
        for ids in torch.randperm(len(rgb)).split(spec["batch"]):
            optimizer.zero_grad(set_to_none=True)
            loss = model.loss(rgb[ids], uv[ids], xy[ids])
            loss.backward()
            optimizer.step()
            total_loss += loss.detach().item()
        model.eval()
        with torch.inference_mode():
            predictions = torch.cat([model(batch)[0] for batch in valid.split(spec["batch"])]).cpu().numpy()
        metric = errors(1000 * np.linalg.norm(predictions - valid_xy, axis=1))
        history.append(
            {"epoch": epoch, "mean_training_loss": total_loss / (len(rgb) / spec["batch"]), **metric}
        )
        if metric["p90_mm"] < best_p90:
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            best_epoch, best_p90 = epoch, metric["p90_mm"]
        write_pt(
            resume,
            {
                "protocol_sha256": protocol_sha,
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "best": best_state,
                "best_epoch": best_epoch,
                "best_p90": best_p90,
                "history": history,
                "cpu_rng": torch.get_rng_state(),
                "cuda_rng": torch.cuda.get_rng_state(),
            },
        )
        print("epoch", epoch, "validation p90 mm", round(metric["p90_mm"], 2), flush=True)
    write_pt(weights, best_state)
    save_json(
        completion,
        {
            "protocol_sha256": protocol_sha,
            "weights_sha256": file_hash(weights),
            "pretrained_sha256": spec["weights"]["imagenet"],
            "selected_epoch": best_epoch,
            "epochs": history,
            "optimizer_updates": int(len(history) * len(rgb) / spec["batch"]),
            "torch": str(torch.__version__),
            "torchvision": str(torchvision.__version__),
            "device": torch.cuda.get_device_name(),
            "training_seed": 1000,
        },
    )


if __name__ == "__main__":
    fit()
