#!/usr/bin/env python3
"""The Menzerath–Altmann measures of Faghiri, Gerdes & Kahane (UDW26), per language.

Reimplements the paper behind `/menzerath/` (`typometrics/UDW26-Menzerath`) so its
central result — MAL behaves differently before and after the verb — becomes an axis in
grugrutyp, crossable with every other measure the tool computes.

Why a file pass rather than a query: the paper's constituent is not "a dependent" and
its size is not our stored `subtree_size`. Dependents bearing `punct`, `discourse`,
`parataxis`, `conj`, `cc`, `vocative`, `aux`, `compound`, `mark` or `case` are excluded
(`dislocated` is kept); size counts the dependent's subtree *without* punctuation; and a
subtree split by intervening material counts as two constituents. None of that is
expressible through the properties we precompute, and the paper's own pipeline is a
Python pass for the same reason.

Definitions (paper §3–5):

    MAL_n(L)   mean constituent size over verbal constructions with n constituents,
               computed only where the language has >= MIN_CONFIGURATIONS of them
    beta       -slope of log(MAL_n) against log(n), over all available n  [beta(1->inf)]
               MAL if beta > 0.1, anti-MAL if beta < -0.1, else grey zone
    LMAL/RMAL  the same, restricted to the preverbal / postverbal constituents, with n
               counting only that side (regardless of what the other side holds)
    compliance share of consecutive n where MAL_{n+1} <= MAL_n (regression-free)

Runs on **UD**, not SUD: the relation filter above is UD's, and the paper used UD 2.17.

    .venv/bin/python scripts/mal_udw26.py                 # every UD language
    .venv/bin/python scripts/mal_udw26.py --languages English Japanese
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

ROOT = Path(__file__).resolve().parent.parent
TREEBANKS = ROOT / "data" / "treebanks" / "v2.18"
OUT = ROOT / "data" / "meta" / "mal_udw26.tsv"

# Paper §3: dependents that are not constituents of the verbal construction.
EXCLUDED_RELATIONS = frozenset(
    {"punct", "discourse", "parataxis", "conj", "cc", "vocative", "aux", "compound",
     "mark", "case"}
)
MIN_CONFIGURATIONS = 100  # paper §4: below this, MAL_n is not computed for that n
MAL_THRESHOLD = 0.1       # paper §4: |beta| <= 0.1 is the grey zone


def sentences(path: Path):
    """(id -> (head, deprel, upos, is_punct)) per sentence; MWT and empty nodes skipped."""
    tokens: dict[int, tuple[int, str, str, bool]] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            if tokens:
                yield tokens
                tokens = {}
            continue
        if line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 8 or "-" in cols[0] or "." in cols[0]:
            continue
        try:
            index, head = int(cols[0]), int(cols[6])
        except ValueError:
            continue
        deprel = cols[7].split(":")[0]
        tokens[index] = (head, deprel, cols[3], deprel == "punct")
    if tokens:
        yield tokens


def constituents_of(verb: int, tokens: dict) -> list[tuple[int, int]]:
    """(size without punctuation, position) for each constituent of one verb.

    Position is -1 preverbal, +1 postverbal. A dependent whose subtree is split by
    intervening material contributes one constituent per contiguous run (paper §3).
    """
    children: dict[int, list[int]] = defaultdict(list)
    for index, (head, _, _, _) in tokens.items():
        children[head].append(index)

    out = []
    for dependent in children.get(verb, []):
        if tokens[dependent][1] in EXCLUDED_RELATIONS:
            continue
        # the dependent's subtree, iteratively (a malformed tree must not recurse forever)
        span, stack, seen = [], [dependent], {dependent}
        while stack:
            node = stack.pop()
            span.append(node)
            for child in children.get(node, []):
                if child not in seen:
                    seen.add(child)
                    stack.append(child)
        for run in contiguous_runs(sorted(span)):
            size = sum(1 for index in run if not tokens[index][3])
            if size:
                out.append((size, -1 if run[-1] < verb else 1))
    return out


def contiguous_runs(indices: list[int]) -> list[list[int]]:
    runs, current = [], [indices[0]]
    for index in indices[1:]:
        if index == current[-1] + 1:
            current.append(index)
        else:
            runs.append(current)
            current = [index]
    runs.append(current)
    return runs


def beta_of(mal: dict[int, float]) -> tuple[float, float] | None:
    """(beta, R^2) from log MAL_n ~ -beta log n, over every available n. Needs 3 points."""
    points = [(math.log(n), math.log(v)) for n, v in sorted(mal.items()) if n >= 1 and v > 0]
    if len(points) < 3:
        return None
    n = len(points)
    mx = sum(x for x, _ in points) / n
    my = sum(y for _, y in points) / n
    sxx = sum((x - mx) ** 2 for x, _ in points)
    if sxx <= 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in points) / sxx
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for _, y in points)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in points)
    return -slope, (1 - ss_res / ss_tot if ss_tot > 0 else float("nan"))


def compliance_of(mal: dict[int, float]) -> float | None:
    """Share of consecutive n where the mean size does not grow (paper §5)."""
    ordered = [mal[n] for n in sorted(mal)]
    if len(ordered) < 2:
        return None
    pairs = list(zip(ordered, ordered[1:]))
    return sum(1 for a, b in pairs if b <= a) / len(pairs)


def category(beta: float | None) -> str:
    if beta is None:
        return ""
    if beta > MAL_THRESHOLD:
        return "MAL"
    return "anti-MAL" if beta < -MAL_THRESHOLD else "grey"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--languages", nargs="*")
    parser.add_argument(
        "--min-mode",
        choices=("constructions", "constituents"),
        default="constructions",
        help="what the >=100 threshold counts. The paper says 'a minimum of 100 tokens "
             "per configuration', which reads either way; constructions is the strict "
             "reading and constituents (n per construction) the loose one.",
    )
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    from grugrutyp.langconfig import measure_exclusions

    excluded = measure_exclusions()
    by_language: dict[str, list[Path]] = defaultdict(list)
    for directory in sorted(TREEBANKS.glob("UD_*")):
        language, _, corpus = directory.name[3:].partition("-")
        if (language, corpus) in excluded:
            continue
        if args.languages and language not in args.languages:
            continue
        by_language[language].extend(sorted(directory.glob("*.conllu")))

    rows = []
    for i, (language, files) in enumerate(sorted(by_language.items()), start=1):
        # sizes[side][n] = [Σ size, Σ constituents]; side "" is bilateral MAL
        sizes: dict[str, dict[int, list[int]]] = {k: defaultdict(lambda: [0, 0])
                                                  for k in ("", "L", "R")}
        counts: dict[str, dict[int, int]] = {k: defaultdict(int) for k in ("", "L", "R")}
        for path in files:
            for tokens in sentences(path):
                verbs = [index for index, (_, _, upos, _) in tokens.items() if upos == "VERB"]
                for verb in verbs:
                    parts = constituents_of(verb, tokens)
                    if not parts:
                        continue
                    groups = {
                        "": parts,
                        "L": [p for p in parts if p[1] < 0],
                        "R": [p for p in parts if p[1] > 0],
                    }
                    for side, chosen in groups.items():
                        if not chosen:
                            continue
                        n = len(chosen)
                        counts[side][n] += 1
                        bucket = sizes[side][n]
                        bucket[0] += sum(size for size, _ in chosen)
                        bucket[1] += n

        row = {"language": language}
        for side, label in (("", "mal"), ("L", "lmal"), ("R", "rmal")):
            mal = {
                n: total / number
                for n, (total, number) in sizes[side].items()
                if (counts[side][n] if args.min_mode == "constructions" else number)
                >= MIN_CONFIGURATIONS and number
            }
            fitted = beta_of(mal)
            row[f"beta_{label}"] = fitted[0] if fitted else None
            row[f"r2_{label}"] = fitted[1] if fitted else None
            row[f"compliance_{label}"] = compliance_of(mal)
            row[f"type_{label}"] = category(fitted[0] if fitted else None)
            row[f"points_{label}"] = len(mal)
        row["n_constructions"] = sum(counts[""].values())
        rows.append(row)
        print(
            f"[{i}/{len(by_language)}] {language:24} "
            f"beta MAL {fmt(row['beta_mal'])} L {fmt(row['beta_lmal'])} "
            f"R {fmt(row['beta_rmal'])}   compliance {fmt(row['compliance_mal'], 2)}"
            f"   ({row['n_constructions']:,} constructions)",
            flush=True,
        )

    fields = ["language", "beta_mal", "r2_mal", "compliance_mal", "type_mal", "points_mal",
              "beta_lmal", "r2_lmal", "compliance_lmal", "type_lmal", "points_lmal",
              "beta_rmal", "r2_rmal", "compliance_rmal", "type_rmal", "points_rmal",
              "n_constructions"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as fh:
        fh.write("\t".join(fields) + "\n")
        for row in rows:
            fh.write("\t".join(
                "" if row.get(f) is None else
                (f"{row[f]:.4f}" if isinstance(row.get(f), float) else str(row.get(f, "")))
                for f in fields
            ) + "\n")

    for label in ("mal", "lmal", "rmal"):
        typed = [r[f"type_{label}"] for r in rows if r[f"type_{label}"]]
        if typed:
            mal = typed.count("MAL")
            anti = typed.count("anti-MAL")
            print(f"\n{label.upper():5} {len(typed):3} languages: "
                  f"{mal} MAL ({100*mal/len(typed):.0f}%), {anti} anti-MAL "
                  f"({100*anti/len(typed):.0f}%), {len(typed)-mal-anti} grey")
    print(f"\n{len(rows)} languages -> {args.out}")
    return 0


def fmt(value, digits: int = 3) -> str:
    return f"{value:+.{digits}f}" if isinstance(value, float) else "  —   "


if __name__ == "__main__":
    sys.exit(main())
