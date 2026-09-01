"""grugrutyp API.

Phase 2: pick a treebank, write a Grew request, get the matching sentences back as
dependency trees -- the `universal.grew.fr`-shaped tool from ideas.md, and the debugging
instrument for everything above it.

Phase 3: a **scope S** and a **response pattern Q** become a typological variable
`100 * #(S and Q) / #(S)` per language, streamed as it is computed, and plotted.
"""

from __future__ import annotations

import json
from typing import Iterator

import os
import secrets
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import langconfig, nl2grew, presets
from .admin import router as admin_router
from .auth import PUBLIC_BASE, require_user, router as auth_router
from .cache import get_cache
from .querylog import get_log
from .users import get_users
from .engine.neo4j_engine import get_engine
from .aggregate import DEFAULT_AGGREGATION, InvalidExpression
from .measure import (
    DEFAULT_CI_TOLERANCE,
    DEFAULT_MIN_SCOPE,
    DEFAULT_TOKEN_BUDGET,
    MeasureSpec,
    Point,
    SamplingPolicy,
    merge_by_language,
)
from .meta import CORPUS_VERSION
from .runner import RunOptions, run, select
from .translate.cypher import UnsupportedConstruct, translate
from .translate.parser import GrewSyntaxError, parse

app = FastAPI(
    title="grugrutyp",
    description="Grew queries over UD/SUD treebanks, backed by Neo4j",
    version="0.1.0",
)

app.include_router(admin_router)
app.include_router(auth_router)

# The signed session cookie carries only the user id (`auth.py`). An unset secret gets an
# ephemeral one so the app still boots -- sessions then die with each restart, which is a
# misconfiguration made visible rather than a crash at import time.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("GRUGRUTYP_SESSION_SECRET") or secrets.token_hex(32),
    session_cookie="grugrutyp_session",
    max_age=30 * 24 * 3600,
    same_site="lax",  # lax, not strict: the OAuth callback is a top-level redirect
    https_only=PUBLIC_BASE.startswith("https"),
)

# The SPA is served from the same origin in production (/grugrutyp/), so CORS only
# matters for `quasar dev` on localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:9000", "http://127.0.0.1:9000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_LIMIT = 100


class ClusterSpec(BaseModel):
    kind: str = Field(pattern="^(key|whether)$")
    value: str


class SearchRequest(BaseModel):
    # Either one treebank or an explicit list -- a whole language is just the list of its
    # treebanks, which the client resolves; the API stays ignorant of language groupings.
    treebank: str = ""
    treebanks: list[str] | None = None
    request: str = Field(description="a Grew request, e.g. pattern { X -[subj]-> Y }")
    limit: int = Field(default=20, ge=1, le=MAX_LIMIT)
    skip: int = Field(default=0, ge=0)
    # grew.fr's "sentences order": corpus order, shortest first, or a deterministic
    # hash-shuffle (reproducible, pageable).
    order: str = Field(default="initial", pattern="^(initial|length|shuffle)$")
    # grew.fr's clustering model: up to two clusterings, each a `key` (X.upos, e.label)
    # or a `whether` (a with/without condition partitioning matchings into yes/no).
    # When any is set the response is a table (one clustering) or a grid (two) of
    # counts instead of a page of trees. `cluster` is the single-key shorthand.
    clusters: list[ClusterSpec] | None = None
    cluster: str = ""

    def cluster_specs(self) -> list[dict]:
        if self.clusters:
            return [
                {"kind": spec.kind, "value": spec.value.strip()}
                for spec in self.clusters[:2]
                if spec.value.strip()
            ]
        if self.cluster.strip():
            return [{"kind": "key", "value": self.cluster.strip()}]
        return []

    def names(self) -> list[str]:
        # Sorted for stable pagination: page 2 must walk the treebanks in the same order
        # page 1 did, whatever order the client sent them in.
        chosen = self.treebanks if self.treebanks else [self.treebank]
        return sorted({name for name in chosen if name})


class ValidateRequest(BaseModel):
    request: str


def _translation_error(exc: Exception) -> HTTPException:
    if isinstance(exc, GrewSyntaxError):
        return HTTPException(status_code=422, detail={"kind": "syntax", **exc.as_dict()})
    if isinstance(exc, (UnsupportedConstruct, InvalidExpression)):
        return HTTPException(
            status_code=422, detail={"kind": "unsupported", "message": str(exc)}
        )
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail={"kind": "invalid", "message": str(exc)})
    return HTTPException(status_code=500, detail={"kind": "internal", "message": str(exc)})


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/treebanks")
def treebanks() -> dict:
    engine = get_engine()
    items = [tb.__dict__ for tb in engine.treebanks()]
    return {"treebanks": items, "count": len(items), "version": CORPUS_VERSION}


@app.post("/validate")
def validate(body: ValidateRequest) -> dict:
    """Parse and translate without executing -- powers inline editor feedback."""
    try:
        request = parse(body.request)
        translation = translate(request, treebank="__validation__", mode="count")
    except (GrewSyntaxError, UnsupportedConstruct) as exc:
        error = _translation_error(exc)
        return {"valid": False, "error": error.detail}
    return {
        "valid": True,
        "nodes": translation.node_vars,
        "edges": translation.edge_vars,
        "cypher": translation.cypher,
    }


def _require_treebank(engine, name: str):
    """404 rather than a partial count.

    The importer rebuilds a treebank in place, and a query landing mid-rebuild returns a
    count over however much has been written -- a plausible wrong number, which is the one
    failure mode this whole project is organised against. `treebank()` excludes a treebank
    whose rebuild is in flight.
    """
    info = engine.treebank(name)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail={
                "kind": "unavailable",
                "message": (
                    f"{name} is not available -- it does not exist, or it is being "
                    "re-imported right now. Try again in a minute."
                ),
            },
        )
    return info


@app.post("/search")
def search(body: SearchRequest) -> dict:
    """Timing-and-logging wrapper; the work is in `_search`.

    Logged by decision, not drift (`querylog` module docstring): text, target, seconds
    and outcome -- never who asked. Failures are logged too; a syntax error many users
    hit is a UI bug wearing a user's name.
    """
    started = time.perf_counter()
    try:
        result = _search(body)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        get_log().record(
            kind="search", query=body.request, target=", ".join(body.names())[:200],
            seconds=time.perf_counter() - started,
            error=f"{detail.get('kind', 'error')}: {detail.get('message', '')}",
        )
        raise
    get_log().record(
        kind="search", query=body.request, target=", ".join(body.names())[:200],
        seconds=time.perf_counter() - started, results=result.get("total"),
    )
    return result


def _search(body: SearchRequest) -> dict:
    """Search one treebank, or several as one corpus.

    The page walks the treebanks in sorted order: count each, skip whole treebanks the
    offset steps over, and fill the page across the boundary when it straddles one.
    Every hit names its treebank, because in a whole-language search "which corpus is
    this sentence from" is part of reading the result.
    """
    engine = get_engine()
    names = body.names()
    if not names:
        raise HTTPException(status_code=422, detail={"kind": "invalid", "message": "no treebank given"})
    for name in names:
        _require_treebank(engine, name)

    specs = body.cluster_specs()
    if specs:
        try:
            merged: dict[tuple, int] = {}
            for name in names:
                for combo, count in engine.cluster(name, body.request, specs).items():
                    merged[combo] = merged.get(combo, 0) + count
        except (GrewSyntaxError, UnsupportedConstruct, ValueError) as exc:
            raise _translation_error(exc) from exc

        labels = [
            spec["value"] if spec["kind"] == "key" else f"whether {spec['value']}"
            for spec in specs
        ]
        base = {
            "total": sum(merged.values()),
            "cluster_labels": labels,
            "n_treebanks": len(names),
            "hits": [],
            "nodes": [],
        }
        if len(specs) == 1:
            ordered = sorted(merged.items(), key=lambda kv: (-kv[1], kv[0]))
            return {
                **base,
                "clusters": [{"value": combo[0], "count": n} for combo, n in ordered],
            }
        # Two clusterings: a pivot grid, rows and columns ordered by their totals so the
        # dominant combinations sit in the top-left corner.
        row_totals: dict[str, int] = {}
        col_totals: dict[str, int] = {}
        for (row, col), n in merged.items():
            row_totals[row] = row_totals.get(row, 0) + n
            col_totals[col] = col_totals.get(col, 0) + n
        rows = sorted(row_totals, key=lambda k: (-row_totals[k], k))
        cols = sorted(col_totals, key=lambda k: (-col_totals[k], k))
        return {
            **base,
            "grid": {
                "rows": rows,
                "cols": cols,
                "cells": [[merged.get((row, col), 0) for col in cols] for row in rows],
                "row_totals": [row_totals[row] for row in rows],
                "col_totals": [col_totals[col] for col in cols],
            },
        }

    try:
        total = 0
        remaining_skip = body.skip
        need = body.limit
        node_vars: list[str] = []
        hits = []
        for name in names:
            count = engine.count(name, body.request)
            total += count
            if need <= 0:
                continue
            if remaining_skip >= count:
                remaining_skip -= count
                continue
            matches, node_vars = engine.search(
                name, body.request, limit=need, skip=remaining_skip, order=body.order
            )
            remaining_skip = 0
            need -= len(matches)
            hits.extend(
                {
                    "treebank": name,
                    "sent_id": match.sent_id,
                    "conllu": match.conllu,
                    "matched_nodes": match.matched_nodes,
                }
                for match in matches
            )
        if not node_vars:
            # Page past the last hit, or zero matches: the node list still describes the
            # request, so derive it without touching the database.
            node_vars = translate(parse(body.request), names[0], mode="count").node_vars
    except (GrewSyntaxError, UnsupportedConstruct) as exc:
        raise _translation_error(exc) from exc

    return {
        "total": total,
        "skip": body.skip,
        "limit": body.limit,
        "nodes": node_vars,
        "n_treebanks": len(names),
        "hits": hits,
    }


# --------------------------------------------------------------------------- measures


class AxisSpec(BaseModel):
    scope: str = Field(description="S -- a Grew request with a `pattern` block")
    response: str = Field(default="", description="Q -- `with`/`without` blocks only")
    kind: str = Field(default="ratio", description="ratio | aggregate")
    expression: str = Field(
        default="", description="aggregate kind: delta(GOV, DEP), sentence.height, ..."
    )
    aggregation: str = Field(default=DEFAULT_AGGREGATION, description="avg | sum | min | max")
    label: str = ""

    def to_spec(self) -> MeasureSpec:
        return MeasureSpec(
            scope=self.scope,
            response=self.response,
            kind="aggregate" if self.kind == "aggregate" else "ratio",
            expression=self.expression,
            aggregation=self.aggregation,
            label=self.label,
        )


class MeasureRequest(BaseModel):
    x: AxisSpec
    y: AxisSpec | None = None
    scheme: str = "SUD"
    treebanks: list[str] | None = None
    token_budget: int | None = Field(
        default=DEFAULT_TOKEN_BUDGET,
        description="tokens to scan per language; null or 0 means no sampling at all",
    )
    min_scope: int = Field(default=DEFAULT_MIN_SCOPE, ge=0)
    ci_tolerance: float = Field(default=DEFAULT_CI_TOLERANCE, gt=0)
    use_cache: bool = True

    def specs(self) -> list[MeasureSpec]:
        return [self.x.to_spec()] + ([self.y.to_spec()] if self.y else [])

    def options(self) -> RunOptions:
        return RunOptions(
            scheme=self.scheme,
            treebanks=self.treebanks,
            policy=SamplingPolicy(
                token_budget=self.token_budget or None,
                min_scope=self.min_scope,
                ci_tolerance=self.ci_tolerance,
            ),
            use_cache=self.use_cache,
        )


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@app.post("/measure")
def measure(body: MeasureRequest) -> StreamingResponse:
    """Stream one event per treebank, then the language-level merge.

    Streaming does not reduce the total time at all -- it reduces the time until the plot
    starts filling in, which is the number the user actually experiences. The `done` event
    carries the merge, because merging is by **summing counts** across a language's
    treebanks and cannot be done incrementally without re-sending every language each time.
    """
    specs = body.specs()
    options = body.options()

    # The measure's text for the query log: both axes, scope and response, one blob.
    def axis_text(axis: AxisSpec) -> str:
        parts = [axis.scope.strip()]
        if axis.response.strip():
            parts.append(axis.response.strip())
        if axis.kind == "aggregate":
            parts.append(f"# {axis.aggregation} {axis.expression}".strip())
        return "\n".join(parts)

    query_text = axis_text(body.x) + (f"\n--- y ---\n{axis_text(body.y)}" if body.y else "")

    try:
        for spec in specs:
            spec.validate()
    except (GrewSyntaxError, UnsupportedConstruct, InvalidExpression, ValueError) as exc:
        get_log().record(
            kind="measure", query=query_text, scheme=body.scheme,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise _translation_error(exc) from exc

    def stream() -> Iterator[str]:
        started = time.perf_counter()
        # What the log line will say. Filled in as the run proceeds; written in the
        # `finally` so an abandoned tab still leaves a row (error: client disconnected)
        # rather than a run that never happened.
        outcome = {"results": None, "cached": 0, "error": "client disconnected", "target": ""}
        try:
            chosen = select(options)
            outcome["target"] = (
                f"{len(chosen)} treebanks @ "
                f"{options.policy.token_budget or 'exact'}"
            )
            yield _sse(
                "start",
                {
                    "n_treebanks": len(chosen),
                    "n_tokens": sum(tb.n_tokens for tb in chosen),
                    "axes": len(specs),
                    "token_budget": options.policy.token_budget,
                },
            )

            collected: list[list] = []
            done = 0
            try:
                for points in run(specs, options):
                    collected.append(points)
                    done += 1
                    if points[0].cached:
                        outcome["cached"] += 1
                    yield _sse(
                        "point",
                        {
                            "done": done,
                            "total": len(chosen),
                            "treebank": points[0].treebank,
                            "language": points[0].language,
                            "axes": [point.to_dict() for point in points],
                        },
                    )
            except Exception as exc:  # noqa: BLE001 -- the stream is the only channel left
                outcome["error"] = f"{type(exc).__name__}: {exc}"
                yield _sse("error", {"message": outcome["error"]})
                return

            languages = []
            for axis in range(len(specs)):
                merged = merge_by_language(points[axis] for points in collected)
                languages.append([lp.to_dict() for lp in merged])

            outcome["results"] = len(languages[0]) if languages else 0
            outcome["error"] = ""
            yield _sse(
                "done",
                {
                    "languages": languages,
                    "errors": [
                        {"treebank": p[0].treebank, "error": p[0].error}
                        for p in collected
                        if p[0].error
                    ],
                },
            )
        finally:
            get_log().record(
                kind="measure", query=query_text, scheme=body.scheme,
                target=outcome["target"], seconds=time.perf_counter() - started,
                results=outcome["results"], cached=outcome["cached"],
                error=outcome["error"],
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        # nginx buffers proxied responses by default, which would hold the whole stream
        # back and defeat the point of streaming it.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class PreviewRequest(BaseModel):
    treebank: str
    scope: str
    response: str = ""
    kind: str = "ratio"
    expression: str = ""
    aggregation: str = DEFAULT_AGGREGATION


@app.post("/measure/preview")
def measure_preview(body: PreviewRequest) -> dict:
    """One treebank, exact, no sampling -- the live feedback under the S and Q editors.

    Exact on purpose: a preview exists to tell you whether the scope is what you meant,
    and a sampled count would answer a slightly different question than the one you are
    debugging.
    """
    engine = get_engine()
    _require_treebank(engine, body.treebank)
    spec = MeasureSpec(
        scope=body.scope,
        response=body.response,
        kind="aggregate" if body.kind == "aggregate" else "ratio",
        expression=body.expression,
        aggregation=body.aggregation,
    )
    point = Point(treebank=body.treebank, language="", kind=spec.kind, aggregation=spec.aggregation)
    try:
        spec.validate()
        if spec.kind == "aggregate":
            total, n_scope = engine.aggregate(
                body.treebank, body.scope, body.expression, body.aggregation
            )
            point.n_scope, point.total = n_scope, (None if total is None else float(total))
        else:
            point.n_scope, point.n_hit = engine.count_pair(
                body.treebank, body.scope, body.response
            )
    except (GrewSyntaxError, UnsupportedConstruct, InvalidExpression, ValueError) as exc:
        raise _translation_error(exc) from exc

    return point.to_dict()


# --------------------------------------------------------------- plain text -> Grew


class TranslateRequest(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    scheme: str = "SUD"


@app.post("/llm/translate")
def llm_translate(body: TranslateRequest, request: Request) -> dict:
    """A description in words becomes a validated query pair -- for allowlisted users.

    Triple-gated (account, `llm_allowed`, daily quota) because this is the one endpoint
    that spends money per call. The result is a *proposal for the editors*: nothing is
    computed over the corpus here, and nothing unvalidated is ever returned.
    """
    user = require_user(request)
    if not user["llm_allowed"]:
        raise HTTPException(
            status_code=403,
            detail={"message": "this account is not on the LLM allowlist -- ask the admin"},
        )
    if not nl2grew.configured():
        raise HTTPException(status_code=503, detail={"message": "no LLM API key configured"})
    used = get_users().llm_usage(user["id"])
    if used >= nl2grew.DAILY_QUOTA:
        raise HTTPException(
            status_code=429,
            detail={"message": f"daily limit reached ({nl2grew.DAILY_QUOTA} translations/day)"},
        )

    try:
        result = nl2grew.translate(body.text, body.scheme)
    except Exception as exc:  # noqa: BLE001 -- provider errors become a readable message
        raise HTTPException(
            status_code=502, detail={"message": f"LLM call failed: {type(exc).__name__}: {exc}"}
        ) from exc
    used = get_users().llm_bump(user["id"])
    # Logged like every query -- text, outcome, never who asked (querylog's contract);
    # the per-user accounting lives only in the quota table.
    get_log().record(
        kind="llm", query=body.text, scheme=body.scheme.upper(), target=result.get("model", ""),
        seconds=result.get("seconds"),
        error=result.get("error", "") or result.get("refusal", "") if not result["ok"] else "",
    )
    return {**result, "quota": {"used": used, "limit": nl2grew.DAILY_QUOTA}}


# ----------------------------------------------------------------- presets and config


@app.get("/presets")
def get_presets(scheme: str = "SUD") -> dict:
    """The current site's measures as query pairs -- starting points, not a menu.

    Each carries both the SUD and the UD spelling: `1=subj` and `nsubj` are different
    relations, so a preset that knew only one scheme would silently measure nothing in the
    other.
    """
    return {"scheme": scheme.upper(), "presets": presets.for_scheme(scheme)}


@app.get("/languages")
def languages(view: str = langconfig.DEFAULT_VIEW) -> dict:
    """Every configured language with its label, colour and marker under one view."""
    if view not in langconfig.VIEWS:
        raise HTTPException(status_code=400, detail={"message": f"unknown view: {view}"})
    engine_languages = sorted({tb.language for tb in get_engine().treebanks()})
    items = []
    for name in engine_languages:
        look = langconfig.appearance_of(name, view)
        items.append(
            {"language": name, "label": look.label, "color": look.color, "marker": look.marker}
        )
    return {
        "view": view,
        "views": list(langconfig.VIEWS),
        "languages": items,
        "legend": langconfig.legend(view, engine_languages),
    }


@app.get("/config/audit")
def config_audit() -> dict:
    """What the current release did to the language configuration.

    The front door of the future admin page: an unconfigured language does not raise, it
    plots grey, so the drift has to be asked for rather than waited for.
    """
    return langconfig.audit().to_dict()


@app.get("/cache/stats")
def cache_stats() -> dict:
    return get_cache().stats()
