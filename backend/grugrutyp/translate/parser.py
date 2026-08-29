"""Grew request text -> AST.

Errors carry a line and column so the frontend editor can point at them.
"""

from __future__ import annotations

from pathlib import Path

from lark import Lark, Token, Transformer, UnexpectedInput, v_args

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

_GRAMMAR = (Path(__file__).parent / "grammar.lark").read_text(encoding="utf-8")


class GrewSyntaxError(ValueError):
    def __init__(self, message: str, line: int | None = None, column: int | None = None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column

    def as_dict(self) -> dict:
        return {"message": self.message, "line": self.line, "column": self.column}


def _unquote(text: str) -> str:
    return text[1:-1].replace('\\"', '"').replace("\\\\", "\\")


@v_args(inline=True)
class _ToAst(Transformer):
    # ------------------------------------------------------------------ values
    def string_value(self, token: Token) -> Value:
        return Value(ValueKind.STRING, _unquote(str(token)))

    def bare_value(self, token: Token) -> Value:
        return Value(ValueKind.STRING, str(token))

    def regex_posix(self, token: Token) -> Value:
        return Value(ValueKind.REGEX_POSIX, _unquote(str(token)[2:]))

    def regex_pcre(self, token: Token) -> Value:
        text = str(token)
        insensitive = text.endswith("i")
        if insensitive:
            text = text[:-1]
        return Value(ValueKind.REGEX_PCRE, text[1:-1], case_insensitive=insensitive)

    def value(self, item) -> Value:
        return item

    def value_alternatives(self, *values: Value) -> tuple[Value, ...]:
        return tuple(values)

    def rel_label(self, token: Token) -> Value:
        return Value(ValueKind.STRING, str(token))

    def label_atom(self, item) -> Value:
        return item

    def label_alternatives(self, *atoms: Value) -> tuple[Value, ...]:
        return tuple(atoms)

    # ------------------------------------------------------------- node clauses
    def feat_absent(self, name: Token) -> FeatConstraint:
        return FeatConstraint(str(name), "absent")

    def feat_present(self, name: Token) -> FeatConstraint:
        return FeatConstraint(str(name), "present")

    def feat_eq(self, name: Token, values: tuple[Value, ...]) -> FeatConstraint:
        return FeatConstraint(str(name), "eq", values)

    def feat_neq(self, name: Token, values: tuple[Value, ...]) -> FeatConstraint:
        return FeatConstraint(str(name), "neq", values)

    def feature_constraint(self, item) -> FeatConstraint:
        return item

    def feature_structure(self, *constraints: FeatConstraint) -> FeatureStructure:
        return FeatureStructure(tuple(constraints))

    def fs_alternatives(self, *structures: FeatureStructure) -> tuple[FeatureStructure, ...]:
        return tuple(structures)

    def named_node(self, ident: Token, dollar: Token | None = None) -> NodeClause:
        return NodeClause(ident=str(ident), non_injective=dollar is not None)

    def anon_node(self) -> NodeClause:
        return NodeClause(ident=None)

    def node_id(self, item) -> NodeClause:
        return item

    def node_clause(self, node: NodeClause, alternatives=None) -> NodeClause:
        node.alternatives = alternatives or ()
        return node

    # ------------------------------------------------------------- edge clauses
    def edge_feat_present(self, name: Token) -> FeatConstraint:
        return FeatConstraint(str(name), "present")

    def edge_feat_absent(self, name: Token) -> FeatConstraint:
        return FeatConstraint(str(name), "absent")

    def edge_feat_eq(self, name: Token, values: tuple[Value, ...]) -> FeatConstraint:
        return FeatConstraint(str(name), "eq", values)

    def edge_value_alternatives(self, *tokens: Token) -> tuple[Value, ...]:
        return tuple(Value(ValueKind.STRING, str(t)) for t in tokens)

    def edge_feature(self, item) -> FeatConstraint:
        return item

    def edge_feature_single(self, name: Token, values: tuple[Value, ...]) -> FeatConstraint:
        return FeatConstraint(str(name), "eq", values)

    def label_positive(self, atoms: tuple[Value, ...]) -> EdgeLabelPositive:
        return EdgeLabelPositive(atoms)

    def label_negated(self, atoms: tuple[Value, ...]) -> EdgeLabelNegated:
        return EdgeLabelNegated(atoms)

    def label_features(self, *constraints: FeatConstraint) -> EdgeLabelFeatures:
        return EdgeLabelFeatures(tuple(constraints))

    def edge_spec(self, item):
        return item

    def labelled_arrow(self, spec):
        return ("labelled", spec)

    def plain_arrow(self):
        return ("plain", None)

    def dominance_arrow(self):
        return ("dominance", None)

    def edge_arrow(self, item):
        return item

    def edge_clause(self, *parts) -> EdgeClause:
        var = None
        if isinstance(parts[0], Token):
            var = str(parts[0])
            parts = parts[1:]
        src, (kind, spec), dst = parts
        return EdgeClause(src=src, dst=dst, kind=kind, spec=spec, var=var)

    # ------------------------------------------------------------ order/distance
    def precedes(self, left: Token, right: Token) -> OrderClause:
        return OrderClause(str(left), str(right), immediate=False)

    def immediately_precedes(self, left: Token, right: Token) -> OrderClause:
        return OrderClause(str(left), str(right), immediate=True)

    # `A >> N` is Grew for "A after N" -- the mirror of `<<`, normalised at parse time by
    # swapping the operands, so downstream (emitter, unparser, cache keys) only ever sees
    # the canonical `<<` direction.
    def follows(self, left: Token, right: Token) -> OrderClause:
        return OrderClause(str(right), str(left), immediate=False)

    def immediately_follows(self, left: Token, right: Token) -> OrderClause:
        return OrderClause(str(right), str(left), immediate=True)

    def order_clause(self, item):
        return item

    def distance_clause(
        self, fn: Token, left: Token, right: Token, comparator: Token, value: Token
    ) -> DistanceClause:
        return DistanceClause(str(fn), str(left), str(right), str(comparator), int(value))

    # -------------------------------------------------------------- comparisons
    def cmp_absent(self, node: Token, feat: Token) -> FeatureComparison:
        return FeatureComparison(str(node), str(feat), "absent")

    def cmp_present(self, node: Token, feat: Token) -> FeatureComparison:
        return FeatureComparison(str(node), str(feat), "present")

    def cmp_feat_eq(self, n1: Token, f1: Token, n2: Token, f2: Token) -> FeatureComparison:
        return FeatureComparison(str(n1), str(f1), "eq", right_node=str(n2), right_feat=str(f2))

    def cmp_feat_neq(self, n1: Token, f1: Token, n2: Token, f2: Token) -> FeatureComparison:
        return FeatureComparison(str(n1), str(f1), "neq", right_node=str(n2), right_feat=str(f2))

    def cmp_value_eq(self, node: Token, feat: Token, values) -> FeatureComparison:
        return FeatureComparison(str(node), str(feat), "eq", values=values)

    def cmp_value_neq(self, node: Token, feat: Token, values) -> FeatureComparison:
        return FeatureComparison(str(node), str(feat), "neq", values=values)

    def feature_comparison(self, item):
        return item

    def edge_label_eq(self, left: Token, right: Token) -> EdgeLabelComparison:
        return EdgeLabelComparison(str(left), str(right), equal=True)

    def edge_label_neq(self, left: Token, right: Token) -> EdgeLabelComparison:
        return EdgeLabelComparison(str(left), str(right), equal=False)

    def edge_comparison(self, item):
        return item

    def meta_present(self, name: Token) -> MetaClause:
        return MetaClause(str(name), "present")

    def meta_absent(self, name: Token) -> MetaClause:
        return MetaClause(str(name), "absent")

    def meta_eq(self, name: Token, values) -> MetaClause:
        return MetaClause(str(name), "eq", values)

    def meta_neq(self, name: Token, values) -> MetaClause:
        return MetaClause(str(name), "neq", values)

    def meta_clause(self, item):
        return item

    # ------------------------------------------------------------------- blocks
    def clause(self, item):
        return item

    def clause_list(self, *clauses):
        return list(clauses)

    def global_list(self, *flags: Token) -> list[GlobalClause]:
        out = []
        for token in flags:
            text = str(token)
            negated = text.startswith("is_not_")
            out.append(GlobalClause(text.replace("is_not_", "").replace("is_", ""), negated))
        return out

    def pattern_item(self, clauses) -> Block:
        return Block("pattern", clauses)

    def with_item(self, clauses) -> Block:
        return Block("with", clauses)

    def without_item(self, clauses) -> Block:
        return Block("without", clauses)

    def global_item(self, clauses) -> Block:
        return Block("global", clauses)

    def item(self, block):
        return block

    def request(self, *blocks: Block) -> Request:
        return Request(list(blocks))


_parser = Lark(_GRAMMAR, start="request", parser="earley", ambiguity="resolve", propagate_positions=True)
_transformer = _ToAst()


def parse(text: str) -> Request:
    """Parse a Grew request. Raises GrewSyntaxError with a position on failure."""
    stripped = text.strip()
    if not stripped:
        raise GrewSyntaxError("empty request")
    try:
        tree = _parser.parse(stripped)
    except UnexpectedInput as exc:
        expected = ""
        if getattr(exc, "expected", None):
            names = sorted({str(t) for t in exc.expected})[:6]
            expected = f" (expected one of: {', '.join(names)})"
        raise GrewSyntaxError(
            f"could not parse the request{expected}",
            line=getattr(exc, "line", None),
            column=getattr(exc, "column", None),
        ) from exc
    return _transformer.transform(tree)


def parse_subquery(text: str, kind: str = "with") -> Request:
    """Parse a bare subquery body, wrapping it in `with { }` / `without { }` if needed.

    The measure UI lets a linguist type just `GOV << DEP` for the subquery, because the
    surrounding `with { }` is boilerplate that is the same every time.
    """
    stripped = text.strip()
    if not stripped:
        raise GrewSyntaxError("empty subquery")
    if stripped.startswith(("with", "without", "pattern", "global")):
        return parse(stripped)
    body = stripped if stripped.endswith("}") else stripped
    return parse(f"{kind} {{ {body} }}")
