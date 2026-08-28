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

from ..translate.cypher import Translation, translate
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
        query = """
        MATCH (t:Treebank)
        WHERE t.n_sents > 0
        RETURN t.name AS name, t.scheme AS scheme, t.language AS language,
               t.corpus AS corpus, t.family AS family,
               t.n_sents AS n_sents, t.n_tokens AS n_tokens
        ORDER BY t.scheme, t.language, t.corpus
        """
        with self._driver.session() as session:
            return [TreebankInfo(**row.data()) for row in session.run(query)]

    # --------------------------------------------------------------------- queries

    def _run_one(self, translation: Translation):
        with self._driver.session() as session:
            return session.run(translation.cypher, **translation.params)

    def count(self, treebank: str, request_text: str) -> int:
        translation = translate(parse(request_text), treebank, mode="count")
        with self._driver.session() as session:
            return session.run(translation.cypher, **translation.params).single()["n"]

    def aggregate(self, treebank: str, request_text: str, expression: str):
        translation = translate(
            parse(request_text), treebank, mode="aggregate", aggregate=expression
        )
        with self._driver.session() as session:
            row = session.run(translation.cypher, **translation.params).single()
            return row["value"], row["n"]

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
