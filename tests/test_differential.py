"""The differential harness: our Cypher must count exactly what Grew counts.

This is the single most important test in the project. Everything downstream is arithmetic
on these counts, and a wrong count does not look wrong -- it looks like a typological
finding. See docs/grew-to-cypher.md section 9.

Requires the opam environment so that `grewpy_backend` is on PATH:

    OPAMROOT=/opt/opam PATH=/opt/opam/grew/bin:$PATH .venv/bin/pytest tests/test_differential.py
"""

from __future__ import annotations

import pytest

from grugrutyp.translate.cypher import translate
from grugrutyp.translate.parser import parse

# Typologically spread, and all SUD so one grewpy config covers them:
#   English  -- SVO, Germanic, large
#   Japanese -- SOV, head-final, no spaces
#   Wolof    -- SVO, Niger-Congo, small, rich MWT
TREEBANKS = ["SUD_English-GUM", "SUD_Japanese-GSD", "SUD_Wolof-WTB"]

# One entry per construct in docs/grew-to-cypher.md sections 1-5.
#
# Entries are (label, our_request, grew_request). The third field is None when Grew
# accepts the same text. It differs where our grammar is a deliberate *superset* of Grew:
# we allow an inline feature structure on an edge endpoint (`X -[r]-> Y [upos=NOUN]`) and
# `*` for an unbound endpoint, both of which grewlib rejects. Those are pure sugar, so the
# oracle runs the desugared form and the counts must still agree exactly.
REQUESTS_RAW = [
    # -- node clauses.  `pattern { X }` alone is rejected by grewlib, so the bare-node
    #    case is covered by test_translate.py instead of here.
    ("node-upos", "pattern { X [upos=VERB] }", None),
    ("node-disjunction", "pattern { X [upos=VERB|NOUN|ADJ] }", None),
    ("node-neq", "pattern { X [upos <> VERB] }", None),
    ("node-present", "pattern { X [Number] }", None),
    ("node-absent", "pattern { X [!Number] }", None),
    ("node-two-feats", "pattern { X [upos=NOUN, Number=Sing] }", None),
    ("node-fs-alternatives", "pattern { X [upos=VERB, VerbForm=Part]|[upos=ADJ] }", None),
    ("node-regex-posix", 'pattern { X [lemma = re"^a.*"] }', None),
    ("node-quoted", 'pattern { X [upos="PRON"] }', None),
    # -- edge clauses
    ("edge-plain", "pattern { X -> Y }", None),
    ("edge-label", "pattern { X -[subj]-> Y }", None),
    ("edge-label-disjunction", "pattern { X -[subj|comp:obj]-> Y }", None),
    ("edge-label-negated", "pattern { X -[^subj]-> Y }", None),
    ("edge-feature-1", "pattern { X -[1=comp]-> Y }", None),
    ("edge-feature-12", "pattern { X -[1=comp, 2=obj]-> Y }", None),
    ("edge-feature-absent-deep", "pattern { X -[1=comp, !deep]-> Y }", None),
    ("edge-named", "pattern { e: X -[subj]-> Y }", None),
    (
        "edge-dominance",
        "pattern { X [upos=VERB]; X ->> Y [upos=ADP] }",
        "pattern { X [upos=VERB]; Y [upos=ADP]; X ->> Y }",
    ),
    ("edge-anon-source", "pattern { * -[subj]-> Y }", "pattern { Z -[subj]-> Y }"),
    ("edge-anon-target", "pattern { Y -[subj]-> * }", "pattern { Y -[subj]-> Z }"),
    (
        "edge-inline-fs",
        "pattern { X [upos=VERB] -[subj]-> Y [upos=NOUN] }",
        "pattern { X [upos=VERB]; Y [upos=NOUN]; X -[subj]-> Y }",
    ),
    # -- order and distance
    ("order-precedes", "pattern { X -[subj]-> Y; X << Y }", None),
    ("order-immediate", "pattern { X -[subj]-> Y; X < Y }", None),
    ("delta-eq", "pattern { X -[subj]-> Y; delta(X,Y) = 1 }", None),
    ("delta-negative", "pattern { X -[subj]-> Y; delta(X,Y) = -1 }", None),
    ("delta-gt", "pattern { X -[subj]-> Y; delta(X,Y) > 2 }", None),
    ("length-le", "pattern { X -[subj]-> Y; length(X,Y) <= 3 }", None),
    # -- comparisons
    ("cmp-feat-eq", "pattern { X -> Y; X.upos = Y.upos }", None),
    ("cmp-feat-neq", "pattern { X -> Y; X.upos <> Y.upos }", None),
    ("cmp-value", 'pattern { X -> Y; X.upos = "VERB" }', None),
    ("cmp-present", "pattern { X -> Y; X.Number = * }", None),
    ("cmp-absent", "pattern { X -> Y; !X.Number }", None),
    # -- with / without
    ("with-filter", "pattern { X -[subj]-> Y } with { X << Y }", None),
    (
        "with-new-node",
        "pattern { X -[subj]-> Y } with { X -> Z [upos=ADV] }",
        "pattern { X -[subj]-> Y } with { Z [upos=ADV]; X -> Z }",
    ),
    ("without-filter", "pattern { X -[subj]-> Y } without { X << Y }", None),
    (
        "without-new-node",
        "pattern { X -[subj]-> Y } without { X -> Z [upos=ADV] }",
        "pattern { X -[subj]-> Y } without { Z [upos=ADV]; X -> Z }",
    ),
    (
        "with-and-without",
        "pattern { X -[subj]-> Y } with { X << Y } without { Y [upos=PRON] }",
        None,
    ),
    # -- injectivity
    ("injective-two-deps", "pattern { X -> Y; X -> Z }", None),
    ("non-injective", "pattern { X -> Y; X -> Z$ }", None),
    # -- global
    ("global-projective", "pattern { X -[subj]-> Y } global { is_projective }", None),
    ("global-not-projective", "pattern { X -[subj]-> Y } global { is_not_projective }", None),
    # -- realistic measures (docs/measures-mapping.md section 2)
    ("measure-head-initiality", "pattern { GOV -[1=subj]-> DEP } with { GOV << DEP }", None),
    (
        "measure-adj-noun",
        "pattern { N [upos=NOUN]; N -[1=mod]-> A [upos=ADJ] } with { A << N }",
        "pattern { N [upos=NOUN]; A [upos=ADJ]; N -[1=mod]-> A } with { A << N }",
    ),
    ("measure-obj-pronoun", "pattern { G -[1=comp, 2=obj]-> D } with { D [upos=PRON] }", None),
]


# (label, our_request, grew_request) with the grew_request defaulted.
REQUESTS = [(label, ours, grew or ours) for label, ours, grew in REQUESTS_RAW]


def _neo4j_count(driver, treebank: str, request_text: str) -> int:
    translation = translate(parse(request_text), treebank)
    with driver.session() as session:
        return session.run(translation.cypher, **translation.params).single()["n"]


@pytest.mark.parametrize("treebank", TREEBANKS)
@pytest.mark.parametrize(
    "label,our_request,grew_request", REQUESTS, ids=[r[0] for r in REQUESTS]
)
def test_counts_match_grew(
    label, our_request, grew_request, treebank, neo4j_driver, grew_corpora, imported_treebanks
):
    if treebank not in imported_treebanks:
        pytest.skip(f"{treebank} not imported yet")

    from grewpy import Request

    expected = grew_corpora(treebank).count(Request(grew_request))
    actual = _neo4j_count(neo4j_driver, treebank, our_request)

    sugar = "" if grew_request == our_request else f"\n  grew req  : {grew_request}"
    assert actual == expected, (
        f"\n  construct : {label}"
        f"\n  treebank  : {treebank}"
        f"\n  request   : {our_request}{sugar}"
        f"\n  grew      : {expected}"
        f"\n  neo4j     : {actual}"
        f"\n  cypher    :\n{translate(parse(our_request), treebank).cypher}"
    )
