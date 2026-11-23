"""Render the frozen docking endpoints and peer calls, with one column per physical simulation reset."""
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from scripts.research_claims import A, D, ROOT, indexed, read


def render(destination):
    from matplotlib.colors import ListedColormap
    measurements = read(A/"common-budget-events.json")
    groups = read(D/"peer-camera-docking/action-value-pilot.json")["scenes"]
    groups = sorted(groups, key=lambda r: (("clean", "queued", "uncertain_transform", "unavailable").index(r["profile"]), r["seed"]))
    trials = indexed(measurements["trials"])
    methods = ("local_only", "immediate_peer", measurements["fixed"], "adaptive")
    labels = ["Local only", "Immediate peer", "Local, then peer", "Adaptive"]
    values = [[int(trials[r["seed"]]["methods"][m]["terminal"]["recipient"] == "success") for r in groups] for m in methods]
    fig, ax = plt.subplots(figsize=(8, 2.65))
    ax.imshow(values, cmap=ListedColormap(["#efdac9","#2e716e"]), aspect="auto", vmin=0, vmax=1)
    for y, m in enumerate(methods):
        for x, row in enumerate(groups):
            events = trials[row["seed"]]["methods"][m]["events"]
            if any(e["stage"] == "requested" for e in events):
                ax.plot(x,y,"o",color="#111111",markeredgecolor="white",markersize=5,markeredgewidth=.7)
        ax.text(15.65,y,f"{sum(values[y])}/16",va="center",fontsize=10)
    for x in (3.5,7.5,11.5):
        ax.axvline(x, color="white", lw=2.5)
    ax.set_xticks([1.5,5.5,9.5,13.5], ["Clean", "Queued", "Uncertain transform", "Unavailable"])
    ax.tick_params(top=True, labeltop=True, bottom=False, labelbottom=False, length=0, pad=5)
    ax.set_yticks(range(4), labels)
    ax.set_xlim(-.5,17)
    ax.set_frame_on(False)
    ax.legend(handles=[Patch(color="#2e716e",label="Docked"),Patch(color="#efdac9",label="Failed"),
                       Line2D([0],[0],color="black",marker="o",ls="",markersize=5,label="Requested peer")],
              loc="upper center",bbox_to_anchor=(.48,-.03),ncol=3,frameon=False)
    fig.subplots_adjust(left=.18,right=.96,top=.84,bottom=.22)
    fig.savefig(destination,dpi=225,bbox_inches="tight",pad_inches=.035)
    plt.close(fig)


if __name__ == "__main__":
    render(Path(ROOT/"docs/paper/figures/common-deadline-docking.png"))
