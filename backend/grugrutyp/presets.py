"""Preset measures: the current site's plots, written as query pairs.

These are **starting points, not a menu**. The whole reason for grugrutyp is that the old
site's twelve measures were hard-coded and a linguist could not ask a thirteenth question;
a preset library that loaded into a read-only dropdown would reproduce that limitation
with extra steps. Each preset loads into the editable Scope (S) and Response (Q) editors,
and most are meant to be edited immediately -- swapping `subj` for `comp:obj`, adding a
POS restriction, negating the response.

Every preset carries **both** spellings. `1=subj` and `nsubj` are different relations in
different schemes, so a preset that only knew SUD would silently measure nothing in UD.

Provenance is in `docs/measures-mapping.md` section 2. Two facts from there that the
`note` fields exist to pass on, because both change what a number means:

* Root dependencies are inside the default scope -- Grew materialises a virtual root node,
  and a root's dependent always follows it, so roots inflate head-initiality. The old site
  counted them too, so leaving them in is what makes the numbers comparable. `no_root`
  variants are provided for when comparability is not what you want.
* `pattern { X }` counts tokens **plus** sentences, for the same reason.
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
    "Root attachments are in the scope: Grew has a virtual root node at position 0, so a "
    "root's dependent always follows its governor and pushes head-initiality up. The "
    "current site counts them the same way -- excluding them changes the number, not a bug."
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
        key="head-initiality-noroot",
        name="Head-initiality, excluding roots",
        group="Word order",
        description=(
            "As above, but only word-to-word dependencies. Differs from the current "
            "site's number by exactly the root share -- use it when you want the "
            "phenomenon rather than comparability with the old plots."
        ),
        scope={
            "SUD": "pattern { GOV -[1=subj]-> DEP }\nwithout { GOV [form=\"__0__\"] }",
            "UD": "pattern { GOV -[1=nsubj]-> DEP }\nwithout { GOV [form=\"__0__\"] }",
        },
        response={"SUD": "with { GOV << DEP }", "UD": "with { GOV << DEP }"},
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
            "The share of all dependencies that bear this relation -- the `f.tsv` / "
            "`distribution` family. The scope is every dependency, so the values of all "
            "relations sum to 100%."
        ),
        scope={"SUD": "pattern { GOV -> DEP }", "UD": "pattern { GOV -> DEP }"},
        response={"SUD": "with { GOV -[1=subj]-> DEP }", "UD": "with { GOV -[1=nsubj]-> DEP }"},
        note=ROOT_NOTE,
    ),
    Preset(
        key="freq-cfc",
        name="Frequency of a POS-relation-POS configuration",
        group="Distribution",
        description=(
            "The share of all dependencies that are this exact governor-POS / relation / "
            "dependent-POS triple -- the `cfc` family."
        ),
        scope={"SUD": "pattern { GOV -> DEP }", "UD": "pattern { GOV -> DEP }"},
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
        scope={"SUD": "pattern { X }", "UD": "pattern { X }"},
        response={"SUD": "with { X [upos=ADP] }", "UD": "with { X [upos=ADP] }"},
        note=(
            "The scope counts tokens plus sentences: Grew's virtual root node is a node, "
            "so every sentence contributes one. The denominator is therefore about 4-5% "
            "larger than the token count."
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
