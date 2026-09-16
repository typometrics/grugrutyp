"""Pattern-mining statistics and the language × measure matrix, as a library.

Two consumers share this code (docs/pattern-mining.md ch. 3-5):

* `scripts/mine_shapes.py` -- the offline sweep over all measure pairs;
* `POST /measure/score` -- a user-typed measure scored on demand against every
  stored measure ("score against everything", Kim 2026-09-05).

The matrix is `data/mining/measures.<scheme>.tsv`, written by the offline sweep and
loaded here once per file revision. Statistics take their RNG and thresholds as
parameters: the offline sweep wants one reproducible stream across the whole run,
the service wants a fresh deterministic stream per request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict
from pathlib import Path
import csv
import json

import numpy as np
from scipy import stats as sstats

from . import langconfig
from .meta import DATA_ROOT

MINING_DIR = DATA_ROOT / "mining"

GRID = 5
Z95 = 1.959963984540054

QUAD_READINGS = [
    "low-low empty: X and Y are never both low",
    "low-X/high-Y empty: high Y implies high X",
    "high-X/low-Y empty: high X implies high Y",
    "high-high empty: X and Y are never both high",
]


@dataclass
class MeasureVector:
    """One measure over the languages that pass its evidence threshold."""

    mid: str
    kind: str                      # ratio | mean
    unit: str                      # pct | words
    # Structural-coupling identity, used by the offline sweep (its build step fills
    # these); a user-typed measure leaves them empty and gets no coupling verdict.
    selfkey: str = ""
    ancestors: frozenset = frozenset()
    values: dict[str, float] = field(default_factory=dict)
    n_scope: dict[str, int] = field(default_factory=dict)
    n_hit: dict[str, int] = field(default_factory=dict)
    ci_low: dict[str, float] = field(default_factory=dict)
    ci_high: dict[str, float] = field(default_factory=dict)


# ------------------------------------------------------------------ shape statistics


def quadrant_counts(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    return np.array([
        np.sum(~xs & ~ys), np.sum(~xs & ys), np.sum(xs & ~ys), np.sum(xs & ys)
    ])


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


_GRID_NULL: dict[tuple[int, int], np.ndarray] = {}


def grid_null(n: int, rng: np.random.Generator, n_perm: int) -> np.ndarray:
    """Null of largest_empty_rect for n rank points, cached per (n, n_perm).
    Rank ties are ignored -- a v1 approximation (docs/pattern-mining.md ch. 3)."""
    key = (n, n_perm)
    if key not in _GRID_NULL:
        base = np.minimum((np.arange(1, n + 1) / n * GRID).astype(int), GRID - 1)
        samples = np.empty(n_perm)
        for i in range(n_perm):
            samples[i] = largest_empty_rect(rng.permutation(base), base)
        _GRID_NULL[key] = np.sort(samples)
    return _GRID_NULL[key]


def triangle(xm: MeasureVector, ym: MeasureVector, langs: list[str]) -> dict:
    """CI-aware inequality claim (ch. 4 filter 5: only a point whose whole interval
    is on the wrong side testifies against a claim)."""
    viol_xy = [l for l in langs if ym.ci_low[l] > xm.ci_high[l]]   # against X >= Y
    viol_yx = [l for l in langs if xm.ci_low[l] > ym.ci_high[l]]   # against Y >= X
    n = len(langs)
    if len(viol_xy) <= len(viol_yx):
        claim, viol, support = f"{xm.mid} >= {ym.mid}", viol_xy, len(viol_yx)
    else:
        claim, viol, support = f"{ym.mid} >= {xm.mid}", viol_yx, len(viol_xy)
    return {"claim": claim, "violators": viol,
            "viol_rate": len(viol) / n, "support": support / n}


def pair_stats(
    xm: MeasureVector,
    ym: MeasureVector,
    lin: dict[str, str],
    rng: np.random.Generator,
    n_perm: int = 1000,
    min_langs: int = 40,
    claim_allowed: bool = False,
) -> dict | None:
    """The screening battery for one pair. `claim_allowed` gates the inequality
    statistic -- callers restrict it to direction-like pairs, because across measure
    families "X >= Y" is a magnitude fact, not typology."""
    langs = sorted(set(xm.values) & set(ym.values))
    if len(langs) < min_langs:
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

    keep = (x != np.median(x)) & (y != np.median(y))
    xs, ys = x[keep] > np.median(x), y[keep] > np.median(y)
    n_split = int(keep.sum())
    counts = quadrant_counts(xs, ys)
    perm_ys = rng.permuted(np.tile(ys, (n_perm, 1)), axis=1)
    q11 = perm_ys[:, xs].sum(axis=1)
    q01 = perm_ys[:, ~xs].sum(axis=1)
    n_hi_x, n_lo_x = int(xs.sum()), int((~xs).sum())
    perm_min = np.minimum.reduce([n_lo_x - q01, q01, n_hi_x - q11, q11])
    p_quad = float(np.mean(perm_min <= counts.min()))
    corner = int(np.argmin(counts))
    near_empty = counts.min() <= max(1, 0.05 * n_split) and n_split >= 12

    grid = largest_empty_rect(grid_cells(x), grid_cells(y))
    null = grid_null(len(langs), rng, n_perm)
    p_grid = float(np.mean(null >= grid))

    out = {
        "x": xm.mid, "y": ym.mid, "n_langs": len(langs), "n_lineages": len(ugroups),
        "pearson": round(float(r), 3), "spearman": round(float(rho), 3),
        "lineage_r": round(float(lr), 3) if np.isfinite(lr) else "",
        "quad_min": int(counts.min()), "quad_expected": round(n_split / 4, 1),
        "quad_reading": QUAD_READINGS[corner] if near_empty else "",
        "p_quad": round(p_quad, 4), "grid_empty": round(grid, 2),
        "p_grid": round(p_grid, 4),
        "sd_x": round(float(x.std()), 1), "sd_y": round(float(y.std()), 1),
        "_corner": corner, "_langs": langs,
    }
    if claim_allowed and xm.unit == ym.unit == "pct":
        tri = triangle(xm, ym, langs)
        out.update(claim=tri["claim"], claim_violators=",".join(tri["violators"][:8]),
                   claim_viol_rate=round(tri["viol_rate"], 3),
                   claim_support=round(tri["support"], 3), _violators=tri["violators"])
    return out


def lineage_bootstrap(
    row: dict,
    xm: MeasureVector,
    ym: MeasureVector,
    lin: dict[str, str],
    rng: np.random.Generator,
    n_boot: int = 500,
) -> tuple[str, float]:
    """Ch. 4 filter 3: does the evidence survive one-language-per-lineage? The
    criterion follows the evidence the pair scored on; every scored candidate gets a
    survival, so no pair is rewarded for having skipped the check."""
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
    for _ in range(n_boot):
        pick = np.array([m[rng.integers(len(m))] for m in members])
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
    return kind, survive / n_boot


def surprise(row: dict, coupled: bool = False) -> float:
    """Ranking, v1 (ch. 5). Components stay separate in the row so any consumer can
    re-weight without re-mining; the spread guard kills degenerate near-constant
    measures (their ties fake every statistic)."""
    if coupled:
        return 0.0
    if min(row["sd_x"], row["sd_y"]) < 5.0:
        return 0.0
    empt = (1 - row["p_quad"]) if row["quad_reading"] else 0.0
    grid = (1 - row["p_grid"]) * row["grid_empty"] \
        if row["grid_empty"] >= 0.08 and row["p_grid"] <= 0.05 else 0.0
    tri = 0.0
    if row.get("claim") and row["claim_viol_rate"] <= 0.05:
        tri = (1 - row["claim_viol_rate"]) * row["claim_support"]
    factor = 0.25 + 0.75 * row["boot_survival"] if "boot_survival" in row else 1.0
    return float((empt + grid + tri) * factor)


# ------------------------------------------------------------- matrix and plot states


def lineages(languages: list[str]) -> dict[str, str]:
    out = {}
    for lang in languages:
        row = langconfig.lookup(lang)
        out[lang] = (row.genus if row and row.genus else
                     row.group if row and row.group else lang)
    return out


_MATRIX_CACHE: dict[str, tuple[float, list[MeasureVector], dict[str, str]]] = {}


def load_matrix(scheme: str = "sud") -> tuple[list[MeasureVector], dict[str, str]]:
    """The stored language × measure matrix + the lineage map, reloaded when the
    offline sweep rewrites the file."""
    path = MINING_DIR / f"measures.{scheme}.tsv"
    mtime = path.stat().st_mtime
    hit = _MATRIX_CACHE.get(scheme)
    if hit and hit[0] == mtime:
        return hit[1], hit[2]

    reg: dict[str, MeasureVector] = {}
    with path.open() as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            mid = row["measure"]
            family = mid.split(":", 1)[0]
            kind, unit = (("mean", "words") if family in ("dist", "adist")
                          else ("ratio", "pct"))
            m = reg.setdefault(mid, MeasureVector(mid, kind, unit))
            lang = row["language"]
            m.values[lang] = float(row["value"])
            if row["n_scope"]:
                m.n_scope[lang] = int(row["n_scope"])
            if row["ci_low"]:
                m.ci_low[lang] = float(row["ci_low"])
                m.ci_high[lang] = float(row["ci_high"])
    measures = sorted(reg.values(), key=lambda m: m.mid)
    lin = lineages(sorted({l for m in measures for l in m.values}))
    _MATRIX_CACHE[scheme] = (mtime, measures, lin)
    return measures, lin


def t2_queries() -> dict:
    path = MINING_DIR / "catalogue.json"
    if not path.exists():
        return {}
    return {e["key"]: e for e in json.loads(path.read_text())["entries"]}


def _edge(label: str) -> str:
    r1, _, r2 = label.partition(":")
    return f"1={r1},2={r2}" if r2 else f"1={r1}"


def mid_to_axis(mid: str, t2q: dict) -> dict | None:
    """A measure id -> the PlotView axis state that reproduces it exactly. Measures
    built on the miner's exclusion list (freq/pos/dir:dependent) get None: a single
    query pair cannot express them."""
    fam, _, rest = mid.partition(":")
    if fam == "t2":
        e = t2q.get(rest)
        return {"s": e["scope"], "q": e["response"], "l": rest,
                "k": "ratio", "e": "", "a": "avg", "u": "%"} if e else None
    if fam == "dir" and rest.startswith("cfc:"):
        body = rest[4:]
        g, _, tail = body.partition("-")
        label, _, d = tail.rpartition("-")
        if not label:
            return None
        return {"s": f"pattern {{ GOV [upos={g}]; GOV -[{_edge(label)}]-> DEP [upos={d}] }}",
                "q": "with { GOV << DEP }", "l": mid, "k": "ratio", "e": "", "a": "avg", "u": "%"}
    if fam == "dir" and rest != "dependent":
        return {"s": f"pattern {{ GOV -[{_edge(rest)}]-> DEP }}",
                "q": "with { GOV << DEP }", "l": mid, "k": "ratio", "e": "", "a": "avg", "u": "%"}
    if fam in ("dist", "adist"):
        expr = "delta(GOV,DEP)" if fam == "dist" else "abs(delta(GOV,DEP))"
        return {"s": f"pattern {{ GOV -[{_edge(rest)}]-> DEP }}", "q": "",
                "l": mid, "k": "aggregate", "e": expr, "a": "avg", "u": "words"}
    return None


# ------------------------------------------------------------- score a user measure


def score_against_matrix(
    user: MeasureVector,
    scheme: str = "sud",
    top_k: int = 40,
    n_perm: int = 500,
    n_boot: int = 300,
    min_langs: int = 40,
) -> dict:
    """The on-demand sweep: one user measure against every stored measure.

    Interactive costs, so lighter nulls than the offline run (500 permutations, 300
    bootstrap draws on the top candidates only) -- honest for browsing; anything
    promoted still goes through the full offline protocol.
    """
    measures, lin = load_matrix(scheme)
    rng = np.random.default_rng(218)   # deterministic per request: same query, same page

    rows = []
    for stored in measures:
        claim_ok = (user.unit == "pct"
                    and (stored.mid.startswith("dir:") or stored.mid.startswith("t2:")))
        row = pair_stats(user, stored, lin, rng, n_perm=n_perm,
                         min_langs=min_langs, claim_allowed=claim_ok)
        if row:
            rows.append(row)

    for row in rows:
        row["surprise"] = round(surprise(row), 4)
    rows.sort(key=lambda r: -r["surprise"])
    for row in rows[:top_k]:
        stored = next(m for m in measures if m.mid == row["y"])
        kind, surv = lineage_bootstrap(row, user, stored, lin, rng, n_boot=n_boot)
        row["boot_kind"], row["boot_survival"] = kind, round(surv, 3)
        row["surprise"] = round(surprise(row), 4)
    rows.sort(key=lambda r: -r["surprise"])

    t2q = t2_queries()
    payload = []
    for row in rows[:top_k]:
        entry = {k: v for k, v in row.items() if not k.startswith("_")}
        entry["axis"] = mid_to_axis(row["y"], t2q)
        # r ~ 1 means the user re-typed a stored measure -- worth telling them, and a
        # triangle claim between near-identical measures is vacuous.
        entry["near_identical"] = abs(row["pearson"]) >= 0.995
        if entry["near_identical"]:
            entry.pop("claim", None)
        payload.append(entry)
    return {"n_measures": len(measures), "n_compared": len(rows), "pairs": payload}
