"""AST back to Grew source.

Two jobs, and the second is the one that pays for it.

**Showing a request back to the user** -- normalised, so `pattern{X[upos=VERB]}` and
`pattern { X [ upos = VERB ] }` look the same in a preset, a shared link, or an error.

**Making the measure cache actually hit.** `MeasureSpec.query_hash` hashed the source text,
which meant that adding a comment, reflowing a line or changing a space produced a
different key and re-ran 705 treebanks for a query that had not changed. Hashing
`unparse(parse(text))` instead keys on the *request*, not on how it was typed.

The output is deliberately canonical rather than faithful: comments are dropped, spacing is
fixed, and clauses keep their order. That is what makes it a cache key. It is **not** a
pretty-printer for the user's own text -- nothing here tries to preserve what they wrote.
"""

from __future__ import annotations

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
)


def unparse(request: Request) -> str:
    return "\n".join(_block(block) for block in request.blocks)


def _block(block: Block) -> str:
    if not block.clauses:
        return f"{block.kind} {{ }}"
    body = "; ".join(_clause(clause) for clause in block.clauses)
    return f"{block.kind} {{ {body} }}"


def _clause(clause) -> str:
    if isinstance(clause, NodeClause):
        return _node(clause)
    if isinstance(clause, EdgeClause):
        return _edge(clause)
    if isinstance(clause, OrderClause):
        return f"{clause.left} {'<' if clause.immediate else '<<'} {clause.right}"
    if isinstance(clause, DistanceClause):
        return (
            f"{clause.fn}({clause.left}, {clause.right}) "
            f"{clause.comparator} {clause.value}"
        )
    if isinstance(clause, FeatureComparison):
        return _feature_comparison(clause)
    if isinstance(clause, EdgeLabelComparison):
        op = "=" if clause.equal else "<>"
        return f"{clause.left}.label {op} {clause.right}.label"
    if isinstance(clause, MetaClause):
        return _meta(clause)
    if isinstance(clause, GlobalClause):
        return f"is_not_{clause.flag}" if clause.negated else f"is_{clause.flag}"
    raise TypeError(f"cannot unparse {type(clause).__name__}")


def _node(clause: NodeClause) -> str:
    name = clause.ident or "*"
    if clause.non_injective:
        name += "$"
    if not clause.alternatives:
        return name
    return f"{name} " + "|".join(_feature_structure(fs) for fs in clause.alternatives)


def _feature_structure(fs: FeatureStructure) -> str:
    return "[" + ", ".join(_constraint(c) for c in fs.constraints) + "]"


def _constraint(constraint: FeatConstraint) -> str:
    if constraint.op == "absent":
        return f"!{constraint.name}"
    if constraint.op == "present":
        return f"{constraint.name}=*"
    op = "=" if constraint.op == "eq" else "<>"
    return f"{constraint.name}{op}{_values(constraint.values)}"


def _values(values: tuple[Value, ...]) -> str:
    return "|".join(_value(v) for v in values)


def _value(value: Value) -> str:
    if value.kind is ValueKind.REGEX_POSIX:
        return f're"{value.text}"' + ("i" if value.case_insensitive else "")
    if value.kind is ValueKind.REGEX_PCRE:
        return f"/{value.text}/" + ("i" if value.case_insensitive else "")
    # Always quoted. A bare identifier and a quoted string mean the same thing to Grew, so
    # quoting unconditionally is what makes the two spellings hash alike.
    return '"' + value.text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _edge(clause: EdgeClause) -> str:
    prefix = f"{clause.var}: " if clause.var else ""
    src, dst = _node(clause.src), _node(clause.dst)
    if clause.kind == "dominance":
        return f"{prefix}{src} ->> {dst}"
    if clause.kind == "plain" or clause.spec is None:
        return f"{prefix}{src} -> {dst}"
    return f"{prefix}{src} -[{_edge_spec(clause.spec)}]-> {dst}"


def _edge_spec(spec) -> str:
    if isinstance(spec, EdgeLabelPositive):
        return "|".join(_edge_atom(a) for a in spec.atoms)
    if isinstance(spec, EdgeLabelNegated):
        return "^" + "|".join(_edge_atom(a) for a in spec.atoms)
    if isinstance(spec, EdgeLabelFeatures):
        # `-[1=comp, 2=obj]->`, never `-[1="comp"]->`. Unlike a node feature structure,
        # the edge form does not accept quoted values -- the grammar reads the label
        # atoms bare. Sharing `_constraint` here produced output that would not re-parse.
        return ", ".join(_edge_constraint(c) for c in spec.constraints)
    raise TypeError(f"cannot unparse edge spec {type(spec).__name__}")


def _edge_constraint(constraint: FeatConstraint) -> str:
    if constraint.op == "absent":
        return f"!{constraint.name}"
    if constraint.op == "present":
        return f"{constraint.name}=*"
    op = "=" if constraint.op == "eq" else "<>"
    return f"{constraint.name}{op}" + "|".join(_edge_atom(v) for v in constraint.values)


def _edge_atom(value: Value) -> str:
    # Edge labels are bare inside the brackets -- `-[subj]->`, not `-["subj"]->` -- so a
    # plain label is written unquoted while a regex keeps its own delimiters.
    if value.kind is ValueKind.STRING:
        return value.text
    return _value(value)


def _feature_comparison(clause: FeatureComparison) -> str:
    left = f"{clause.left_node}.{clause.left_feat}"
    if clause.op == "absent":
        return f"!{left}"
    if clause.op == "present":
        return f"{left}=*"
    op = " = " if clause.op == "eq" else " <> "
    if clause.right_node:
        return f"{left}{op}{clause.right_node}.{clause.right_feat}"
    return f"{left}{op}{_values(clause.values)}"


def _meta(clause: MetaClause) -> str:
    name = f"meta.{clause.name}"
    if clause.op == "absent":
        return f"!{name}"
    if clause.op == "present":
        return f"{name} = *"
    op = " = " if clause.op == "eq" else " <> "
    return f"{name}{op}{_values(clause.values)}"
