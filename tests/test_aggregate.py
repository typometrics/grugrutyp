"""The aggregate expression compiler.

Half of these are injection tests. An aggregate expression is the one piece of a
translated query that cannot be a bound parameter -- `avg(DEP.idx - GOV.idx)` is
structure, and Cypher has no parameter form for it -- so it is the one place where user
input could reach the statement text. It does not: the expression is parsed against a
closed grammar and the Cypher is generated. These tests are what keeps that true.
"""

from __future__ import annotations

import pytest

from grugrutyp.aggregate import (
    InvalidExpression,
    aggregation_cypher,
    compile_expression,
    merge_rule,
)

BOUND = {"GOV", "DEP"}


# ------------------------------------------------------------------- supported forms


def test_delta_is_signed_dependent_minus_governor():
    """The sign carries the word order, which is the whole point of the measure.

    `statConll.py` computes `ni - gi`, so a positive value means DEP follows GOV.
    """
    compiled = compile_expression("delta(GOV, DEP)", BOUND)
    assert compiled.cypher == "(DEP.idx - GOV.idx)"
    assert compiled.nodes == {"GOV", "DEP"}


def test_abs_delta_and_length_are_the_same_thing():
    assert compile_expression("abs(delta(GOV, DEP))", BOUND).cypher == "abs(DEP.idx - GOV.idx)"
    assert compile_expression("length(GOV, DEP)", BOUND).cypher == "abs(DEP.idx - GOV.idx)"


def test_whitespace_is_irrelevant():
    assert compile_expression("  delta ( GOV , DEP )  ", BOUND).cypher == "(DEP.idx - GOV.idx)"


def test_a_numeric_feature_of_a_bound_node():
    compiled = compile_expression("DEP.Number", BOUND)
    assert compiled.cypher == "toFloat(DEP.`Number`)"
    assert compiled.nodes == {"DEP"}


def test_a_layered_feature_name_is_backticked_not_rejected():
    """`Number[psor]` is legal UD and is not a legal bare Cypher identifier."""
    assert compile_expression("DEP.Number[psor]", BOUND).cypher == "toFloat(DEP.`Number[psor]`)"


def test_sentence_values_need_no_bound_node():
    compiled = compile_expression("sentence.height", set())
    assert compiled.cypher == "_s.height"
    assert compiled.sentence_level and not compiled.nodes


def test_sentence_length_is_an_alias_for_n_tokens():
    assert compile_expression("sentence.length", set()).cypher == "_s.n_tokens"


# --------------------------------------------------------------------- binding rule


def test_an_unbound_node_is_refused_and_the_message_says_what_is_bound():
    with pytest.raises(InvalidExpression) as excinfo:
        compile_expression("delta(GOV, X)", BOUND)
    message = str(excinfo.value)
    assert "X" in message and "GOV" in message and "DEP" in message


def test_an_unbound_node_in_a_feature_reference_is_refused():
    with pytest.raises(InvalidExpression, match="Z"):
        compile_expression("Z.Number", BOUND)


def test_an_unknown_sentence_value_lists_the_known_ones():
    with pytest.raises(InvalidExpression, match="sentence.height"):
        compile_expression("sentence.perplexity", set())


# ----------------------------------------------------------------------- injection


@pytest.mark.parametrize(
    "attack",
    [
        "1) AS x MATCH (n) DETACH DELETE n RETURN count(1",
        "DEP.idx) + (SELECT 1",
        "delta(GOV, DEP)) UNION MATCH (n:Word) RETURN count(n",
        "GOV.idx; DROP DATABASE neo4j",
        "apoc.util.sleep(100000)",
        "delta(GOV, DEP) + delta(GOV, DEP)",  # arithmetic is not in the grammar either
        "count(*)",
        "GOV.`idx` + 1",
        "abs(delta(GOV, DEP)))",
        "delta(GOV, DEP) // comment",
        "$param",
        "",
        "   ",
    ],
)
def test_nothing_outside_the_grammar_compiles(attack):
    with pytest.raises(InvalidExpression):
        compile_expression(attack, BOUND)


def test_the_generated_cypher_never_contains_user_text_verbatim():
    """Every compiled form is built from pattern-checked captures, not concatenation.

    A node name reaching the output has already been matched against `bound`; a feature
    name has already survived the feature pattern. Nothing else from the input appears.
    """
    compiled = compile_expression("abs(delta(GOV, DEP))", BOUND)
    assert compiled.cypher == "abs(DEP.idx - GOV.idx)"
    # `delta` is the user's spelling; it does not survive into the output, because the
    # output was generated rather than edited.
    assert "delta" not in compiled.cypher


# --------------------------------------------------------------------- aggregations


def test_avg_accumulates_a_sum_so_that_treebanks_can_be_merged_by_weight():
    """A mean of means would weigh a 27k-token treebank like a 400k one.

    The count comes back alongside the sum and the division happens after merging, the
    same rule the ratio kind follows.
    """
    assert aggregation_cypher("avg", "X") == "sum(X)"
    assert merge_rule("avg") == "ratio"


def test_min_and_max_merge_as_themselves():
    assert aggregation_cypher("min", "X") == "min(X)"
    assert merge_rule("max") == "max"


def test_median_and_stddev_are_refused_with_the_reason():
    """Not an oversight: they cannot be reconstructed from per-treebank results."""
    for name in ("median", "stddev"):
        with pytest.raises(InvalidExpression, match="per-treebank"):
            aggregation_cypher(name, "X")


def test_an_unknown_aggregation_is_refused():
    with pytest.raises(InvalidExpression, match="avg"):
        aggregation_cypher("collect", "X")


def test_an_aggregation_name_cannot_smuggle_cypher():
    with pytest.raises(InvalidExpression):
        aggregation_cypher("avg(x)) MATCH (n) DELETE n RETURN avg((", "X")
