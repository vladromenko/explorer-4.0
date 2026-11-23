"""Rebuild the README and manuscript tables from the released per-scene observations."""
import argparse
import csv
import json
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "docs/results"
A = D / "research-audit/trials"
G = D / "conditioned_grasp_v1"


def read(path):
    return json.loads(path.read_bytes())


def indexed(rows):
    result = {row["seed"]: row for row in rows}
    if not result or len(result) != len(rows):
        raise ValueError("A comparison needs distinct scene IDs")
    return result


def paired(left, right):
    if set(left) != set(right) or not left:
        raise ValueError("Unequal scene banks")
    return sum(right[k] and not left[k] for k in left), sum(left[k] and not right[k] for k in left)


def claims():
    rows = []
    def add(experiment, values, source):
        rows.append((experiment, values, str(source.relative_to(ROOT))))

    source = A / "common-budget-events.json"
    pilot = read(source)
    budget_rows = indexed(pilot["trials"])
    arms = (pilot["fixed"], "adaptive", "local_only", "immediate_peer")
    outcomes = {}
    calls = {}
    average = {}
    for arm in arms:
        outcomes[arm] = {}
        calls[arm] = 0
        utility = []
        for seed, trial in budget_rows.items():
            branch = trial["methods"][arm]
            events = branch["events"]
            measured_calls = sum(e["stage"] == "requested" for e in events)
            if (branch["protocol_sha256"] != pilot["protocol_sha256"] or measured_calls != branch["calls"]
                    or events[-1]["stage"] != "recipient_outcome" or events[-1]["success"] != (branch["terminal"]["recipient"] == "success")):
                raise ValueError("The branch and its terminal event disagree")
            outcomes[arm][seed] = branch["terminal"]["recipient"] == "success"
            calls[arm] += measured_calls
            utility.append(int(outcomes[arm][seed]) - pilot["prices"]["time_weight"] * branch["seconds"]
                           - pilot["prices"]["help_weight"] * branch["help_units"])
        average[arm] = mean(utility)
    n = len(budget_rows)
    fixed, adaptive, local, immediate = arms
    gain, loss = paired(outcomes[fixed], outcomes[adaptive])
    add("Common-deadline peer docking",
        f"Local {sum(outcomes[local].values())}/{n}, immediate {sum(outcomes[immediate].values())}/{n} "
        f"({calls[immediate]} calls), local-first {sum(outcomes[fixed].values())}/{n} ({calls[fixed]} calls), "
        f"adaptive {sum(outcomes[adaptive].values())}/{n} ({calls[adaptive]} calls). "
        f"Adaptive gained {gain} and lost {loss} vs local-first. Mean utility difference {average[adaptive]-average[fixed]:+.6f}.", source)

    raw = [indexed(read(A / f"raw-act-{name}.json")["trials"]) for name in ("before", "after", "control")]
    if not all(list(bank) == list(range(88300, 88320)) for bank in raw):
        raise ValueError("Historical seed order changed")
    totals = [sum(v["outcome"] == "success" for v in bank.values()) for bank in raw]
    add("Recorded starts, raw ACT", f"Before {totals[0]}/20, skill initialization {totals[1]}/20, scratch {totals[2]}/20. Baseline reset vectors were unavailable.", A / "raw-act-after.json")

    source = G / "optimizer-seed-1001.json"
    matched = indexed(read(source)["blocks"]["fresh"]["scenes"])
    def holds(arm, epoch):
        return sum(row["terminal_holds"][arm][epoch] for row in matched.values())
    add("Fixed-look grasp", f"ACT {holds('act',0)}/{len(matched)} and Diffusion {holds('diffusion',0)}/{len(matched)}. Second optimizer seed on the same scenes gave {holds('act',1)} and {holds('diffusion',1)}. RBF {holds('rbf',0)}, IK {holds('ik',0)}.", source)

    source = G / "field-admission-v3.json"
    data = read(source)
    bank = set(data["conditional"]["source_bank"])
    eligible = {r["seed"] for r in data["candidates"] if r["seed"] in bank and r["eligible"]}
    ran = {k: v for k, v in indexed(data["trials"]).items() if k in bank and v["executed_ticks"] > 0}
    if not set(ran) <= eligible:
        raise ValueError("An ineligible native trial ran")
    add("Native grasp admission", f"{len(eligible)}/{len(bank)} eligible, {len(ran)} executed, {sum(r['terminal_success'] for r in ran.values())} terminal holds. {len(eligible)-len(ran)} eligible starts unexecuted.", source)

    source = A / "peer-confirmation.json"
    peer = read(source)
    recovered = set(peer["shared_first_image_seeds"])
    peer_rows = indexed(peer["rows"])
    strict = read(A / "peer-original-strict.json")
    if recovered != {r["seed"] for r in strict["unmatched"]}:
        raise ValueError("Historical recovery receipt differs")
    for scope, bank_rows in (("original strict", [v for k,v in peer_rows.items() if k not in recovered]),
                             ("including recovery", list(peer_rows.values()))):
        totals = []
        for arm in ("learned", "sequential", "immediate_peer"):
            m = [v["methods"][arm] for v in bank_rows]
            totals.append(f"{sum(r['success'] for r in m)}/{len(m)}, {sum(r['calls'] for r in m)} calls, {mean(r['utility'] for r in m):.5f}")
        add(f"Peer docking, {scope}", "Learned / local-first / always peer, each reported as success, calls and utility. " + " | ".join(totals) + ".", source)

    source = D / "knowledge_gap_sim/20261122-e1/cells.csv"
    with source.open() as f:
        rooms = list(csv.DictReader(f))
    K = {}
    for condition in ("K0","K1","K2","K3","K5"):
        group = indexed([r for r in rooms if r["condition"] == condition])
        K[condition] = {k: r["delivered"] == "True" for k,r in group.items()}
    numbers = ", ".join(f"{k} {sum(g.values())}/{len(g)}" for k,g in K.items())
    comparisons = [paired(K[k], K["K3"]) for k in ("K2","K5")]
    add("2D delivery, matched rooms", numbers + f". K3 gained {comparisons[0][0]} and lost {comparisons[0][1]} against K2, gained {comparisons[1][0]} and lost {comparisons[1][1]} against K5.", source)

    source = D / "research-audit-20261122/tank-nav2-camera.json"
    nav = read(source)
    nav_rows = indexed(nav["by_seed"])
    corrected = set(nav["shared_initial_recovery"]["corrected_seeds"])
    def count_nav(arm, exclude):
        return sum(r["outcomes"][arm] == "success" for k,r in nav_rows.items() if k not in exclude)
    nav_arms = ("nav2_memory","ppo_memory")
    add("Docking with common visual memory", f"Nav2 control law / PPO achieved {' / '.join(str(count_nav(arm,corrected)) for arm in nav_arms)} on {len(nav_rows)-len(corrected)} strict scenes, {' / '.join(str(count_nav(arm,())) for arm in nav_arms)} on all {len(nav_rows)} including RGB recovery.", source)

    source = G / "native-residual/result.json"
    native = read(source)
    arms = [indexed([r for r in native["fresh_trials"] if r["correction"] == variant])
            for variant in ([0,0],native["parameters"])]
    retention = [{k: r["retained"] for k,r in group.items()} for group in arms]
    plus, minus = paired(*retention)
    add("Bounded motor correction", f"Terminal bilateral carry, original {sum(retention[0].values())}/{len(arms[0])}, fitted {sum(retention[1].values())}/{len(arms[1])}. {plus} gained and {minus} lost. Among {native['fresh_screen']['eligible']} eligible of {native['fresh_screen']['candidates']} assigned.", source)

    source = A / "active-view-fresh.json"
    views = indexed(read(source))
    add("A second camera pose", f"Full target seen {sum(v['base']['full'] for v in views.values())} to {sum(v['active_full'] for v in views.values())} on {len(views)} assigned. Strict holds {sum(v['base_outcome']['hold'] for v in views.values())} to {sum(v['active_outcome']['hold'] for v in views.values())}.", source)

    source = G / "wrist-heatmap/result.json"
    wrist = indexed(read(source)["rows"])
    scores = [{k:r["methods"][arm]["native"]["terminal_success"] for k,r in wrist.items()} for arm in ("baseline","keypoint")]
    plus, minus = paired(*scores)
    add("Learned RGB keypoint", f"Native unrestricted holds {sum(scores[0].values())} to {sum(scores[1].values())} on {len(wrist)} fresh scenes. {plus} gained and {minus} lost.", source)

    source = A / "recovery-monitor.json"
    monitor = indexed(read(source)["pairs"])
    unchanged = {k:r["stale_hold"] for k,r in monitor.items()}
    relook = {k:r["recovery_hold"] for k,r in monitor.items()}
    plus, minus = paired(unchanged, relook)
    alarms = {name: {k:r["decisions"][name]["first_alarm"] is not None for k,r in monitor.items()}
              for name in ("tracker","visual_probe")}
    failures = sum(not win for win in unchanged.values())
    false = sum(v and unchanged[k] for k,v in alarms["visual_probe"].items())
    missed = sum(not v and not unchanged[k] for k,v in alarms["visual_probe"].items())
    add("Pre-closure reobservation", f"First stable carries {sum(unchanged.values())} to {sum(relook.values())} on {len(monitor)} starts. "
        f"The return gained {plus} and lost {minus}. RGB probe missed {missed}/{failures} failures and raised {false} false alarms. "
        f"Template tracker issued {sum(alarms['tracker'].values())} alarms.",source)

    source = A / "human11-results.json"
    trials = indexed(read(source)["scenes"])
    hp = read(A / "human-prefix-plan.json")
    prefixes = len(hp["prefixes"])
    count = [sum(r[arm]["outcome"] == "success" for r in trials.values()) for arm in ("T0","T1")]
    add("Archived human sequences", f"{hp['split_counts']['train']-prefixes} full takes and {prefixes} prefixes. Scratch {count[0]}/{len(trials)}, pretrained {count[1]}/{len(trials)} terminal holds in MuJoCo.", source)
    return rows


def render(rows):
    md = ["| Experiment | Per-scene result |", "| --- | --- |"]
    latex = [r"\begin{table*}[t]", r"\centering\footnotesize", r"\caption{Evidence computed from archived simulator outcomes. Each denominator refers to its own registered scene bank.}",
             r"\begin{tabular}{@{}p{.24\textwidth}p{.71\textwidth}@{}}\hline",r"Comparison & Measured outcome \\\hline"]
    for name, value, source in rows:
        clean = value.replace(" | ", " / ")
        md.append(f"| {name} | {clean} [Rows]({source}) |")
        latex.append(f"{name} & {clean}" + r" \\")
    latex.extend([r"\hline\end{tabular}",r"\end{table*}"])
    return "\n".join(md), "\n".join(latex)


def update(path, begin, end, content, write):
    old = path.read_text()
    if old.count(begin) != 1 or old.count(end) != 1:
        raise ValueError(f"Missing table boundaries in {path}")
    before, middle = old.split(begin)
    _, after = middle.split(end)
    new = before + begin + "\n" + content + "\n" + end + after
    if write:
        path.write_text(new)
    elif old != new:
        raise ValueError(f"Table is stale: {path}")


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--write", action="store_true")
    args.add_argument("--check", action="store_true")
    mode = args.parse_args()
    markdown, tex = render(claims())
    if mode.write or mode.check:
        update(ROOT/"README.md", "<!-- measured-results -->", "<!-- end-measured-results -->", markdown, mode.write)
        update(ROOT/"docs/paper/peer-assisted-robots.tex", "% measured-results", "% end-measured-results", tex, mode.write)
    else:
        print(markdown)
