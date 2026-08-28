"""Query pairs into typological variables.

One measure is a pair of Grew requests -- a **scope S** and a **response pattern Q**, the
vocabulary of Herrera, Corro & Kahane 2024 (`docs/query-pairs.md`) -- evaluated per
treebank as

    value = 100 * #(S and Q) / #(S)

which is the paper's base rate mu, computed across 705 treebanks instead of one.

This module owns three things the raw counts do not give you:

* **honest uncertainty** -- a point from 40 matchings and a point from 400 000 must not
  look alike, so every point carries a Wilson interval;
* **a sampling policy** -- a token budget rather than a fixed percentage, with automatic
  escalation to the full treebank when the interval is too wide to plot
  (`docs/sampling.md`);
* **language-level merging by summing counts**, never by averaging percentages.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Iterable, Literal

from .translate.cypher import combine, translate
from .translate.parser import parse

Kind = Literal["ratio", "aggregate"]

# --------------------------------------------------------------------------- defaults

# Tokens per treebank the sampler aims to scan. 100k scans 28% of the corpus for a 3.5x
# speed-up and samples 203 of 705 treebanks; everything smaller is queried in full.
# Measured in `docs/sampling.md` section 3.
DEFAULT_TOKEN_BUDGET = 100_000

# Below this many scope matchings a point is not worth plotting -- it is the role
# `axminocc` plays on the current site, but applied to a number we actually know.
DEFAULT_MIN_SCOPE = 30

# A Wilson interval wider than this (in percentage points) is escalated to the full
# treebank. Two points is invisible on a 0-100 axis; anything wider is a claim we cannot
# make from a sample.
DEFAULT_CI_TOLERANCE = 2.0

# Below this many hits, escalate regardless of how narrow the interval looks. A count of
# n has a relative standard error of about 1/sqrt(n): 3 hits is +/- 58%, 10 is +/- 32%.
# The absolute interval stays tiny -- 3/50 000 spans 0.002%-0.018%, well inside the
# tolerance above -- so the percentage-point rule alone never fires, and the number goes
# on the plot looking exact when it is a coin flip between "0.006%" and "0.05%".
DEFAULT_MIN_HITS = 10

Z_95 = 1.959963984540054


def wilson(hits: int, total: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion, as percentages.

    Not the normal approximation: at the edges -- 0 of 5 000, 3 of 50 000, which is where
    typology actually lives -- the normal interval runs off the end of the scale or
    collapses to a point, and either way it lies. Wilson stays inside [0, 100] and stays
    asymmetric when the data are.
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
    """The percentage of sentences to scan for a treebank of this size.

    A fixed percentage would over-sample the giants and destroy the small treebanks; a
    budget cuts only what is already more precise than the plot can show. Czech-PDTC's
    6.9M tokens become 2%, while the median 35k-token treebank is untouched.
    """
    if not token_budget or n_tokens <= token_budget:
        return 100
    return max(1, min(100, math.ceil(100 * token_budget / n_tokens)))


# ------------------------------------------------------------------------------ spec


@dataclass(frozen=True)
class MeasureSpec:
    """One axis of a plot."""

    scope: str  # S, a Grew request with a `pattern` block
    response: str = ""  # Q, `with`/`without` blocks only; empty => count the scope
    kind: Kind = "ratio"
    expression: str = ""  # aggregate mode: avg(delta(GOV,DEP)) and friends
    label: str = ""

    def validate(self) -> None:
        """Parse and combine without touching the database.

        Doing this once up front matters: the alternative is discovering that Q names an
        unbound node on treebank 300 of 705, having spent five minutes on numbers that
        mean nothing.
        """
        scope = parse(self.scope)
        if not list(scope.blocks_of("pattern")):
            raise ValueError("the scope needs a `pattern { ... }` block")
        if self.response.strip():
            combine(scope, parse(self.response))

    def query_hash(self) -> str:
        """Cache key for this measure.

        Over the *parsed and re-serialised* request, so that whitespace, comments and
        clause order do not miss the cache... except that there is no `unparse` yet
        (`todo.md` 1.1), so for now it hashes the source text. That is conservative --
        it causes extra recomputation, never a wrong cached value.
        """
        payload = "\x00".join([self.kind, self.scope.strip(), self.response.strip(), self.expression])
        return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()


@dataclass
class Point:
    """One treebank's value for one measure."""

    treebank: str
    language: str
    n_scope: int = 0
    n_hit: int = 0
    sample_pct: int = 100
    escalated: bool = False
    cached: bool = False
    seconds: float = 0.0
    error: str = ""

    @property
    def value(self) -> float | None:
        return 100.0 * self.n_hit / self.n_scope if self.n_scope else None

    @property
    def ci(self) -> tuple[float, float]:
        return wilson(self.n_hit, self.n_scope)

    def to_dict(self) -> dict:
        low, high = self.ci
        return {
            "treebank": self.treebank,
            "language": self.language,
            "value": self.value,
            "n_scope": self.n_scope,
            "n_hit": self.n_hit,
            "ci_low": low,
            "ci_high": high,
            "sample_pct": self.sample_pct,
            "escalated": self.escalated,
            "cached": self.cached,
            "seconds": round(self.seconds, 3),
            "error": self.error,
        }


@dataclass
class LanguagePoint:
    """Several treebanks of one language, merged.

    **By summing counts, never by averaging percentages.** French-GSD has 400k tokens and
    French-ParTUT has 27k; averaging their percentages would give the small one fifteen
    times the weight it deserves. Summing is also what the current site's `statConll.py`
    effectively did, since it concatenated a language's files before counting -- so this
    keeps the new numbers comparable with the old.
    """

    language: str
    treebanks: list[Point] = field(default_factory=list)

    @property
    def n_scope(self) -> int:
        return sum(p.n_scope for p in self.treebanks)

    @property
    def n_hit(self) -> int:
        return sum(p.n_hit for p in self.treebanks)

    @property
    def value(self) -> float | None:
        return 100.0 * self.n_hit / self.n_scope if self.n_scope else None

    def to_dict(self) -> dict:
        low, high = wilson(self.n_hit, self.n_scope)
        return {
            "language": self.language,
            "value": self.value,
            "n_scope": self.n_scope,
            "n_hit": self.n_hit,
            "ci_low": low,
            "ci_high": high,
            "n_treebanks": len(self.treebanks),
            "sampled": any(p.sample_pct < 100 for p in self.treebanks),
            "escalated": any(p.escalated for p in self.treebanks),
            "treebanks": [p.treebank for p in self.treebanks],
        }


def merge_by_language(points: Iterable[Point]) -> list[LanguagePoint]:
    merged: dict[str, LanguagePoint] = {}
    for point in points:
        if point.error or not point.n_scope:
            continue
        merged.setdefault(point.language, LanguagePoint(point.language)).treebanks.append(point)
    return sorted(merged.values(), key=lambda lp: lp.language)


# ------------------------------------------------------------------------ evaluation


@dataclass(frozen=True)
class SamplingPolicy:
    token_budget: int | None = DEFAULT_TOKEN_BUDGET  # None => never sample
    min_scope: int = DEFAULT_MIN_SCOPE
    ci_tolerance: float = DEFAULT_CI_TOLERANCE
    min_hits: int = DEFAULT_MIN_HITS

    def escalate(self, n_scope: int, n_hit: int) -> bool:
        """Should this sampled treebank be re-run in full?

        Three triggers, because there are three distinct ways a sample can fail, and each
        of the first two is invisible to the others:

        1. **The scope is too small to plot.** `n_scope < min_scope` -- the role
           `axminocc` plays on the current site, but applied to a number we know.

        2. **The interval is too wide.** Not the same test: `n_scope` is the
           *denominator*, and a scope can be perfectly common while the value is
           imprecise. 1 000 subjects split 50/50 passes any threshold on `n_scope` and
           still lands +/- 3.1 points, which is visible on the axis.

        3. **The numerator is too small.** Also not the same test, and the one that is
           easy to miss: 3 post-verbal subjects out of 50 000 gives a Wilson interval of
           0.002%-0.018% -- *narrower* than the tolerance, so rule 2 never fires -- while
           being a ninefold range and a 58% relative error. On a linear 0-100 axis that
           does not matter; in the tooltip, in an exported table, and in the sentence a
           paper writes about it, it does. This subsumes the zero-hit case, which needed
           catching anyway: "this language never does X" and "we did not sample enough to
           see X" are different claims and only the full treebank separates them.
        """
        if n_scope < self.min_scope:
            return True
        low, high = wilson(n_hit, n_scope)
        if high - low > self.ci_tolerance:
            return True
        return n_hit < self.min_hits
