"""CoNLL-U reading, plus the per-sentence properties we precompute at import time.

Deliberately dependency-free and streaming: the full 2.18 release is ~6 GB unpacked and
we never want it all in memory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# CoNLL-U columns
ID, FORM, LEMMA, UPOS, XPOS, FEATS, HEAD, DEPREL, DEPS, MISC = range(10)

_MWT_ID = re.compile(r"^(\d+)-(\d+)$")
_EMPTY_ID = re.compile(r"^\d+\.\d+$")

# Property names we must not clash with when flattening FEATS/MISC onto the Word node.
RESERVED_WORD_PROPS = frozenset(
    {"treebank", "sent_id", "idx", "form", "lemma", "upos", "xpos", "head", "deprel"}
)


@dataclass
class Word:
    idx: int  # 1-based position among syntactic words
    form: str
    lemma: str | None
    upos: str | None
    xpos: str | None
    feats: dict[str, str]
    misc: dict[str, str]
    head: int  # 0 == root
    deprel: str


@dataclass
class Mwt:
    start: int
    end: int
    form: str


@dataclass
class Sentence:
    sent_id: str
    text: str
    conllu: str
    words: list[Word]
    mwts: list[Mwt] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)

    @property
    def n_tokens(self) -> int:
        return len(self.words)


def _parse_kv(field_value: str) -> dict[str, str]:
    """FEATS / MISC: `Case=Dat|Gender=Masc` -> {'Case': 'Dat', 'Gender': 'Masc'}."""
    if not field_value or field_value == "_":
        return {}
    out: dict[str, str] = {}
    for item in field_value.split("|"):
        key, sep, value = item.partition("=")
        if sep and key:
            out[key.strip()] = value.strip()
    return out


def decompose_deprel(deprel: str) -> dict[str, str]:
    """Split a dependency label into Grew's edge-label feature structure.

    Grew stores an edge label as a flat feature structure, and queries in **both**
    schemes depend on it: `comp:obl@agent` is `1=comp, 2=obl, deep=agent`, so
    `-[1=comp]->` subsumes every `comp:*` in SUD -- and equally `aux:pass` is
    `1=aux, 2=pass`, so `-[1=aux]->` subsumes every `aux:*` in UD. The same applies to
    every UD subrelation (`nsubj:pass`, `obl:arg`, `acl:relcl`, `flat:name`, ...).

    A single opaque `deprel` string cannot answer that without a prefix hack that breaks
    on `comp` vs `compound`. See docs/grew-query-language.md section 1.

    Only the third feature, `@deep`, is SUD-specific.
    """
    if not deprel or deprel == "_":
        return {}
    main, _, deep = deprel.partition("@")
    rel_1, _, rel_2 = main.partition(":")
    props = {"deprel": deprel, "rel_1": rel_1}
    if rel_2:
        props["rel_2"] = rel_2
    if deep:
        props["rel_deep"] = deep
    return props


def read_conllu(path: Path) -> Iterator[Sentence]:
    """Yield one Sentence per blank-line-separated block.

    Empty nodes (`1.1`, enhanced-dependency material) are skipped: v1 does not import
    DEPS, and keeping them would break the `idx` contiguity that `<` relies on.
    """
    with path.open(encoding="utf-8") as handle:
        block: list[str] = []
        for line in handle:
            line = line.rstrip("\n")
            if line.strip():
                block.append(line)
            elif block:
                sentence = _block_to_sentence(block, path)
                if sentence is not None:
                    yield sentence
                block = []
        if block:
            sentence = _block_to_sentence(block, path)
            if sentence is not None:
                yield sentence


def _block_to_sentence(block: list[str], path: Path) -> Sentence | None:
    meta: dict[str, str] = {}
    words: list[Word] = []
    mwts: list[Mwt] = []

    for line in block:
        if line.startswith("#"):
            key, sep, value = line[1:].partition("=")
            if sep:
                meta[key.strip()] = value.strip()
            continue

        cols = line.split("\t")
        if len(cols) != 10:
            continue

        token_id = cols[ID]
        mwt_match = _MWT_ID.match(token_id)
        if mwt_match:
            mwts.append(Mwt(int(mwt_match.group(1)), int(mwt_match.group(2)), cols[FORM]))
            continue
        if _EMPTY_ID.match(token_id):
            continue
        if not token_id.isdigit():
            continue

        try:
            head = int(cols[HEAD]) if cols[HEAD] not in ("_", "") else 0
        except ValueError:
            head = 0

        words.append(
            Word(
                idx=int(token_id),
                form=cols[FORM],
                lemma=None if cols[LEMMA] == "_" else cols[LEMMA],
                upos=None if cols[UPOS] == "_" else cols[UPOS],
                xpos=None if cols[XPOS] == "_" else cols[XPOS],
                feats=_parse_kv(cols[FEATS]),
                misc=_parse_kv(cols[MISC]),
                head=head,
                deprel=cols[DEPREL],
            )
        )

    if not words:
        return None

    return Sentence(
        sent_id=meta.get("sent_id") or f"{path.stem}-{words[0].form[:16]}-{len(words)}",
        text=meta.get("text", ""),
        conllu="\n".join(block),
        words=words,
        mwts=mwts,
        meta=meta,
    )


# --------------------------------------------------------------------------------------
# Per-sentence properties precomputed at import.
#
# These are either impossible (is_projective) or expensive (height) to express in Cypher,
# and cheap to compute once. See docs/data-intake.md section 4.
# --------------------------------------------------------------------------------------


def _children(sentence: Sentence) -> dict[int, list[int]]:
    children: dict[int, list[int]] = {}
    for word in sentence.words:
        children.setdefault(word.head, []).append(word.idx)
    return children


def tree_height(sentence: Sentence) -> int:
    """Depth of the deepest node, roots counted as depth 1. 0 if the graph is not rooted.

    Iterative BFS: some treebanks contain sentences of several thousand tokens, and
    recursion would blow the stack.
    """
    children = _children(sentence)
    frontier = children.get(0, [])
    if not frontier:
        return 0
    seen = set(frontier)
    depth = 0
    while frontier:
        depth += 1
        nxt = []
        for node in frontier:
            for child in children.get(node, ()):
                if child not in seen:  # guard against cycles in malformed data
                    seen.add(child)
                    nxt.append(child)
        frontier = nxt
    return depth


def is_tree(sentence: Sentence) -> bool:
    """Exactly one root, and every word reachable from it."""
    roots = [w.idx for w in sentence.words if w.head == 0]
    if len(roots) != 1:
        return False
    children = _children(sentence)
    seen = {roots[0]}
    stack = [roots[0]]
    while stack:
        for child in children.get(stack.pop(), ()):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return len(seen) == len(sentence.words)


def is_projective(sentence: Sentence) -> bool:
    """No dependency arc crosses another.

    An arc (head, dep) is non-projective if some word strictly between them is not a
    descendant of head. Computed with explicit descendant sets: sentences are short, so
    the quadratic worst case does not matter, and it is easy to check by eye.
    """
    children = _children(sentence)
    descendants: dict[int, set[int]] = {}

    def descendants_of(node: int) -> set[int]:
        # Iterative post-order; the recursion-free form matters for pathological trees.
        stack = [(node, False)]
        while stack:
            current, expanded = stack.pop()
            if current in descendants:
                continue
            if not expanded:
                stack.append((current, True))
                for child in children.get(current, ()):
                    if child not in descendants:
                        stack.append((child, False))
            else:
                acc: set[int] = set()
                for child in children.get(current, ()):
                    acc.add(child)
                    acc |= descendants.get(child, set())
                descendants[current] = acc
        return descendants[node]

    for word in sentence.words:
        if word.head == 0:
            continue
        low, high = sorted((word.head, word.idx))
        if high - low <= 1:
            continue
        covered = descendants_of(word.head)
        for between in range(low + 1, high):
            if between != word.head and between not in covered:
                return False
    return True
