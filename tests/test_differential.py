"""The differential harness: our Cypher must count exactly what Grew counts.

This is the single most important test in the project. Everything downstream is arithmetic
on these counts, and a wrong count does not look wrong -- it looks like a typological
finding. See docs/grew-to-cypher.md section 9.

Requires the opam environment so that `grewpy_backend` is on PATH:

    OPAMROOT=/opt/opam PATH=/opt/opam/grew/bin:$PATH .venv/bin/pytest tests/test_differential.py
"""

from __future__ import annotations

import os

import pytest

from grugrutyp.translate.cypher import translate
from grugrutyp.translate.parser import parse

# grewpy holds ONE config per process, so the two schemes are two invocations
# (audit 2026-09-02, syntax §13 -- the UD half of the tool was never oracle-tested):
#   default            -> SUD leg
#   GRUGRUTYP_DIFF_SCHEME=ud -> UD leg, same treebank trio in their UD twins
SCHEME = os.environ.get("GRUGRUTYP_DIFF_SCHEME", "sud").lower()

# Typologically spread:
#   English  -- SVO, Germanic, large
#   Japanese -- SOV, head-final, no spaces
#   Wolof    -- SVO, Niger-Congo, small, rich MWT
TREEBANKS = {
    "sud": ["SUD_English-GUM", "SUD_Japanese-GSD", "SUD_Wolof-WTB"],
    "ud": ["UD_English-GUM", "UD_Japanese-GSD", "UD_Wolof-WTB"],
}[SCHEME]

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
    # The mirror spellings (Kim hit `A >> N` failing to parse, 2026-08-29). Normalised to
    # `<<`/`<` at parse time, so the oracle comparison is the whole verification.
    ("order-follows", "pattern { X -[subj]-> Y; Y >> X }", None),
    ("order-immediately-follows", "pattern { X -[subj]-> Y; Y > X }", None),
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
    # -- constructs the audit found uncovered (2026-09-02, syntax §13), both schemes
    ("edge-label-cmp", "pattern { e1: X -> Y; e2: Y -> Z; e1.label = e2.label }", None),
    ("node-regex-pcre", 'pattern { X [lemma = /a.*/i] }', None),
    ("global-is-tree", "pattern { X -[1=subj]-> Y } global { is_tree }", None),
    # Binds the virtual root: whether Grew orders __0__ identically is exactly the
    # kind of assumption this suite exists to check. Bare nodes are our sugar
    # (grewlib rejects them), so the oracle runs the bracketed form.
    ("order-broad-root", "pattern { X; Y; X < Y }", "pattern { X []; Y []; X < Y }"),
]

# The UD matrix: the scheme-neutral constructs above, with the relation vocabulary
# swapped, PLUS the UD-specific semantics the docs assert but nothing verified --
# `1=` subsumption over subtypes, plain-label exactness, subtype decomposition.
_UD_SWAPS = [
    ("-[subj]->", "-[nsubj]->"),
    ("-[subj|comp:obj]->", "-[nsubj|obj]->"),
    ("-[^subj]->", "-[^nsubj]->"),
    ("-[1=comp, 2=obj]->", "-[1=obj]->"),
    ("-[1=comp, !deep]->", "-[1=nsubj, !2]->"),
    ("-[1=comp]->", "-[1=nsubj]->"),
    ("-[1=subj]->", "-[1=nsubj]->"),
    ("-[1=mod]->", "-[1=amod]->"),
]


def _to_ud(text: str) -> str:
    for sud, ud in _UD_SWAPS:
        text = text.replace(sud, ud)
    return text


REQUESTS_RAW_UD = [
    (label, _to_ud(ours), _to_ud(grew) if grew else None) for label, ours, grew in REQUESTS_RAW
] + [
    ("ud-plain-label-exact", "pattern { X -[nsubj]-> Y }", None),
    ("ud-1eq-subsumes-subtypes", "pattern { X -[1=nsubj]-> Y }", None),
    ("ud-subtype-exact", "pattern { X -[nsubj:pass]-> Y }", None),
    ("ud-subtype-as-features", "pattern { X -[1=nsubj, 2=pass]-> Y }", None),
    ("ud-acl-relcl", "pattern { X -[1=acl, 2=relcl]-> Y }", None),
    ("ud-aux-subsumes", "pattern { X -[1=aux]-> Y }", None),
    ("ud-obl-subsumes", "pattern { X -[1=obl]-> Y }", None),
    ("ud-case-subsumes", "pattern { N -[1=case]-> A }", None),
]

# (label, our_request, grew_request) with the grew_request defaulted.
_RAW = {"sud": REQUESTS_RAW, "ud": REQUESTS_RAW_UD}[SCHEME]
REQUESTS = [(label, ours, grew or ours) for label, ours, grew in _RAW]


def _neo4j_count(driver, treebank: str, request_text: str) -> int:
    """With the runner's transient-retry: the first cold pass over the UD treebanks
    turned 20 minutes of spinning-disk timeouts into fake mismatch reports
    (2026-09-02 -- most of the UD leg's initial 43 'failures' were this)."""
    from grugrutyp.runner import _is_transient

    translation = translate(parse(request_text), treebank)
    for attempt in range(3):
        try:
            with driver.session() as session:
                return session.run(translation.cypher, **translation.params).single()["n"]
        except Exception as exc:  # noqa: BLE001
            if attempt == 2 or not _is_transient(exc):
                raise
            import time as _time

            _time.sleep(5 * (attempt + 1))


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
