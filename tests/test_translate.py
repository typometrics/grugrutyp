"""Unit tests for the Grew -> Cypher translator.

These check the *shape* of the emitted Cypher and the parameter binding. Semantic
equivalence with Grew is the job of test_differential.py; this file catches the things an
oracle cannot -- constructs grewlib rejects, injection safety, and error quality.
"""

from __future__ import annotations

import pytest

from grugrutyp.translate.cypher import UnsupportedConstruct, combine, translate
from grugrutyp.translate.parser import GrewSyntaxError, parse, parse_subquery

TB = "SUD_French-GSD"


def emit(text: str, **kwargs):
    return translate(parse(text), TB, **kwargs)


def test_every_literal_is_a_parameter():
    """No literal may reach the query string: plan reuse across treebanks, and safety."""
    result = emit('pattern { X [lemma="d\'; DETACH DELETE X //"] }')
    assert "DETACH DELETE" not in result.cypher
    assert "d'; DETACH DELETE X //" in result.params.values()


def test_treebank_is_parameterised():
    result = emit("pattern { X [upos=VERB] }")
    assert TB in result.params.values()
    assert TB not in result.cypher


def test_bare_node_is_accepted_even_though_grew_rejects_it():
    # grewlib refuses `pattern { X }`; we allow it, so it has no oracle and lives here.
    result = emit("pattern { X }")
    assert "MATCH (X:Word" in result.cypher
    assert "RETURN count(*) AS n" in result.cypher


def test_same_sentence_constraint_is_emitted_for_every_node():
    result = emit("pattern { X [upos=VERB]; Y [upos=NOUN] }")
    assert result.cypher.count("-[:IN_SENTENCE]->(_s)") == 2


def test_injectivity_guard_between_pattern_nodes():
    result = emit("pattern { X -> Y; X -> Z }")
    assert "Y.idx <> Z.idx" in result.cypher


def test_dollar_suffix_disables_the_injectivity_guard():
    result = emit("pattern { X -> Y; X -> Z$ }")
    assert "Y.idx <> Z.idx" not in result.cypher
    assert "Z.idx <> Y.idx" not in result.cypher


def test_injectivity_spans_with_blocks():
    """A node introduced by `with` is distinct from the pattern's nodes too."""
    result = emit("pattern { X -[subj]-> Y } with { X -> Z [upos=ADV] }")
    assert "Z.idx <> X.idx" in result.cypher or "Z.idx <> Y.idx" in result.cypher


def test_with_becomes_exists_not_inline_match():
    """Inlining `with` would multiply the matching count -- see docs/query-pairs.md."""
    result = emit("pattern { X -[subj]-> Y } with { X -> Z [upos=ADV] }")
    assert "EXISTS {" in result.cypher
    assert "NOT EXISTS {" not in result.cypher


def test_without_becomes_not_exists():
    result = emit("pattern { X -[subj]-> Y } without { X -> Z [upos=ADV] }")
    assert "NOT EXISTS {" in result.cypher


def test_pure_filter_without_uses_coalesce():
    """`without` over a plain condition must not drop rows where the feature is absent."""
    result = emit("pattern { X -> Y } without { X [upos=VERB] }")
    assert "coalesce(" in result.cypher
    assert "EXISTS" not in result.cypher


def test_neq_requires_the_feature_to_be_defined():
    result = emit("pattern { X [upos <> VERB] }")
    assert "IS NOT NULL" in result.cypher


def test_regex_is_passed_through_unanchored():
    """Grew and Cypher both match the whole string, so no `.*` wrapping."""
    result = emit('pattern { X [lemma = re"ab"] }')
    assert "ab" in result.params.values()
    assert ".*ab.*" not in result.params.values()


def test_pcre_case_insensitive_flag_becomes_inline():
    result = emit("pattern { X [lemma = /ab/i] }")
    assert "(?i)ab" in result.params.values()


def test_order_uses_idx_arithmetic_not_successor():
    precedes = emit("pattern { X -> Y; X << Y }")
    assert "X.idx < Y.idx" in precedes.cypher
    assert "SUCCESSOR" not in precedes.cypher

    immediate = emit("pattern { X -> Y; X < Y }")
    assert "X.idx + 1 = Y.idx" in immediate.cypher


def test_follows_is_the_mirror_of_precedes():
    """Grew has all four order spellings; `A >> N` is `N << A` and must compile to it."""
    assert emit("pattern { X -> Y; Y >> X }").cypher == emit("pattern { X -> Y; X << Y }").cypher
    assert emit("pattern { X -> Y; Y > X }").cypher == emit("pattern { X -> Y; X < Y }").cypher


def test_delta_and_length():
    assert "(Y.idx - X.idx) = " in emit("pattern { X -> Y; delta(X,Y) = 3 }").cypher
    assert "abs(Y.idx - X.idx) <= " in emit("pattern { X -> Y; length(X,Y) <= 3 }").cypher


def test_edge_label_features_map_to_decomposed_properties():
    result = emit("pattern { X -[1=comp, 2=obj]-> Y }")
    assert "rel_1:" in result.cypher and "rel_2:" in result.cypher


def test_plain_edge_label_matches_full_deprel():
    result = emit("pattern { X -[comp]-> Y }")
    assert "deprel:" in result.cypher
    assert "comp" in result.params.values()


def test_dominance_becomes_variable_length_path():
    assert "[:DEPREL*1..]" in emit("pattern { X -> Y; X ->> Y$ }").cypher


def test_global_maps_to_precomputed_sentence_properties():
    assert "_s.is_projective" in emit("pattern { X -> Y } global { is_projective }").cypher
    assert "_s.is_tree" in emit("pattern { X -> Y } global { is_tree }").cypher


def test_search_mode_returns_conllu_and_positions():
    result = emit("pattern { X -[subj]-> Y }", mode="search", limit=5)
    assert "_s.conllu AS conllu" in result.cypher
    assert "matched_nodes" in result.cypher
    assert 5 in result.params.values()


def test_aggregate_mode():
    result = emit(
        "pattern { GOV -[1=subj]-> DEP }", mode="aggregate", aggregate="avg(DEP.idx - GOV.idx)"
    )
    assert "avg(DEP.idx - GOV.idx) AS value" in result.cypher
    assert "count(*) AS n" in result.cypher


# ------------------------------------------------------------------ error quality


def test_syntax_error_carries_a_position():
    with pytest.raises(GrewSyntaxError) as excinfo:
        parse("pattern { X -[subj-> Y }")
    assert excinfo.value.line == 1
    assert excinfo.value.column is not None


def test_unknown_edge_feature_is_rejected_with_a_hint():
    with pytest.raises(UnsupportedConstruct, match="rel_deep|deep"):
        emit("pattern { X -[3=comp]-> Y }")


def test_unsupported_global_is_rejected_rather_than_mistranslated():
    with pytest.raises(UnsupportedConstruct, match="is_forest"):
        emit("pattern { X -> Y } global { is_forest }")


def test_unqueryable_meta_key_is_rejected():
    with pytest.raises(UnsupportedConstruct, match="meta"):
        emit('pattern { X -> Y; meta.speaker_id = "a" }')


# ------------------------------------------------------------ query-pair assembly


def test_combine_rejects_a_pattern_block_in_the_subquery():
    scope = parse("pattern { GOV -[1=subj]-> DEP }")
    subquery = parse("pattern { GOV -> OTHER }")
    with pytest.raises(UnsupportedConstruct, match="pattern"):
        combine(scope, subquery)


def test_combine_appends_with_blocks():
    scope = parse("pattern { GOV -[1=subj]-> DEP }")
    combined = combine(scope, parse_subquery("GOV << DEP"))
    assert [b.kind for b in combined.blocks] == ["pattern", "with"]
    assert "GOV.idx < DEP.idx" in translate(combined, TB).cypher


def test_parse_subquery_wraps_a_bare_body():
    assert [b.kind for b in parse_subquery("GOV << DEP").blocks] == ["with"]
    assert [b.kind for b in parse_subquery("with { GOV << DEP }").blocks] == ["with"]
    assert [b.kind for b in parse_subquery("GOV << DEP", kind="without").blocks] == ["without"]
