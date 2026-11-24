from pathlib import Path

from udcorpus.conllu import (
    decompose_deprel,
    is_projective,
    is_tree,
    menzerath_features,
    read_conllu,
    sample_bucket,
    sentence_from_conllu,
    tree_height,
)

AAA = Path(__file__).parent / "fixtures/data/treebanks/v9.9/SUD_Testish-AAA"


def test_reader_keeps_words_and_multiword_tokens_and_skips_empty_nodes():
    sentences = list(read_conllu(AAA / "xx_aaa-sud-train.conllu"))
    assert [s.sent_id for s in sentences] == ["a1", "a2", "a3"]
    a2 = sentences[1]
    assert [w.idx for w in a2.words] == [1, 2, 3, 4]  # 2-3 is an MWT, 3.1 an empty node
    assert [(m.start, m.end, m.form) for m in a2.mwts] == [(2, 3, "thedog")]
    assert a2.words[2].deprel == "subj@expl"
    assert a2.text == "Barks thedog it"
    assert sentences[0].words[0].feats == {"Number": "Plur"}
    assert sentences[0].words[0].lemma == "dog"


def test_deprel_decomposes_into_grews_feature_structure():
    assert decompose_deprel("comp:obl@agent") == {
        "deprel": "comp:obl@agent", "rel_1": "comp", "rel_2": "obl", "rel_deep": "agent",
    }
    assert decompose_deprel("nsubj") == {"deprel": "nsubj", "rel_1": "nsubj"}
    assert decompose_deprel("_") == {}


def test_tree_properties():
    a1, a2, a3 = read_conllu(AAA / "xx_aaa-sud-train.conllu")
    assert tree_height(a1) == 2
    assert is_tree(a1) and is_projective(a1)
    assert not is_tree(a3)  # word 1 hangs from a governor that does not exist
    features = menzerath_features(a2)
    assert features[1] == {"subtree_size": 4, "n_children": 2, "n_left": 0, "n_right": 2}
    assert features[3]["subtree_size"] == 2


def test_sentence_round_trips_through_its_conllu_text():
    a2 = list(read_conllu(AAA / "xx_aaa-sud-train.conllu"))[1]
    again = sentence_from_conllu(a2.conllu)
    assert [(w.idx, w.deprel) for w in again.words] == [(w.idx, w.deprel) for w in a2.words]


def test_sample_bucket_is_a_stable_hash():
    # Pinned: grugrutyp's database stores these buckets, so a change here silently
    # changes every sampled number.
    assert sample_bucket("a1") == sample_bucket("a1")
    assert [sample_bucket(s) for s in ("a1", "a2", "news-s1")] == PINNED
    assert all(0 <= sample_bucket(f"s{i}") < 100 for i in range(200))


PINNED = [27, 18, 56]  # computed by grugrutyp's original backend/grugrutyp/conllu.py
