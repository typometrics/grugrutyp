"""Accounts layer: the store, the flags, the saved queries, the route guards.

The OAuth dance itself is not tested here -- it is authlib's code and three external
providers -- but everything after the callback is: identity upsert, flag handling, and
that unauthenticated requests are refused rather than half-served.
"""

from __future__ import annotations

import pytest

from grugrutyp.users import UserStore


@pytest.fixture()
def store(tmp_path):
    return UserStore(tmp_path / "users.sqlite")


def test_login_creates_then_freshens_the_row(store):
    first = store.login("orcid", "0000-0002-1825-0097", "J. Carberry")
    again = store.login("orcid", "0000-0002-1825-0097", "Josiah Carberry", "jc@example.org")
    assert again["id"] == first["id"], "same identity, same row"
    assert again["name"] == "Josiah Carberry", "name freshened on every login"
    assert again["email"] == "jc@example.org"
    assert store.list_users()[0]["id"] == first["id"]


def test_identity_is_provider_plus_subject_not_name(store):
    a = store.login("github", "12345", "Sam")
    b = store.login("google", "12345", "Sam")
    assert a["id"] != b["id"], "the same subject at two providers is two accounts"


def test_flags_default_off_and_toggle_independently(store):
    user = store.login("github", "42", "Ada")
    assert user["is_admin"] is False and user["llm_allowed"] is False
    store.set_flags(user["id"], llm_allowed=True)
    fresh = store.get(user["id"])
    assert fresh["llm_allowed"] is True and fresh["is_admin"] is False
    store.set_flags(user["id"], is_admin=True, llm_allowed=False)
    fresh = store.get(user["id"])
    assert fresh["is_admin"] is True and fresh["llm_allowed"] is False


def test_saved_queries_are_scoped_to_their_owner(store):
    kim = store.login("orcid", "kim", "Kim")
    other = store.login("orcid", "other", "Other")
    saved = store.add_query(kim["id"], "subj order", "eyJ2IjoxfQ")
    assert [q["name"] for q in store.queries(kim["id"])] == ["subj order"]
    assert store.queries(other["id"]) == []
    # another user cannot delete it, the owner can
    assert store.delete_query(other["id"], saved["id"]) is False
    assert store.delete_query(kim["id"], saved["id"]) is True
    assert store.queries(kim["id"]) == []


def test_routes_refuse_the_signed_out(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUGRUTYP_USERS", str(tmp_path / "u.sqlite"))
    monkeypatch.setenv("GRUGRUTYP_QUERYLOG", str(tmp_path / "q.sqlite"))
    from fastapi.testclient import TestClient
    from grugrutyp.main import app

    client = TestClient(app)
    assert client.get("/auth/me").json() == {"user": None}
    assert client.get("/me/queries").status_code == 401
    assert client.post("/me/queries", json={"name": "x", "payload": "y"}).status_code == 401
    # the provider list mirrors what .env configures (on the production box that is all
    # three; on a fresh clone it is empty) -- never anything outside the known set, and
    # an unknown provider 404s regardless
    providers = client.get("/auth/providers").json()["providers"]
    assert set(providers) <= {"google", "github", "orcid"}
    assert client.get("/auth/login/nope").status_code == 404
