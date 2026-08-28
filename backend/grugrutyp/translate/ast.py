"""AST for Grew requests.

The interchange point of the pipeline: parser -> AST -> validator -> emitter. Keeping the
emitter behind an AST is what lets a second backend (node-based Neo4j encoding, or grewpy)
be added without touching the parser. See docs/grew-to-cypher.md section 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator, Literal


class ValueKind(str, Enum):
    STRING = "string"  # "être"  or  bare identifier
    REGEX_POSIX = "regex_posix"  # re"s.*"
    REGEX_PCRE = "regex_pcre"  # /.*POSS.*/i


@dataclass(frozen=True)
class Value:
    kind: ValueKind
    text: str
    case_insensitive: bool = False

    @property
    def is_regex(self) -> bool:
        return self.kind is not ValueKind.STRING


Op = Literal["eq", "neq", "present", "absent"]
Comparator = Literal["=", "<>", "<", "<=", ">", ">="]


@dataclass(frozen=True)
class FeatConstraint:
    name: str
    op: Op
    values: tuple[Value, ...] = ()


@dataclass(frozen=True)
class FeatureStructure:
    constraints: tuple[FeatConstraint, ...] = ()


@dataclass
class NodeClause:
    """`X [upos=VERB]`, `X`, or `*`. `alternatives` holds `[fs1]|[fs2]` disjunctions."""

    ident: str | None  # None == anonymous `*`
    alternatives: tuple[FeatureStructure, ...] = ()
    non_injective: bool = False  # the `X$` suffix


@dataclass
class EdgeLabelPositive:
    atoms: tuple[Value, ...]


@dataclass
class EdgeLabelNegated:
    atoms: tuple[Value, ...]


@dataclass
class EdgeLabelFeatures:
    constraints: tuple[FeatConstraint, ...]


EdgeSpec = EdgeLabelPositive | EdgeLabelNegated | EdgeLabelFeatures


@dataclass
class EdgeClause:
    src: NodeClause
    dst: NodeClause
    kind: Literal["labelled", "plain", "dominance"]
    spec: EdgeSpec | None = None
    var: str | None = None  # `e: X -[nsubj]-> Y`


@dataclass
class OrderClause:
    left: str
    right: str
    immediate: bool  # True for `<`, False for `<<`


@dataclass
class DistanceClause:
    fn: Literal["delta", "length"]
    left: str
    right: str
    comparator: Comparator
    value: int


@dataclass
class FeatureComparison:
    """`X.f = Y.g`, `X.f = "v"`, `!X.f`, `X.f = *`."""

    left_node: str
    left_feat: str
    op: Op
    right_node: str | None = None
    right_feat: str | None = None
    values: tuple[Value, ...] = ()


@dataclass
class EdgeLabelComparison:
    left: str
    right: str
    equal: bool


@dataclass
class MetaClause:
    name: str
    op: Op
    values: tuple[Value, ...] = ()


@dataclass
class GlobalClause:
    flag: Literal["tree", "forest", "cyclic", "projective"]
    negated: bool


Clause = (
    NodeClause
    | EdgeClause
    | OrderClause
    | DistanceClause
    | FeatureComparison
    | EdgeLabelComparison
    | MetaClause
    | GlobalClause
)

BlockKind = Literal["pattern", "with", "without", "global"]


@dataclass
class Block:
    kind: BlockKind
    clauses: list[Clause] = field(default_factory=list)


@dataclass
class Request:
    blocks: list[Block] = field(default_factory=list)

    def blocks_of(self, kind: BlockKind) -> Iterator[Block]:
        return (block for block in self.blocks if block.kind == kind)

    def bound_nodes(self) -> set[str]:
        """Node identifiers a *pattern* block binds -- i.e. usable by a subquery.

        Identifiers introduced only inside `with`/`without` are local to that block and
        deliberately excluded (docs/query-pairs.md section 3).
        """
        names: set[str] = set()
        for block in self.blocks_of("pattern"):
            for clause in block.clauses:
                names |= _clause_nodes(clause)
        return names

    def bound_edges(self) -> set[str]:
        names: set[str] = set()
        for block in self.blocks_of("pattern"):
            for clause in block.clauses:
                if isinstance(clause, EdgeClause) and clause.var:
                    names.add(clause.var)
        return names


def _clause_nodes(clause: Clause) -> set[str]:
    if isinstance(clause, NodeClause):
        return {clause.ident} if clause.ident else set()
    if isinstance(clause, EdgeClause):
        return {n.ident for n in (clause.src, clause.dst) if n.ident}
    if isinstance(clause, OrderClause):
        return {clause.left, clause.right}
    if isinstance(clause, DistanceClause):
        return {clause.left, clause.right}
    if isinstance(clause, FeatureComparison):
        names = {clause.left_node}
        if clause.right_node:
            names.add(clause.right_node)
        return names
    return set()


def referenced_nodes(clause: Clause) -> set[str]:
    """Public wrapper -- used by the validator and the emitter."""
    return _clause_nodes(clause)
