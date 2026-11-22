"""Read-only preflight, then a separately invoked frozen simulation comparison."""

import argparse
import json
from pathlib import Path

from .design import PLAN, freeze, preflight


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    pre = subs.add_parser("preflight")
    pre.add_argument("--plan", default=PLAN)
    register = subs.add_parser("freeze")
    register.add_argument("--packet", required=True)
    register.add_argument("--plan", default=PLAN)
    collect = subs.add_parser("collect")
    collect.add_argument("protocol")
    prepare = subs.add_parser("prepare")
    prepare.add_argument("protocol")
    prepare.add_argument("--day", required=True)
    report = subs.add_parser("report")
    report.add_argument("protocol")
    report.add_argument("--study", required=True)
    report.add_argument("--ledger", type=Path)
    report.add_argument("--figure", type=Path)
    size = subs.add_parser("size")
    size.add_argument("--pilot", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "preflight":
        result = preflight(args.plan)
    elif args.command == "freeze":
        result = {"protocol": freeze(args.packet, args.plan)}
    elif args.command == "collect":
        from .examples import collect

        result = collect(args.protocol)
    elif args.command == "prepare":
        from .prepare import prepare

        sid = prepare(args.protocol, args.day)
        result = {
            "study_day": sid,
            "training_started": False,
            "run": ".venv/bin/python -m explorer4.study_day " + sid,
        }
    elif args.command == "size":
        from .accounting import paired_size, verify_reference

        data = json.loads(args.pilot.read_text())
        if data.get("contrast") != "T2-T1 at k=3" or data["domain"] not in ("real", "sim"):
            raise ValueError("Pilot must use the registered primary contrast in one domain")
        if set(data.get("reserved_scene_ids", [])) & {r["scene"] for r in data["pairs"]}:
            raise ValueError("Independent pilot and planned confirmation share a scene")
        for row in data["pairs"]:
            verify_reference(row["evidence"])
        result = paired_size(data["pairs"], domain=data["domain"])
    else:
        from .report import plot, summarize

        result = summarize(
            args.protocol, args.study, json.loads(args.ledger.read_text()) if args.ledger else None
        )
        if args.figure:
            plot(result, args.figure)
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
