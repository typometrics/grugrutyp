"""Unit tests for the measure layer: statistics, sampling policy, merging, binding rule.

No services needed. The differential suite guards the counts; this guards what we do to
them afterwards, which is where a plot acquires a lie that still looks like a finding.
"""

from __future__ import annotations

import pytest

from grugrutyp.measure import (
    LanguagePoint,
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


def test_a_cheap_escalation_still_runs_by_itself():
    """A 200k-token language escalates to 100%: that pass reads 200k tokens, seconds."""
    assert not SamplingPolicy().defers_escalation(200_000)


def test_a_mid_size_language_also_escalates_by_itself():
    """Belarusian, Catalan, Ancient Greek-sized languages (300k-1M tokens).

    The first cut deferred anything over 300k, which flagged 31 SUD languages and put a
    refine proposal on every rare measure (Kim, 2026-08-30: "every query i try now" --
    27 names in the banner). A language whose escalation reaches its full corpus in one
    bounded pass refines itself; slightly slower runs beat a banner that cries wolf.
    """
    policy = SamplingPolicy()
    for n_tokens in (305_000, 530_000, 990_000):
        assert policy.escalated_pct(n_tokens) == 100
        assert not policy.defers_escalation(n_tokens)


def test_a_giant_language_defers_its_escalation_to_the_user():
    """Czech's SUD ~4.2M tokens escalate to ~24% -- a 1M-token rescan, minutes cold.

    Still a *sample* at the escalation ceiling: that is the mark of the giants, whose
    automatic rescans were the whole tail of a cold run, incurred because a rare
    response tripped the policy, not because anyone asked for precision on Czech. Those
    are a proposal in the plot, not an automatic cost.
    """
    policy = SamplingPolicy()
    assert policy.escalated_pct(4_200_000) < 100, "the giants stay sampled even escalated"
    assert policy.defers_escalation(4_200_000)


def test_deferral_can_be_switched_off():
    assert not SamplingPolicy(auto_escalation_tokens=None).defers_escalation(4_200_000)


def test_escalation_slots_bound_the_automatic_rescans_per_run():
    """A rare measure trips the policy in dozens of languages at once; each automatic
    rescan is minutes of cold disk. Measured 2026-09-01: 23 rescans, 100-260s each.
    The slots cap that at one worker round; the rest join the refine button."""
    from unittest.mock import patch

    from grugrutyp import runner
    from grugrutyp.engine.neo4j_engine import TreebankInfo

    def tb(name, lang, n):
        return TreebankInfo(name=name, scheme="SUD", language=lang, corpus=name,
                            family="", n_sents=n // 20, n_tokens=n, imported_at="r")

    spec = MeasureSpec(scope="pattern { GOV -[1=subj]-> DEP }", response="with { GOV << DEP }")
    options = runner.RunOptions(policy=SamplingPolicy())
    slots = runner.EscalationSlots(1)

    with patch.object(runner, "_counts_at", lambda *a, **k: (50_000, 3.0, False)):
        first = runner.evaluate_language(
            [spec], [tb("SUD_A-x", "A", 500_000)], options, slots=slots
        )
        second = runner.evaluate_language(
            [spec], [tb("SUD_B-x", "B", 500_000)], options, slots=slots
        )
    assert first[0][0].escalated and not first[0][0].refinable, "the slot is spent here"
    assert not second[0][0].escalated and second[0][0].refinable, "and refused here"


def test_the_refine_budget_cannot_defer_again():
    """The refine run uses token_budget = escalation_budget; its own escalation target
    then never exceeds the percentage already run, so refining terminates in one pass."""
    policy = SamplingPolicy(token_budget=1_000_000)
    for n_tokens in (1_200_000, 3_500_000, 4_200_000):
        assert policy.escalated_pct(n_tokens) <= sample_pct(n_tokens, policy.token_budget)


def test_a_deferred_point_says_so_in_its_dict():
    point = Point(treebank="SUD_Czech-PDTC", language="Czech", n_scope=5_000, n_hit=3,
                  sample_pct=3, refinable=True)
    assert point.to_dict()["refinable"] is True
    merged = merge_by_language([point])
    assert merged[0].to_dict()["refinable"] is True


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


# ------------------------------------------------------------------------------- cache


def test_cache_is_keyed_on_the_treebank_revision(tmp_path):
    """A re-imported treebank must not serve counts taken against its previous contents.

    This is not hypothetical: the full 2.18 import re-imports every treebank, and the
    dev-slice numbers were computed before it ran.
    """
    from grugrutyp.cache import MeasureCache

    cache = MeasureCache(tmp_path / "c.sqlite")
    cache.put("SUD_French-GSD", "h", 100, 1000, 500, revision="2026-08-28T10:00:00")

    assert cache.get("SUD_French-GSD", "h", 100, revision="2026-08-28T10:00:00") == (1000, 500)
    assert cache.get("SUD_French-GSD", "h", 100, revision="2026-08-29T04:00:00") is None


def test_cache_separates_sampled_from_exact_counts(tmp_path):
    """Asking for an exact number must never be answered from a sampled one."""
    from grugrutyp.cache import MeasureCache

    cache = MeasureCache(tmp_path / "c.sqlite")
    cache.put("SUD_Russian-SynTagRus", "h", 7, 12044, 3644, revision="r")
    assert cache.get("SUD_Russian-SynTagRus", "h", 100, revision="r") is None
    assert cache.get("SUD_Russian-SynTagRus", "h", 7, revision="r") == (12044, 3644)


def test_pruning_removes_superseded_revisions_only(tmp_path):
    from grugrutyp.cache import MeasureCache

    cache = MeasureCache(tmp_path / "c.sqlite")
    cache.put("a", "h", 100, 1, 1, revision="old")
    cache.put("a", "h", 100, 2, 2, revision="new")
    cache.put("b", "h", 100, 3, 3, revision="keep")

    assert cache.prune({"a": "new", "b": "keep"}) == 1
    assert cache.get("a", "h", 100, revision="new") == (2, 2)
    assert cache.get("b", "h", 100, revision="keep") == (3, 3)


# ------------------------------------------------------------------ treebank spread


def test_spread_reports_the_range_of_a_languages_treebanks():
    """The Wilson interval says how precisely the corpus mix was measured; the spread
    says whether there is one language in there to measure (audit 2026-09-02)."""
    point = LanguagePoint(
        language="French",
        treebanks=[
            Point(treebank="A", language="French", n_scope=1000, n_hit=192),  # 19.2%
            Point(treebank="B", language="French", n_scope=500, n_hit=196),   # 39.2%
        ],
    )
    low, high = point.spread()
    assert low == pytest.approx(19.2) and high == pytest.approx(39.2)
    # the merged interval is an order of magnitude narrower than the disagreement
    data = point.to_dict()
    assert data["ci_high"] - data["ci_low"] < high - low
    assert data["spread_low"] == pytest.approx(19.2)


def test_a_thin_treebank_does_not_widen_the_spread():
    """Its own value is noise, so it would report variability that is not there."""
    point = LanguagePoint(
        language="Wolof",
        treebanks=[
            Point(treebank="A", language="Wolof", n_scope=1000, n_hit=300),
            Point(treebank="B", language="Wolof", n_scope=800, n_hit=248),
            Point(treebank="tiny", language="Wolof", n_scope=4, n_hit=4),  # 100%, n=4
        ],
    )
    assert point.spread()[1] == pytest.approx(31.0)


def test_a_single_treebank_language_has_no_spread():
    point = LanguagePoint(
        language="Manx",
        treebanks=[Point(treebank="A", language="Manx", n_scope=200, n_hit=50)],
    )
    assert point.spread() is None
    assert point.to_dict()["spread_low"] is None


# ------------------------------------------------------------------- flexibility (C)


def test_flexibility_needs_gov_and_dep():
    """The measure adds its own `with { GOV << DEP }`, so the names are the contract."""
    with pytest.raises(ValueError) as excinfo:
        MeasureSpec(scope="pattern { X -[1=subj]-> Y }", kind="flexibility").validate()
    assert "GOV and DEP" in str(excinfo.value)


def test_flexibility_refuses_a_response():
    with pytest.raises(ValueError) as excinfo:
        MeasureSpec(
            scope="pattern { GOV -[1=subj]-> DEP }",
            response="with { GOV << DEP }",
            kind="flexibility",
        ).validate()
    assert "no response pattern" in str(excinfo.value)


def test_flexibility_merges_as_a_weighted_mean():
    """Two treebanks, weights 100 and 300: the language value is the weighted mean of
    40 and 80, i.e. 70 -- not the unweighted 60."""
    point = LanguagePoint(
        language="Test",
        treebanks=[
            Point(treebank="A", language="Test", kind="flexibility", n_scope=100, total=4000.0),
            Point(treebank="B", language="Test", kind="flexibility", n_scope=300, total=24000.0),
        ],
    )
    assert point.value == pytest.approx(70.0)
    data = point.to_dict()
    assert data["ci_low"] is None, "a weighted mean has no binomial interval"


def test_flexibility_hashes_differently_from_a_ratio_on_the_same_scope():
    """Otherwise the two measures would share a cache row."""
    scope = "pattern { GOV -[1=subj]-> DEP }"
    assert (
        MeasureSpec(scope=scope, kind="flexibility").query_hash()
        != MeasureSpec(scope=scope, response="with { GOV << DEP }").query_hash()
    )
