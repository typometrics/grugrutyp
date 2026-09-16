"""The pattern-mining battery library (`grugrutyp.mining`).

Deterministic parts only: correlations, grid emptiness, CI-aware triangles, and the
matrix loader's shape. The RNG-dependent nulls are exercised through fixed seeds --
same seed, same verdict -- which is also the service's reproducibility contract."""

from __future__ import annotations

import numpy as np
import pytest

from grugrutyp import mining
from grugrutyp.mining import MeasureVector, pair_stats, surprise, triangle


def vec(mid, values, lo_hi_width=2.0, unit="pct"):
    m = MeasureVector(mid, "ratio", unit)
    for lang, value in values.items():
        m.values[lang] = value
        m.ci_low[lang] = value - lo_hi_width
        m.ci_high[lang] = value + lo_hi_width
    return m


LANGS = [f"L{i}" for i in range(60)]


def test_triangle_only_counts_ci_certain_violators():
    rng = np.random.default_rng(1)
    x = vec("dir:a", {l: float(v) for l, v in zip(LANGS, rng.uniform(40, 90, 60))})
    # y below x everywhere except one CI-certain violator and one within-noise touch
    y_vals = {l: x.values[l] - 10 for l in LANGS}
    y_vals["L0"] = x.values["L0"] + 20   # certain violator
    y_vals["L1"] = x.values["L1"] + 1    # inside the intervals: not a violator
    y = vec("dir:b", y_vals)
    tri = triangle(x, y, LANGS)
    assert tri["claim"] == "dir:a >= dir:b"
    assert tri["violators"] == ["L0"]


def test_pair_stats_perfect_correlation_and_empty_corners():
    rng = np.random.default_rng(2)
    base = {l: float(v) for l, v in zip(LANGS, rng.uniform(0, 100, 60))}
    x = vec("dir:a", base)
    y = vec("dir:b", {l: v * 0.9 + 5 for l, v in base.items()})
    lin = {l: f"fam{i % 12}" for i, l in enumerate(LANGS)}
    row = pair_stats(x, y, lin, np.random.default_rng(3), n_perm=200, min_langs=40,
                     claim_allowed=True)
    assert row["pearson"] == 1.0
    assert row["grid_empty"] >= 0.16          # a diagonal cloud leaves empty corners
    assert row["p_grid"] <= 0.05


def test_pair_stats_needs_enough_shared_languages():
    x = vec("dir:a", {l: 50.0 for l in LANGS[:10]})
    y = vec("dir:b", {l: 50.0 for l in LANGS[:10]})
    assert pair_stats(x, y, {}, np.random.default_rng(4), min_langs=40) is None


def test_spread_guard_zeroes_near_constant_pairs():
    rng = np.random.default_rng(5)
    x = vec("dir:a", {l: 99.0 + float(e) for l, e in zip(LANGS, rng.uniform(0, 0.5, 60))})
    y = vec("dir:b", {l: float(v) for l, v in zip(LANGS, rng.uniform(0, 100, 60))})
    lin = {l: f"fam{i % 12}" for i, l in enumerate(LANGS)}
    row = pair_stats(x, y, lin, np.random.default_rng(6), n_perm=200, min_langs=40,
                     claim_allowed=True)
    assert surprise(row) == 0.0


def test_load_matrix_shape_and_cache():
    if not (mining.MINING_DIR / "measures.sud.tsv").exists():
        pytest.skip("no mined matrix on this machine")
    measures, lineages = mining.load_matrix("sud")
    assert len(measures) > 100
    assert all(m.values for m in measures)
    dist = [m for m in measures if m.mid.startswith("dist:")]
    assert dist and all(m.kind == "mean" for m in dist)
    again, _ = mining.load_matrix("sud")
    assert again is measures  # cached by mtime
