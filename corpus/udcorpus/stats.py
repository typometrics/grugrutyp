"""The two numeric rules a reproduction needs: the Wilson interval and the sample rate.

Both are copied verbatim from grugrutyp's `backend/grugrutyp/measure.py`, which keeps
using its own copy; `corpus/tests/test_stats.py` pins them to known values, and
grugrutyp's tests compare the two.
"""

from __future__ import annotations

import math

Z_95 = 1.959963984540054


def wilson(hits: int, total: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion, as percentages.

    Not the normal approximation: at the edges -- 0 of 5 000, 3 of 50 000, which is where
    typology actually lives -- the normal interval runs off the end of the scale or
    collapses to a point. Wilson stays inside [0, 100] and stays asymmetric when the
    data are.
    """
    if total <= 0:
        return (0.0, 100.0)
    p = hits / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    low = 0.0 if hits == 0 else max(0.0, (centre - spread) * 100)
    high = 100.0 if hits == total else min(100.0, (centre + spread) * 100)
    return (low, high)


def sample_pct(n_tokens: int, token_budget: int | None) -> int:
    """The percentage of sentences grugrutyp scans for a language of this size.

    A language over the token budget is read on a reproducible k% of its sentences
    (those whose `conllu.sample_bucket(sent_id) < k`), the same k for all its treebanks.
    No budget, or a language under it: 100%.
    """
    if not token_budget or n_tokens <= token_budget:
        return 100
    return max(1, min(100, math.ceil(100 * token_budget / n_tokens)))
