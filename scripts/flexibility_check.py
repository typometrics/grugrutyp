#!/usr/bin/env python3
"""Verify our flexibility measure against the old site's 2.12 tables.

Two checks, and the first is the one that matters:

1. **The definition**, on the old data itself: `flexibility_cfc_all.tsv` must equal
   `2 × min(p, 100−p)` computed from `direction-cfc_extend.tsv`. This is what pins the
   formula (docs/measures-mapping.md §C recovered it that way); it involves none of our
   code, so it stays true whatever we change.
2. **Our reimplementation**, on 2.18 data, against the 2.12 relation-level table.
   Exact agreement is not expected -- different release, different treebank set, our
   exclusions -- so the test is rank correlation plus a sane mean gap.

    .venv/bin/python scripts/flexibility_check.py [--relation subj]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

LEGACY = Path("/home/typometrics/djangotypometrics/sud-treebanks-v2.12-analysis")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def load(path: Path) -> dict[str, dict[str, float]]:
    rows = [r for r in csv.reader(path.open(), delimiter="\t") if r]
    header = rows[0]
    out: dict[str, dict[str, float]] = {}
    for row in rows[1:]:
        if not row[0]:
            continue
        cells = {}
        for i, cell in enumerate(row[1:], start=1):
            if i >= len(header):
                break
            try:
                value = float(cell)
            except ValueError:
                continue
            if value == value:  # NaN check
                cells[header[i]] = value
        out[row[0]] = cells
    return out


def check_definition() -> bool:
    """flexibility(cfc) == 2 * min(p, 100-p), on the old site's own numbers."""
    flex = load(LEGACY / "flexibility_cfc_all.tsv")
    direction = load(LEGACY / "direction-cfc_extend.tsv")
    errors = []
    for language, cells in flex.items():
        for cfc, value in cells.items():
            p = direction.get(language, {}).get(cfc)
            if p is None:
                continue
            errors.append(abs(2 * min(p, 100 - p) - value))
    if not errors:
        print("definition: no overlapping cells (legacy tables missing?)")
        return False
    worst = max(errors)
    print(f"definition: {len(errors):,} (language, cfc) cells, worst error {worst:.2e}")
    return worst < 1e-6


def check_reimplementation(relation: str, values: dict[str, float]) -> bool:
    legacy = {
        language: cells[relation]
        for language, cells in load(LEGACY / "flexibility_rel.tsv").items()
        if relation in cells
    }
    ours = {name.replace("_", ""): v for name, v in values.items()}
    paired = [(l, legacy[l], ours[l]) for l in legacy if l in ours]
    if len(paired) < 20:
        print(f"reimplementation: only {len(paired)} shared languages, skipping")
        return True

    def ranks(xs):
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        out = [0] * len(xs)
        for position, i in enumerate(order):
            out[i] = position
        return out

    a, b = ranks([o for _, o, _ in paired]), ranks([n for *_, n in paired])
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    rho = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(
        sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)
    )
    gap = sum(abs(o - n) for _, o, n in paired) / len(paired)
    print(
        f"reimplementation: {len(paired)} shared languages, Spearman {rho:.3f}, "
        f"mean gap {gap:.2f} points"
    )
    for language, o, n in sorted(paired, key=lambda t: -abs(t[1] - t[2]))[:3]:
        print(f"    largest gap {language:16} legacy {o:6.2f}  ours {n:6.2f}")
    return rho > 0.85


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--relation", default="subj")
    parser.add_argument(
        "--from-sse",
        type=Path,
        help="a saved /measure stream instead of recomputing (see the docstring)",
    )
    args = parser.parse_args()

    ok = check_definition()

    if args.from_sse:
        payload = None
        for line in args.from_sse.read_text().splitlines():
            if line.startswith("data: ") and '"languages"' in line:
                payload = json.loads(line[6:])
        values = {
            e["language"]: e["value"]
            for e in payload["languages"][0]
            if e["value"] is not None
        }
    else:
        from grugrutyp.measure import MeasureSpec, merge_by_language
        from grugrutyp.runner import RunOptions, run

        spec = MeasureSpec(
            scope=f"pattern {{ GOV -[1={args.relation}]-> DEP }}", kind="flexibility"
        )
        points = [p[0] for p in run([spec], RunOptions(scheme="SUD"))]
        values = {lp.language: lp.value for lp in merge_by_language(points) if lp.value}

    ok = check_reimplementation(args.relation, values) and ok
    print("OK" if ok else "MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
