"""Build the operator-facing copy of the English register from tracked sources."""

from pathlib import Path
from html import escape
from urllib.parse import urlsplit, quote
import argparse, hashlib, subprocess
from explorer4.paths import ROOT, DATA
from markdown_it import MarkdownIt

repo = ROOT
published = DATA / "simlab/reports/research-register-20261122"
audit = repo / "docs/results/research-audit-20261122"
pages = {
    "RESEARCH_AUDIT.md": ("audit.html", "Audit and paired experiments"),
    "RESEARCH_LINEAGE.md": ("lineage.html", "Sources and code changes"),
    "RESEARCH_REGISTER.md": ("index.html", "Overview"),
    "RESEARCH_REGISTER_LEARNING.md": ("learning.html", "Learning and models"),
    "RESEARCH_REGISTER_ROBOTS.md": ("robots.html", "Robot capabilities"),
    "RESEARCH_REGISTER_ASSISTANCE.md": ("assistance.html", "Selective assistance"),
}
base = "https://github.com/vladromenko/explorer-4.0/blob/"
parser = argparse.ArgumentParser(
    description="Publish the research register with local evidence and permanent code links."
)
parser.add_argument(
    "--historical-source",
    type=Path,
    help="Optional original checkout for publishing the historical source snapshots",
)
args = parser.parse_args()
revision = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
).strip()


def export(name, content):
    dest = published / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_name("." + dest.name + ".new")
    if isinstance(content, str):
        content = content.encode()
    temp.write_bytes(content)
    temp.replace(dest)


def wrap(title, body, root=""):
    nav = " ".join(
        f'<a href="{root}{url}">{escape(label)}</a>' for url, label in pages.values()
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(title)} · Explorer 4</title><style>
html{{color-scheme:light}}body{{font:17px/1.55 'DM Sans',system-ui,sans-serif;color:#1d2b2c;background:#f9faf8;margin:0}}header,main{{max-width:77rem;margin:auto;padding:1rem clamp(1rem,3vw,3.2rem)}}header{{border-bottom:1px solid #ccd7d2}}nav{{display:flex;gap:.9rem;align-items:center;flex-wrap:wrap}}main{{padding-bottom:4rem}}h1{{line-height:1.12;font-size:clamp(1.85rem,4vw,3rem)}}h2{{line-height:1.2;margin:2.2rem 0 .85rem}}a{{color:#095a56;text-decoration-thickness:1px;text-underline-offset:.16em}}p,ul{{max-width:85ch}}code{{overflow-wrap:anywhere;font-size:.87em}}table{{border-collapse:collapse;background:white;width:100%;font-size:.92em}} .table-scroll{{overflow-x:auto}}td,th{{padding:.7em .85em;border:1px solid #d7dfda;text-align:left;vertical-align:top;min-width:10rem}}th{{background:#e6eeea}}h1,p,td{{overflow-wrap:break-word}} li{{margin-bottom:.55rem}} @media (max-width:700px){{td,th{{min-width:12rem}}body{{font-size:16px}}}} </style></head><body><header><nav aria-label="Research register">{nav}</nav></header><main>{body}</main></body></html>"""


md = MarkdownIt("commonmark", {"html": False}).enable("table")


def link_open(tokens, idx, options, env):
    t = tokens[idx]
    href = t.attrGet("href")
    u = urlsplit(href)
    if not u.scheme and u.path:
        target = ((repo / "docs") / u.path).resolve()
        if target.name in pages and target.parent == repo / "docs":
            href = pages[target.name][0]
        elif target.is_relative_to(repo / "docs/results"):
            relative = str(target.relative_to(repo / "docs/results"))
            href = "evidence/" + quote(relative)
            export("evidence/" + relative, target.read_bytes())
        else:
            if not target.exists():
                raise FileNotFoundError(target)
            href = (
                base
                + revision
                + "/"
                + quote(str(target.relative_to(repo)))
                + ("#" + u.fragment if u.fragment else "")
            )
        t.attrSet("href", href)
    return md.renderer.renderToken(tokens, idx, options, env)


md.renderer.rules["link_open"] = link_open
for p in audit.iterdir():
    export("evidence/" + p.name, p.read_bytes())
for name, (dest, title) in pages.items():
    content = md.render((repo / "docs" / name).read_text())
    content = content.replace("<table>", '<div class="table-scroll"><table>').replace(
        "</table>", "</table></div>"
    )
    if dest == "index.html":
        content = content.replace(
            "</h1>",
            '</h1><p><a href="/workspace">Homebrain experiment panel</a> · <a href="/recording/readiness">Physical readiness</a> · <a href="source/index.html">Study source snapshots</a></p>',
            1,
        )
    export(dest, wrap(title, content))
if args.historical_source:
    study = args.historical_source
    rows = []
    for name in [
        "article_trajectory_study",
        "article_help_before_grasp",
        "recorded_start_visual_pick",
        "article_location_act",
        "article_human_prefix_pilot",
    ]:
        raw = (study / "scripts" / (name + ".py")).read_bytes()
        export("source/" + name + ".py.txt", raw)
        rows.append(
            '<tr><td><a href="'
            + name
            + '.py.txt">'
            + name
            + ".py</a></td><td><code>"
            + hashlib.sha256(raw).hexdigest()
            + "</code></td></tr>"
        )
    export(
        "source/index.html",
        wrap(
            "Study source snapshots",
            '<h1>Study source snapshots</h1><p>Read-only copies from the historical Homebrain working tree on 22 November 2026. The source digest identifies these snapshots. Protocol and weight digests are recorded separately in the trial evidence.</p><div class="table-scroll"><table><thead><tr><th>Study script</th><th>SHA-256</th></tr></thead><tbody>'
            + "".join(rows)
            + "</tbody></table></div>",
            "../",
        ),
    )
print("Published", len(pages), "research pages at", revision)
