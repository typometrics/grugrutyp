"""AST -> Cypher.

Implements docs/grew-to-cypher.md. Every literal becomes a query parameter, never string
interpolation: it lets Neo4j reuse the query plan across the ~250 treebanks of a single
measure, and it makes injection structurally impossible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from .ast import (
    Block,
    DistanceClause,
    EdgeClause,
    EdgeLabelComparison,
    EdgeLabelFeatures,
    EdgeLabelNegated,
    EdgeLabelPositive,
    FeatConstraint,
    FeatureComparison,
    FeatureStructure,
    GlobalClause,
    MetaClause,
    NodeClause,
    OrderClause,
    Request,
    Value,
    ValueKind,
    referenced_nodes,
)

Mode = Literal["count", "search", "aggregate", "pair", "cluster"]

# grew.fr's clustering keys: `X.upos` groups the matchings by a feature of a bound node,
# `e.label` by the label of a named edge. The identifier must be bound by the request and
# the feature name is regex-restricted, then backtick-quoted -- the pair of checks that
# keeps a user-typed key out of injection territory (features like `Number[psor]` are
# legal property names here, backticks are not).
_CLUSTER_KEY = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_\[\]]*)")

# Grew edge-label features -> our DEPREL edge properties (docs/neo4j-encoding.md, dev. 3).
EDGE_FEATURE_PROPS = {"1": "rel_1", "2": "rel_2", "deep": "rel_deep"}

# Sentence metadata we actually store as properties. Anything else lives only inside the
# raw `conllu` blob and cannot be queried, so we reject it rather than silently ignore it.
META_PROPS = {"sent_id": "sent_id", "text": "text"}

# Per-word counters the importer stores as INTEGERS (conllu.menzerath_features). A Grew
# value is textual, so `S[subtree_size=2]` would otherwise compare the integer 2 to the
# string "2" -- silently false everywhere in Cypher -- and the dead axis would look like
# a typological finding of zero, not like an error.
NUMERIC_NODE_PROPS = frozenset({"subtree_size", "n_children", "n_left", "n_right"})

# Bump this when the SEMANTICS of what this module (or the sampling bucket hash, or an
# importer backfill) produces change for unchanged request text -- the numeric-counter
# fix above would have been a bump. The measure cache folds it into its version key
# (cache.cache_version), so a bump makes every older row unreachable instead of
# silently wrong; see docs/menzerath.md, "the cache aftermath".
TRANSLATION_VERSION = 1


def _as_int(text: str) -> int | None:
    return int(text) if text.lstrip("-").isdigit() and text.lstrip("-") else None

SUPPORTED_GLOBALS = {"tree": "is_tree", "projective": "is_projective"}


class UnsupportedConstruct(ValueError):
    """A construct Grew has that this translator will not pretend to support."""


@dataclass
class Translation:
    cypher: str
    params: dict
    node_vars: list[str]
    edge_vars: list[str]


@dataclass
class _Emitter:
    treebank: str
    params: dict = field(default_factory=dict)
    _counter: int = 0
    _edge_counter: int = 0

    def param(self, value) -> str:
        self._counter += 1
        name = f"p{self._counter}"
        self.params[name] = value
        return f"${name}"

    def edge_var(self) -> str:
        """A fresh anonymous edge variable, unique across the *whole* translation.

        Must not be per-block: reusing `_e1` inside an EXISTS subquery makes Cypher bind
        the same relationship as the outer MATCH, which then cannot also point at the
        subquery's node -- the query silently returns 0 instead of erroring.
        """
        self._edge_counter += 1
        return f"_e{self._edge_counter}"

    # ------------------------------------------------------------------ values

    def _regex_param(self, value: Value) -> str:
        """Normalise a Grew regex to Cypher's `=~`.

        Both are **whole-string** matches, so the pattern passes through unchanged.

        This was measured, not assumed. On SUD_Wolof-WTB, grewlib gives
        `[lemma=re"a"]` == `[lemma="a"]` == 1116, `[upos=re"OU"]` == 0, and
        `-[re"subj"]->` == `-[subj]->` == 4722 -- all only possible if Grew anchors. An
        earlier version of this function wrapped patterns in `.*`, which silently turned
        every regex into a substring search. Divergence #2 of
        docs/grew-to-cypher.md section 7 is therefore closed.

        The only real adjustment is PCRE's `i` flag, which becomes an inline `(?i)`.
        """
        pattern = value.text
        if value.case_insensitive:
            pattern = "(?i)" + pattern
        return self.param(pattern)

    def _match_value(
        self, expr: str, values: tuple[Value, ...], negate: bool, feature: str | None = None
    ) -> str:
        """`expr` compared against a Grew value disjunction. `feature` is the feature
        name when known: values against a numeric stored property become int params."""
        numeric = feature in NUMERIC_NODE_PROPS
        parts: list[str] = []
        literals = [
            (_as_int(v.text) if numeric and _as_int(v.text) is not None else v.text)
            for v in values
            if v.kind is ValueKind.STRING
        ]
        if literals:
            if len(literals) == 1:
                parts.append(f"{expr} = {self.param(literals[0])}")
            else:
                parts.append(f"{expr} IN {self.param(literals)}")
        for value in values:
            if value.is_regex:
                parts.append(f"{expr} =~ {self._regex_param(value)}")
        condition = parts[0] if len(parts) == 1 else "(" + " OR ".join(parts) + ")"
        if negate:
            # Grew requires the feature to be defined *and* different. Cypher's `<>` is
            # null-propagating, so the IS NOT NULL guard is what keeps the two in step.
            # Divergence #1 in docs/grew-to-cypher.md section 7.
            return f"({expr} IS NOT NULL AND NOT {condition})"
        return condition

    # ------------------------------------------------------- feature structures

    def _feat_condition(self, node: str, constraint: FeatConstraint) -> str:
        prop = f"{node}.`{constraint.name}`"
        if constraint.op == "present":
            return f"{prop} IS NOT NULL"
        if constraint.op == "absent":
            return f"{prop} IS NULL"
        return self._match_value(
            prop, constraint.values, negate=constraint.op == "neq", feature=constraint.name
        )

    def _fs_condition(self, node: str, structure: FeatureStructure) -> str:
        parts = [self._feat_condition(node, c) for c in structure.constraints]
        if not parts:
            return "true"
        return " AND ".join(parts) if len(parts) == 1 else "(" + " AND ".join(parts) + ")"

    def node_conditions(self, clause: NodeClause) -> list[str]:
        if not clause.alternatives or clause.ident is None:
            return []
        options = [self._fs_condition(clause.ident, fs) for fs in clause.alternatives]
        if len(options) == 1:
            return [options[0]]
        return ["(" + " OR ".join(options) + ")"]

    # ------------------------------------------------------------------- edges

    def _edge_label(self, spec, var: str) -> tuple[str, list[str]]:
        """Return (inline property map, extra WHERE conditions) for an edge spec."""
        if spec is None:
            return "", []

        if isinstance(spec, EdgeLabelPositive):
            atoms = spec.atoms
            if len(atoms) == 1 and not atoms[0].is_regex:
                # The common case, and the one the deprel index can serve.
                return f" {{deprel: {self.param(atoms[0].text)}}}", []
            return "", [self._match_value(f"{var}.deprel", atoms, negate=False)]

        if isinstance(spec, EdgeLabelNegated):
            return "", [
                f"NOT {self._match_value(f'{var}.deprel', spec.atoms, negate=False)}"
            ]

        if isinstance(spec, EdgeLabelFeatures):
            conditions: list[str] = []
            inline: dict[str, str] = {}
            for constraint in spec.constraints:
                prop = EDGE_FEATURE_PROPS.get(constraint.name)
                if prop is None:
                    raise UnsupportedConstruct(
                        f"unknown edge-label feature '{constraint.name}'. "
                        f"Supported: {', '.join(sorted(EDGE_FEATURE_PROPS))}"
                    )
                expr = f"{var}.{prop}"
                if constraint.op == "present":
                    conditions.append(f"{expr} IS NOT NULL")
                elif constraint.op == "absent":
                    conditions.append(f"{expr} IS NULL")
                elif (
                    constraint.op == "eq"
                    and len(constraint.values) == 1
                    and not constraint.values[0].is_regex
                ):
                    inline[prop] = self.param(constraint.values[0].text)
                else:
                    conditions.append(
                        self._match_value(expr, constraint.values, negate=constraint.op == "neq")
                    )
            inline_text = (
                " {" + ", ".join(f"{k}: {v}" for k, v in inline.items()) + "}" if inline else ""
            )
            return inline_text, conditions

        raise UnsupportedConstruct(f"unsupported edge specification: {spec!r}")


@dataclass
class _Scope:
    """Cypher fragments accumulated for one block."""

    matches: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    new_nodes: set[str] = field(default_factory=set)


def _node_pattern(clause: NodeClause) -> str:
    return f"({clause.ident})" if clause.ident else "()"


def _emit_clauses(
    emitter: _Emitter,
    clauses: list,
    known_nodes: set[str],
    sentence_var: str,
    declare_nodes: bool,
) -> _Scope:
    """Turn one block's clauses into MATCH fragments and boolean conditions.

    `known_nodes` are variables already bound by an enclosing scope; anything else this
    block mentions is new and must be declared (and tied to the same sentence).
    """
    scope = _Scope()

    def ensure(name: str | None) -> None:
        if name and name not in known_nodes and name not in scope.new_nodes:
            scope.new_nodes.add(name)
            if declare_nodes:
                scope.matches.append(
                    f"MATCH ({name}:Word {{treebank: {emitter.param(emitter.treebank)}}})"
                )
                scope.matches.append(f"MATCH ({name})-[:IN_SENTENCE]->({sentence_var})")

    for clause in clauses:
        if isinstance(clause, NodeClause):
            ensure(clause.ident)
            scope.conditions.extend(emitter.node_conditions(clause))

        elif isinstance(clause, EdgeClause):
            ensure(clause.src.ident)
            ensure(clause.dst.ident)
            scope.conditions.extend(emitter.node_conditions(clause.src))
            scope.conditions.extend(emitter.node_conditions(clause.dst))

            if clause.kind == "dominance":
                scope.matches.append(
                    f"MATCH {_node_pattern(clause.src)}-[:DEPREL*1..]->{_node_pattern(clause.dst)}"
                )
                continue

            var = clause.var or emitter.edge_var()
            inline, conditions = emitter._edge_label(clause.spec, var)
            scope.matches.append(
                f"MATCH {_node_pattern(clause.src)}-[{var}:DEPREL{inline}]->{_node_pattern(clause.dst)}"
            )
            scope.conditions.extend(conditions)

        elif isinstance(clause, OrderClause):
            ensure(clause.left)
            ensure(clause.right)
            if clause.immediate:
                scope.conditions.append(f"{clause.left}.idx + 1 = {clause.right}.idx")
            else:
                scope.conditions.append(f"{clause.left}.idx < {clause.right}.idx")

        elif isinstance(clause, DistanceClause):
            ensure(clause.left)
            ensure(clause.right)
            delta = f"({clause.right}.idx - {clause.left}.idx)"
            expr = delta if clause.fn == "delta" else f"abs{delta}"
            operator = "<>" if clause.comparator == "<>" else clause.comparator
            scope.conditions.append(f"{expr} {operator} {emitter.param(clause.value)}")

        elif isinstance(clause, FeatureComparison):
            ensure(clause.left_node)
            left = f"{clause.left_node}.`{clause.left_feat}`"
            if clause.op == "present":
                scope.conditions.append(f"{left} IS NOT NULL")
            elif clause.op == "absent":
                scope.conditions.append(f"{left} IS NULL")
            elif clause.right_node:
                ensure(clause.right_node)
                right = f"{clause.right_node}.`{clause.right_feat}`"
                guard = f"{left} IS NOT NULL AND {right} IS NOT NULL"
                operator = "=" if clause.op == "eq" else "<>"
                scope.conditions.append(f"({guard} AND {left} {operator} {right})")
            else:
                scope.conditions.append(
                    emitter._match_value(
                        left, clause.values, negate=clause.op == "neq",
                        feature=clause.left_feat,
                    )
                )

        elif isinstance(clause, EdgeLabelComparison):
            operator = "=" if clause.equal else "<>"
            scope.conditions.append(
                f"({clause.left}.deprel IS NOT NULL AND {clause.right}.deprel IS NOT NULL "
                f"AND {clause.left}.deprel {operator} {clause.right}.deprel)"
            )

        elif isinstance(clause, MetaClause):
            prop = META_PROPS.get(clause.name)
            if prop is None:
                raise UnsupportedConstruct(
                    f"meta.{clause.name} is not stored as a queryable property. "
                    f"Available: {', '.join(sorted(META_PROPS))}"
                )
            expr = f"{sentence_var}.{prop}"
            if clause.op == "present":
                scope.conditions.append(f"{expr} IS NOT NULL")
            elif clause.op == "absent":
                scope.conditions.append(f"{expr} IS NULL")
            else:
                scope.conditions.append(
                    emitter._match_value(expr, clause.values, negate=clause.op == "neq")
                )

        elif isinstance(clause, GlobalClause):
            prop = SUPPORTED_GLOBALS.get(clause.flag)
            if prop is None:
                raise UnsupportedConstruct(
                    f"global {{ is_{clause.flag} }} is not supported. "
                    f"Supported: {', '.join('is_' + f for f in sorted(SUPPORTED_GLOBALS))}"
                )
            scope.conditions.append(
                f"{sentence_var}.{prop} = {emitter.param(not clause.negated)}"
            )

        else:  # pragma: no cover -- every AST node type is handled above
            raise UnsupportedConstruct(f"unhandled clause: {clause!r}")

    return scope


def _non_injective_idents(clauses: list) -> set[str]:
    """Identifiers written with the `$` suffix, which opt out of injective matching."""
    names: set[str] = set()
    for clause in clauses:
        if isinstance(clause, NodeClause) and clause.non_injective and clause.ident:
            names.add(clause.ident)
        elif isinstance(clause, EdgeClause):
            for endpoint in (clause.src, clause.dst):
                if endpoint.non_injective and endpoint.ident:
                    names.add(endpoint.ident)
    return names


def _injectivity_guards(left: list[str], right: list[str] | None = None) -> list[str]:
    """`X.idx <> Y.idx` for every relevant pair.

    All pattern nodes live in one sentence and `idx` is unique within it, so comparing
    idx is cheaper than comparing node identity and means the same thing.
    """
    if right is None:
        return [
            f"{a}.idx <> {b}.idx"
            for i, a in enumerate(left)
            for b in left[i + 1 :]
        ]
    return [f"{a}.idx <> {b}.idx" for a in left for b in right]


def _subquery(scope: _Scope, negated: bool) -> str:
    """Render a with/without block.

    A block that introduces no new nodes and no MATCHes is a pure filter, so it collapses
    to a plain boolean -- much cheaper than an EXISTS subquery. `without` on a pure filter
    needs `coalesce(..., false)`: in Grew a constraint over an undefined feature simply
    does not hold, so the matching survives, whereas Cypher's `NOT null` is null and would
    drop it.
    """
    if not scope.matches:
        if not scope.conditions:
            return "true" if not negated else "false"
        body = " AND ".join(scope.conditions)
        if negated:
            return f"NOT coalesce({body}, false)"
        return f"({body})"

    inner = "\n    ".join(scope.matches)
    where = ""
    if scope.conditions:
        where = "\n    WHERE " + "\n      AND ".join(scope.conditions)
    keyword = "NOT EXISTS" if negated else "EXISTS"
    return f"{keyword} {{\n    {inner}{where}\n  }}"


def translate(
    request: Request,
    treebank: str,
    mode: Mode = "count",
    aggregate: str | None = None,
    limit: int = 50,
    skip: int = 0,
    sample: int | None = None,
    response: Request | None = None,
    clusters: list[dict] | None = None,
    order: str = "initial",
) -> Translation:
    """Compile a parsed Grew request into a single Cypher statement.

    `sample` restricts the query to a deterministic k% of the treebank's sentences. It is
    a filter on the sentence node, so both halves of a query pair and both axes of a plot
    see the same sub-corpus as long as they are given the same value -- which is the
    property that makes the ratio still a ratio. See `docs/sampling.md` section 4.
    """
    emitter = _Emitter(treebank=treebank)
    sentence_var = "_s"

    pattern_clauses = [c for block in request.blocks_of("pattern") for c in block.clauses]
    global_clauses = [c for block in request.blocks_of("global") for c in block.clauses]

    scope = _emit_clauses(
        emitter,
        pattern_clauses + global_clauses,
        known_nodes=set(),
        sentence_var=sentence_var,
        declare_nodes=True,
    )
    bound = set(scope.new_nodes)

    lines: list[str] = [
        f"MATCH ({sentence_var}:Sentence {{treebank: {emitter.param(treebank)}}})"
    ]
    lines.extend(scope.matches)
    conditions = list(scope.conditions)

    if sample is not None and sample < 100:
        # `bucket` is blake2b(sent_id) % 100, written at import and indexed together with
        # `treebank`. Deliberately not `rand()`: a cached value has to stay meaningful and
        # a published result has to reproduce.
        conditions.append(f"{sentence_var}.bucket < {emitter.param(sample)}")

    # Injectivity: distinct Grew identifiers denote distinct nodes unless suffixed with $.
    injective = sorted(bound - _non_injective_idents(pattern_clauses))
    conditions.extend(_injectivity_guards(injective))

    def response_condition(block) -> str:
        """One `with`/`without` block as a boolean, ready for a WHERE or a CASE."""
        sub = _emit_clauses(
            emitter,
            block.clauses,
            known_nodes=bound,
            sentence_var=sentence_var,
            declare_nodes=True,
        )
        # Injectivity spans the whole request, not just the pattern block: a node
        # introduced by `with`/`without` is distinct from every pattern node too.
        # Without these guards `with { X -> Z [upos=ADV] }` would happily bind Z to
        # the same word as Y.
        sub_injective = sorted(sub.new_nodes - _non_injective_idents(block.clauses))
        sub.conditions.extend(_injectivity_guards(sub_injective))
        sub.conditions.extend(_injectivity_guards(sub_injective, injective))
        return _subquery(sub, negated=block.kind == "without")

    for block in request.blocks:
        if block.kind in ("with", "without"):
            conditions.append(response_condition(block))

    if conditions:
        lines.append("WHERE " + "\n  AND ".join(conditions))

    node_vars = sorted(bound)
    edge_vars = sorted(request.bound_edges())

    if mode == "pair":
        # #(S) and #(S and Q) from **one** scope match.
        #
        # Two separate statements traverse the scope twice, and the scope is the expensive
        # half -- `pattern { GOV -> DEP }` over Czech is millions of edges whether or not a
        # response filters it afterwards. Folding Q into a conditional count halves both
        # the round trips and the traversal. See `Neo4jEngine.count_pair`.
        response_blocks = [] if response is None else [
            b for b in response.blocks if b.kind in ("with", "without")
        ]
        if not response_blocks:
            lines.append("RETURN count(*) AS n_scope, count(*) AS n_hit")
        else:
            predicate = " AND ".join(response_condition(b) for b in response_blocks)
            lines.append(
                f"RETURN count(*) AS n_scope,\n"
                f"       count(CASE WHEN {predicate} THEN 1 END) AS n_hit"
            )
    elif mode == "count":
        lines.append("RETURN count(*) AS n")
    elif mode == "cluster":
        # grew.fr's model: up to two clusterings, each either a **key** (a feature of a
        # bound node, or a named edge's label) or a **whether** (a with/without request
        # that partitions the matchings into yes/no). Grouping happens in the database,
        # so clustering a giant treebank by lemma does not ship a million rows -- only
        # the distinct value combinations and their counts come back. An undefined
        # feature is a group of its own, exactly as on grew.fr.
        if not clusters:
            raise ValueError("cluster mode requires at least one clustering")
        if len(clusters) > 2:
            raise ValueError("at most two clusterings are supported")
        projections = []
        for index, spec in enumerate(clusters, 1):
            if spec.get("kind") == "whether":
                wrapped = spec["request"]
                blocks = [b for b in wrapped.blocks if b.kind in ("with", "without")]
                if not blocks:
                    raise ValueError(
                        "a 'whether' clustering needs a condition, e.g. GOV << DEP"
                    )
                predicate = " AND ".join(response_condition(b) for b in blocks)
                projections.append(
                    f"CASE WHEN {predicate} THEN 'yes' ELSE 'no' END AS key{index}"
                )
                continue
            match = _CLUSTER_KEY.fullmatch((spec.get("value") or "").strip())
            if not match:
                raise ValueError(
                    "a clustering key looks like X.upos, Y.lemma, Y.Number or e.label"
                )
            ident, feature = match.groups()
            if ident in edge_vars:
                if feature != "label":
                    raise ValueError(f"an edge clusters by its label: try {ident}.label")
                accessor = f"{ident}.deprel"
            elif ident in bound:
                if feature == "label":
                    raise ValueError(
                        f"'{ident}' is a node; .label only applies to a named edge"
                    )
                accessor = f"{ident}.`{feature}`"
            else:
                raise ValueError(
                    f"'{ident}' is not bound by the request "
                    f"(bound: {', '.join(node_vars + edge_vars) or 'nothing'})"
                )
            projections.append(
                f"coalesce(toString({accessor}), '__undefined__') AS key{index}"
            )
        keys = ", ".join(f"key{index}" for index in range(1, len(clusters) + 1))
        lines.append(
            f"RETURN {', '.join(projections)}, count(*) AS n\nORDER BY n DESC, {keys}"
        )
    elif mode == "aggregate":
        if not aggregate:
            raise ValueError("aggregate mode requires an expression")
        lines.append(f"RETURN {aggregate} AS value, count(*) AS n")
    else:
        projection = (
            "[" + ", ".join(f"{name}.idx" for name in node_vars) + "]" if node_vars else "[]"
        )
        # grew.fr's "sentences order". All three are deterministic -- page 2 must
        # continue page 1, and a shared result must reproduce -- so "shuffle" is the
        # per-sentence hash bucket, which decorrelates the order from the corpus without
        # any randomness.
        order_by = {
            "initial": "sent_id",
            "length": f"{sentence_var}.n_tokens, sent_id",
            "shuffle": f"{sentence_var}.bucket, sent_id",
        }.get(order)
        if order_by is None:
            raise ValueError("order must be one of: initial, length, shuffle")
        lines.append(
            f"RETURN {sentence_var}.sent_id AS sent_id, {sentence_var}.conllu AS conllu,\n"
            f"       {projection} AS matched_nodes\n"
            f"ORDER BY {order_by}\n"
            f"SKIP {emitter.param(skip)} LIMIT {emitter.param(limit)}"
        )

    return Translation(
        cypher="\n".join(lines),
        params=emitter.params,
        node_vars=node_vars,
        edge_vars=edge_vars,
    )


def combine(scope: Request, subquery: Request) -> Request:
    """S (+) Q: append the response pattern's blocks to the scope's.

    Two rules, both from `docs/query-pairs.md` section 3, and both about the same danger:
    a response pattern that quietly means something other than "of the S I just counted,
    how many also do Q".

    1. Q may not contain a `pattern` block. That would add nodes and multiply the matching
       count, so #(S and Q)/#(S) could exceed 100%.
    2. Every node Q names must be bound by S. `pattern { GOV -[1=subj]-> DEP }` with
       `with { GOV << X }` does not measure subject position -- it measures "a subject
       whose governor precedes *some word*", which is true of almost every sentence. Grew
       is happy to introduce X; a typological measure is not.
    """
    for block in subquery.blocks:
        if block.kind == "pattern":
            raise UnsupportedConstruct(
                "a subquery may not contain a `pattern` block: it would add nodes and "
                "multiply the matching count, so #(S and Q)/#(S) could exceed 100%. "
                "Use `with { ... }` or `without { ... }`."
            )

    bound = scope.bound_nodes()
    free: set[str] = set()
    for block in subquery.blocks:
        for clause in block.clauses:
            free |= referenced_nodes(clause)
    # `*` is Grew's anonymous node and binds nothing, so it is never "free".
    unbound = sorted(name for name in free - bound if name and name != "*")
    if unbound:
        names = ", ".join(unbound)
        known = ", ".join(sorted(bound)) or "nothing"
        raise UnsupportedConstruct(
            f"the response pattern uses {names}, which the scope does not bind "
            f"(the scope binds {known}). A new node in the response makes the "
            f"measure mean something else -- it would count scope matchings for which "
            f"*some* such node exists, not scope matchings that satisfy the response. "
            f"Name a node the scope binds, or move the node into the scope."
        )

    return Request(blocks=list(scope.blocks) + list(subquery.blocks))
