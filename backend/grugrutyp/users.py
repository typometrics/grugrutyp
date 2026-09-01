"""Accounts: who is signed in, what they saved, and what they may spend.

Phase 6.3 (`todo.md`). Three OAuth providers -- Google, GitHub, ORCID -- and **no
password accounts, ever**: grugrutyp must not hold credentials. A user row is the
identity a provider vouched for, plus the two flags the rest of the system reads:

* `is_admin` -- replaces the `.env` token for the admin routes once real accounts exist
  (the token keeps working as a fallback; see `admin.py`);
* `llm_allowed` -- the allowlist for the plain-text-to-Grew feature (Phase 6.5), the one
  feature that spends money per use. Off by default; an admin turns it on per person.

Saved queries are a name plus the share-link payload -- the same base64 state a copied
link carries, stored opaque. The link format is already the complete, versioned
serialisation of a plot; inventing a second format here would mean two of them.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .meta import DATA_ROOT

DEFAULT_PATH = Path(os.environ.get("GRUGRUTYP_USERS", DATA_ROOT / "cache" / "users.sqlite"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    provider    TEXT NOT NULL,
    subject     TEXT NOT NULL,          -- the provider's stable id (sub / id / ORCID iD)
    name        TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL DEFAULT '',
    avatar      TEXT NOT NULL DEFAULT '',   -- profile-picture URL; ORCID has none
    created_at  TEXT NOT NULL,
    last_login  TEXT NOT NULL,
    is_admin    INTEGER NOT NULL DEFAULT 0,
    llm_allowed INTEGER NOT NULL DEFAULT 0,
    UNIQUE (provider, subject)
);
CREATE TABLE IF NOT EXISTS saved_queries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    name       TEXT NOT NULL,
    payload    TEXT NOT NULL,           -- the share-link state, opaque base64
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS saved_queries_user ON saved_queries (user_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_dict(row: sqlite3.Row) -> dict:
    out = dict(row)
    for flag in ("is_admin", "llm_allowed"):
        if flag in out:
            out[flag] = bool(out[flag])
    return out


class UserStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or DEFAULT_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            # Migration for stores created before the avatar column (2026-09-01, same
            # day -- but the production db already existed). ADD COLUMN is the whole
            # sqlite migration story, and failing because it is already there is fine.
            try:
                conn.execute("ALTER TABLE users ADD COLUMN avatar TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError:
                pass

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------------ users

    def login(
        self, provider: str, subject: str, name: str = "", email: str = "", avatar: str = ""
    ) -> dict:
        """The row for this identity, created on first sight, freshened on every login.

        Name, email and avatar are updated from the provider each time -- people rename
        themselves, and a stale name on the admin page misleads exactly the person
        deciding who gets the LLM allowlist.
        """
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO users (provider, subject, name, email, avatar, created_at, last_login)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (provider, subject) DO UPDATE SET"
                "   name = excluded.name, email = excluded.email, avatar = excluded.avatar,"
                "   last_login = excluded.last_login",
                (provider, subject, name or "", email or "", avatar or "", now, now),
            )
            row = conn.execute(
                "SELECT * FROM users WHERE provider = ? AND subject = ?", (provider, subject)
            ).fetchone()
        return _row_dict(row)

    def get(self, user_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_dict(row) if row else None

    def list_users(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY last_login DESC").fetchall()
        return [_row_dict(row) for row in rows]

    def set_flags(
        self, user_id: int, is_admin: bool | None = None, llm_allowed: bool | None = None
    ) -> dict | None:
        with self._connect() as conn:
            if is_admin is not None:
                conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (int(is_admin), user_id))
            if llm_allowed is not None:
                conn.execute(
                    "UPDATE users SET llm_allowed = ? WHERE id = ?", (int(llm_allowed), user_id)
                )
        return self.get(user_id)

    # ---------------------------------------------------------------- saved queries

    def queries(self, user_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, payload, created_at FROM saved_queries"
                " WHERE user_id = ? ORDER BY id DESC",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_query(self, user_id: int, name: str, payload: str) -> dict:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO saved_queries (user_id, name, payload, created_at)"
                " VALUES (?, ?, ?, ?)",
                (user_id, name, payload, _now()),
            )
            row = conn.execute(
                "SELECT id, name, payload, created_at FROM saved_queries WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return dict(row)

    def delete_query(self, user_id: int, query_id: int) -> bool:
        """Scoped to the owner: the id alone must not let one user delete another's."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM saved_queries WHERE id = ? AND user_id = ?", (query_id, user_id)
            )
            return cursor.rowcount > 0


_store: UserStore | None = None
_lock = threading.Lock()


def get_users() -> UserStore:
    global _store
    with _lock:
        if _store is None:
            _store = UserStore()
        return _store
