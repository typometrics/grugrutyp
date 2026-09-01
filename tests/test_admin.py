"""Admin layer: token auth, TSV upserts with per-change commits, the query log.

The TSV editing is tested against scratch copies -- an admin edit is a git commit on the
real files, and a test that commits to the repository is a test nobody runs twice.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from grugrutyp import admin as admin_module
from grugrutyp import langconfig
from grugrutyp.querylog import QueryLog


# ------------------------------------------------------------------------- query log


def test_querylog_records_and_lists(tmp_path):
    log = QueryLog(tmp_path / "ql.sqlite")
    log.record(kind="search", query="pattern { X }", target="SUD_French-GSD",
               seconds=1.2, results=42)
    log.record(kind="measure", query="pattern { X }", scheme="SUD", error="boom")

    rows = log.recent()
    assert len(rows) == 2
    assert rows[0]["kind"] == "measure" and rows[0]["error"] == "boom"  # newest first
    assert rows[1]["results"] == 42
    assert log.recent(kind="search")[0]["kind"] == "search"
    stats = log.stats()
    assert stats["total"] == 2 and stats["errors"] == 1


def test_querylog_never_raises_on_a_broken_store(tmp_path):
    """A broken log must not break the query it was logging."""
    log = QueryLog(tmp_path / "ql.sqlite")
    log.path = tmp_path / "missing" / "nope.sqlite"  # writes will fail from here on
    log.record(kind="search", query="q")  # must not raise


def test_querylog_prunes_old_rows(tmp_path):
    log = QueryLog(tmp_path / "ql.sqlite")
    with log._connect() as conn:
        conn.execute(
            "INSERT INTO queries (ts, kind, query) VALUES ('2020-01-01T00:00:00+00:00', 'search', 'old')"
        )
    log.record(kind="search", query="new")
    assert log.prune(days=30) == 1
    assert [row["query"] for row in log.recent()] == ["new"]


# ----------------------------------------------------------------------- TSV upserts


@pytest.fixture()
def scratch_meta(tmp_path, monkeypatch):
    """Scratch TSVs, git commits recorded instead of run, langconfig pointed away and
    back so the real caches are not poisoned with test data."""
    meta = tmp_path / "meta"
    meta.mkdir()
    (meta / "languages.tsv").write_text(
        "language\tgroup\tgenus\tsubgenus\tsimple_group\tarea\ttypology\tlcode\n"
        "French\tIndo-European\tItalic\t\tIndo-European\tE\t\tfr\n"
        "Wu\tSino-Austronesian\tChinese\t\tOther\tAs\t\twuu\n",
        encoding="utf-8",
    )
    (meta / "appearance.tsv").write_text(
        "group\tcolor\tmarker\nIndo-European\troyalBlue\ttriangle\n", encoding="utf-8"
    )
    commits = []
    monkeypatch.setattr(admin_module, "META_DIR", meta)
    monkeypatch.setattr(langconfig, "META_DIR", meta)
    monkeypatch.setattr(
        admin_module, "_commit", lambda path, message: commits.append((path.name, message)) or ""
    )
    langconfig.reload()
    yield meta, commits
    # monkeypatch restores META_DIR after the test; the caches must follow it back.
    monkeypatch.undo()
    langconfig.reload()


def test_upsert_edits_one_column_and_commits_once(scratch_meta):
    meta, commits = scratch_meta
    result = admin_module._upsert(
        "appearance.tsv", "group", "Indo-European", {"color": "navy"}
    )
    assert result["changed"] == ["color royalBlue→navy"]
    assert "navy" in (meta / "appearance.tsv").read_text()
    assert len(commits) == 1 and "Indo-European" in commits[0][1]


def test_upsert_appends_a_new_row(scratch_meta):
    meta, commits = scratch_meta
    result = admin_module._upsert(
        "languages.tsv", "language", "Klingon", {"group": "Other", "lcode": "tlh"}
    )
    assert "new row" in result["changed"]
    text = (meta / "languages.tsv").read_text()
    assert "Klingon\tOther" in text and text.endswith("\n")


def test_upsert_rename_keeps_the_rows_curation(scratch_meta):
    """Confirming an audit rename: the new name takes over the old row, nothing is lost."""
    meta, commits = scratch_meta
    result = admin_module._upsert(
        "languages.tsv", "language", "Shanghainese", {}, original_key="Wu"
    )
    assert any("renamed" in change for change in result["changed"])
    text = (meta / "languages.tsv").read_text()
    assert "Shanghainese\tSino-Austronesian" in text and "Wu\t" not in text
    # And the reload means the API answers with the new state immediately.
    assert langconfig.languages().get(langconfig._fold("Shanghainese")) is not None


def test_upsert_without_changes_does_not_commit(scratch_meta):
    meta, commits = scratch_meta
    result = admin_module._upsert(
        "appearance.tsv", "group", "Indo-European", {"color": "royalBlue"}
    )
    assert result["changed"] == [] and not commits


def test_upsert_rejects_unknown_columns(scratch_meta):
    with pytest.raises(HTTPException) as excinfo:
        admin_module._upsert("appearance.tsv", "group", "Indo-European", {"shape": "blob"})
    assert excinfo.value.status_code == 422
    assert "shape" in str(excinfo.value.detail)


# ------------------------------------------------------------------------------ auth


def test_admin_requires_the_configured_token(monkeypatch):
    monkeypatch.setenv("GRUGRUTYP_ADMIN_TOKEN", "sesame")
    with pytest.raises(HTTPException) as excinfo:
        admin_module.require_admin(authorization="", x_admin_token="wrong")
    assert excinfo.value.status_code == 401
    admin_module.require_admin(authorization="", x_admin_token="sesame")
    admin_module.require_admin(authorization="Bearer sesame", x_admin_token="")


def test_admin_reports_a_missing_token_as_configuration_not_login(monkeypatch):
    monkeypatch.delenv("GRUGRUTYP_ADMIN_TOKEN", raising=False)
    with pytest.raises(HTTPException) as excinfo:
        admin_module.require_admin(authorization="Bearer whatever", x_admin_token="")
    assert excinfo.value.status_code == 503
