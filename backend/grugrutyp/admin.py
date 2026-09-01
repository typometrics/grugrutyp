"""Admin routes: the language configuration tables and the query log.

Phase 6.2b (`todo.md`): the release-update problem needs **one** authenticated admin, not
a login system. Auth is a bearer token in `.env` (`GRUGRUTYP_ADMIN_TOKEN`), checked with a
constant-time compare; an OAuth admin flag can replace this dependency later without
touching the routes behind it.

Two design rules from `docs/language-config.md` are enforced here rather than trusted to
the UI:

* **Every write is a git commit**, one per change, naming the language and the columns
  that moved. The TSVs are curation; `git log data/meta/languages.tsv` is the revision
  history the Google Sheet used to provide, and better, because it is greppable by
  language.
* **Rows are never deleted.** A language dropped from a release often returns, and
  deleting its row throws away curation for nothing. The API offers upsert only.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from . import langconfig
from .engine.neo4j_engine import load_env
from .langconfig import META_DIR
from .querylog import get_log
from .users import get_users

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# The token lives in `.env`, which is otherwise loaded lazily by the engine on its first
# database call. An admin request must not 503 just because it arrived first.
load_env()

# One lock for both TSVs: edits are rare and human-paced, and interleaved read-modify-
# write on a shared file is the one race worth excluding.
_write_lock = threading.Lock()


def require_admin(
    request: Request,
    authorization: str = Header(default=""),
    x_admin_token: str = Header(default=""),
) -> None:
    """A signed-in account with `is_admin`, or the `.env` token.

    The session path is what Phase 6.3 planned: the account flag replaces the token
    without touching the routes behind it. The token stays as the bootstrap and the
    break-glass -- it is also what grants the *first* account its admin flag.
    """
    try:
        from .auth import current_user  # local import: auth pulls authlib, admin must not require it at import

        user = current_user(request)
        if user and user["is_admin"]:
            return
    except Exception:  # noqa: BLE001 -- no session middleware (tests), no users db, ...
        pass

    expected = os.environ.get("GRUGRUTYP_ADMIN_TOKEN", "")
    if not expected:
        # Configuration problem, not a failed login -- say so instead of 401-ing forever.
        raise HTTPException(
            status_code=503,
            detail={"message": "GRUGRUTYP_ADMIN_TOKEN is not set in .env"},
        )
    supplied = x_admin_token.strip()
    if not supplied and authorization.startswith("Bearer "):
        supplied = authorization[len("Bearer "):].strip()
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail={"message": "bad admin token"})


router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


# ----------------------------------------------------------------------- TSV plumbing


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        if not line.strip():
            continue
        values = line.split("\t")
        values += [""] * (len(headers) - len(values))
        rows.append({h: v.strip() for h, v in zip(headers, values)})
    return headers, rows


def _write_rows(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    lines = ["\t".join(headers)]
    lines.extend("\t".join(row.get(h, "") for h in headers) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _commit(path: Path, message: str) -> str:
    """One commit per change. Returns the error text instead of raising: the file IS
    written at this point, and failing the request over the history entry would make the
    admin re-apply an edit that already took."""
    try:
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "commit", "-m", message, "--", str(path)],
            capture_output=True, text=True, check=True, timeout=30,
        )
        return ""
    except subprocess.CalledProcessError as exc:
        return (exc.stdout or "") + (exc.stderr or "")
    except Exception as exc:  # noqa: BLE001 -- e.g. git missing
        return str(exc)


def _upsert(
    filename: str, key_column: str, key: str, updates: dict[str, str], original_key: str = ""
) -> dict:
    """Update or append one row, commit, reload the caches.

    `original_key` renames a row: the admin confirms an audit rename suggestion and the
    row keeps its curation under the new name.
    """
    path = META_DIR / filename
    with _write_lock:
        headers, rows = _read_rows(path)
        unknown = [column for column in updates if column not in headers]
        if unknown:
            raise HTTPException(
                status_code=422,
                detail={"message": f"unknown column(s) {unknown}; {filename} has {headers}"},
            )

        match_key = original_key or key
        found = next((r for r in rows if r[key_column] == match_key), None)
        changed: list[str] = []
        if found is None:
            found = {h: "" for h in headers}
            found[key_column] = key
            rows.append(found)
            changed.append("new row")
        elif original_key and original_key != key:
            found[key_column] = key
            changed.append(f"renamed from {original_key}")
        for column, value in updates.items():
            if column == key_column:
                continue
            if found.get(column, "") != value:
                changed.append(f"{column} {found.get(column, '') or '∅'}→{value or '∅'}")
                found[column] = value

        if not changed:
            return {"ok": True, "changed": [], "committed": False}

        _write_rows(path, headers, rows)
        commit_error = _commit(path, f"config: {key}: {', '.join(changed)} (admin page)")

    langconfig.reload()
    return {
        "ok": True,
        "changed": changed,
        "committed": not commit_error,
        "commit_error": commit_error,
    }


# ----------------------------------------------------------------------------- routes


@router.get("/config/languages")
def config_languages() -> dict:
    headers, rows = _read_rows(META_DIR / "languages.tsv")
    return {"columns": headers, "rows": rows}


@router.get("/config/appearance")
def config_appearance() -> dict:
    headers, rows = _read_rows(META_DIR / "appearance.tsv")
    return {"columns": headers, "rows": rows}


class LanguageEdit(BaseModel):
    language: str = Field(min_length=1)
    original_language: str = ""  # set when confirming a rename
    group: str | None = None
    genus: str | None = None
    subgenus: str | None = None
    simple_group: str | None = None
    area: str | None = None
    typology: str | None = None
    lcode: str | None = None


@router.put("/config/language")
def put_language(body: LanguageEdit) -> dict:
    updates = {
        column: value
        for column, value in body.model_dump(exclude={"language", "original_language"}).items()
        if value is not None
    }
    return _upsert(
        "languages.tsv", "language", body.language.strip(), updates,
        body.original_language.strip(),
    )


class AppearanceEdit(BaseModel):
    group: str = Field(min_length=1)
    original_group: str = ""
    color: str | None = None
    marker: str | None = None


@router.put("/config/appearance")
def put_appearance(body: AppearanceEdit) -> dict:
    updates = {
        column: value
        for column, value in body.model_dump(exclude={"group", "original_group"}).items()
        if value is not None
    }
    return _upsert(
        "appearance.tsv", "group", body.group.strip(), updates, body.original_group.strip()
    )


@router.get("/queries")
def queries(limit: int = 200, kind: str = "") -> dict:
    log = get_log()
    return {"queries": log.recent(min(max(limit, 1), 1000), kind), "stats": log.stats()}


# ------------------------------------------------------------------------------ users


@router.get("/users")
def users() -> dict:
    """Every account, for the admin's two decisions: who administers, who may spend
    LLM money (the Phase 6.5 allowlist)."""
    return {"users": get_users().list_users()}


class UserFlags(BaseModel):
    id: int
    is_admin: bool | None = None
    llm_allowed: bool | None = None


@router.put("/user")
def put_user(body: UserFlags) -> dict:
    user = get_users().set_flags(body.id, body.is_admin, body.llm_allowed)
    if user is None:
        raise HTTPException(status_code=404, detail={"message": f"no user {body.id}"})
    return {"user": user}
