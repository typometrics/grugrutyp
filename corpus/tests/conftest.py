import sys
from pathlib import Path

import pytest

CORPUS = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(CORPUS))

from udcorpus import config  # noqa: E402


@pytest.fixture()
def fixture_corpus(monkeypatch):
    """A tiny fake release `v9.9` (tests/fixtures/data) and its metadata (fixtures/meta).

    Environment variables are cleared so that a developer's UDCORPUS_* cannot leak in.
    """
    for name in ("UDCORPUS_DATA", "UDCORPUS_META", "UDCORPUS_VERSION"):
        monkeypatch.delenv(name, raising=False)
    config.reset()
    config.configure(data_dir=FIXTURES / "data", meta_dir=FIXTURES / "meta")
    yield FIXTURES
    config.reset()
