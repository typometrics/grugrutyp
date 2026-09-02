#!/usr/bin/env python3
"""Cross-check frontend/src/stats.js against scipy.

The plot statistics run in the browser, so pytest never sees them; this script is the
verification. It feeds the same datasets to scipy and to stats.js (via node) and
compares r, rho, both p-values, and the regression. A wrong statistic does not look
wrong — it looks like a typological finding — so run this after touching stats.js.

Needs scipy (`.venv/bin/pip install scipy`; it is a dev tool, not a dependency).
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

from scipy import stats as sp

STATS_JS = Path(__file__).resolve().parent.parent / "frontend" / "src" / "stats.js"

NODE_SNIPPET = """
import { scatterStats } from '%s';
const datasets = JSON.parse(process.argv[1]);
const out = datasets.map(([xs, ys]) =>
  scatterStats(xs.map((x, i) => ({ x, y: ys[i] }))));
console.log(JSON.stringify(out));
"""


def datasets():
    rng = random.Random(20260902)
    sets = []
    # correlated, anticorrelated, near-independent, with ties (values rounded)
    for slope, noise, digits in [(0.8, 5, None), (-1.2, 20, None), (0.0, 30, None), (0.5, 8, 0)]:
        xs = [rng.uniform(0, 100) for _ in range(60)]
        ys = [slope * x + rng.gauss(0, noise) for x in xs]
        if digits is not None:  # force ties to exercise the average-rank path
            xs = [round(x, digits) for x in xs]
            ys = [round(y, digits) for y in ys]
        sets.append((xs, ys))
    sets.append(([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], [2, 1, 4, 3, 6, 5, 8, 7, 10, 9]))  # tiny n
    return sets


def main() -> int:
    sets = datasets()
    node = subprocess.run(
        ["node", "--input-type=module", "-e", NODE_SNIPPET % STATS_JS.as_uri(), json.dumps(sets)],
        capture_output=True, text=True, check=True,
    )
    js_results = json.loads(node.stdout)

    failures = 0
    for i, ((xs, ys), js) in enumerate(zip(sets, js_results)):
        r, r_p = sp.pearsonr(xs, ys)
        rho, rho_p = sp.spearmanr(xs, ys)
        fit = sp.linregress(xs, ys)
        checks = {
            "pearson r": (js["pearson"]["r"], r),
            "pearson p": (js["pearson"]["p"], r_p),
            "spearman rho": (js["spearman"]["rho"], rho),
            "spearman p": (js["spearman"]["p"], rho_p),
            "slope": (js["regression"]["slope"], fit.slope),
            "intercept": (js["regression"]["intercept"], fit.intercept),
            "r2": (js["regression"]["r2"], fit.rvalue**2),
        }
        for name, (ours, theirs) in checks.items():
            tolerance = 1e-9 + 1e-6 * abs(theirs)
            if abs(ours - theirs) > tolerance:
                print(f"MISMATCH set {i} {name}: js={ours!r} scipy={theirs!r}")
                failures += 1
    if failures:
        print(f"{failures} mismatches")
        return 1
    print(f"{len(sets)} datasets, all statistics match scipy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
