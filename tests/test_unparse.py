"""Round-trip: `parse(unparse(parse(s))) == parse(s)` for every construct we support.

The property that matters is **idempotence of the AST**, not of the text. `unparse` is
canonical on purpose -- it drops comments and fixes spacing -- so the text will not come
back identical, and should not. What must hold is that unparsing and re-parsing lands on
the same tree, because that is what makes `unparse` usable as a cache key.

The construct list is deliberately the same one `tests/test_differential.py` runs against
Grew: anything the translator claims to support has to survive the round trip too.
"""

from __future__ import annotations

import pytest

from grugrutyp.measure import MeasureSpec
from grugrutyp.translate.parser import parse
from grugrutyp.translate.unparse import unparse

REQUESTS = [
    # nodes and feature structures
    "pattern { X }",
    "pattern { X [upos=VERB] }",
    "pattern { X [upos=VERB|NOUN] }",
    "pattern { X [upos=VERB, Number=Sing] }",
    "pattern { X [upos<>VERB] }",
    "pattern { X [!Person] }",
    "pattern { X [Number] }",
    'pattern { X [lemma="être"] }',
    'pattern { X [form=re"a.*"] }',
    "pattern { X [form=/POSS/i] }",
    "pattern { X [upos=NOUN]|[upos=PROPN] }",
    "pattern { X [Number[psor]=Sing] }",
    # edges
    "pattern { X -> Y }",
    "pattern { X -[subj]-> Y }",
    "pattern { X -[subj|comp]-> Y }",
    "pattern { X -[^subj]-> Y }",
    "pattern { X -[1=comp, 2=obj]-> Y }",
    "pattern { e: X -[subj]-> Y }",
    "pattern { X ->> Y }",
    "pattern { * -[subj]-> Y }",
    "pattern { X -[subj]-> * }",
    "pattern { X [upos=VERB] -[subj]-> Y [upos=NOUN] }",
    # order and distance
    "pattern { X < Y }",
    "pattern { X << Y }",
    "pattern { X -[subj]-> Y; delta(X, Y) > 3 }",
    "pattern { X -[subj]-> Y; length(X, Y) <= 5 }",
    # comparisons
    "pattern { X -> Y; X.upos = Y.upos }",
    "pattern { X -> Y; X.upos <> Y.upos }",
    'pattern { X -> Y; X.lemma = "be" }',
    "pattern { X -> Y; !X.Person }",
    "pattern { e1: X -> Y; e2: Y -> Z; e1.label = e2.label }",
    # blocks
    "pattern { X -[subj]-> Y }\nwith { X << Y }",
    "pattern { X -[subj]-> Y }\nwithout { Y [upos=PRON] }",
    "pattern { X -> Y }\nglobal { is_projective }",
    "pattern { X -> Y }\nglobal { is_not_projective }",
    'pattern { X; meta.sent_id = "s1" }',
    "pattern { X; meta.text = * }",
    # injectivity opt-out
    "pattern { X -> Y; X -> Z$ }",
]


@pytest.mark.parametrize("source", REQUESTS)
def test_round_trip_preserves_the_ast(source):
    once = parse(source)
    twice = parse(unparse(once))
    assert twice == once, f"{source!r}\n  ->  {unparse(once)!r}"


@pytest.mark.parametrize("source", REQUESTS)
def test_unparse_is_idempotent(source):
    """A second pass must not keep rewriting -- otherwise it is not canonical."""
    first = unparse(parse(source))
    assert unparse(parse(first)) == first


def test_the_output_still_parses_as_the_same_translation():
    """Round-tripping must not change the emitted Cypher either."""
    from grugrutyp.translate.cypher import translate

    source = 'pattern { GOV [upos=VERB] -[1=subj]-> DEP }\nwith { GOV << DEP }'
    a = translate(parse(source), "tb", mode="count")
    b = translate(parse(unparse(parse(source))), "tb", mode="count")
    assert a.cypher == b.cypher and a.params == b.params


# ------------------------------------------------------------------ the cache pay-off


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("pattern { X -[subj]-> Y }", "pattern{X-[subj]->Y}"),
        ("pattern { X -[subj]-> Y }", "pattern {\n  X -[subj]-> Y\n}"),
        ("pattern { X -[subj]-> Y }", "% a comment\npattern { X -[subj]-> Y }"),
        ('pattern { X [lemma="be"] }', "pattern { X [lemma=be] }"),
    ],
)
def test_the_same_request_typed_differently_hashes_the_same(a, b):
    """The reason `unparse` exists.

    Hashing the source text meant that adding a comment or reflowing a line re-ran the
    measure over every treebank for a query that had not changed.
    """
    assert MeasureSpec(scope=a).query_hash() == MeasureSpec(scope=b).query_hash()


def test_a_genuinely_different_request_still_hashes_differently():
    assert (
        MeasureSpec(scope="pattern { X -[subj]-> Y }").query_hash()
        != MeasureSpec(scope="pattern { X -[comp]-> Y }").query_hash()
    )


def test_an_unparsable_scope_falls_back_to_the_text_rather_than_raising():
    """`query_hash` must never be the thing that reports a syntax error.

    Validation does that, with a position. A hash over the raw text of a broken query is
    harmless -- it can only cause a miss, never a wrong hit.
    """
    assert MeasureSpec(scope="pattern { X -[").query_hash()
