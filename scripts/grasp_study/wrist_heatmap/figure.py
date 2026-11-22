"""Render the opened diagnostic RGB and empirical errors of the independent paired native study."""

import json

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .data import OUT
from .study import DIAGNOSTIC


def plot():
    result = json.loads((OUT / "result.json").read_text())
    seed = 976115
    diag = next(row for row in result["opened_v3"] if row["seed"] == seed)
    original = json.loads((DIAGNOSTIC / "result.json").read_text())
    candidate = next(row for row in original["candidates"] if row["seed"] == seed)
    rgb = cv2.imread(str(DIAGNOSTIC / "frames" / f"{seed}.png"))[:, :, ::-1]
    figure, (image, ecdf) = plt.subplots(1, 2, figsize=(8.1, 3.5), layout="constrained")
    image.imshow(rgb)
    u, v = (np.array(diag["keypoint"]["uv_160x120"]) + 0.5) * 4 - 0.5
    x1, y1, x2, y2 = candidate["visibility"]["box"]
    image.add_patch(plt.Rectangle((x1, y1), x2 - x1, y2 - y1, fill=False, edgecolor="#dc9638", lw=1.6))
    image.plot(u, v, "+", c="#5ff5ff", mew=2.3, ms=12)
    image.set_title(f"Opened wrist view · scene {seed}", fontsize=11)
    image.set_xlabel("Simulator box (orange), predicted centre (cyan)")
    image.set_xticks([])
    image.set_yticks([])
    for method, label, color in [
        ("baseline", "Direct XY", "#34639c"),
        ("keypoint", "Keypoint + plane", "#b04d32"),
    ]:
        errors = np.sort([row["methods"][method]["error_mm"] for row in result["rows"]])
        ecdf.step(
            np.r_[0, errors], np.arange(len(errors) + 1) / len(errors), where="post", label=label, color=color
        )
    ecdf.set_xlabel("Base-frame XY error (mm)")
    ecdf.set_ylabel("Fraction of scenes at or below error")
    ecdf.set_title("Independent wrist views · 48 starts", fontsize=11)
    ecdf.set_ylim(0, 1.04)
    ecdf.set_xlim(left=0)
    ecdf.grid(alpha=0.17)
    ecdf.legend(frameon=False)
    figure.savefig(OUT / "localization.png", dpi=175)
    plt.close(figure)


if __name__ == "__main__":
    plot()
