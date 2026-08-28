"""grugrutyp API.

Phase 2 of plan.md: pick a treebank, write a Grew request, get the matching sentences back
as dependency trees. The `universal.grew.fr`-shaped tool from ideas.md, and the debugging
instrument for every measure built on top of it.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .engine.neo4j_engine import get_engine
from .translate.cypher import UnsupportedConstruct, translate
from .translate.parser import GrewSyntaxError, parse

app = FastAPI(
    title="grugrutyp",
    description="Grew queries over UD/SUD treebanks, backed by Neo4j",
    version="0.1.0",
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


class SearchRequest(BaseModel):
    treebank: str
    request: str = Field(description="a Grew request, e.g. pattern { X -[subj]-> Y }")
    limit: int = Field(default=20, ge=1, le=MAX_LIMIT)
    skip: int = Field(default=0, ge=0)


class ValidateRequest(BaseModel):
    request: str


def _translation_error(exc: Exception) -> HTTPException:
    if isinstance(exc, GrewSyntaxError):
        return HTTPException(status_code=422, detail={"kind": "syntax", **exc.as_dict()})
    if isinstance(exc, UnsupportedConstruct):
        return HTTPException(
            status_code=422, detail={"kind": "unsupported", "message": str(exc)}
        )
    return HTTPException(status_code=500, detail={"kind": "internal", "message": str(exc)})


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/treebanks")
def treebanks() -> dict:
    engine = get_engine()
    items = [tb.__dict__ for tb in engine.treebanks()]
    return {"treebanks": items, "count": len(items)}


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


@app.post("/search")
def search(body: SearchRequest) -> dict:
    engine = get_engine()
    try:
        total = engine.count(body.treebank, body.request)
        matches, node_vars = engine.search(
            body.treebank, body.request, limit=body.limit, skip=body.skip
        )
    except (GrewSyntaxError, UnsupportedConstruct) as exc:
        raise _translation_error(exc) from exc

    return {
        "total": total,
        "skip": body.skip,
        "limit": body.limit,
        "nodes": node_vars,
        "hits": [
            {
                "sent_id": match.sent_id,
                "conllu": match.conllu,
                "matched_nodes": match.matched_nodes,
            }
            for match in matches
        ],
    }
