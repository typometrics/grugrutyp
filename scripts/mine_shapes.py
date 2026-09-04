#!/usr/bin/env python3
"""Shape mining over the Tier-1 language matrix: find candidate quantitative universals.

    .venv/bin/python scripts/mine_shapes.py                    # full battery, SUD
    .venv/bin/python scripts/mine_shapes.py --min-langs 50 --top 60

Design: `docs/pattern-mining.md` ch. 3 (battery), ch. 4 (triviality gauntlet), ch. 5
(ranking). Input is `data/mining/lang_cfc.sud.tsv` from `mine_cfc_matrix.py`. Outputs:

    data/mining/measures.sud.tsv    language x measure long table (value, counts, CI)
    data/mining/shapes.sud.tsv      one row per measure pair with the full battery
    data/mining/oned.sud.tsv        the 1-D battery per measure
    data/mining/ranked.sud.md       human-readable top-k with exceptions named

Two phases, because the expensive honesty checks only pay on candidates: a cheap
screen over every pair (correlations, quadrant deficit with a vectorised permutation
null, rank-grid emptiness against a cached null, CI-aware inequality violations),
then the lineage bootstrap (ch. 4 filter 3) on the screened survivors only.

v1 conventions, deliberate and revisable (docs/pattern-mining.md keeps the todo):
`freq:` shares are relative to the *included* (non-excluded) word-to-word
dependencies; the grid null is cached per pair-size ignoring rank ties; the
bimodality statistic is the coefficient proxy, not Hartigan's dip. The miner is a
HYPOTHESIS GENERATOR: nothing it emits is a claim until it passes ch. 5's protocol.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy import stats as sstats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from grugrutyp import langconfig  # noqa: E402

MINING = ROOT / "data" / "mining"
Z95 = 1.959963984540054

MIN_SCOPE = 30      # per-language cell threshold (docs/pattern-mining.md ch. 2)
MIN_LANGS = 40      # per-measure language threshold
N_PERM = 1000
N_BOOT = 500
GRID = 5
RNG = np.random.default_rng(218)  # fixed: a re-run must reproduce (sampling.md rule 1)


# --------------------------------------------------------------------------- loading


def load_excluded() -> tuple[set[str], set[str]]:
    always, per_rel = set(), set()
    with (MINING / "excluded_rels.tsv").open() as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            rel, scope = line.rstrip("\n").split("\t")
            (always if scope == "always" else per_rel).add(rel)
    return always, per_rel


def load_long(path: Path) -> dict[str, dict[tuple, np.ndarray]]:
    """language -> {(gupos, rel1, rel2, dupos): [n, n_right, sum_delta, sum_abs_delta]}"""
    table: dict[str, dict[tuple, np.ndarray]] = defaultdict(dict)
    with path.open() as fh:
        reader = csv.reader(fh, delimiter="\t")
        next(reader)
        for lang, gupos, rel1, rel2, dupos, n, nr, sd, sad in reader:
            table[lang][(gupos, rel1, rel2, dupos)] = np.array(
                [int(n), int(nr), int(sd), int(sad)], dtype=np.int64
            )
    return table


# --------------------------------------------------------------------- measure build


@dataclass
class Measure:
    mid: str                       # e.g. "dir:subj", "dist:comp:obj", "pos:NOUN"
    kind: str                      # ratio | mean
    unit: str                      # pct | words
    values: dict[str, float] = field(default_factory=dict)
    n_scope: dict[str, int] = field(default_factory=dict)
    n_hit: dict[str, int] = field(default_factory=dict)
    ci_low: dict[str, float] = field(default_factory=dict)
    ci_high: dict[str, float] = field(default_factory=dict)


# POS shares that measure annotation practice or genre, not typology. Kept in
# measures.tsv, excluded from mining (same logic as excluded_rels.tsv).
EXCLUDED_POS = {"SYM", "X", "PUNCT"}

# A relation carried almost entirely by one POS makes freq:<rel> and pos:<POS> the
# same quantity twice (first smoke test: freq:det x pos:DET at r = 0.95). The general
# arithmetic-coupling check is ch. 4's todo; these are the known identities.
REL_POS_ALIASES = {("det", "DET"), ("cc", "CCONJ"), ("aux", "AUX"), ("case", "ADP")}


def coupled(a: Measure, b: Measure) -> bool:
    """Structural coupling flag (ch. 4 filter 1, v1: flag, no mixture arithmetic yet).

    Same relation across any families is coupled (dir:comp vs dist:comp share every
    matching; dir:comp vs dir:comp:obj share most of them); the global `dependent`
    and `pos:` measures contain everything, so `dependent` couples with every
    relation-level measure; and a relation-POS near-identity couples freq with pos.
    """
    ka = a.mid.split(":", 1)[1]
    kb = b.mid.split(":", 1)[1]
    if ka.lower() == kb.lower():
        return True
    if ka.startswith(kb + ":") or kb.startswith(ka + ":"):
        return True
    if (ka, kb) in REL_POS_ALIASES or (kb, ka) in REL_POS_ALIASES:
        return True
    return "dependent" in (ka, kb)


def wilson(k: int, n: int) -> tuple[float, float]:
    p = k / n
    denom = 1 + Z95**2 / n
    center = (p + Z95**2 / (2 * n)) / denom
    half = Z95 * np.sqrt(p * (1 - p) / n + Z95**2 / (4 * n**2)) / denom
    return 100 * (center - half), 100 * (center + half)


def build_measures(table) -> list[Measure]:
    always_excl, per_rel_excl = load_excluded()
    per_rel_dead = always_excl | per_rel_excl

    reg: dict[str, Measure] = {}

    def add_ratio(mid: str, lang: str, k: int, n: int) -> None:
        if n < MIN_SCOPE:
            return
        m = reg.setdefault(mid, Measure(mid, "ratio", "pct"))
        m.values[lang] = 100 * k / n
        m.n_scope[lang], m.n_hit[lang] = n, k
        m.ci_low[lang], m.ci_high[lang] = wilson(k, n)

    def add_mean(mid: str, lang: str, total: int, n: int) -> None:
        if n < MIN_SCOPE:
            return
        m = reg.setdefault(mid, Measure(mid, "mean", "words"))
        m.values[lang] = total / n
        m.n_scope[lang] = n

    for lang, cells in table.items():
        by_rel1 = defaultdict(lambda: np.zeros(4, dtype=np.int64))
        by_full = defaultdict(lambda: np.zeros(4, dtype=np.int64))
        by_pos = defaultdict(int)
        glob = np.zeros(4, dtype=np.int64)
        n_words = 0        # every word is a dependent exactly once, root edges included
        n_included = 0

        for (gupos, rel1, rel2, dupos), v in cells.items():
            n_words += int(v[0])
            by_pos[dupos] += int(v[0])
            if gupos == "__0__" or rel1 in always_excl:
                continue
            glob += v                      # global keeps `dislocated` (the paper's choice)
            if rel1 in per_rel_dead:
                continue
            n_included += int(v[0])
            by_rel1[rel1] += v
            if rel2:
                by_full[f"{rel1}:{rel2}"] += v

        for rel, v in by_rel1.items():
            add_ratio(f"dir:{rel}", lang, int(v[1]), int(v[0]))
            add_mean(f"dist:{rel}", lang, int(v[2]), int(v[0]))
            add_mean(f"adist:{rel}", lang, int(v[3]), int(v[0]))
            add_ratio(f"freq:{rel}", lang, int(v[0]), n_included)
        for rel, v in by_full.items():
            add_ratio(f"dir:{rel}", lang, int(v[1]), int(v[0]))
            add_mean(f"dist:{rel}", lang, int(v[2]), int(v[0]))
        add_ratio("dir:dependent", lang, int(glob[1]), int(glob[0]))
        for upos, n in by_pos.items():
            if upos != "_":
                add_ratio(f"pos:{upos}", lang, n, n_words)

    kept = [m for m in reg.values() if len(m.values) >= MIN_LANGS]
    kept.sort(key=lambda m: m.mid)
    return kept


def lineages(languages: list[str]) -> dict[str, str]:
    out = {}
    for lang in languages:
        row = langconfig.lookup(lang)
        out[lang] = (row.genus if row and row.genus else
                     row.group if row and row.group else lang)
    return out


# ------------------------------------------------------------------- 2-D statistics


def quadrant_counts(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    return np.array([
        np.sum(~xs & ~ys), np.sum(~xs & ys), np.sum(xs & ~ys), np.sum(xs & ys)
    ])


QUAD_READINGS = [
    "low-low empty: X and Y are never both low",
    "low-X/high-Y empty: high Y implies high X",
    "high-X/low-Y empty: high X implies high Y",
    "high-high empty: X and Y are never both high",
]

_GRID_NULL: dict[int, np.ndarray] = {}


def grid_cells(vals: np.ndarray) -> np.ndarray:
    ranks = sstats.rankdata(vals) / len(vals)
    return np.minimum((ranks * GRID).astype(int), GRID - 1)


def largest_empty_rect(ix: np.ndarray, iy: np.ndarray) -> float:
    occ = np.zeros((GRID, GRID), dtype=bool)
    occ[ix, iy] = True
    best = 0
    for i0 in range(GRID):
        for i1 in range(i0, GRID):
            run = 0
            for j in range(GRID):
                if occ[i0:i1 + 1, j].any():
                    run = 0
                else:
                    run += 1
                    best = max(best, (i1 - i0 + 1) * run)
    return best / (GRID * GRID)


def grid_null(n: int) -> np.ndarray:
    """Null distribution of largest_empty_rect for n rank points, cached per n.
    Ties are ignored (ranks assumed distinct) -- a v1 approximation."""
    if n not in _GRID_NULL:
        base = np.minimum((np.arange(1, n + 1) / n * GRID).astype(int), GRID - 1)
        samples = np.empty(N_PERM)
        for i in range(N_PERM):
            samples[i] = largest_empty_rect(RNG.permutation(base), base)
        _GRID_NULL[n] = np.sort(samples)
    return _GRID_NULL[n]


def triangle(xm: Measure, ym: Measure, langs: list[str]) -> dict:
    """CI-aware inequality claim between two pct measures (ch. 4 filter 5: only a
    point whose interval is wholly on the wrong side testifies against a claim)."""
    viol_xy = [l for l in langs if ym.ci_low[l] > xm.ci_high[l]]   # against X >= Y
    viol_yx = [l for l in langs if xm.ci_low[l] > ym.ci_high[l]]   # against Y >= X
    n = len(langs)
    if len(viol_xy) <= len(viol_yx):
        claim, viol, support = f"{xm.mid} >= {ym.mid}", viol_xy, len(viol_yx)
    else:
        claim, viol, support = f"{ym.mid} >= {xm.mid}", viol_yx, len(viol_xy)
    return {"claim": claim, "violators": viol,
            "viol_rate": len(viol) / n, "support": support / n}


def screen_pair(xm: Measure, ym: Measure, lin: dict[str, str]) -> dict | None:
    langs = sorted(set(xm.values) & set(ym.values))
    if len(langs) < MIN_LANGS:
        return None
    x = np.array([xm.values[l] for l in langs])
    y = np.array([ym.values[l] for l in langs])

    r, _ = sstats.pearsonr(x, y)
    rho, _ = sstats.spearmanr(x, y)

    lin_arr = np.array([lin[l] for l in langs])
    ugroups = np.unique(lin_arr)
    lr = np.nan
    if len(ugroups) >= 5:
        med_x = [np.median(x[lin_arr == g]) for g in ugroups]
        med_y = [np.median(y[lin_arr == g]) for g in ugroups]
        lr = sstats.pearsonr(med_x, med_y)[0]

    # median-split quadrant with vectorised permutation null
    keep = (x != np.median(x)) & (y != np.median(y))
    xs, ys = x[keep] > np.median(x), y[keep] > np.median(y)
    n_split = int(keep.sum())
    counts = quadrant_counts(xs, ys)
    perm_ys = RNG.permuted(np.tile(ys, (N_PERM, 1)), axis=1)
    q11 = perm_ys[:, xs].sum(axis=1)
    q01 = perm_ys[:, ~xs].sum(axis=1)
    n_hi_x, n_lo_x = int(xs.sum()), int((~xs).sum())
    perm_min = np.minimum.reduce([n_lo_x - q01, q01, n_hi_x - q11, q11])
    p_quad = float(np.mean(perm_min <= counts.min()))
    corner = int(np.argmin(counts))
    near_empty = counts.min() <= max(1, 0.05 * n_split) and n_split >= 12

    grid = largest_empty_rect(grid_cells(x), grid_cells(y))
    null = grid_null(len(langs))
    p_grid = float(np.mean(null >= grid))

    out = {
        "x": xm.mid, "y": ym.mid, "n_langs": len(langs), "n_lineages": len(ugroups),
        "pearson": round(float(r), 3), "spearman": round(float(rho), 3),
        "lineage_r": round(float(lr), 3) if np.isfinite(lr) else "",
        "quad_min": int(counts.min()), "quad_expected": round(n_split / 4, 1),
        "quad_reading": QUAD_READINGS[corner] if near_empty else "",
        "p_quad": round(p_quad, 4), "grid_empty": round(grid, 2),
        "p_grid": round(p_grid, 4), "coupled": coupled(xm, ym),
        "_corner": corner, "_langs": langs,
    }
    # Inequality claims only between DIRECTION measures: same 0-100 scale, same
    # phenomenon type, so the ordering is typological (the paper's V-object-NOUN >=
    # V-object-PRON). freq/pos orderings are magnitude-trivial ("more verbs than
    # interjections everywhere") -- both smoke tests filled the top with them.
    if xm.mid.startswith("dir:") and ym.mid.startswith("dir:"):
        tri = triangle(xm, ym, langs)
        out.update(claim=tri["claim"], claim_violators=",".join(tri["violators"][:8]),
                   claim_viol_rate=round(tri["viol_rate"], 3),
                   claim_support=round(tri["support"], 3), _violators=tri["violators"])
    return out


def lineage_bootstrap(
    row: dict, xm: Measure, ym: Measure, lin: dict[str, str]
) -> tuple[str, float]:
    """Ch. 4 filter 3: does the evidence survive one-language-per-lineage?

    The criterion follows the evidence the pair scored on: the near-empty quadrant
    corner if it has one, else the empty grid rectangle, else the CI-certain
    violator rate of its inequality claim. Every scored candidate gets a survival,
    so no pair is rewarded for having skipped the check.
    """
    langs = row["_langs"]
    x = np.array([xm.values[l] for l in langs])
    y = np.array([ym.values[l] for l in langs])
    groups = defaultdict(list)
    for idx, lang in enumerate(langs):
        groups[lin[lang]].append(idx)
    members = [np.array(v) for v in groups.values()]

    if row["quad_reading"]:
        kind, corner = "corner", row["_corner"]
    elif row["p_grid"] <= 0.05:
        kind, target = "grid", 0.8 * row["grid_empty"]
    elif row.get("claim"):
        kind = "claim"
        lang_idx = {l: i for i, l in enumerate(langs)}
        viol = np.zeros(len(langs), dtype=bool)
        for l in row["_violators"]:
            viol[lang_idx[l]] = True
    else:
        return "none", 0.0

    survive = 0
    for _ in range(N_BOOT):
        pick = np.array([m[RNG.integers(len(m))] for m in members])
        if kind == "corner":
            xp, yp = x[pick], y[pick]
            keep = (xp != np.median(xp)) & (yp != np.median(yp))
            if keep.sum() < 12:
                continue
            counts = quadrant_counts(xp[keep] > np.median(xp), yp[keep] > np.median(yp))
            if counts[corner] <= max(1, 0.05 * keep.sum()):
                survive += 1
        elif kind == "grid":
            if largest_empty_rect(grid_cells(x[pick]), grid_cells(y[pick])) >= target:
                survive += 1
        else:
            if viol[pick].sum() <= max(0, int(0.02 * len(pick))):
                survive += 1
    return kind, survive / N_BOOT


# ------------------------------------------------------------------- 1-D statistics


def oned_battery(m: Measure) -> dict:
    v = np.array(sorted(m.values.values()))
    skew = float(sstats.skew(v))
    kurt = float(sstats.kurtosis(v, fisher=False))
    bimodality = (skew**2 + 1) / kurt if kurt > 0 else np.nan
    lo, hi = np.percentile(v, [5, 95])
    span = hi - lo if hi > lo else 1.0
    inner = v[(v >= lo) & (v <= hi)]
    gap = float(np.max(np.diff(inner)) / span) if len(inner) > 2 else 0.0
    split = 50.0 if m.unit == "pct" else float(np.median(v))
    below, above = v[v < split], v[v >= split]
    return {
        "measure": m.mid, "n_langs": len(v),
        "mean": round(float(v.mean()), 1), "sd": round(float(v.std()), 1),
        "bimodality": round(float(bimodality), 2) if np.isfinite(bimodality) else "",
        "max_gap": round(gap, 2),
        "low_pole_n": len(below),
        "low_pole_sd": round(float(below.std()), 1) if len(below) > 2 else "",
        "high_pole_n": len(above),
        "high_pole_sd": round(float(above.std()), 1) if len(above) > 2 else "",
    }


# --------------------------------------------------------------------------- output


def surprise(row: dict) -> float:
    """Ranking, v1 (ch. 5): emptiness beyond the permutation null, times lineage
    survival, killed by structural coupling. Components stay in the TSV so the
    ranking can be re-weighted without re-mining."""
    if row["coupled"]:
        return 0.0
    empt = (1 - row["p_quad"]) if row["quad_reading"] else 0.0
    # one empty cell of 25 is the minimum nonzero and pure noise; demand two
    grid = (1 - row["p_grid"]) * row["grid_empty"] \
        if row["grid_empty"] >= 0.08 and row["p_grid"] <= 0.05 else 0.0
    tri = 0.0
    if row.get("claim") and row["claim_viol_rate"] <= 0.05:
        tri = (1 - row["claim_viol_rate"]) * row["claim_support"]
    factor = 0.25 + 0.75 * row["boot_survival"] if "boot_survival" in row else 1.0
    return float((empt + grid + tri) * factor)


def write_tsv(path: Path, rows: list[dict]) -> None:
    rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    if not rows:
        path.write_text("")
        return
    keys = list(rows[0].keys())
    for r in rows[1:]:
        keys += [k for k in r if k not in keys]
    with path.open("w") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys, delimiter="\t", restval="")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    global MIN_LANGS
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scheme", default="sud")
    ap.add_argument("--min-langs", type=int, default=MIN_LANGS)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--families", default="dir,freq,dist,adist,pos",
                    help="measure families crossed in the 2-D battery")
    args = ap.parse_args()
    MIN_LANGS = args.min_langs

    table = load_long(MINING / f"lang_cfc.{args.scheme}.tsv")
    print(f"[load] {len(table)} languages", flush=True)
    measures = build_measures(table)
    print(f"[measures] {len(measures)} kept (>= {MIN_LANGS} languages)", flush=True)

    write_tsv(MINING / f"measures.{args.scheme}.tsv", [
        {"measure": m.mid, "language": lang, "value": round(m.values[lang], 4),
         "n_scope": m.n_scope.get(lang, ""), "n_hit": m.n_hit.get(lang, ""),
         "ci_low": round(m.ci_low[lang], 3) if lang in m.ci_low else "",
         "ci_high": round(m.ci_high[lang], 3) if lang in m.ci_high else ""}
        for m in measures for lang in sorted(m.values)
    ])

    lin = lineages(sorted(table))
    print(f"[lineages] {len(set(lin.values()))} lineages over {len(lin)} languages",
          flush=True)

    write_tsv(MINING / f"oned.{args.scheme}.tsv",
              sorted((oned_battery(m) for m in measures),
                     key=lambda r: -(r["bimodality"] or 0)))

    fams = set(args.families.split(","))
    by_mid = {m.mid: m for m in measures}
    core = [m for m in measures
            if m.mid.split(":")[0] in fams
            and not (m.mid.startswith("pos:") and m.mid.split(":")[1] in EXCLUDED_POS)]
    n_pairs = len(core) * (len(core) - 1) // 2
    print(f"[screen] {len(core)} core measures -> {n_pairs} pairs", flush=True)

    rows = []
    for i, (xm, ym) in enumerate(combinations(core, 2), 1):
        row = screen_pair(xm, ym, lin)
        if row:
            rows.append(row)
        if i % 2000 == 0:
            print(f"[screen] {i}/{n_pairs}", flush=True)

    candidates = [r for r in rows if surprise(r) > 0]
    candidates.sort(key=lambda r: -surprise(r))
    to_boot = candidates[:1000]
    print(f"[bootstrap] {len(to_boot)} screened candidates of {len(rows)} pairs",
          flush=True)
    for r in to_boot:
        kind, surv = lineage_bootstrap(r, by_mid[r["x"]], by_mid[r["y"]], lin)
        r["boot_kind"], r["boot_survival"] = kind, round(surv, 3)
    for r in rows:
        r["surprise"] = round(surprise(r), 4)
    rows.sort(key=lambda r: -r["surprise"])
    write_tsv(MINING / f"shapes.{args.scheme}.tsv", rows)

    top = [r for r in rows if r["surprise"] > 0][: args.top]
    lines = [
        f"# Mined shape candidates — {args.scheme.upper()} 2.18",
        "",
        f"{len(rows)} pairs scored; top {len(top)} by surprise (v1: emptiness beyond "
        "permutation null × lineage-bootstrap survival; structural coupling kills). "
        "HYPOTHESES, not claims — docs/pattern-mining.md ch. 5.",
        "",
    ]
    for i, r in enumerate(top, 1):
        lines += [
            f"## {i}. {r['x']}  ×  {r['y']}   (surprise {r['surprise']})",
            f"- n = {r['n_langs']} languages, {r['n_lineages']} lineages; "
            f"r = {r['pearson']}, rho = {r['spearman']}, lineage-median r = {r['lineage_r']}",
            f"- quadrant: min corner {r['quad_min']} vs {r['quad_expected']} expected "
            f"(p_perm = {r['p_quad']}); {r['quad_reading'] or 'no near-empty corner'}",
            f"- grid emptiness {r['grid_empty']} (p_perm = {r['p_grid']}); "
            f"lineage-bootstrap survival {r.get('boot_survival', '—')} "
            f"({r.get('boot_kind', 'not run')})",
        ]
        if r.get("claim") and r.get("claim_viol_rate", 1) <= 0.05:
            lines.append(
                f"- inequality: **{r['claim']}** — CI-certain violators "
                f"{r['claim_viol_rate']:.1%}: {r['claim_violators'] or 'none'}"
            )
        lines.append("")
    (MINING / f"ranked.{args.scheme}.md").write_text("\n".join(lines))
    print(f"[done] ranked report: data/mining/ranked.{args.scheme}.md", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
