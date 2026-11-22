"""Reconstruct the paired RBF plans from archived RGB, time CPU planning and draw the observed starts."""

import json
import time

import cv2
import matplotlib
import numpy as np
import torch
from scipy.spatial import ConvexHull

from scripts.grasp_study.coverage_design import METHODS, OUTPUT, fit, read
from scripts.grasp_study.evaluate import (
    VISION,
    file_hash,
    load_localizer,
    locate_cube,
    sha_array,
)


def replay(rows, models):
    torch.set_num_threads(1)
    cv2.setNumThreads(1)
    estimator = load_localizer(VISION)
    black = np.zeros((120, 160, 3), dtype=np.uint8)
    for estimator_rbf in models.values():
        estimator_rbf(locate_cube(estimator, black).astype(float)[None] / 0.05)
    times = {method: [] for method in METHODS}
    for i, row in enumerate(rows):
        path = OUTPUT / "frames" / f"{row['seed']}.png"
        rgb = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
        if sha_array(rgb) != row["rgb_sha256"]:
            raise ValueError("Replayed image differs")
        for method in METHODS[:: 1 if i % 2 == 0 else -1]:
            start = time.perf_counter_ns()
            xy = locate_cube(estimator, rgb).astype(float)
            trajectory = models[method](xy[None] / 0.05)[0]
            times[method].append((time.perf_counter_ns() - start) / 1e6)
            if (
                xy.tolist() != row["predicted_xy"]
                or sha_array(trajectory) != row["methods"][method]["plan_sha256"]
            ):
                raise ValueError("Replayed perception or motor plan differs")
    return {
        m: {
            "calls": len(t),
            "median_ms": float(np.median(t)),
            "p95_ms": float(np.percentile(t, 95)),
            "within_40_ms": sum(x <= 40 for x in t),
            "per_call_ms": t,
        }
        for m, t in times.items()
    }


def plot(points, rows):
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pool = np.array(list(read(OUTPUT / "allocation.json")["points"].values())) * 1000
    truth = np.array([r["initial"]["cube"][:2] for r in rows]) * 1000
    fig, axes = plt.subplots(
        1, 2, sharex=True, sharey=True, figsize=(9, 4.8), layout="constrained"
    )
    for ax, method, label in zip(
        axes, METHODS, ("Random", "Farthest-first"), strict=True
    ):
        pts = points[method] * 1000
        ax.scatter(*pool.T, s=7, c="#c7cbd0", label="Candidate placement")
        edge = pts[ConvexHull(pts).vertices]
        ax.fill(*edge.T, facecolor="#16847712", edgecolor="#138175", linewidth=1.1)
        ax.scatter(*pts.T, s=22, c="#138175", label="Accepted demonstration")
        success = np.array([r["methods"][method]["outcome"] == "success" for r in rows])
        ax.scatter(
            *truth[success].T,
            s=44,
            facecolors="white",
            edgecolors="#2b54a2",
            linewidths=1.6,
            label="Held on test",
        )
        ax.scatter(
            *truth[~success].T,
            s=39,
            c="#ac4532",
            marker="x",
            linewidths=1.5,
            label="Missed on test",
        )
        ax.set(
            aspect="equal",
            xlabel="Cube centre X (mm)",
            title=f"{label} · {sum(success)}/{len(rows)} holds",
        )
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Cube centre Y (mm)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="outside lower center", ncol=4, frameon=False, fontsize=8
    )
    fig.savefig(OUTPUT / "coverage.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    result = read(OUTPUT / "result.json")
    paths = {m: OUTPUT / "banks" / f"{m}.npz" for m in METHODS}
    models = {m: fit(path) for m, path in paths.items()}
    points = {}
    for m, path in paths.items():
        with np.load(path, allow_pickle=False) as bank:
            points[m] = bank["xy"].copy()
    audit = {
        "source_result_sha256": file_hash(OUTPUT / "result.json"),
        "scope": "Post-hoc engineering replay of decoded archived RGB on one warmed CPU core. Alternating AB/BA order, one call per method per frame. Excludes capture, file decode, transport, inference-process IPC and motor execution. Timing depends on host load.",
        "planning": replay(result["rows"], models),
    }
    # Keep each timing of the same plan, so rerunning the replay preserves the first estimate.
    path = OUTPUT / "planning-time.json"
    if not path.exists():
        path.write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n")
    elif read(path)["source_result_sha256"] != audit["source_result_sha256"]:
        raise ValueError("Wrong original timing input")
    plot(points, result["rows"])
