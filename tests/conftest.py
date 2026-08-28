import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))


def _load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


_load_env()


@pytest.fixture(scope="session")
def neo4j_driver():
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )
    yield driver
    driver.close()


@pytest.fixture(scope="session")
def imported_treebanks(neo4j_driver) -> set[str]:
    with neo4j_driver.session() as session:
        return {
            row["name"]
            for row in session.run("MATCH (t:Treebank) WHERE t.n_sents > 0 RETURN t.name AS name")
        }


@pytest.fixture(scope="session")
def grew_corpora():
    """grewpy Corpus objects, the oracle. Requires the opam env (see setup.md section 1).

    grewpy holds a global config, so both schemes cannot be queried in one process;
    every treebank in the differential matrix is SUD for that reason.
    """
    # `import grewpy` spawns the OCaml backend, so this check has to come *before* the
    # import, not after: without it a plain `pytest` produces 132 copies of an
    # uninformative `FileNotFoundError: 'grewpy_backend'` from deep inside subprocess,
    # instead of one line saying which command to run.
    if shutil.which("grewpy_backend") is None:
        pytest.skip(
            "grewpy_backend is not on PATH -- the differential suite needs the Grew oracle:\n"
            "  OPAMROOT=/opt/opam PATH=/opt/opam/grew/bin:$PATH .venv/bin/pytest "
            "tests/test_differential.py"
        )
    grewpy = pytest.importorskip("grewpy")
    grewpy.set_config("sud")
    from grewpy import Corpus

    cache: dict[str, object] = {}

    def get(name: str):
        if name not in cache:
            path = ROOT / "data" / "treebanks" / "v2.18" / name
            if not path.is_dir():
                pytest.skip(f"{name} not unpacked")
            cache[name] = Corpus(str(path))
        return cache[name]

    return get
