"""The *aggregate* measure kind: a mean over matchings rather than a ratio of them.

`docs/measures-mapping.md` §3. Four of the current site's twelve measures are not query
pairs at all -- `f-dist`, `f-dist-abs`, `cfc-dist` and `treeHeight` are means of a numeric
value over the matchings of a scope, not `#(S∧Q)/#(S)`. They need the same scope query and
a different reduction:

    measure = mean over matchings of S of  delta(GOV, DEP)

**This module exists because that expression cannot be passed through to Cypher.** Every
other literal in a translated query is a bound parameter (`CLAUDE.md` rule 3), but an
aggregate expression is *structure* -- it has to be interpolated into the statement, and
there is no parameter form for `avg(DEP.idx - GOV.idx)`. A user-supplied string reaching
that position is Cypher injection, and Neo4j's Cypher is expressive enough that it would
be a serious one.

So the expression is not passed through. It is parsed against a closed grammar, every node
identifier is checked against the ones the scope actually binds, and the Cypher is
*generated*. Nothing the user typed is ever concatenated into the statement -- only
identifiers we have already matched against a whitelist, and property names that survived
a strict pattern.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Which aggregations exist, and how a language's treebanks combine.
#
# The merge rule is the constraint, and it excludes two obvious candidates. Points are
# plotted per language but computed per treebank, so every aggregation has to be
# reconstructible from per-treebank results. `avg` is, if the query returns the *sum* and
# the count rather than the mean -- a mean of means would weigh a 27k-token treebank the
# same as a 400k one, the same error the ratio kind avoids by summing counts.
# `median` and `stddev` are **not**: there is no way to combine per-treebank medians into
# a corpus median, or per-treebank standard deviations into a corpus one, without the raw
# values. Offering them would mean plotting a number nobody could define. They are left
# out, and `compile` says so rather than failing obscurely.
#
# `accumulator` is what Cypher computes per treebank; `merge` is how those combine.
AGGREGATIONS: dict[str, dict[str, str]] = {
    "avg": {"accumulator": "sum({expr})", "merge": "ratio", "label": "mean"},
    "sum": {"accumulator": "sum({expr})", "merge": "sum", "label": "total"},
    "min": {"accumulator": "min({expr})", "merge": "min", "label": "minimum"},
    "max": {"accumulator": "max({expr})", "merge": "max", "label": "maximum"},
}
UNMERGEABLE = {
    "median": "a corpus median cannot be reconstructed from per-treebank medians",
    "stddev": "a corpus standard deviation cannot be reconstructed from per-treebank ones",
    "percentile": "percentiles cannot be reconstructed from per-treebank percentiles",
}
DEFAULT_AGGREGATION = "avg"

# A node identifier as Grew allows it, and nothing else. Checked against the scope's bound
# names as well -- this pattern only rules out the shapes that could not be an identifier.
_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"

# A feature name, including UD's layered notation (`Number[psor]`).
_FEATURE = r"[A-Za-z_][A-Za-z0-9_]*(?:\[[A-Za-z0-9_]+\])?"

_DELTA = re.compile(rf"^\s*delta\s*\(\s*({_IDENT})\s*,\s*({_IDENT})\s*\)\s*$")
_ABS_DELTA = re.compile(rf"^\s*abs\s*\(\s*delta\s*\(\s*({_IDENT})\s*,\s*({_IDENT})\s*\)\s*\)\s*$")
_LENGTH = re.compile(rf"^\s*length\s*\(\s*({_IDENT})\s*,\s*({_IDENT})\s*\)\s*$")
_FEATURE_REF = re.compile(rf"^\s*({_IDENT})\.({_FEATURE})\s*$")

# Sentence-level values precomputed at import (`docs/measures-mapping.md` §3 recommends
# exactly this rather than a path-length aggregate). They take no node argument.
SENTENCE_VALUES = {
    "height": "height",
    "n_tokens": "n_tokens",
    "length": "n_tokens",  # a friendlier spelling of the same thing
}
_SENTENCE_REF = re.compile(rf"^\s*sentence\.({_IDENT})\s*$")


class InvalidExpression(ValueError):
    """A message a linguist can act on, not a parser dump."""


@dataclass(frozen=True)
class CompiledExpression:
    cypher: str
    # Which node identifiers the expression reads, so the caller can check they are bound
    # and so an aggregate over a sentence value can skip the node machinery entirely.
    nodes: frozenset[str]
    sentence_level: bool = False


def compile_expression(
    expression: str, bound: set[str], sentence_var: str = "_s"
) -> CompiledExpression:
    """Turn a measure expression into Cypher, or refuse.

    `bound` is the set of node identifiers the scope binds. Checking against it is not
    only a safety property: an expression naming a node the scope does not bind is a
    measure that means nothing, exactly as in the query-pair binding rule.
    """
    text = (expression or "").strip()
    if not text:
        raise InvalidExpression("an aggregate measure needs an expression, e.g. delta(GOV, DEP)")

    def check(*names: str) -> None:
        unknown = sorted(n for n in names if n not in bound)
        if unknown:
            known = ", ".join(sorted(bound)) or "nothing"
            raise InvalidExpression(
                f"{', '.join(unknown)} is not bound by the scope (it binds {known})"
            )

    match = _SENTENCE_REF.match(text)
    if match:
        value = match.group(1)
        if value not in SENTENCE_VALUES:
            raise InvalidExpression(
                f"sentence.{value} is not available. "
                f"Try: {', '.join('sentence.' + k for k in sorted(SENTENCE_VALUES))}"
            )
        return CompiledExpression(
            cypher=f"{sentence_var}.{SENTENCE_VALUES[value]}",
            nodes=frozenset(),
            sentence_level=True,
        )

    match = _ABS_DELTA.match(text)
    if match:
        left, right = match.groups()
        check(left, right)
        return CompiledExpression(f"abs({right}.idx - {left}.idx)", frozenset({left, right}))

    match = _DELTA.match(text)
    if match:
        left, right = match.groups()
        check(left, right)
        # Signed, dependent minus governor, which is `ni - gi` in statConll.py -- so a
        # positive value means the second node follows the first, and the sign carries the
        # word-order information the measure exists for.
        return CompiledExpression(f"({right}.idx - {left}.idx)", frozenset({left, right}))

    match = _LENGTH.match(text)
    if match:
        left, right = match.groups()
        check(left, right)
        # Grew's `length` counts the words between, inclusive of neither endpoint's own
        # position -- the same absolute distance, which is what `abs(delta(...))` gives.
        return CompiledExpression(f"abs({right}.idx - {left}.idx)", frozenset({left, right}))

    match = _FEATURE_REF.match(text)
    if match:
        node, feature = match.groups()
        check(node)
        # The property name is generated from a pattern-checked capture, never from raw
        # input, and backticked so a layered name like `Number[psor]` is a legal
        # identifier. Cypher has no parameter form for a property name.
        return CompiledExpression(
            f"toFloat({node}.`{feature}`)", frozenset({node})
        )

    raise InvalidExpression(
        f"{text!r} is not an expression I can compute. Supported forms:\n"
        "  delta(GOV, DEP)        signed distance, dependent minus governor\n"
        "  abs(delta(GOV, DEP))   absolute distance\n"
        "  length(GOV, DEP)       same as abs(delta(...))\n"
        "  X.Feature              a numeric feature of a bound node\n"
        "  sentence.height        a precomputed sentence value "
        f"({', '.join(sorted(SENTENCE_VALUES))})"
    )


def aggregation_cypher(aggregation: str, expression_cypher: str) -> str:
    """The Cypher accumulator for this aggregation.

    For `avg` this is `sum(...)`, not `avg(...)`: the count comes back alongside it and the
    division happens after merging, so a language's treebanks combine by weight rather than
    by count of treebanks.
    """
    if aggregation in UNMERGEABLE:
        raise InvalidExpression(
            f"{aggregation} is not available, because {UNMERGEABLE[aggregation]}. "
            "Points are plotted per language but computed per treebank, so an aggregation "
            "has to be reconstructible from per-treebank results. Available: "
            + ", ".join(sorted(AGGREGATIONS))
        )
    if aggregation not in AGGREGATIONS:
        raise InvalidExpression(
            f"{aggregation!r} is not an aggregation. Use one of: "
            + ", ".join(sorted(AGGREGATIONS))
        )
    return AGGREGATIONS[aggregation]["accumulator"].format(expr=expression_cypher)


def merge_rule(aggregation: str) -> str:
    return AGGREGATIONS[aggregation]["merge"]
