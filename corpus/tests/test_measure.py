import pytest

from udcorpus.measure import head_initial, main, relation_matcher
from udcorpus.stats import sample_pct, wilson


def _by_language(rows):
    return {row["language"]: row for row in rows}


def test_relation_matching_has_grews_subset_semantics():
    subj = relation_matcher("subj")
    assert subj("subj") and subj("subj:pass") and subj("subj@expl")
    assert not subj("comp:obj")
    comp_obj = relation_matcher("comp:obj")
    assert comp_obj("comp:obj") and comp_obj("comp:obj@x") and not comp_obj("comp")
    assert relation_matcher("any") is None


def test_subject_head_initiality_sums_treebanks_and_skips_broken_edges(fixture_corpus):
    rows = _by_language(head_initial("subj", "SUD"))
    t = rows["Testish"]
    # a1 subject before its verb, a2 (subj@expl) after, a4 (subj:pass, dev file) after;
    # a3's subject hangs from word 9, which does not exist; BBB is excluded.
    assert (t["n_scope"], t["n_hit"], t["treebanks"]) == (3, 2, 1)
    assert t["value"] == pytest.approx(66.6667, abs=1e-3)
    low, high = wilson(2, 3)
    assert (t["ci_low"], t["ci_high"]) == (round(low, 4), round(high, 4))
    assert rows["Shanghainese"]["n_scope"] == 1 and rows["Shanghainese"]["n_hit"] == 0
    assert rows["Other_Lang"]["n_scope"] == 0 and rows["Other_Lang"]["value"] is None


def test_any_excludes_the_root_attachment(fixture_corpus):
    t = _by_language(head_initial("any", "SUD", languages=["Testish"]))["Testish"]
    # a1: subj, punct; a2: det, subj, comp:obj; a3: (broken subj); a4: subj:pass
    assert t["n_scope"] == 6
    assert t["n_hit"] == 4  # punct, subj@expl, comp:obj, subj:pass


def test_root_attachments_are_head_initial(fixture_corpus):
    t = _by_language(head_initial("root", "SUD", languages=["Testish"]))["Testish"]
    assert t["n_scope"] == t["n_hit"] == 4


def test_ud_relations_are_named_the_ud_way(fixture_corpus):
    t = _by_language(head_initial("nsubj", "UD"))["Testish"]
    assert (t["n_scope"], t["n_hit"]) == (1, 0)


def test_budget_samples_by_sentence_bucket(fixture_corpus):
    full = _by_language(head_initial("subj", "SUD", languages=["Testish"]))["Testish"]
    assert full["sample_pct"] == 100
    # 11 tokens in Testish-AAA; a budget of 3 tokens -> ceil(100 * 3 / 11) = 28%, i.e. the
    # sentences whose bucket is < 28. Buckets: a1 27, a2 18, a3 50, a4 11 -- so a1, a2
    # and a4 are read and a3 (whose subject is broken anyway) is not.
    sampled = _by_language(head_initial("subj", "SUD", languages=["Testish"], budget=3))["Testish"]
    assert sampled["n_tokens"] == 11
    assert sampled["sample_pct"] == sample_pct(11, 3) == 28
    assert (sampled["n_scope"], sampled["n_hit"]) == (3, 2)
    # a budget of 1 token -> ceil(100 / 11) = 10%: every bucket here is >= 11
    tiny = _by_language(head_initial("subj", "SUD", languages=["Testish"], budget=1))["Testish"]
    assert tiny["sample_pct"] == 10
    assert (tiny["n_scope"], tiny["n_hit"]) == (0, 0)  # no sentence has a bucket below 10


def test_unknown_language_is_an_error(fixture_corpus):
    with pytest.raises(KeyError, match="Klingon"):
        head_initial("subj", "SUD", languages=["Klingon"])


def test_command_line_prints_a_tsv(fixture_corpus, capsys):
    assert main(["head-initial", "--rel", "subj", "--scheme", "SUD", "--language", "Testish"]) == 0
    lines = capsys.readouterr().out.strip().split("\n")
    assert lines[0].startswith("language\tfamily\ttreebanks")
    assert lines[1].split("\t")[:2] == ["Testish", "Testic"]


def test_wilson_and_sample_rate():
    assert wilson(0, 10)[0] == 0.0 and wilson(10, 10)[1] == 100.0
    low, high = wilson(5, 10)
    assert low == pytest.approx(23.659, abs=1e-3) and high == pytest.approx(76.341, abs=1e-3)
    assert wilson(0, 0) == (0.0, 100.0)
    assert sample_pct(50_000, 100_000) == 100
    assert sample_pct(4_000_000, 100_000) == 3
    assert sample_pct(4_000_000, None) == 100
