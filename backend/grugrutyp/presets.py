"""Preset measures: the current site's plots, written as query pairs.

These are **starting points, not a menu**. The whole reason for grugrutyp is that the old
site's twelve measures were hard-coded and a linguist could not ask a thirteenth question;
a preset library that loaded into a read-only dropdown would reproduce that limitation
with extra steps. Each preset loads into the editable Scope (S) and Response (Q) editors,
and most are meant to be edited immediately -- swapping `subj` for `comp:obj`, adding a
POS restriction, negating the response.

Every preset carries **both** spellings. `1=subj` and `nsubj` are different relations in
different schemes, so a preset that only knew SUD would silently measure nothing in UD.

Provenance is in `docs/measures-mapping.md` section 2. One fact the `note` fields exist to
pass on, because it silently changes what a number means:

**Grew materialises a virtual root node `__0__`, and it falls inside any scope broad
enough to catch it.** Measured on `SUD_English-GUM` (256 739 tokens, 14 353 sentences):

    pattern { X }                                    271 092   = tokens + sentences
    pattern { X [upos=*] }                           256 739   = tokens
    pattern { GOV -> DEP }                           256 739   = every token has a governor
    pattern { GOV -> DEP }, no root governor         242 386   = word-to-word only

`statConll.py` runs with `skipFuncs=['root']`, so the current site's tables are the
*narrow* numbers. The scopes below are written to match. For a scope naming a specific
relation -- `subj`, `mod`, `comp:obj` -- it makes no difference at all, because those
edges never come from the root; it only bites on `pattern { X }` and
`pattern { GOV -> DEP }`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Preset:
    key: str
    name: str
    group: str
    description: str
    scope: dict[str, str]  # scheme -> S
    response: dict[str, str]  # scheme -> Q
    note: str = ""
    # `aggregate` presets replace the response with a numeric expression: the measure is a
    # mean over the scope's matchings, not a share of them. See `docs/measures-mapping.md`
    # section 3 -- four of the current site's twelve measures are this shape.
    kind: str = "ratio"
    expression: str = ""
    aggregation: str = "avg"
    unit: str = "%"

    def for_scheme(self, scheme: str) -> dict:
        scheme = scheme.upper()
        return {
            "key": self.key,
            "name": self.name,
            "group": self.group,
            "description": self.description,
            "scope": self.scope.get(scheme, ""),
            "response": self.response.get(scheme, ""),
            "kind": self.kind,
            "expression": self.expression,
            "aggregation": self.aggregation,
            "unit": self.unit,
            "note": self.note,
            "available": scheme in self.scope,
        }


ROOT_NOTE = (
    "The scope names a relation, so the virtual root node cannot fall inside it -- a "
    "`subj` edge never comes from `__0__`. Root handling changes nothing here."
)

BROAD_SCOPE_NOTE = (
    "The scope excludes the virtual root node `__0__` explicitly. Without that exclusion "
    "the denominator would be about 5% larger (one extra node and one extra edge per "
    "sentence), and would no longer match the current site, whose statConll.py runs with "
    "skipFuncs=['root']."
)

PRESETS: list[Preset] = [
    Preset(
        key="head-initiality",
        name="Head-initiality of a relation",
        group="Word order",
        description=(
            "Of all dependencies bearing this relation, the share where the dependent "
            "follows its governor. The classic typometrics axis; on subj, verb-initial "
            "languages sit high — SVO and verb-final ones both sit low."
        ),
        scope={"SUD": "pattern { GOV -[1=subj]-> DEP }", "UD": "pattern { GOV -[1=nsubj]-> DEP }"},
        response={"SUD": "with { GOV << DEP }", "UD": "with { GOV << DEP }"},
        note=ROOT_NOTE,
    ),
    Preset(
        key="head-initiality-any",
        name="Head-initiality of all dependencies",
        group="Word order",
        description=(
            "Over every word-to-word dependency at once, rather than one relation. A "
            "single-number summary of how head-initial a language is; useful as a "
            "baseline to read the per-relation values against."
        ),
        scope={
            "SUD": 'pattern { GOV -> DEP }\nwithout { GOV [form="__0__"] }',
            "UD": 'pattern { GOV -> DEP }\nwithout { GOV [form="__0__"] }',
        },
        response={"SUD": "with { GOV << DEP }", "UD": "with { GOV << DEP }"},
        note=BROAD_SCOPE_NOTE,
    ),
    Preset(
        key="head-initiality-cfc",
        name="Head-initiality by POS-relation-POS",
        group="Word order",
        description=(
            "Head-initiality restricted to one governor POS and one dependent POS -- the "
            "`posdircfc` / `direction-cfc` family. Noun-adjective order is the standard "
            "example; edit the two `upos` values for any other pairing."
        ),
        scope={
            "SUD": "pattern { GOV [upos=NOUN]; GOV -[1=mod]-> DEP [upos=ADJ] }",
            "UD": "pattern { GOV [upos=NOUN]; GOV -[1=amod]-> DEP [upos=ADJ] }",
        },
        response={"SUD": "with { GOV << DEP }", "UD": "with { GOV << DEP }"},
    ),
    Preset(
        key="distribution",
        name="Relative frequency of a relation",
        group="Distribution",
        description=(
            "The share of all word-to-word dependencies that bear this relation -- the "
            "`f.tsv` / `distribution` family. The scope is every dependency, so the "
            "values of all relations sum to 100%."
        ),
        scope={
            "SUD": 'pattern { GOV -> DEP }\nwithout { GOV [form="__0__"] }',
            "UD": 'pattern { GOV -> DEP }\nwithout { GOV [form="__0__"] }',
        },
        response={"SUD": "with { GOV -[1=subj]-> DEP }", "UD": "with { GOV -[1=nsubj]-> DEP }"},
        note=BROAD_SCOPE_NOTE,
    ),
    Preset(
        key="freq-cfc",
        name="Frequency of a POS-relation-POS configuration",
        group="Distribution",
        description=(
            "The share of all word-to-word dependencies that are this exact "
            "governor-POS / relation / dependent-POS triple -- the `cfc` family."
        ),
        scope={
            "SUD": 'pattern { GOV -> DEP }\nwithout { GOV [form="__0__"] }',
            "UD": 'pattern { GOV -> DEP }\nwithout { GOV [form="__0__"] }',
        },
        response={
            "SUD": "with { GOV [upos=NOUN]; GOV -[1=mod]-> DEP [upos=ADJ] }",
            "UD": "with { GOV [upos=NOUN]; GOV -[1=amod]-> DEP [upos=ADJ] }",
        },
    ),
    Preset(
        key="pos-share",
        name="Share of a part of speech",
        group="Distribution",
        description=(
            "The share of words carrying this UPOS -- `cat.tsv`. Adposition share against "
            "case-marking is a quick isolating-vs-agglutinating axis."
        ),
        scope={"SUD": "pattern { X [upos=*] }", "UD": "pattern { X [upos=*] }"},
        response={"SUD": "with { X [upos=ADP] }", "UD": "with { X [upos=ADP] }"},
        note=(
            "`[upos=*]` is what makes the denominator the token count. A bare "
            "`pattern { X }` also matches Grew's virtual root node, which has no UPOS, "
            "and would inflate the denominator by one per sentence -- about 5%. Measured "
            "on SUD_English-GUM: 271,092 against 256,739."
        ),
    ),
    Preset(
        key="subj-obj-order",
        name="Subject before object",
        group="Word order",
        description=(
            "Among clauses with both a subject and an object, how often the subject comes "
            "first. Not one of the old site's measures -- it needs two dependents of the "
            "same governor, which the precomputed tables could not express."
        ),
        scope={
            "SUD": "pattern { V -[1=subj]-> S; V -[1=comp,2=obj]-> O }",
            "UD": "pattern { V -[1=nsubj]-> S; V -[1=obj]-> O }",
        },
        response={"SUD": "with { S << O }", "UD": "with { S << O }"},
        note=(
            "The two schemes cover different clause sets: SUD attaches the subject to "
            "the finite auxiliary, so periphrastic clauses (subject on the aux, object "
            "on the lexical verb) fall out of the SUD scope while staying in the UD one. "
            "A value jump on the scheme toggle is (partly) this denominator change, not "
            "the language."
        ),
    ),
    Preset(
        key="adposition-prepositional",
        name="Prepositions vs postpositions",
        group="Word order",
        description=(
            "Of all adpositions, the share that precede the noun they attach to. One of "
            "the strongest correlates of basic word order in the typological literature."
        ),
        scope={
            "SUD": "pattern { N [upos=NOUN|PROPN|PRON]; A [upos=ADP]; A -> N }",
            "UD": "pattern { N [upos=NOUN|PROPN|PRON]; A [upos=ADP]; N -[1=case]-> A }",
        },
        response={"SUD": "with { A << N }", "UD": "with { A << N }"},
        note=(
            "The two schemes disagree about the direction of this edge, not just its "
            "label: SUD makes the adposition the governor, UD makes it a `case` dependent "
            "of the noun. The scopes are written accordingly and are not interchangeable."
        ),
    ),
    Preset(
        key="projectivity",
        name="Projective dependencies",
        group="Structure",
        description=(
            "The share of dependencies that sit in a projective sentence. A crude "
            "word-order-freedom proxy, and a treebank-quality signal: an outlier here is "
            "often an annotation convention rather than a language."
        ),
        scope={"SUD": "pattern { GOV -> DEP }", "UD": "pattern { GOV -> DEP }"},
        response={"SUD": "global { is_projective }", "UD": "global { is_projective }"},
    ),
]

# --------------------------------------------------------------- the aggregate measures

DISTANCE_NOTE = (
    "Signed, dependent minus governor, which is what statConll.py computes as `ni - gi`. "
    "A positive mean means the dependent tends to follow its governor; head-final "
    "languages come out negative. Take the absolute value instead if you want distance "
    "without direction."
)

PRESETS += [
    Preset(
        key="mean-distance",
        name="Mean dependency distance",
        group="Distance",
        description=(
            "The average signed distance between governor and dependent for a relation -- "
            "the `f-dist` family. Not a percentage: this axis is measured in words."
        ),
        scope={"SUD": "pattern { GOV -[1=subj]-> DEP }", "UD": "pattern { GOV -[1=nsubj]-> DEP }"},
        response={"SUD": "", "UD": ""},
        kind="aggregate",
        expression="delta(GOV, DEP)",
        unit="words",
        note=DISTANCE_NOTE,
    ),
    Preset(
        key="mean-distance-abs",
        name="Mean dependency length",
        group="Distance",
        description=(
            "The average distance ignoring direction -- `f-dist-abs`. A proxy for how far "
            "a language lets its dependencies stretch, and the quantity the "
            "dependency-length-minimisation literature is about."
        ),
        scope={
            "SUD": 'pattern { GOV -> DEP }\nwithout { GOV [form="__0__"] }',
            "UD": 'pattern { GOV -> DEP }\nwithout { GOV [form="__0__"] }',
        },
        response={"SUD": "", "UD": ""},
        kind="aggregate",
        expression="abs(delta(GOV, DEP))",
        unit="words",
        note=BROAD_SCOPE_NOTE,
    ),
    Preset(
        key="tree-height",
        name="Mean tree height",
        group="Structure",
        description=(
            "The average depth of a sentence's dependency tree -- `height.tsv`. The scope "
            "is sentences rather than dependencies, and the value is read off a property "
            "precomputed at import."
        ),
        scope={"SUD": 'pattern { X [form="__0__"] }', "UD": 'pattern { X [form="__0__"] }'},
        response={"SUD": "", "UD": ""},
        kind="aggregate",
        expression="sentence.height",
        unit="nodes",
        note=(
            "The scope is the virtual root, one matching per sentence, so this is the "
            "plain mean over sentences -- the same averaging as `statConll.py`. (Before "
            "2026-09-02 the scope was any node, which weighted each sentence by its "
            "length; the audit caught it.)"
        ),
    ),
    Preset(
        key="sentence-length",
        name="Mean sentence length",
        group="Structure",
        description="Average tokens per sentence -- one matching per sentence, a plain mean.",
        scope={"SUD": 'pattern { X [form="__0__"] }', "UD": 'pattern { X [form="__0__"] }'},
        response={"SUD": "", "UD": ""},
        kind="aggregate",
        expression="sentence.length",
        unit="tokens",
    ),
    Preset(
        key="menzerath-constituent-size",
        name="Mean constituent size (Menzerath)",
        group="Menzerath",
        description=(
            "Average size in words of a verb's direct constituents (each dependent's "
            "subtree). The Menzerath-Altmann law predicts this shrinks as verbs take "
            "more dependents -- Faghiri, Gerdes & Kahane (UDW26). Narrow the scope "
            "freely: a POS on DEP, a relation on the edge."
        ),
        scope={
            "SUD": "pattern { V [upos=VERB]; V -> DEP }",
            "UD": "pattern { V [upos=VERB]; V -> DEP }",
        },
        response={"SUD": "", "UD": ""},
        kind="aggregate",
        expression="DEP.subtree_size",
        aggregation="avg",
        unit="words",
        note=(
            "subtree_size / n_children / n_left / n_right are written onto every word at "
            "import (docs/menzerath.md). In the search tab, cluster the same scope by "
            "V.n_children for the per-complexity table."
        ),
    ),
    Preset(
        key="menzerath-dependents-per-verb",
        name="Mean dependents per verb",
        group="Menzerath",
        description=(
            "The construct-size half of the Menzerath pair: how many direct dependents "
            "a verb takes on average."
        ),
        scope={"SUD": "pattern { V [upos=VERB] }", "UD": "pattern { V [upos=VERB] }"},
        response={"SUD": "", "UD": ""},
        kind="aggregate",
        expression="V.n_children",
        aggregation="avg",
        unit="deps",
    ),
]

BY_KEY = {preset.key: preset for preset in PRESETS}


def for_scheme(scheme: str) -> list[dict]:
    return [preset.for_scheme(scheme) for preset in PRESETS]


def as_dicts() -> list[dict]:
    return [asdict(preset) for preset in PRESETS]

# ------------------------------------------------------------- the flexibility measures
#
# `docs/measures-mapping.md` section C: word-order flexibility, the C-class measure of
# the old site, recovered from its 2.12 tables on 2026-09-04. Not a share and not a mean
# over an expression -- a weighted mean, per governor-POS/dependent-POS pair, of how far
# that pair's order sits from categorical. Verified against the legacy table: Spearman
# 0.949 over the 102 languages both cover, mean gap 4.7 points.

FLEXIBILITY_NOTE = (
    "Measured per governor-POS/dependent-POS pair and averaged by frequency, not over "
    "the relation as a whole. That distinction is the point: a relation can sit at 50% "
    "overall because each construction genuinely varies (flexible) or because two rigid "
    "constructions pull opposite ways (rigid, but heterogeneous), and only the "
    "per-pair computation tells them apart. 0 = every pair is categorical, "
    "100 = every pair is an even split."
)

PRESETS += [
    Preset(
        key="flexibility-subj",
        name="Word-order flexibility (subject)",
        group="Flexibility",
        description=(
            "How freely subjects sit before or after their governor — the old site's "
            "`flexibility_rel` measure. Verb-final and verb-initial languages both score "
            "low; a language that really allows both orders scores high."
        ),
        scope={
            "SUD": "pattern { GOV -[1=subj]-> DEP }",
            "UD": "pattern { GOV -[1=nsubj]-> DEP }",
        },
        response={"SUD": "", "UD": ""},
        kind="flexibility",
        note=FLEXIBILITY_NOTE,
    ),
    Preset(
        key="flexibility-any",
        name="Word-order flexibility (all dependencies)",
        group="Flexibility",
        description=(
            "The same measure over every word-to-word dependency at once: a single "
            "number for how rigidly a language orders its constituents."
        ),
        scope={
            "SUD": 'pattern { GOV -> DEP }\nwithout { GOV [form="__0__"] }',
            "UD": 'pattern { GOV -> DEP }\nwithout { GOV [form="__0__"] }',
        },
        response={"SUD": "", "UD": ""},
        kind="flexibility",
        note=FLEXIBILITY_NOTE + " " + BROAD_SCOPE_NOTE,
    ),
]

# ------------------------------------------------------- the reference-table measures
#
# `docs/measures-mapping.md` section D: the two measures that are not query pairs at
# all. Both are per-language numbers read from a table (`backend/grugrutyp/reference.py`)
# -- an external typology in one case, our own batch fit in the other -- and both exist
# to be plotted *against* a measure the engine computes.

PRESETS += [
    Preset(
        key="menzerath-b",
        name="Menzerath exponent b (fitted)",
        group="Menzerath",
        description=(
            "The exponent of the Menzerath–Altmann law fitted per language, "
            "y = a·x^b·e^(−c·x) over the verbal domain. Negative means constituents "
            "shrink as the verb takes more dependents — the law's prediction, which "
            "holds for 77% of the languages fitted well enough to judge."
        ),
        scope={"SUD": "", "UD": ""},
        response={"SUD": "", "UD": ""},
        kind="table",
        expression="menzerath_abc.b",
        unit="",
        note=(
            "A batch result, not a query: `scripts/menzerath_fit.py` writes "
            "`data/meta/menzerath_abc.tsv`. Plot it against a measure to ask what kind "
            "of language obeys the law most strongly; `menzerath_abc.r2` says which "
            "rows to trust (median 0.755). Not the old site's a/b/c — theirs use a "
            "different parameterisation, see docs/menzerath.md."
        ),
    ),
    Preset(
        key="bakker-flexibility",
        name="Bakker's flexibility (external)",
        group="Flexibility",
        description=(
            "Word-order flexibility as scored in Bakker's typology, for the 24 "
            "languages it covers. External data — plot it against our own flexibility "
            "measure to see where the two traditions agree."
        ),
        scope={"SUD": "", "UD": ""},
        response={"SUD": "", "UD": ""},
        kind="table",
        expression="bakker.bakker_flexibility",
        unit="",
        note=(
            "24 languages only; everything else has no point on this axis. "
            "`bakker.bakker_like_flexibility` extends the same scale to a few more, and "
            "`bakker.typometric_flexibility_2_12` is the old site's own measure as of "
            "2.12, kept for comparison."
        ),
    ),
]

PRESETS += [
    Preset(
        key="vo-score",
        name="VO score (object after the verb)",
        group="Word order",
        description=(
            "Of all direct objects with a nominal head, the share following the verb — "
            "the token-based VO/OV score of Faghiri, Gerdes & Kahane (UDW26). Their "
            "thresholds: above 67% the language counts as VO, below 33% as OV, between "
            "them as having no dominant order."
        ),
        scope={
            "SUD": "pattern { V -[1=comp,2=obj]-> O [upos=NOUN|PROPN] }",
            "UD": "pattern { V -[1=obj]-> O [upos=NOUN|PROPN] }",
        },
        response={"SUD": "with { V << O }", "UD": "with { V << O }"},
        note=(
            "Verified against the published table of that paper: English 0.97 here vs "
            "0.99 there, Japanese 0.00 vs 0.00, Wolof 0.99 vs 0.97 — the residue is the "
            "corpus version and the treebank selection, not the definition. The paper "
            "uses this score as the control when asking whether MAL behaves differently "
            "on either side of the verb; docs/menzerath.md §UDW26."
        ),
    ),
]
