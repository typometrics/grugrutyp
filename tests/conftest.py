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
    # One config per PROCESS -- grewpy holds it globally. The default leg is SUD; the
    # UD leg is a second invocation: GRUGRUTYP_DIFF_SCHEME=ud pytest tests/test_differential.py
    scheme = os.environ.get("GRUGRUTYP_DIFF_SCHEME", "sud").lower()
    grewpy.set_config(scheme)
    from grewpy import Corpus

    def basic_only_copy(name: str, source):
        """Strip enhanced dependencies for the oracle's UD load.

        grew's `ud` config reads the DEPS column as ADDITIONAL edges and empty nodes as
        real nodes; our importer reads the basic tree only. Measured on UD_English-GUM:
        `1=aux` counted 16,859 in grew vs 8,257 here -- exactly the enhanced-graph
        doubling. The suite verifies OUR declared semantics (basic tree), so the oracle
        gets a copy with DEPS blanked and empty nodes dropped; the user-facing
        divergence is documented in docs/grew-to-cypher.md (addendum 2026-09-02).
        """
        import tempfile

        target = Path(tempfile.mkdtemp(prefix=f"basic-{name}-"))
        for conllu in source.glob("*.conllu"):
            kept = []
            for line in conllu.read_text().splitlines():
                if line and not line.startswith("#"):
                    cols = line.split("\t")
                    if len(cols) == 10:
                        if "." in cols[0]:
                            continue  # empty node, exists only in the enhanced graph
                        cols[8] = "_"
                        line = "\t".join(cols)
                kept.append(line)
            (target / conllu.name).write_text("\n".join(kept) + "\n")
        return target

    cache: dict[str, object] = {}

    def get(name: str):
        if name not in cache:
            path = ROOT / "data" / "treebanks" / "v2.18" / name
            if not path.is_dir():
                pytest.skip(f"{name} not unpacked")
            if scheme == "ud":
                path = basic_only_copy(name, path)
            cache[name] = Corpus(str(path))
        return cache[name]

    return get
