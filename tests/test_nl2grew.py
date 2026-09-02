"""Plain-text -> Grew: the harness, not the model.

The model is benchmarked by `scripts/nl2grew_bench.py` (results in `docs/nl2grew.md`);
these tests pin the machinery around it: nothing unvalidated is ever returned, the
validator's error goes back to the model exactly once, and the endpoint's three gates
(account, allowlist, quota) actually gate.
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from grugrutyp import nl2grew


GOOD = json.dumps(
    {
        "kind": "ratio",
        "scope": "pattern { GOV -[1=subj]-> DEP }",
        "response": "with { GOV << DEP }",
        "expression": "",
        "aggregation": "avg",
        "label": "subj after governor",
        "explanation": "Share of subjects following their governor.",
    }
)
BROKEN = json.dumps({"kind": "ratio", "scope": "pattern { GOV -[1=subj]-> }", "response": ""})
UNBOUND = json.dumps(
    {"kind": "ratio", "scope": "pattern { GOV -[1=subj]-> DEP }", "response": "with { GOV << Z }"}
)


def test_a_valid_answer_comes_back_validated(monkeypatch):
    monkeypatch.setattr(nl2grew, "_chat", lambda model, messages: GOOD)
    result = nl2grew.translate("subject after verb?", "SUD", "test-model")
    assert result["ok"] and result["attempts"] == 1
    assert result["scope"].startswith("pattern")


def test_an_invalid_answer_goes_back_once_with_the_validators_error(monkeypatch):
    answers = iter([UNBOUND, GOOD])
    seen = []

    def fake_chat(model, messages):
        seen.append(messages[-1]["content"])
        return next(answers)

    monkeypatch.setattr(nl2grew, "_chat", fake_chat)
    result = nl2grew.translate("subject after verb?", "SUD", "test-model")
    assert result["ok"] and result["attempts"] == 2
    # the retry message carries the validator's own complaint, naming the unbound node
    assert "does not validate" in seen[1] and "Z" in seen[1]


def test_two_failures_return_the_error_never_the_query(monkeypatch):
    monkeypatch.setattr(nl2grew, "_chat", lambda model, messages: BROKEN)
    result = nl2grew.translate("subject after verb?", "SUD", "test-model")
    assert not result["ok"] and result["attempts"] == 2
    assert "scope" not in result, "an unvalidated query must never reach the caller"


def test_a_refusal_is_passed_through_as_a_refusal(monkeypatch):
    monkeypatch.setattr(
        nl2grew, "_chat", lambda model, messages: json.dumps({"error": "not a measure"})
    )
    result = nl2grew.translate("what is the capital of France?", "SUD", "test-model")
    assert not result["ok"] and result["refusal"] == "not a measure"


# ---------------------------------------------------------------------- chat mode


CHAT_GOOD = json.dumps(
    {
        "reply": "Two nominal-order measures, then.",
        "proposal": {
            "x": {"kind": "ratio", "scope": "pattern { GOV -[1=subj]-> DEP }",
                  "response": "with { GOV << DEP }", "expression": "",
                  "aggregation": "avg", "label": "subj order"},
            "y": None,
            "languages": ["French"],
            "comment": "share of post-verbal subjects",
        },
    }
)


def test_chat_returns_a_validated_proposal(monkeypatch):
    monkeypatch.setattr(nl2grew, "_chat", lambda model, messages: CHAT_GOOD)
    result = nl2grew.chat([{"role": "user", "content": "compare things"}], "SUD")
    assert result["ok"] and result["proposal"]["y"] is None
    assert result["proposal"]["x"]["scope"].startswith("pattern")
    assert result["proposal"]["languages"] == ["French"]


def test_chat_sends_an_invalid_proposal_back_once(monkeypatch):
    bad = json.dumps(
        {"reply": "here", "proposal": {"x": {"kind": "ratio",
         "scope": "pattern { GOV -[1=subj]-> DEP }", "response": "with { GOV << Z }"}}}
    )
    answers = iter([bad, CHAT_GOOD])
    monkeypatch.setattr(nl2grew, "_chat", lambda model, messages: next(answers))
    result = nl2grew.chat([{"role": "user", "content": "compare things"}], "SUD")
    assert result["ok"] and result["attempts"] == 2


def test_chat_may_just_talk(monkeypatch):
    monkeypatch.setattr(
        nl2grew, "_chat",
        lambda model, messages: json.dumps({"reply": "which relation?", "proposal": None}),
    )
    result = nl2grew.chat([{"role": "user", "content": "compare stuff"}], "SUD")
    assert result["ok"] and result["proposal"] is None


# ------------------------------------------------------------------- endpoint gates


@pytest.fixture()
def gated(monkeypatch, tmp_path):
    from grugrutyp import users as users_module
    from grugrutyp import main as main_module

    store = users_module.UserStore(tmp_path / "u.sqlite")
    monkeypatch.setattr(users_module, "_store", store)
    monkeypatch.setattr(main_module.nl2grew, "configured", lambda: True)
    monkeypatch.setattr(
        main_module.nl2grew, "translate",
        lambda text, scheme, model=None: {"ok": True, "kind": "ratio", "scope": "s",
                                          "response": "", "expression": "", "aggregation": "avg",
                                          "label": "", "explanation": "", "model": "test",
                                          "attempts": 1, "seconds": 0.1},
    )
    monkeypatch.setenv("GRUGRUTYP_QUERYLOG", str(tmp_path / "ql.sqlite"))
    return store, main_module


def _request_for(user_id):
    class _Request:
        session = {} if user_id is None else {"uid": user_id}

    return _Request()


def _body(main_module):
    return main_module.TranslateRequest(text="subject after verb?", scheme="SUD")


def test_endpoint_requires_a_session(gated):
    store, main_module = gated
    with pytest.raises(HTTPException) as excinfo:
        main_module.llm_translate(_body(main_module), _request_for(None))
    assert excinfo.value.status_code == 401


def test_endpoint_requires_the_allowlist_flag(gated):
    store, main_module = gated
    account = store.login("github", "1", "NoBudget")
    with pytest.raises(HTTPException) as excinfo:
        main_module.llm_translate(_body(main_module), _request_for(account["id"]))
    assert excinfo.value.status_code == 403


def test_endpoint_enforces_the_daily_quota_and_counts_spend(gated, monkeypatch):
    store, main_module = gated
    account = store.login("github", "2", "Spender")
    store.set_flags(account["id"], llm_allowed=True)
    monkeypatch.setattr(main_module.nl2grew, "DAILY_QUOTA", 2)

    first = main_module.llm_translate(_body(main_module), _request_for(account["id"]))
    assert first["ok"] and first["quota"] == {"used": 1, "limit": 2}
    second = main_module.llm_translate(_body(main_module), _request_for(account["id"]))
    assert second["quota"]["used"] == 2
    with pytest.raises(HTTPException) as excinfo:
        main_module.llm_translate(_body(main_module), _request_for(account["id"]))
    assert excinfo.value.status_code == 429
