"""grugrutyp over udcorpus (corpus/): the re-exports are the same objects, and the numeric
rules udcorpus copies from grugrutyp have not drifted apart.

udcorpus has its own tests (`corpus/tests`, no grugrutyp needed); these only pin the seam.
"""

from __future__ import annotations

import pytest

from grugrutyp import conllu, langconfig, measure, meta

import udcorpus.conllu
import udcorpus.languages
import udcorpus.stats
import udcorpus.treebanks


def test_reexports_are_the_udcorpus_objects():
    assert langconfig.lookup is udcorpus.languages.lookup
    assert langconfig.audit is udcorpus.languages.audit
    assert conllu.read_conllu is udcorpus.conllu.read_conllu
    assert meta.treebanks is udcorpus.treebanks.treebanks
    assert "subtree_size" in conllu.RESERVED_WORD_PROPS  # grugrutyp's own, not udcorpus's


def test_udcorpus_is_configured_with_grugrutyps_release():
    import udcorpus.config

    assert udcorpus.config.default_version() == meta.CORPUS_VERSION
    assert udcorpus.config.data_dir() == meta.DATA_ROOT


@pytest.mark.parametrize("hits,total", [(0, 0), (0, 10), (3, 50_000), (5, 10), (10, 10), (999, 1000)])
def test_wilson_is_the_same_in_both_copies(hits, total):
    assert udcorpus.stats.wilson(hits, total) == measure.wilson(hits, total)


@pytest.mark.parametrize("tokens", [0, 50_000, 100_000, 100_001, 166_000, 4_000_000, 60_000_000])
def test_sample_rate_is_the_same_in_both_copies(tokens):
    for budget in (None, 0, 100_000, 25_000):
        assert udcorpus.stats.sample_pct(tokens, budget) == measure.sample_pct(tokens, budget)
