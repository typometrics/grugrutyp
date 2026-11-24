import json

from udcorpus import audit as audit_cli
from udcorpus import languages as lc


def test_fold_ignores_case_spacing_underscores_and_accents():
    assert lc.fold("Ancient_Greek") == lc.fold("Ancient Greek") == lc.fold("ancientgreek")
    assert lc.fold("Xavánte") == lc.fold("Xavante")


def test_lookup_by_code_first_then_by_name(fixture_corpus):
    assert lc.lookup("Shanghainese", "wuu").language == "Wu"
    assert lc.lookup("Other_Lang").language == "Other Lang"
    assert lc.lookup("Nowhere") is None
    # without a code from the caller, the code is read off the files on disk
    assert lc.row_for("Shanghainese").language == "Wu"


def test_views_and_appearance_walk_up_to_a_styled_parent(fixture_corpus):
    assert lc.label_of("Testish") == "Testic"  # family view: genus first
    assert lc.label_of("Testish", "group") == "Fictional"
    look = lc.appearance_of("Testish")  # "Testic" is not styled, "Fictional" is
    assert (look.label, look.color, look.marker) == ("Testic", "royalBlue", "triangle")
    unknown = lc.appearance_of("Nowhere")
    assert unknown.label == lc.UNKNOWN and unknown.color == "darkGrey"
    # `area` is not genetic: a generated, label-stable palette rather than the family's
    assert lc.appearance_of("Testish", "area").label == "E"
    assert lc.appearance_of("Testish", "area") == lc.appearance_of("Testish", "area")


def test_display_names_curated_over_reference(fixture_corpus):
    assert lc.display_names()["wuu"] == "Wu"
    assert lc.display_names()["xx"] == "Testish"


def test_exclusions_and_historical_flag(fixture_corpus):
    assert lc.measure_exclusions() == frozenset({("Testish", "BBB")})
    assert lc.languages()[lc.fold("Lostish")].is_historical


def test_audit_reports_unconfigured_and_orphaned(fixture_corpus):
    report = lc.audit()
    assert report.version == "9.9"
    assert report.unconfigured == ["Unknownish"]
    assert report.orphaned == ["Lostish"]
    assert not report.clean


def test_audit_command_line(fixture_corpus, capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["udcorpus.audit", "--json"])
    assert audit_cli.main() == 1  # action needed: Unknownish has no row
    out = json.loads(capsys.readouterr().out)
    assert out["unconfigured"] == ["Unknownish"]


def test_backfill_lcodes_writes_codes_only(fixture_corpus, tmp_path):
    import shutil

    from udcorpus import config

    meta = tmp_path / "meta"
    shutil.copytree(fixture_corpus / "meta", meta)
    config.configure(meta_dir=meta)
    assert audit_cli.backfill_lcodes() == 0  # Other Lang's files carry no code; nothing to add
    text = (meta / "languages.tsv").read_text()
    assert text == (fixture_corpus / "meta/languages.tsv").read_text()
