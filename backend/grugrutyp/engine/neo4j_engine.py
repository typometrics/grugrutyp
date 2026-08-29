"""Neo4j query engine.

Kept behind a narrow interface (count / aggregate / search) so a second implementation --
a grewpy fallback, or the node-based encoding -- can be dropped in without touching the
API layer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from neo4j import GraphDatabase

from ..aggregate import aggregation_cypher, compile_expression
from ..translate.cypher import Translation, combine, translate
from ..translate.parser import parse

ROOT = Path(__file__).resolve().parents[3]


def load_env(path: Path | None = None) -> None:
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


@dataclass
class Match:
    sent_id: str
    conllu: str
    matched_nodes: list[int]


@dataclass
class TreebankInfo:
    name: str
    scheme: str
    language: str
    corpus: str
    family: str
    n_sents: int
    n_tokens: int
    # When this treebank was last written. Part of the measure cache key, so a re-import
    # discards its old counts instead of serving them against new data.
    imported_at: str = ""


class Neo4jEngine:
    def __init__(self, uri: str | None = None, auth: tuple[str, str] | None = None):
        load_env()
        self._driver = GraphDatabase.driver(
            uri or os.environ["NEO4J_URI"],
            auth=auth or (os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        )

    def close(self) -> None:
        self._driver.close()

    # ------------------------------------------------------------------ catalogue

    def treebanks(self) -> list[TreebankInfo]:
        # `n_sents > 0` is not cosmetic: the importer zeroes it before deleting a
        # treebank's nodes and writes the real count only once the rebuild is finished, so
        # this predicate is what keeps a half-imported treebank out of every query.
        query = """
        MATCH (t:Treebank)
        WHERE t.n_sents > 0
        RETURN t.name AS name, t.scheme AS scheme, t.language AS language,
               t.corpus AS corpus, t.family AS family,
               t.n_sents AS n_sents, t.n_tokens AS n_tokens,
               coalesce(t.imported_at, '') AS imported_at
        ORDER BY t.scheme, t.language, t.corpus
        """
        with self._driver.session() as session:
            return [TreebankInfo(**row.data()) for row in session.run(query)]

    def treebank(self, name: str) -> TreebankInfo | None:
        """One treebank, or None if it is absent **or currently being re-imported**.

        Worth a round trip before any query naming a treebank directly. The importer
        deletes and rebuilds in place, and a read landing in that window does not fail --
        it returns a count over whatever has been written so far. That is the worst
        possible outcome for this system: a number, plausible, and wrong.

        It is not hypothetical. The differential suite was run against a database while
        the full 2.18 import was rewriting it and produced two silent count mismatches;
        re-run on an idle database the same suite is 132/132.
        """
        query = """
        MATCH (t:Treebank {name: $name})
        WHERE t.n_sents > 0
        RETURN t.name AS name, t.scheme AS scheme, t.language AS language,
               t.corpus AS corpus, t.family AS family,
               t.n_sents AS n_sents, t.n_tokens AS n_tokens,
               coalesce(t.imported_at, '') AS imported_at
        """
        with self._driver.session() as session:
            row = session.run(query, name=name).single()
        return TreebankInfo(**row.data()) if row else None

    # --------------------------------------------------------------------- queries

    def _run_one(self, translation: Translation):
        with self._driver.session() as session:
            return session.run(translation.cypher, **translation.params)

    def count(self, treebank: str, request_text: str, sample: int | None = None) -> int:
        translation = translate(parse(request_text), treebank, mode="count", sample=sample)
        with self._driver.session() as session:
            return session.run(translation.cypher, **translation.params).single()["n"]

    def count_pair(
        self, treebank: str, scope_text: str, response_text: str, sample: int | None = None
    ) -> tuple[int, int]:
        """#(S) and #(S and Q) for one treebank, in **one** statement.

        This used to be two, on the reasoning that Cypher has no cheap way to return a
        count and a filtered count over the same match. That was wrong: Q compiles to a
        boolean, so `count(CASE WHEN <Q> THEN 1 END)` gets both from a single scope
        traversal. And the scope is the expensive half -- `pattern { GOV -> DEP }` over
        Czech is millions of edges whether or not a response filters it afterwards -- so
        the second statement was paying full price for the same work.

        `combine` still runs, for its validation: it is what enforces that every node Q
        names is bound by S. Only its *output* is unused here.

        One `sample` for both halves, which is what keeps the ratio a ratio -- if S and Q
        saw different sub-corpora, `n_hit > n_scope` would be possible.
        """
        scope = parse(scope_text)
        response = parse(response_text) if response_text.strip() else None
        if response is not None:
            combine(scope, response)  # validation only; see the docstring

        translation = translate(
            scope, treebank, mode="pair", sample=sample, response=response
        )
        with self._driver.session() as session:
            row = session.run(translation.cypher, **translation.params).single()
        return (row["n_scope"], row["n_hit"]) if row else (0, 0)

    def aggregate(
        self,
        treebank: str,
        request_text: str,
        expression: str,
        aggregation: str = "avg",
        sample: int | None = None,
    ) -> tuple[float | None, int]:
        """`(accumulated_value, n_matchings)` for an aggregate measure.

        The value is the *accumulator*, not the final statistic: for `avg` it is the sum,
        so that a language's treebanks can be merged by weight rather than by count of
        treebanks. `measure.LanguagePoint` does the division.

        The expression is compiled, never interpolated -- see `aggregate.py`.
        """
        request = parse(request_text)
        compiled = compile_expression(expression, request.bound_nodes())
        translation = translate(
            request,
            treebank,
            mode="aggregate",
            aggregate=aggregation_cypher(aggregation, compiled.cypher),
            sample=sample,
        )
        with self._driver.session() as session:
            row = session.run(translation.cypher, **translation.params).single()
        return (row["value"], row["n"]) if row else (None, 0)

    def cluster(self, treebank: str, request_text: str, key: str) -> dict[str, int]:
        """Matching counts grouped by a clustering key (`X.upos`, `e.label`, ...).

        Grouping runs inside the database, so the answer for a giant treebank is the
        distinct values and their counts, never the matchings themselves.
        """
        request = parse(request_text)
        translation = translate(request, treebank, mode="cluster", cluster=key)
        with self._driver.session() as session:
            rows = list(session.run(translation.cypher, **translation.params))
        return {row["key"]: row["n"] for row in rows}

    def search(
        self, treebank: str, request_text: str, limit: int = 20, skip: int = 0
    ) -> tuple[list[Match], list[str]]:
        request = parse(request_text)
        translation = translate(request, treebank, mode="search", limit=limit, skip=skip)
        with self._driver.session() as session:
            rows = list(session.run(translation.cypher, **translation.params))
        matches = [
            Match(
                sent_id=row["sent_id"],
                conllu=row["conllu"],
                matched_nodes=[i for i in row["matched_nodes"] if i is not None],
            )
            for row in rows
        ]
        return matches, translation.node_vars


@lru_cache(maxsize=1)
def get_engine() -> Neo4jEngine:
    return Neo4jEngine()
