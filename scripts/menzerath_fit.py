#!/usr/bin/env python3
"""Fit the Menzerath–Altmann law per language, the D-class measure of the old site.

    mean constituent size  y(x) = a · x^b · e^(−c·x)        x = dependents of the verb

The old site ships fitted `a`, `b`, `c` per language in
`abc.languages.*_typometricsformat.tsv`; the presets in this repo plot the *raw*
quantities (mean constituent size, mean dependents per verb), never the fitted curve.
This script closes that gap.

The data comes out of the database in one grouped query per treebank: cluster
`pattern { V [upos=VERB]; V -> DEP }` by `V.n_children` × `DEP.subtree_size`, which is
the full joint distribution, from which the per-x mean constituent size follows exactly.
Fitting is then linear least squares on

    ln y = ln a + b·ln x − c·x

so there is no optimiser to babysit and no starting point to choose. Points with x < 1
or y <= 0 cannot be logged and are dropped; a language needs `--min-points` distinct
values of x to be fitted at all.

    .venv/bin/python scripts/menzerath_fit.py                  # every SUD language
    .venv/bin/python scripts/menzerath_fit.py --languages French English
    .venv/bin/python scripts/menzerath_fit.py --side left      # left dependents only

Output: `data/meta/menzerath_abc.tsv` (tracked; it is small and it is a result).
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

OUT = Path(__file__).resolve().parent.parent / "data" / "meta" / "menzerath_abc.tsv"

SCOPES = {
    # every verb-dependent pair; the side variants use the order of DEP against V
    "any": "pattern { V [upos=VERB]; V -> DEP }",
    "left": "pattern { V [upos=VERB]; V -> DEP }\nwith { DEP << V }",
    "right": "pattern { V [upos=VERB]; V -> DEP }\nwith { V << DEP }",
}


def fit_abc(points: list[tuple[float, float, int]]) -> dict | None:
    """Least squares for ln y = ln a + b·ln x − c·x over (x, y, weight) triples.

    Returns a, b, c and the fit's R² on the log scale, or None when the system is
    underdetermined (fewer than three distinct x, or a degenerate design).
    """
    rows = [(x, y, w) for x, y, w in points if x >= 1 and y > 0 and w > 0]
    if len({x for x, _, _ in rows}) < 3:
        return None
    # normal equations for the design [1, ln x, −x], weighted by the number of
    # constituents behind each mean (a mean over 5 000 pairs should outweigh one over 3)
    n = len(rows)
    design = [(1.0, math.log(x), -x) for x, _, _ in rows]
    target = [math.log(y) for _, y, _ in rows]
    weights = [float(w) for _, _, w in rows]

    ata = [[sum(weights[i] * design[i][r] * design[i][c] for i in range(n)) for c in range(3)]
           for r in range(3)]
    atb = [sum(weights[i] * design[i][r] * target[i] for i in range(n)) for r in range(3)]

    # Gaussian elimination with partial pivoting on a 3x3 -- no numpy dependency here
    m = [row[:] + [atb[i]] for i, row in enumerate(ata)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            return None
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(3):
            if r == col:
                continue
            factor = m[r][col] / m[col][col]
            for k in range(col, 4):
                m[r][k] -= factor * m[col][k]
    solution = [m[i][3] / m[i][i] for i in range(3)]
    ln_a, b, c = solution

    mean_y = sum(weights[i] * target[i] for i in range(n)) / sum(weights)
    ss_tot = sum(weights[i] * (target[i] - mean_y) ** 2 for i in range(n))
    ss_res = sum(
        weights[i] * (target[i] - (ln_a + b * design[i][1] - c * rows[i][0])) ** 2
        for i in range(n)
    )
    return {
        "a": math.exp(ln_a),
        "b": b,
        "c": c,
        "n_points": n,
        "n_pairs": int(sum(weights)),
        "r2": 1 - ss_res / ss_tot if ss_tot > 0 else float("nan"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheme", default="SUD")
    parser.add_argument("--side", default="any", choices=sorted(SCOPES))
    parser.add_argument("--languages", nargs="*", help="default: all")
    parser.add_argument("--min-points", type=int, default=3)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    from grugrutyp.engine.neo4j_engine import get_engine
    from grugrutyp.runner import RunOptions, select

    engine = get_engine()
    chosen = select(RunOptions(scheme=args.scheme))  # exclusions apply, as everywhere
    by_language: dict[str, list] = defaultdict(list)
    for tb in chosen:
        if not args.languages or tb.language in args.languages:
            by_language[tb.language].append(tb)

    scope = SCOPES[args.side]
    keys = [{"kind": "key", "value": "V.n_children"}, {"kind": "key", "value": "DEP.subtree_size"}]
    results = []
    for i, (language, treebanks) in enumerate(sorted(by_language.items()), start=1):
        # sum the joint distribution across the language's treebanks, which is the same
        # merge rule the rest of the system uses: counts add, never percentages
        joint: dict[tuple[int, int], int] = defaultdict(int)
        for tb in treebanks:
            try:
                for (n_children, size), count in engine.cluster(tb.name, scope, keys).items():
                    if n_children is None or size is None:
                        continue
                    joint[(int(n_children), int(size))] += count
            except Exception as exc:  # noqa: BLE001 -- one treebank must not stop the run
                print(f"  {tb.name}: {type(exc).__name__}: {exc}", file=sys.stderr)

        per_x: dict[int, list[int]] = defaultdict(lambda: [0, 0])  # x -> [Σ size, Σ count]
        for (x, size), count in joint.items():
            per_x[x][0] += size * count
            per_x[x][1] += count
        points = [(x, total / count, count) for x, (total, count) in per_x.items() if count]
        fit = fit_abc(points) if len(points) >= args.min_points else None
        if fit:
            results.append({"language": language, **fit})
        print(
            f"[{i}/{len(by_language)}] {language:24} "
            + (f"a={fit['a']:6.2f} b={fit['b']:6.3f} c={fit['c']:6.3f} "
               f"R2={fit['r2']:.3f} ({fit['n_pairs']:,} pairs)" if fit else "not enough data"),
            flush=True,
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as fh:
        fh.write("language\tside\ta\tb\tc\tr2\tn_points\tn_pairs\n")
        for row in results:
            fh.write(
                f"{row['language']}\t{args.side}\t{row['a']:.4f}\t{row['b']:.4f}\t"
                f"{row['c']:.4f}\t{row['r2']:.4f}\t{row['n_points']}\t{row['n_pairs']}\n"
            )
    print(f"\n{len(results)} languages fitted -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
