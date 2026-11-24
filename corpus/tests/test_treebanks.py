import pytest

from udcorpus import config
from udcorpus.treebanks import lcode_of, measure_selection, missing_families, treebanks


def test_version_defaults_to_the_highest_release_on_disk(fixture_corpus):
    assert config.available_versions() == ["9.9"]
    assert config.default_version() == "9.9"


def test_environment_variables_are_honoured(fixture_corpus, monkeypatch):
    config.reset()
    monkeypatch.setenv("UDCORPUS_DATA", str(fixture_corpus / "data"))
    monkeypatch.setenv("UDCORPUS_META", str(fixture_corpus / "meta"))
    monkeypatch.setenv("UDCORPUS_VERSION", "9.9")
    assert config.treebanks_root() == fixture_corpus / "data/treebanks/v9.9"
    assert "SUD_Testish-AAA" in treebanks()


def test_registry_parses_directory_names_and_ignores_the_rest(fixture_corpus):
    found = treebanks()
    assert sorted(found) == [
        "SUD_Other_Lang-CCC", "SUD_Shanghainese-ZZZ", "SUD_Testish-AAA", "SUD_Testish-BBB",
        "SUD_Unknownish-QQQ", "UD_Testish-AAA",
    ]
    aaa = found["SUD_Testish-AAA"]
    assert (aaa.scheme, aaa.language, aaa.corpus, aaa.lcode) == ("SUD", "Testish", "AAA", "xx")
    assert [p.name for p in aaa.conllu_files()] == ["xx_aaa-sud-dev.conllu", "xx_aaa-sud-train.conllu"]
    assert found["SUD_Other_Lang-CCC"].language == "Other_Lang"


def test_iso_code_comes_from_file_names_when_they_follow_the_convention(fixture_corpus):
    assert lcode_of(fixture_corpus / "data/treebanks/v9.9/SUD_Shanghainese-ZZZ") == "wuu"
    assert lcode_of(fixture_corpus / "data/treebanks/v9.9/SUD_Other_Lang-CCC") == ""


def test_families_resolve_by_code_then_name(fixture_corpus):
    found = treebanks()
    assert found["SUD_Shanghainese-ZZZ"].family == "Chinese"  # row "Wu", code wuu
    assert found["SUD_Other_Lang-CCC"].family == "Fictional"  # genus "Other" means none: group
    assert missing_families() == ["Unknownish"]


def test_measure_selection_is_one_scheme_minus_exclusions(fixture_corpus):
    sud = measure_selection("SUD")
    assert [tb.name for tb in sud["Testish"]] == ["SUD_Testish-AAA"]  # BBB is excluded
    assert set(sud) == {"Other_Lang", "Shanghainese", "Testish", "Unknownish"}
    ud = measure_selection("ud")
    assert {k: [t.name for t in v] for k, v in ud.items()} == {"Testish": ["UD_Testish-AAA"]}


def test_a_missing_release_says_what_to_do(fixture_corpus):
    with pytest.raises(FileNotFoundError, match="unpack"):
        treebanks("1.0")
