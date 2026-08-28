"""Unit tests for the measure layer: statistics, sampling policy, merging, binding rule.

No services needed. The differential suite guards the counts; this guards what we do to
them afterwards, which is where a plot acquires a lie that still looks like a finding.
"""

from __future__ import annotations

import pytest

from grugrutyp.measure import (
    MeasureSpec,
    Point,
    SamplingPolicy,
    merge_by_language,
    sample_pct,
    wilson,
)
from grugrutyp.translate.cypher import UnsupportedConstruct, combine, translate
from grugrutyp.translate.parser import parse


# ------------------------------------------------------------------------- statistics


def test_wilson_matches_measured_values():
    """The two intervals recorded in docs/sampling.md section 2, to 2 decimal places."""
    assert [round(v, 2) for v in wilson(35691, 120203)] == [29.43, 29.95]
    assert [round(v, 2) for v in wilson(3644, 12044)] == [29.44, 31.08]


def test_wilson_stays_inside_the_scale_at_the_edges():
    """Where the normal approximation runs off the end of the axis and Wilson does not."""
    low, high = wilson(0, 100)
    assert low == 0.0 and 0 < high < 5
    low, high = wilson(100, 100)
    assert high == 100.0 and 95 < low < 100
    # A rare phenomenon in a large scope: still an interval, still asymmetric.
    low, high = wilson(3, 50_000)
    assert 0 < low < 0.006 < high < 0.02


def test_wilson_of_an_empty_scope_is_maximally_uncertain():
    assert wilson(0, 0) == (0.0, 100.0)


def test_wilson_narrows_with_n_at_a_fixed_proportion():
    widths = [wilson(n // 2, n)[1] - wilson(n // 2, n)[0] for n in (100, 1_000, 10_000)]
    assert widths[0] > widths[1] > widths[2]


# ---------------------------------------------------------------------------- sampling


def test_sample_pct_never_cuts_a_treebank_under_the_budget():
    assert sample_pct(35_000, 100_000) == 100
    assert sample_pct(100_000, 100_000) == 100


def test_sample_pct_cuts_the_giants_proportionally():
    assert sample_pct(6_950_000, 100_000) == 2  # UD_Czech-PDTC
    assert sample_pct(1_500_000, 100_000) == 7  # SUD_Russian-SynTagRus
    assert sample_pct(200_000, 100_000) == 50


def test_sample_pct_never_reaches_zero():
    assert sample_pct(10**9, 100) == 1


def test_no_budget_means_no_sampling():
    assert sample_pct(10**9, None) == 100
    assert sample_pct(10**9, 0) == 100


def test_escalation_triggers_on_a_small_scope():
    assert SamplingPolicy().escalate(n_scope=10, n_hit=5)


def test_escalation_triggers_on_a_wide_interval_despite_a_large_scope():
    """n_scope is the denominator: a common scope can still give an imprecise value."""
    assert SamplingPolicy(min_scope=30, ci_tolerance=2.0).escalate(n_scope=1_000, n_hit=500)


def test_escalation_triggers_on_a_tiny_numerator_the_interval_test_misses():
    """The third failure mode, and the one the percentage-point rule cannot see.

    3 of 50 000 has a Wilson interval of 0.002%-0.018% -- narrower than any sane
    tolerance -- while being a ninefold range and a 58% relative error.
    """
    policy = SamplingPolicy(min_scope=30, ci_tolerance=2.0, min_hits=10)
    low, high = wilson(3, 50_000)
    assert high - low < policy.ci_tolerance, "the interval rule must not be what fires here"
    assert policy.escalate(n_scope=50_000, n_hit=3)


def test_escalation_triggers_on_zero_hits():
    """'This language never does X' and 'we did not sample enough to see X' differ."""
    assert SamplingPolicy().escalate(n_scope=100_000, n_hit=0)


def test_a_precise_sample_is_left_alone():
    assert not SamplingPolicy().escalate(n_scope=120_000, n_hit=35_691)


# ----------------------------------------------------------------------------- merging


def _point(language, treebank, n_scope, n_hit):
    return Point(treebank=treebank, language=language, n_scope=n_scope, n_hit=n_hit)


def test_languages_merge_by_summing_counts_not_by_averaging_percentages():
    """The whole reason merging is done here rather than in the plot.

    A 27k-token treebank at 90% and a 400k-token one at 10% is 17.9%, not 50%.
    """
    merged = merge_by_language(
        [_point("French", "SUD_French-GSD", 10_000, 1_000),
         _point("French", "SUD_French-ParTUT", 1_000, 900)]
    )
    assert len(merged) == 1
    assert merged[0].n_scope == 11_000 and merged[0].n_hit == 1_900
    assert round(merged[0].value, 2) == 17.27
    assert round((10.0 + 90.0) / 2, 2) == 50.0  # what averaging would have said


def test_merging_skips_failed_and_empty_treebanks():
    points = [
        _point("French", "SUD_French-GSD", 100, 10),
        Point(treebank="SUD_French-Broken", language="French", error="boom"),
        _point("Wolof", "SUD_Wolof-WTB", 0, 0),
    ]
    merged = {lp.language: lp for lp in merge_by_language(points)}
    assert set(merged) == {"French"}
    assert merged["French"].n_scope == 100


def test_a_language_point_reports_how_many_treebanks_it_came_from():
    merged = merge_by_language(
        [_point("French", "a", 10, 1), _point("French", "b", 10, 2), _point("Wolof", "c", 10, 3)]
    )
    assert [lp.to_dict()["n_treebanks"] for lp in merged] == [2, 1]


def test_point_value_is_none_for_an_empty_scope():
    assert Point(treebank="t", language="l").value is None


# ------------------------------------------------------------- the query-pair contract


SCOPE = "pattern { GOV -[1=subj]-> DEP }"


def test_a_response_may_only_use_nodes_the_scope_binds():
    """`with { GOV << Z }` measures 'some word follows GOV', not subject position."""
    with pytest.raises(UnsupportedConstruct, match=r"\bZ\b"):
        combine(parse(SCOPE), parse("with { GOV << Z }"))


def test_a_response_using_only_bound_nodes_is_accepted():
    combined = combine(parse(SCOPE), parse("with { GOV << DEP }"))
    assert len(combined.blocks) == 2


def test_a_response_may_not_contain_a_pattern_block():
    with pytest.raises(UnsupportedConstruct, match="pattern"):
        combine(parse(SCOPE), parse("pattern { GOV -> X }"))


def test_a_without_response_is_legitimate():
    combined = combine(parse(SCOPE), parse("without { DEP [upos=PRON] }"))
    assert [b.kind for b in combined.blocks] == ["pattern", "without"]


def test_the_binding_error_names_the_offending_node_and_what_is_available():
    with pytest.raises(UnsupportedConstruct) as excinfo:
        combine(parse(SCOPE), parse("with { GOV -> OBL }"))
    message = str(excinfo.value)
    assert "OBL" in message and "GOV" in message and "DEP" in message


def test_a_spec_with_no_pattern_block_is_rejected():
    with pytest.raises(ValueError, match="pattern"):
        MeasureSpec(scope="with { GOV << DEP }").validate()


def test_query_hash_ignores_surrounding_whitespace_but_not_content():
    a = MeasureSpec(scope=SCOPE, response="with { GOV << DEP }")
    b = MeasureSpec(scope=f"  {SCOPE}  ", response="with { GOV << DEP }\n")
    c = MeasureSpec(scope=SCOPE, response="without { GOV << DEP }")
    assert a.query_hash() == b.query_hash()
    assert a.query_hash() != c.query_hash()


# ---------------------------------------------------------------------- sampling clause


def test_sampling_adds_a_bucket_filter_bound_as_a_parameter():
    translation = translate(parse(SCOPE), "SUD_French-GSD", mode="count", sample=10)
    assert "_s.bucket <" in translation.cypher
    assert 10 in translation.params.values()


def test_a_full_sample_adds_no_filter():
    for sample in (None, 100):
        translation = translate(parse(SCOPE), "SUD_French-GSD", mode="count", sample=sample)
        assert "bucket" not in translation.cypher


def test_the_bucket_filter_is_on_the_sentence_so_both_halves_see_one_sub_corpus():
    """S and Q must be evaluated over the same sentences or the ratio is not a ratio."""
    combined = combine(parse(SCOPE), parse("with { GOV << DEP }"))
    scope_only = translate(parse(SCOPE), "SUD_French-GSD", mode="count", sample=25)
    with_response = translate(combined, "SUD_French-GSD", mode="count", sample=25)
    assert scope_only.cypher.count("_s.bucket <") == 1
    assert with_response.cypher.count("_s.bucket <") == 1
