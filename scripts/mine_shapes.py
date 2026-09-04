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

v1 statistics (proxies noted in docs/pattern-mining.md stay on its todo lists):
Pearson/Spearman, lineage-median r, median-split quadrant deficit with permutation
null, CI-aware triangle (inequality) violation, grid emptiness (largest empty
rectangle over a rank-space grid) with permutation null, lineage bootstrap survival,
and structural coupling flags. The miner is a HYPOTHESIS GENERATOR: nothing it emits
is a claim until it passes ch. 5's confirmation protocol.
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

# thresholds (docs/pattern-mining.md ch. 2): a cell needs enough scope to mean anything,
# a measure needs enough languages to have a shape.
MIN_SCOPE = 30
MIN_LANGS = 40
N_PERM = 1000
N_BOOT = 500
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

    def coupling_key(self) -> str:
        """Structural family for the coupling flag: same relation -> coupled."""
        parts = self.mid.split(":")
        return parts[1] if len(parts) > 1 else self.mid


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return 0.0, 100.0
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
        n_words = 0
        n_included = 0

        for (gupos, rel1, rel2, dupos), v in cells.items():
            if gupos != "__0__":            # word-to-word only; every word once below
                n_words += v[0]
            else:
                n_words += v[0]             # root edges: their dependents are words too
            by_pos[dupos] += v[0]           # each word is a dependent exactly once
            if gupos == "__0__" or rel1 in always_excl:
                continue
            glob += v                       # global keeps dislocated (paper's choice)
            if rel1 in per_rel_dead:
                continue
            n_included += v[0]
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


# --------------------------------------------------------------------- lineage info


def lineages(languages: list[str]) -> dict[str, str]:
    out = {}
    for lang in languages:
        row = langconfig.lookup(lang)
        out[lang] = (row.genus if row and row.genus else
                     row.group if row and row.group else lang)
    return out


# ------------------------------------------------------------------------- battery


def quadrant(x: np.ndarray, y: np.ndarray) -> tuple[int, np.ndarray]:
    mx, my = np.median(x), np.median(y)
    keep = (x != mx) & (y != my)
    xs, ys = x[keep] > mx, y[keep] > my
    counts = np.array([
        np.sum(~xs & ~ys), np.sum(~xs & ys), np.sum(xs & ~ys), np.sum(xs & ys)
    ])
    return int(keep.sum()), counts


QUAD_READINGS = [
    "low-low empty: X and Y are never both low",
    "low-X/high-Y empty: high Y implies high X",
    "high-X/low-Y empty: high X implies high Y",
    "high-high empty: X and Y are never both high",
]


def grid_emptiness(x: np.ndarray, y: np.ndarray, g: int = 5) -> float:
    """Largest empty axis-aligned rectangle, in grid cells over rank space (0..1)."""
    rx = sstats.rankdata(x) / len(x)
    ry = sstats.rankdata(y) / len(y)
    occ = np.zeros((g, g), dtype=bool)
    ix = np.minimum((rx * g).astype(int), g - 1)
    iy = np.minimum((ry * g).astype(int), g - 1)
    occ[ix, iy] = True
    best = 0
    for i0 in range(g):
        for i1 in range(i0, g):
            run = 0
            for j in range(g):
                if not occ[i0:i1 + 1, j].any():
                    run += 1
                    best = max(best, (i1 - i0 + 1) * run)
                else:
                    run = 0
    return best / (g * g)


def triangle(xm: Measure, ym: Measure, langs: list[str]) -> dict:
    """CI-aware inequality claim between two pct measures: is one side ~empty?"""
    viol_xy, viol_yx = [], []           # violators of X>=Y resp. Y>=X, beyond both CIs
    for lang in langs:
        if ym.ci_low[lang] > xm.ci_high[lang]:
            viol_xy.append(lang)
        if xm.ci_low[lang] > ym.ci_high[lang]:
            viol_yx.append(lang)
    n = len(langs)
    if len(viol_xy) <= len(viol_yx):
        return {"claim": f"{xm.mid} >= {ym.mid}", "violators": viol_xy,
                "support": len(viol_yx) / n, "viol_rate": len(viol_xy) / n}
    return {"claim": f"{ym.mid} >= {xm.mid}", "violators": viol_yx,
            "support": len(viol_xy) / n, "viol_rate": len(viol_yx) / n}


def pair_battery(xm: Measure, ym: Measure, lin: dict[str, str]) -> dict | None:
    langs = sorted(set(xm.values) & set(ym.values))
    if len(langs) < MIN_LANGS:
        return None
    x = np.array([xm.values[l] for l in langs])
    y = np.array([ym.values[l] for l in langs])

    r, _ = sstats.pearsonr(x, y)
    rho, _ = sstats.spearmanr(x, y)

    lins = np.array([lin[l] for l in langs])
    med_x = [np.median(x[lins == g]) for g in np.unique(lins)]
    med_y = [np.median(y[lins == g]) for g in np.unique(lins)]
    lr = sstats.pearsonr(med_x, med_y)[0] if len(med_x) >= 5 else np.nan

    n_split, counts = quadrant(x, y)
    corner = int(np.argmin(counts))
    # permutation null for the min corner and for grid emptiness
    perm_min = np.empty(N_PERM)
    perm_grid = np.empty(N_PERM)
    for i in range(N_PERM):
        yp = RNG.permutation(y)
        _, c = quadrant(x, yp)
        perm_min[i] = c.min()
        perm_grid[i] = grid_emptiness(x, yp)
    p_quad = float(np.mean(perm_min <= counts.min()))
    grid = grid_emptiness(x, y)
    p_grid = float(np.mean(perm_grid >= grid))

    out = {
        "x": xm.mid, "y": ym.mid, "n_langs": len(langs), "n_lineages": len(set(lins)),
        "pearson": round(float(r), 3), "spearman": round(float(rho), 3),
        "lineage_r": round(float(lr), 3) if np.isfinite(lr) else "",
        "quad_min": int(counts.min()), "quad_expected": round(n_split / 4, 1),
        "quad_reading": QUAD_READINGS[corner] if counts.min() <= max(1, 0.05 * n_split) else "",
        "p_quad": p_quad, "grid_empty": round(grid, 2), "p_grid": p_grid,
        "coupled": xm.coupling_key() == ym.coupling_key(),
    }

    if xm.unit == ym.unit == "pct":
        tri = triangle(xm, ym, langs)
        out.update(claim=tri["claim"], claim_violators=",".join(tri["violators"][:8]),
                   claim_viol_rate=round(tri["viol_rate"], 3),
                   claim_support=round(tri["support"], 3))
        # lineage bootstrap: does the emptiest corner stay <= 5% under one-per-lineage?
        groups = defaultdict(list)
        for idx, g in enumerate(lins):
            groups[g].append(idx)
        members = list(groups.values())
        survive = 0
        for _ in range(N_BOOT):
            pick = np.array([m[RNG.integers(len(m))] for m in members])
            ns, c = quadrant(x[pick], y[pick])
            if ns >= 12 and c[corner] <= max(1, 0.05 * ns):
                survive += 1
        out["boot_quad_survival"] = round(survive / N_BOOT, 3)
    return out


def oned_battery(m: Measure, lin: dict[str, str]) -> dict:
    v = np.array(sorted(m.values.values()))
    n = len(v)
    skew = float(sstats.skew(v))
    kurt = float(sstats.kurtosis(v, fisher=False))
    bimodality = (skew**2 + 1) / kurt if kurt > 0 else np.nan
    lo, hi = np.percentile(v, [5, 95])
    span = hi - lo if hi > lo else 1.0
    inner = v[(v >= lo) & (v <= hi)]
    gap = float(np.max(np.diff(inner)) / span) if len(inner) > 2 else 0.0
    below, above = (v[v < 50], v[v >= 50]) if m.unit == "pct" else (v[v < np.median(v)], v[v >= np.median(v)])
    return {
        "measure": m.mid, "n_langs": n,
        "mean": round(float(v.mean()), 1), "sd": round(float(v.std()), 1),
        "bimodality": round(float(bimodality), 2) if np.isfinite(bimodality) else "",
        "max_gap": round(gap, 2),
        "low_pole_n": len(below), "low_pole_sd": round(float(below.std()), 1) if len(below) > 2 else "",
        "high_pole_n": len(above), "high_pole_sd": round(float(above.std()), 1) if len(above) > 2 else "",
    }


# --------------------------------------------------------------------------- output


def write_tsv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    keys = list(rows[0].keys())
    with path.open("w") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def surprise(row: dict) -> float:
    """Ranking score, v1 (docs/pattern-mining.md ch. 5): emptiness beyond the
    permutation null, discounted by lineage survival, killed by structural coupling."""
    if row.get("coupled"):
        return 0.0
    empt = (1 - row["p_quad"]) * (1 if row.get("quad_reading") else 0)
    grid = (1 - row["p_grid"]) * row["grid_empty"]
    boot = row.get("boot_quad_survival", 0.5) or 0.0
    tri = (1 - row.get("claim_viol_rate", 1.0)) * row.get("claim_support", 0.0)
    return float((empt + grid + tri) * (0.25 + 0.75 * boot))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scheme", default="sud")
    ap.add_argument("--min-langs", type=int, default=MIN_LANGS)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--families", default="dir,freq,dist,adist,pos",
                    help="measure families to cross in the 2-D battery")
    args = ap.parse_args()
    global MIN_LANGS
    MIN_LANGS = args.min_langs

    table = load_long(MINING / f"lang_cfc.{args.scheme}.tsv")
    print(f"[load] {len(table)} languages", flush=True)
    measures = build_measures(table)
    print(f"[measures] {len(measures)} kept (>= {MIN_LANGS} languages)", flush=True)

    long_rows = [
        {"measure": m.mid, "language": lang, "value": round(m.values[lang], 4),
         "n_scope": m.n_scope.get(lang, ""), "n_hit": m.n_hit.get(lang, ""),
         "ci_low": round(m.ci_low[lang], 3) if lang in m.ci_low else "",
         "ci_high": round(m.ci_high[lang], 3) if lang in m.ci_high else ""}
        for m in measures for lang in sorted(m.values)
    ]
    write_tsv(MINING / f"measures.{args.scheme}.tsv", long_rows)

    lin = lineages(sorted(table))
    print(f"[lineages] {len(set(lin.values()))} lineages", flush=True)

    oned = [oned_battery(m, lin) for m in measures]
    write_tsv(MINING / f"oned.{args.scheme}.tsv", oned)

    fams = set(args.families.split(","))
    core = [m for m in measures if m.mid.split(":")[0] in fams]
    print(f"[pairs] {len(core)} core measures -> {len(core) * (len(core)-1) // 2} pairs",
          flush=True)
    rows = []
    for xm, ym in combinations(core, 2):
        row = pair_battery(xm, ym, lin)
        if row:
            rows.append(row)
    for row in rows:
        row["surprise"] = round(surprise(row), 4)
    rows.sort(key=lambda r: -r["surprise"])
    write_tsv(MINING / f"shapes.{args.scheme}.tsv", rows)

    top = [r for r in rows if r["surprise"] > 0][: args.top]
    lines = [
        f"# Mined shape candidates — {args.scheme.upper()} 2.18",
        "",
        f"{len(rows)} pairs scored; top {len(top)} by surprise (v1 score: emptiness "
        "beyond permutation null x lineage-bootstrap survival; structural coupling "
        "kills). HYPOTHESES, not claims — docs/pattern-mining.md ch. 5.",
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
            f"lineage-bootstrap survival {r.get('boot_quad_survival', '—')}",
        ]
        if r.get("claim"):
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
