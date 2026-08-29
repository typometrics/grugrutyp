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

from .aggregate import (
    DEFAULT_AGGREGATION,
    aggregation_cypher,
    compile_expression,
    merge_rule,
)
from .translate.cypher import combine, translate
from .translate.parser import parse
from .translate.unparse import unparse

Kind = Literal["ratio", "aggregate"]

# --------------------------------------------------------------------------- defaults

# Tokens per **language** the sampler aims to scan (the runner samples a language as one
# unit, at one rate across its treebanks -- see `runner.evaluate_language`). 100k gave a
# measured 2.7x speed-up when it was applied per treebank; per language it cuts slightly
# deeper, since the small treebanks of large languages now share the language's rate.
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

# How far an escalating treebank may go. Ten times the ordinary budget: enough to narrow a
# Wilson interval by ~3x, while keeping the giants out of the multi-minute tail that
# dominates a full pass on this hardware (`docs/performance.md`).
DEFAULT_ESCALATION_BUDGET = 1_000_000

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
    """The percentage of sentences to scan for a corpus of this size.

    A fixed percentage would over-sample the giants and destroy the small languages; a
    budget cuts only what is already more precise than the plot can show. Czech's ~4M
    SUD tokens become 3%, while the median small language is untouched.
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
    expression: str = ""  # aggregate kind: delta(GOV,DEP), sentence.height, ...
    aggregation: str = DEFAULT_AGGREGATION  # avg | median | stddev | min | max | sum
    label: str = ""

    def validate(self) -> None:
        """Parse, combine and compile without touching the database.

        Doing this once up front matters: the alternative is discovering that Q names an
        unbound node on treebank 300 of 705, having spent five minutes on numbers that
        mean nothing.
        """
        scope = parse(self.scope)
        if not list(scope.blocks_of("pattern")):
            raise ValueError("the scope needs a `pattern { ... }` block")
        if self.response.strip():
            combine(scope, parse(self.response))
        if self.kind == "aggregate":
            # Compiled here as well as at query time, so an unusable expression is
            # reported before the fan-out rather than 705 times during it.
            compile_expression(self.expression, scope.bound_nodes())
            aggregation_cypher(self.aggregation, "x")

    @property
    def is_ratio(self) -> bool:
        return self.kind != "aggregate"

    @property
    def unit(self) -> str:
        """What the axis is measured in. A ratio is a percentage; an aggregate is not.

        The plot needs this: a percentage axis is fixed to 0-100, and pinning a mean
        dependency distance to that range would put every language in the bottom 5% of the
        chart.
        """
        return "%" if self.is_ratio else ""

    def query_hash(self) -> str:
        """Cache key for this measure.

        Over the **parsed and re-serialised** request, so that a comment, a reflowed line
        or a changed space does not re-run 705 treebanks for a query that has not changed.
        A request that will not parse falls back to its raw text: `validate()` is what
        reports syntax errors, with a position, and a hash over broken text can only cause
        a miss, never a wrong hit.
        """
        def canonical(text: str) -> str:
            text = text.strip()
            if not text:
                return ""
            try:
                return unparse(parse(text))
            except Exception:  # noqa: BLE001 -- see the docstring
                return text

        payload = "\x00".join(
            [
                self.kind,
                canonical(self.scope),
                canonical(self.response),
                self.expression.strip(),
                self.aggregation,
            ]
        )
        return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()


@dataclass
class Point:
    """One treebank's value for one measure."""

    treebank: str
    language: str
    n_scope: int = 0
    n_hit: int = 0
    # Aggregate kind only: the accumulator Cypher returned (a sum, for `avg`). Kept
    # separate from `n_hit` because it is a float and can be negative -- a mean signed
    # dependency distance is negative in a head-final language.
    total: float | None = None
    kind: Kind = "ratio"
    aggregation: str = DEFAULT_AGGREGATION
    sample_pct: int = 100
    escalated: bool = False
    cached: bool = False
    seconds: float = 0.0
    error: str = ""

    @property
    def value(self) -> float | None:
        if self.kind == "aggregate":
            if self.total is None or not self.n_scope:
                return None
            return self.total / self.n_scope if merge_rule(self.aggregation) == "ratio" else self.total
        return 100.0 * self.n_hit / self.n_scope if self.n_scope else None

    @property
    def ci(self) -> tuple[float, float]:
        """Only a ratio has a binomial interval.

        An aggregate would need the variance of the expression, which the query does not
        return. Reporting a binomial interval around a mean distance would be nonsense
        dressed as rigour, so an aggregate reports none and the plot draws no whisker.
        """
        if self.kind == "aggregate":
            return (float("nan"), float("nan"))
        return wilson(self.n_hit, self.n_scope)

    def to_dict(self) -> dict:
        low, high = self.ci
        has_ci = low == low  # NaN is the only value not equal to itself
        return {
            "treebank": self.treebank,
            "language": self.language,
            "value": self.value,
            "kind": self.kind,
            "n_scope": self.n_scope,
            "n_hit": self.n_hit,
            "total": self.total,
            "ci_low": low if has_ci else None,
            "ci_high": high if has_ci else None,
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
    def kind(self) -> Kind:
        return self.treebanks[0].kind if self.treebanks else "ratio"

    @property
    def value(self) -> float | None:
        """The language's value, merged from its treebanks by the aggregation's own rule.

        `ratio` and `avg` both merge as a weighted quotient -- sum the numerators, sum the
        denominators, divide once at the end. That is the whole reason the query returns a
        sum rather than a mean.
        """
        if self.kind == "aggregate":
            totals = [p.total for p in self.treebanks if p.total is not None]
            if not totals:
                return None
            rule = merge_rule(self.treebanks[0].aggregation)
            if rule == "ratio":
                return sum(totals) / self.n_scope if self.n_scope else None
            if rule == "sum":
                return sum(totals)
            return min(totals) if rule == "min" else max(totals)
        return 100.0 * self.n_hit / self.n_scope if self.n_scope else None

    def to_dict(self) -> dict:
        # An aggregate has no binomial interval: see `Point.ci`.
        low, high = wilson(self.n_hit, self.n_scope) if self.kind != "aggregate" else (None, None)
        return {
            "language": self.language,
            "value": self.value,
            "kind": self.kind,
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
        if point.kind == "aggregate" and point.total is None:
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
    escalation_budget: int | None = DEFAULT_ESCALATION_BUDGET

    def escalated_pct(self, n_tokens: int) -> int:
        """How far to escalate a language that wants more data than the budget gave it.

        Not to 100%. Measured over 5 615 timed queries on this box: the median treebank
        answers in 1.48 s and 58% answer in under 2 s, but 3% take over a minute and the
        worst took 602 s -- and those are the giants, which is exactly what the token
        budget existed to protect the plot from. Escalating them to the full corpus undoes
        the sampling for the only treebanks where it was earning anything.

        So escalation is bounded by cost too: go to ten times the ordinary budget, and no
        further. That is enough to shrink a Wilson interval by roughly a factor of three
        while scanning at most ~1 M words instead of 3.5 M. A user who genuinely needs the
        exact number still has "exact (no sampling)" in the corpus-coverage control, where
        the cost is asked for rather than incurred behind their back.
        """
        if self.escalation_budget is None:
            return 100
        return sample_pct(n_tokens, self.escalation_budget)

    def escalate(self, n_scope: int, n_hit: int) -> bool:
        """Should this sampled language be re-run at a higher rate?

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
