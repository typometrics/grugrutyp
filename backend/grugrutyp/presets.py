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

    def for_scheme(self, scheme: str) -> dict:
        scheme = scheme.upper()
        return {
            "key": self.key,
            "name": self.name,
            "group": self.group,
            "description": self.description,
            "scope": self.scope.get(scheme, ""),
            "response": self.response.get(scheme, ""),
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
            "follows its governor. The classic typometrics axis; SVO-ish languages sit "
            "high on subj, verb-final ones low."
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
            "UD": "pattern { N [upos=NOUN|PROPN|PRON]; A [upos=ADP]; N -[case]-> A }",
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

BY_KEY = {preset.key: preset for preset in PRESETS}


def for_scheme(scheme: str) -> list[dict]:
    return [preset.for_scheme(scheme) for preset in PRESETS]


def as_dicts() -> list[dict]:
    return [asdict(preset) for preset in PRESETS]
