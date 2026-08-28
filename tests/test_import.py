"""Phase 0 exit criterion: what is in Neo4j is exactly what is in the CoNLL-U files."""

from __future__ import annotations

from pathlib import Path

import pytest

from grugrutyp import meta
from grugrutyp.conllu import is_projective, is_tree, read_conllu, tree_height

ROOT = Path(__file__).resolve().parent.parent


def _file_stats(treebank: meta.Treebank) -> tuple[int, int, int]:
    """(sentences, syntactic words, multiword tokens) straight from the files."""
    sentences = words = mwts = 0
    for path in treebank.conllu_files():
        for sentence in read_conllu(path):
            sentences += 1
            words += len(sentence.words)
            mwts += len(sentence.mwts)
    return sentences, words, mwts


CHECKED = ["SUD_Wolof-WTB", "SUD_Coptic-Scriptorium", "SUD_Irish-IDT"]


def _import_stamp(session, name: str) -> str | None:
    """`imported_at`, or None while the treebank's rebuild is in flight.

    The importer zeroes `n_sents` before deleting and writes the real count only once the
    rebuild finishes, so `n_sents > 0` is what distinguishes "finished" from "in progress".
    """
    row = session.run(
        "MATCH (t:Treebank {name:$tb}) WHERE t.n_sents > 0 RETURN t.imported_at AS at",
        tb=name,
    ).single()
    return row["at"] if row else None


@pytest.mark.parametrize("name", CHECKED)
def test_database_matches_the_files(name, neo4j_driver, imported_treebanks):
    if name not in imported_treebanks:
        pytest.skip(f"{name} not imported")

    treebank = meta.treebanks()[name]
    sentences, words, mwts = _file_stats(treebank)

    with neo4j_driver.session() as session:
        # A full import re-imports every treebank, and this test takes minutes. Reading a
        # treebank the importer is rebuilding returns a count over however much has been
        # written -- it does not fail -- so without this guard the run reports a
        # data-integrity failure that is really a race. Observed twice.
        before = _import_stamp(session, name)
        if before is None:
            pytest.skip(f"{name} is being re-imported right now")

        def scalar(query: str) -> int:
            return session.run(query, tb=name).single()[0]

        try:
            assert scalar("MATCH (s:Sentence {treebank:$tb}) RETURN count(s)") == sentences

            # One extra Word per sentence: Grew's virtual root node `__0__`.
            # See docs/neo4j-encoding.md section 2, deviation 4.
            assert (
                scalar("MATCH (w:Word {treebank:$tb}) RETURN count(w)") == words + sentences
            )
            assert (
                scalar("MATCH (w:Word {treebank:$tb}) WHERE w.idx = 0 RETURN count(w)")
                == sentences
            )

            # Every syntactic word has exactly one incoming DEPREL, including the root
            # (whose governor is `__0__`).
            assert (
                scalar("MATCH (:Word {treebank:$tb})-[r:DEPREL]->() RETURN count(r)") == words
            )

            # SUCCESSOR links adjacent real words only, so one fewer per sentence.
            assert (
                scalar("MATCH (:Word {treebank:$tb})-[r:SUCCESSOR]->() RETURN count(r)")
                == words - sentences
            )

            assert scalar("MATCH (m:Mwt {treebank:$tb}) RETURN count(m)") == mwts
            assert scalar("MATCH (w:Word:Root {treebank:$tb}) RETURN count(w)") == sentences
            assert (
                scalar(
                    "MATCH (w:Word {treebank:$tb}) "
                    "WHERE NOT (w)-[:IN_SENTENCE]->() RETURN count(w)"
                )
                == 0
            )
        except AssertionError:
            # Only now ask whether the ground moved. Checking up front would not help --
            # the treebank can be rebuilt between the first query and the last -- and
            # skipping unconditionally would hide a real defect. So: a mismatch is a
            # failure unless the import stamp changed, in which case it is a race.
            after = _import_stamp(session, name)
            if after != before:
                pytest.skip(f"{name} was re-imported during the test ({before} -> {after})")
            raise


def test_precomputed_sentence_properties_match_recomputation(neo4j_driver, imported_treebanks):
    """height / is_tree / is_projective in the DB must equal a fresh computation."""
    name = "SUD_Wolof-WTB"
    if name not in imported_treebanks:
        pytest.skip(f"{name} not imported")

    treebank = meta.treebanks()[name]
    expected = {}
    for path in treebank.conllu_files():
        for sentence in read_conllu(path):
            expected[sentence.sent_id] = (
                tree_height(sentence),
                is_tree(sentence),
                is_projective(sentence),
            )

    with neo4j_driver.session() as session:
        rows = session.run(
            "MATCH (s:Sentence {treebank:$tb}) "
            "RETURN s.sent_id AS sent_id, s.height AS height, "
            "       s.is_tree AS is_tree, s.is_projective AS is_projective",
            tb=name,
        )
        checked = 0
        for row in rows:
            assert (row["height"], row["is_tree"], row["is_projective"]) == expected[
                row["sent_id"]
            ], row["sent_id"]
            checked += 1
    assert checked == len(expected)


def test_deprel_decomposition():
    from grugrutyp.conllu import decompose_deprel

    assert decompose_deprel("comp:obl@agent") == {
        "deprel": "comp:obl@agent",
        "rel_1": "comp",
        "rel_2": "obl",
        "rel_deep": "agent",
    }
    assert decompose_deprel("aux:pass") == {
        "deprel": "aux:pass",
        "rel_1": "aux",
        "rel_2": "pass",
    }
    assert decompose_deprel("subj") == {"deprel": "subj", "rel_1": "subj"}
    assert decompose_deprel("_") == {}
