#!/usr/bin/env python3
"""The welcome page's hero figure: Greenberg's verb–object / adposition correlation.

    x = % of nominal objects after their verb        VERB -comp:obj-> NOUN, V << N
    y = % of adpositions before their nominal object  ADP  -comp:obj-> NOUN, A << N

computed in SUD straight from the CoNLL-U on disk (no database, so it can be drawn for a
release before its import finishes). Counts are summed per language, never averaged
(CLAUDE.md), `measure_exclusions.tsv` is honoured, and a language needs `--min` cases on
both axes. The same plot opens live in grugrutyp from the page's "open this plot" link,
whose Grew pair is `GREW_X` / `GREW_Y` below -- keep them in step with the counting.

    GRUGRUTYP_VERSION=2.19 .venv/bin/python scripts/welcome_plot.py
    -> welcome/hero-plot.svg, welcome/hero-plot.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from grugrutyp import langconfig  # noqa: E402
from grugrutyp.conllu import decompose_deprel, read_conllu  # noqa: E402
from grugrutyp.meta import CORPUS_VERSION, treebanks  # noqa: E402

OUT = ROOT / "welcome"

GREW_X = {
    # verbatim the Findings tab's Grew text, so the "open this plot" link hits the cache
    # NOUN|PROPN|ADP: in SUD a case particle heads its noun, so a Japanese object is
    # VERB -comp:obj-> ADP. NOUN alone drops every case-marked object (and Japanese).
    "s": "pattern { GOV [upos=VERB]; GOV -[1=comp,2=obj]-> DEP [upos=NOUN|PROPN|ADP] }",
    "q": "with { GOV << DEP }",
    "l": "nominal objects after the verb (%)",
}
GREW_Y = {
    # `-[1=comp]->`, not `comp:obj`: SUD 2.19 relabelled every function word's complement
    # from comp:obj to bare comp (docs/data-intake.md §2b); [1=comp] matches both releases.
    "s": "pattern { GOV [upos=ADP]; GOV -[1=comp]-> DEP [upos=NOUN] }",
    "q": "with { GOV << DEP }",
    "l": "adpositions before their noun (%)",
}

# Points labelled one by one: the spread-out, telling cases. The two crowded corners get
# one group label each instead (CLUSTERS), placed in empty space -- per-point labels there
# overprint. Only languages that made the threshold are named.
LABELLED = ["German", "Persian", "Chinese", "Basque"]
CLUSTERS = [
    # (corner test, preferred names, label position x, y, anchor)
    (lambda p: p["x"] > 85 and p["y"] > 85, ["English", "French", "Arabic", "Wolof", "Indonesian"], 93, 84, "end"),
    (lambda p: p["x"] < 10 and p["y"] < 10, ["Japanese", "Korean", "Turkish", "Hindi", "Tamil"], 6, 34, "start"),
]


def count(min_cases: int) -> list[dict]:
    excluded = langconfig.measure_exclusions()
    acc: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])  # vo_n, vo_hit, adp_n, adp_hit
    lcode_of: dict[str, str] = {}
    for tb in treebanks(CORPUS_VERSION).values():
        if tb.scheme != "SUD" or (tb.language, tb.corpus) in excluded:
            continue
        lcode_of.setdefault(tb.language, tb.lcode)
        a = acc[tb.language]
        for path in sorted(tb.path.glob("*.conllu")):
            for sent in read_conllu(path):
                upos = {w.idx: w.upos for w in sent.words}
                for w in sent.words:
                    if not w.head:
                        continue
                    rel = decompose_deprel(w.deprel)
                    if rel.get("rel_1") != "comp":
                        continue
                    head_pos = upos.get(w.head)
                    if head_pos == "VERB" and rel.get("rel_2") == "obj" and w.upos in ("NOUN", "PROPN", "ADP"):
                        a[0] += 1
                        a[1] += w.head < w.idx
                    elif head_pos == "ADP" and w.upos == "NOUN":
                        a[2] += 1
                        a[3] += w.head < w.idx
        print(f"  {tb.name}", file=sys.stderr, flush=True)
    points = []
    for lang, (vo_n, vo_hit, adp_n, adp_hit) in sorted(acc.items()):
        if vo_n < min_cases or adp_n < min_cases:
            continue
        look = langconfig.appearance_of(lang, lcode=lcode_of.get(lang, ""))
        row = langconfig.row_for(lang, lcode_of.get(lang, ""))
        points.append({
            "language": lang.replace("_", " "),
            "x": round(100 * vo_hit / vo_n, 1),
            "y": round(100 * adp_hit / adp_n, 1),
            "n_x": vo_n,
            "n_y": adp_n,
            "family": look.label,
            "color": look.color,
            "historical": bool(row and row.is_historical),
        })
    return points


# Self-contained so the file reads right as an <img> too (no page CSS reaches into it).
# `--c` is the family colour from appearance.tsv, a CSS colour name.
STYLE = """
.frame{fill:none;stroke:#c9ccd1}.grid{stroke:#e6e8eb;stroke-width:1}
.tick{font:11px system-ui,sans-serif;fill:#5b6168}
.axis{font:600 12.5px system-ui,sans-serif;fill:#30353b}
.corner{font:italic 13px Georgia,serif;fill:#5b6168}
.pt{fill:var(--c);fill-opacity:.78;stroke:#fff;stroke-width:.8}
.pt.hist{fill-opacity:.15;stroke:var(--c);stroke-width:1.4}
.pt:hover{fill-opacity:1;stroke:#111;stroke-width:1.4}
.lab{font:11.5px system-ui,sans-serif;fill:#30353b;paint-order:stroke;stroke:#fff;stroke-width:3px}
@media (prefers-color-scheme:dark){
.frame{stroke:#454b52}.grid{stroke:#2b3036}.tick{fill:#9aa1a9}.axis{fill:#d5d9de}
.corner{fill:#9aa1a9}.pt{stroke:#16191d}.pt:hover{stroke:#fff}
.lab{fill:#d5d9de;stroke:#16191d}
.pt[style$=":black"]{fill:#c9ccd1}.pt.hist[style$=":black"]{fill:none;stroke:#c9ccd1}}
"""


def svg(points: list[dict]) -> str:
    w, h = 560, 520
    left, right, top, bottom = 64, 20, 20, 58
    pw, ph = w - left - right, h - top - bottom

    def px(v: float) -> float:
        return left + pw * v / 100

    def py(v: float) -> float:
        return top + ph * (1 - v / 100)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" '
        f'aria-labelledby="hero-title hero-desc" class="hero-plot">',
        '<title id="hero-title">Objects after the verb vs. prepositions, one point per language</title>',
        f'<desc id="hero-desc">{len(points)} languages. Languages that put objects after the '
        "verb also put adpositions before the noun, and vice versa: the points gather in two "
        "opposite corners.</desc>",
        f"<style>{STYLE}</style>",
        f'<rect x="{left}" y="{top}" width="{pw}" height="{ph}" class="frame"/>',
    ]
    for t in range(0, 101, 25):
        out.append(f'<line x1="{px(t)}" y1="{top}" x2="{px(t)}" y2="{top + ph}" class="grid"/>')
        out.append(f'<line x1="{left}" y1="{py(t)}" x2="{left + pw}" y2="{py(t)}" class="grid"/>')
        out.append(f'<text x="{px(t)}" y="{top + ph + 18}" class="tick" text-anchor="middle">{t}</text>')
        out.append(f'<text x="{left - 8}" y="{py(t) + 4}" class="tick" text-anchor="end">{t}</text>')
    out.append(
        f'<text x="{left + pw / 2}" y="{h - 12}" class="axis" text-anchor="middle">'
        "nominal objects after the verb (%)</text>"
    )
    out.append(
        f'<text transform="translate(16 {top + ph / 2}) rotate(-90)" class="axis" '
        'text-anchor="middle">adpositions before the noun (%)</text>'
    )
    for test, names, lx, ly, anchor in CLUSTERS:
        members = [p for p in points if test(p)]
        named = [n for n in names if any(p["language"] == n for p in members)][:4]
        if not members:
            continue
        arrow = "↗ " if anchor == "end" else "↙ "
        text = f"{len(members)} languages: {', '.join(named)} …"
        out.append(
            f'<text x="{px(lx):.1f}" y="{py(ly):.1f}" class="corner" text-anchor="{anchor}">'
            f'{escape(arrow + text if anchor == "start" else text + " " + arrow.strip())}</text>'
        )
    for p in sorted(points, key=lambda p: p["n_x"] + p["n_y"]):
        cls = "pt hist" if p["historical"] else "pt"
        title = escape(f'{p["language"]} ({p["family"]}): {p["x"]}% VO, {p["y"]}% prepositions')
        out.append(
            f'<circle cx="{px(p["x"]):.1f}" cy="{py(p["y"]):.1f}" r="4.2" class="{cls}" '
            f'style="--c:{p["color"]}"><title>{title}</title></circle>'
        )
    by_name = {p["language"]: p for p in points}
    for name in LABELLED:
        p = by_name.get(name)
        if not p:
            continue
        anchor = "end" if p["x"] > 80 else "start"
        dx = -7 if anchor == "end" else 7
        out.append(
            f'<text x="{px(p["x"]) + dx:.1f}" y="{py(p["y"]) + 4:.1f}" class="lab" '
            f'text-anchor="{anchor}">{escape(name)}</text>'
        )
    out.append("</svg>")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min", type=int, default=30, dest="min_cases")
    ap.add_argument("--from-json", action="store_true",
                    help="redraw the SVG from welcome/hero-plot.json without recounting")
    args = ap.parse_args()
    if args.from_json:
        points = json.loads((OUT / "hero-plot.json").read_text())["points"]
        (OUT / "hero-plot.svg").write_text(svg(points))
        print(f"redrawn: {len(points)} languages")
        return 0
    points = count(args.min_cases)
    OUT.mkdir(exist_ok=True)
    (OUT / "hero-plot.svg").write_text(svg(points))
    vo = [p for p in points if p["x"] > 65]
    ov = [p for p in points if p["x"] < 35]
    summary = {
        "n": len(points),
        "vo": len(vo), "vo_prep": sum(p["y"] > 65 for p in vo),
        "ov": len(ov), "ov_postp": sum(p["y"] < 35 for p in ov),
    }
    (OUT / "hero-plot.json").write_text(json.dumps({
        "summary": summary,
        "version": CORPUS_VERSION,
        "scheme": "SUD",
        "min_cases": args.min_cases,
        "x": GREW_X,
        "y": GREW_Y,
        "points": points,
    }, ensure_ascii=False, indent=1))
    print(f"{len(points)} languages, UD/SUD {CORPUS_VERSION} -> {OUT}/hero-plot.svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
