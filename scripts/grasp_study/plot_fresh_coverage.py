"""Plot the published fresh-scene outcomes. Run with .venv-sim/bin/python -m scripts.grasp_study.plot_fresh_coverage."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import ConvexHull

STUDY = Path(__file__).resolve().parents[2] / "docs/results/conditioned_grasp_v1"
METHODS = {
    "act": "LeRobot ACT",
    "diffusion": "LeRobot Diffusion",
    "rbf": "SciPy radial basis interpolation",
    "ik": "Vendor inverse kinematics",
}


def main():
    data = json.loads((STUDY / "fresh-coverage.json").read_text())
    train = 1000 * np.array(data["training_xy_m"])
    rows = data["rows"]
    reset = 1000 * np.array([r["reset_xy_m"] for r in rows])
    if (
        train.shape != (32, 2)
        or len({r["seed"] for r in rows}) != len(rows)
        or reset.shape != (20, 2)
    ):
        raise ValueError(
            "Expected the 32 demonstration positions and 20 paired fresh scenes"
        )
    hull = train[ConvexHull(train).vertices]
    inside = np.array([r["reset_in_train_hull"] for r in rows])
    pair = [i for i, r in enumerate(rows) if r["seed"] in (940209, 940210)]

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "text.color": "#182937",
            "axes.labelcolor": "#182937",
            "axes.edgecolor": "#8b96a2",
            "xtick.color": "#475665",
            "ytick.color": "#475665",
        }
    )
    fig, axes = plt.subplots(2, 2, figsize=(7.15, 7.8), sharex=True, sharey=True)
    fig.subplots_adjust(
        left=0.10, right=0.975, top=0.805, bottom=0.115, wspace=0.17, hspace=0.33
    )
    fig.text(
        0.065,
        0.962,
        "Grasp outcomes across the cube workspace",
        fontsize=16,
        weight="bold",
    )
    fig.text(
        0.065,
        0.926,
        "ROSMASTER in MuJoCo  ·  Cube centres at reset  ·  Same 20 scenes per planner",
        fontsize=9.3,
    )
    for ax, (key, label) in zip(axes.flat, METHODS.items()):
        outcomes = [r["mujoco"][key]["outcome"] for r in rows]
        if set(outcomes) - {"success", "failure"}:
            raise ValueError(f"Unscored condition in {key}")
        held = np.array([v == "success" for v in outcomes])
        ax.set_axisbelow(True)
        ax.grid(True, color="#e0e5e9", linewidth=0.5)
        (region,) = ax.fill(
            *hull.T,
            facecolor="#edf0f4",
            edgecolor="#8b99a6",
            linewidth=0.85,
            zorder=0.5,
        )
        training = ax.scatter(
            *train.T, marker="+", s=23, color="#6c7885", linewidths=0.85, zorder=2
        )
        win = ax.scatter(
            *reset[held].T,
            marker="o",
            s=34,
            color="#16756c",
            edgecolors="white",
            linewidths=0.8,
            zorder=3,
        )
        loss = ax.scatter(
            *reset[~held].T,
            marker="x",
            s=46,
            color="#bf491c",
            linewidths=1.75,
            zorder=4,
        )
        # Preserve true positions; mark the two successful starts just 1.2 mm apart.
        ax.annotate(
            "×2",
            xy=reset[pair].mean(axis=0),
            xytext=(1, 7),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=7.5,
            color="#145d56",
            arrowprops={
                "arrowstyle": "-",
                "color": "#38786f",
                "linewidth": 0.6,
                "shrinkB": 2,
            },
            zorder=5,
        )
        ax.set_title(label, loc="left", fontsize=10.5, weight="bold", pad=17)
        ax.text(
            0,
            1.025,
            f"{held.sum()}/{len(rows)} held  ·  Inside {(held & inside).sum()}/{inside.sum()}"
            f"  ·  Outside {(held & ~inside).sum()}/{(~inside).sum()}",
            transform=ax.transAxes,
            fontsize=8,
            color="#475665",
        )
        ax.set(
            xlim=(162, 258),
            ylim=(-54, 54),
            xticks=[175, 200, 225, 250],
            yticks=[-50, -25, 0, 25, 50],
            aspect="equal",
        )
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(length=3, width=0.6, labelsize=8)
    fig.legend(
        [training, region, win, loss],
        ["Training position (32)", "Training hull", "Held for 1 s", "Hold failed"],
        loc="upper left",
        bbox_to_anchor=(0.054, 0.905),
        ncol=4,
        frameon=False,
        fontsize=8.4,
        handlelength=1.3,
        columnspacing=1.6,
        handletextpad=0.45,
    )
    for ax in axes[-1]:
        ax.set_xlabel("Base-frame x (mm)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Base-frame y (mm)")
    fig.text(
        0.065,
        0.042,
        "×2 marks two cube centres 1.2 mm apart. The shaded region is the convex hull of the 32 motor demonstrations.",
        fontsize=7.7,
        color="#475665",
    )
    fig.savefig(STUDY / "fresh-coverage.png", dpi=230, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
