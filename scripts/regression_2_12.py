#!/usr/bin/env python3
"""Compare grugrutyp's head-initiality against the current site's precomputed tables.

    python3 scripts/regression_2_12.py --scheme SUD --relations subj comp:obj mod

**Head-initiality is the right measure to compare on**, and deliberately the only one
offered here. It is a per-relation ratio, so it is immune to the root-node question that
`docs/measures-mapping.md` section 2 point 1 is about: a `subj` edge never originates at
Grew's virtual root, so both systems are counting the same thing without any adjustment.
`distribution` and `cat` would need the exclusion replayed, and a disagreement there would
be ambiguous between a real bug and a mis-replayed convention.

**This is not a pass/fail test, and it must not be turned into one.** The old tables are
UD/SUD **2.12**; the database is **2.18**. Six releases changed annotations, added
treebanks to existing languages, and re-tokenised some. A language moving by a few points
is expected and says nothing. What the comparison is actually good for:

* a **systematic** offset -- every language shifted the same way -- which is a convention
  mismatch on our side, not six releases of annotation work;
* a **sign flip** or a value near `100 - old`, which means a direction convention is
  inverted somewhere;
* a language that moves by 40 points on its own, which is worth opening the treebank for.

So the script prints the comparison and the summary statistics, and leaves the judgement
to a person. `tests/test_regression.py` asserts only the systematic part.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from grugrutyp import langconfig  # noqa: E402
from grugrutyp.measure import MeasureSpec, SamplingPolicy, merge_by_language  # noqa: E402
from grugrutyp.runner import RunOptions, run  # noqa: E402

OLD = Path("/home/typometrics/djangotypometrics")
TABLES = {
    # The two schemes named the file differently; the contents are the same measure.
    "SUD": OLD / "sud-treebanks-v2.12-analysis" / "head_initiality_comb.tsv",
    "UD": OLD / "ud-treebanks-v2.12-analysis" / "positive-direction.tsv",
}


def load_table(path: Path) -> dict[str, dict[str, float]]:
    """`{folded language: {relation: percentage}}` from a 2.12 analysis TSV."""
    lines = path.read_text(encoding="utf-8").rstrip("\n").split("\n")
    relations = lines[0].split("\t")[1:]
    out: dict[str, dict[str, float]] = {}
    for line in lines[1:]:
        cells = line.split("\t")
        language = cells[0]
        if not language:
            continue
        values = {}
        for relation, cell in zip(relations, cells[1:]):
            if cell.strip():
                values[relation] = float(cell)
        out[langconfig._fold(language)] = values
    return out


def grew_scope(relation: str, scheme: str) -> str:
    """`comp:obj` -> `-[1=comp, 2=obj]->`, `subj` -> `-[1=subj]->`.

    The old pipeline counted each dependency under both its simple function and its
    syntactic one, which is exactly the distinction Grew's edge feature structure makes
    natively (`docs/grew-query-language.md` section 1). The `@deep` part is dropped: the
    old tables have no column for it.
    """
    main = relation.split("@")[0]
    first, _, second = main.partition(":")
    label = f"1={first}" + (f", 2={second}" if second else "")
    return f"pattern {{ GOV -[{label}]-> DEP }}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scheme", default="SUD", choices=["SUD", "UD"])
    ap.add_argument("--relations", nargs="+", default=None)
    ap.add_argument("--min-scope", type=int, default=100)
    ap.add_argument("--budget", type=int, default=0, help="0 = exact, no sampling")
    args = ap.parse_args()

    table = load_table(TABLES[args.scheme])
    relations = args.relations or (["subj", "comp:obj", "mod"] if args.scheme == "SUD"
                                   else ["nsubj", "obj", "amod"])

    all_deltas = []
    for relation in relations:
        spec = MeasureSpec(scope=grew_scope(relation, args.scheme), response="with { GOV << DEP }")
        options = RunOptions(
            scheme=args.scheme,
            policy=SamplingPolicy(token_budget=args.budget or None, min_scope=args.min_scope),
        )
        points = [group[0] for group in run([spec], options)]

        rows = []
        for merged in merge_by_language(points):
            if merged.n_scope < args.min_scope:
                continue
            old = table.get(langconfig._fold(merged.language), {}).get(relation)
            if old is None:
                continue
            rows.append((merged.language, old, merged.value, merged.value - old, merged.n_scope))

        if not rows:
            print(f"\n{relation}: no language in common with the 2.12 table")
            continue

        deltas = [row[3] for row in rows]
        all_deltas += deltas
        rows.sort(key=lambda row: -abs(row[3]))

        print(f"\n=== {relation} ({args.scheme}) — {len(rows)} languages in common ===")
        print(f"{'language':<22}{'2.12':>9}{'2.18':>9}{'delta':>9}{'n_scope':>10}")
        for language, old, new, delta, n_scope in rows[:12]:
            print(f"{language:<22}{old:9.2f}{new:9.2f}{delta:+9.2f}{n_scope:>10,}")
        if len(rows) > 12:
            print(f"  … {len(rows) - 12} more, all closer than {abs(rows[11][3]):.2f}")
        print(
            f"  median delta {statistics.median(deltas):+.2f}"
            f" · mean |delta| {statistics.fmean(abs(d) for d in deltas):.2f}"
            f" · within 5 points: {sum(abs(d) <= 5 for d in deltas)}/{len(deltas)}"
        )

    if all_deltas:
        median = statistics.median(all_deltas)
        print(
            f"\nOVERALL median delta {median:+.2f} over {len(all_deltas)} language-relation pairs."
        )
        # A median near zero is the claim worth making: the two systems agree on where the
        # centre is, and the spread is six releases of annotation.
        print(
            "A median near zero means no systematic convention mismatch; the spread is\n"
            "2.12-vs-2.18 annotation drift and is expected."
            if abs(median) < 2
            else "A median this far from zero suggests a convention mismatch, not drift."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
