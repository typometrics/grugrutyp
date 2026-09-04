"""The `/measure` SSE stream, end to end through the app.

`/measure` is the endpoint that changes most often and the one whose failures reach
users first -- twice in one week (a rate limit that rejected the page's own auto-plot,
a frozen dataclass that 500'd every exact run). Both were invisible to the unit tests
because nothing exercised the streaming endpoint itself.

The fan-out is faked: what is under test is the *stream contract* -- the event
sequence, that a mid-run failure becomes an `error` event rather than a dead socket,
that a failure BEFORE the first event does the same (it used to escape the generator
after the 200 header, leaving the browser with a generic network error), and that the
query log always gets its row.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from grugrutyp.engine.neo4j_engine import TreebankInfo
from grugrutyp.measure import Point


BODY = {
    "scheme": "SUD",
    "x": {"scope": "pattern { GOV -[1=subj]-> DEP }", "response": "with { GOV << DEP }"},
}

TREEBANKS = [
    TreebankInfo("SUD_French-GSD", "SUD", "French", "GSD", "Indo-European", 400, 10_000),
    TreebankInfo("SUD_Wolof-WTB", "SUD", "Wolof", "WTB", "Niger-Congo", 200, 5_000),
]


def events(response) -> list[tuple[str, dict]]:
    """The SSE frames of a completed response, as (name, payload)."""
    out = []
    for chunk in response.text.split("\n\n"):
        name, data = None, []
        for line in chunk.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data.append(line[6:])
        if name and data:
            out.append((name, json.loads("\n".join(data))))
    return out


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUGRUTYP_QUERYLOG", str(tmp_path / "q.sqlite"))
    monkeypatch.setenv("GRUGRUTYP_USERS", str(tmp_path / "u.sqlite"))
    from grugrutyp import main as main_module
    from grugrutyp import querylog

    # both are module singletons: reset so the tmp paths above take effect, and again
    # afterwards so a test file never leaves the next one pointed at a deleted file
    monkeypatch.setattr(querylog, "_log", None)
    monkeypatch.setattr(main_module, "select", lambda options: list(TREEBANKS))
    return TestClient(main_module.app), main_module


def test_the_happy_path_streams_start_points_then_done(client, monkeypatch):
    http, main_module = client

    def fake_run(specs, options, chosen=None):
        for tb in chosen or TREEBANKS:
            yield [Point(treebank=tb.name, language=tb.language, n_scope=100, n_hit=42)]

    monkeypatch.setattr(main_module, "run", fake_run)
    response = http.post("/measure", json=BODY)
    assert response.status_code == 200

    names = [name for name, _ in events(response)]
    assert names == ["start", "point", "point", "done"]

    frames = dict(events(response))
    assert frames["start"]["n_treebanks"] == 2
    # the done event carries the language-level merge, one entry per language
    languages = frames["done"]["languages"][0]
    assert {entry["language"] for entry in languages} == {"French", "Wolof"}
    assert languages[0]["value"] == pytest.approx(42.0)


def test_a_midrun_failure_becomes_an_error_event(client, monkeypatch):
    http, main_module = client

    def fake_run(specs, options, chosen=None):
        yield [Point(treebank="SUD_French-GSD", language="French", n_scope=10, n_hit=1)]
        raise RuntimeError("neo4j went away")

    monkeypatch.setattr(main_module, "run", fake_run)
    response = http.post("/measure", json=BODY)
    names = [name for name, _ in events(response)]
    assert names == ["start", "point", "error"]
    assert "neo4j went away" in dict(events(response))["error"]["message"]


def test_a_failure_before_the_first_event_still_reports(client, monkeypatch):
    """The regression that shipped as a silent dead stream: `select()` raising (Neo4j
    down at run start) escaped the generator after the 200 header, so the browser saw
    a network error instead of the cause."""
    http, main_module = client
    monkeypatch.setattr(
        main_module, "select", _raise(RuntimeError("ServiceUnavailable: no route"))
    )

    response = http.post("/measure", json=BODY)
    assert response.status_code == 200  # headers are long gone by then, by design
    names = [name for name, _ in events(response)]
    assert names == ["error"]
    assert "no route" in dict(events(response))["error"]["message"]


def test_every_run_leaves_a_query_log_row(client, monkeypatch):
    http, main_module = client

    def fake_run(specs, options, chosen=None):
        yield [Point(treebank="SUD_Wolof-WTB", language="Wolof", n_scope=50, n_hit=5)]

    monkeypatch.setattr(main_module, "run", fake_run)
    http.post("/measure", json=BODY)

    from grugrutyp.querylog import get_log

    rows = get_log().recent(limit=5)
    assert rows and rows[0]["kind"] == "measure"
    assert "1=subj" in rows[0]["query"] and rows[0]["error"] == ""


def test_an_invalid_query_is_refused_before_streaming(client):
    http, _ = client
    bad = {"scheme": "SUD", "x": {"scope": "pattern { GOV -[1=subj]-> DEP }",
                                  "response": "with { GOV << NOPE }"}}
    response = http.post("/measure", json=bad)
    assert response.status_code == 422
    assert "NOPE" in json.dumps(response.json())


def test_the_query_text_is_capped(client):
    http, _ = client
    huge = {"scheme": "SUD", "x": {"scope": "pattern { X [upos=VERB] }" + " " * 20_000}}
    assert http.post("/measure", json=huge).status_code == 422


# --------------------------------------------------------------------------- helpers
#
# `run` and `select` are imported into main's namespace, so that is where they must be
# replaced -- patching runner.run would leave main holding the original reference.


def _raise(exc):
    def boom(*args, **kwargs):
        raise exc

    return boom
