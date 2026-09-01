"""A log of the queries users actually run, for the admin's eyes.

This exists by decision, not drift: the share link deliberately carries the plot state in
the URL *fragment* so that query text stays out of the web server's logs, and this module
reverses that for the application's own log (Kim, 2026-08-30, Phase 6.2). The terms of
the reversal are part of the design:

* **what is logged**: the query text, its scheme and target, wall-clock seconds, result
  size, and whether it failed -- the material for "what do people try to ask" (which is
  the spec for the plain-text-to-Grew feature) and "which shapes are slow";
* **what is never logged**: IP address, user agent, or anything else that ties a query to
  a person. There is no user column to fill until accounts exist, and adding one then is
  a decision to take then, not a schema slot waiting here;
* **retention**: rows older than `RETENTION_DAYS` are pruned on startup, so the log
  answers "lately", not "ever".

Failures are logged too -- a syntax error a dozen users hit is a UI bug wearing a user's
name -- with the error text in place of a result size.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .meta import DATA_ROOT

DEFAULT_PATH = Path(os.environ.get("GRUGRUTYP_QUERYLOG", DATA_ROOT / "cache" / "querylog.sqlite"))

RETENTION_DAYS = 180

_SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    kind    TEXT NOT NULL,
    scheme  TEXT NOT NULL DEFAULT '',
    target  TEXT NOT NULL DEFAULT '',
    query   TEXT NOT NULL,
    seconds REAL,
    results INTEGER,
    cached  INTEGER,
    error   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS queries_ts ON queries (ts);
"""


class QueryLog:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or DEFAULT_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # One connection per call: a log write happens once per user query, so connection
        # reuse buys nothing, and per-call connections need no thread bookkeeping.
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
        self.prune()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30, isolation_level=None)

    def record(
        self,
        kind: str,
        query: str,
        scheme: str = "",
        target: str = "",
        seconds: float | None = None,
        results: int | None = None,
        cached: int | None = None,
        error: str = "",
    ) -> None:
        """Never raises: a broken log must not break the query it was logging."""
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO queries (ts, kind, scheme, target, query, seconds, results,"
                    " cached, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        kind,
                        scheme,
                        target,
                        query,
                        None if seconds is None else round(seconds, 3),
                        results,
                        cached,
                        error[:500],
                    ),
                )
        except Exception:  # noqa: BLE001 -- see the docstring
            pass

    def recent(self, limit: int = 200, kind: str = "") -> list[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if kind:
                rows = conn.execute(
                    "SELECT * FROM queries WHERE kind = ? ORDER BY id DESC LIMIT ?",
                    (kind, limit),
                )
            else:
                rows = conn.execute("SELECT * FROM queries ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in rows]

    def stats(self) -> dict:
        with self._connect() as conn:
            total, errors = conn.execute(
                "SELECT COUNT(*), SUM(error != '') FROM queries"
            ).fetchone()
            by_kind = dict(conn.execute("SELECT kind, COUNT(*) FROM queries GROUP BY kind"))
        return {"total": total, "errors": errors or 0, "by_kind": by_kind, "path": str(self.path)}

    def prune(self, days: int = RETENTION_DAYS) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        try:
            with self._connect() as conn:
                return conn.execute("DELETE FROM queries WHERE ts < ?", (cutoff,)).rowcount
        except Exception:  # noqa: BLE001
            return 0


_log: QueryLog | None = None
_lock = threading.Lock()


def get_log() -> QueryLog:
    global _log
    with _lock:
        if _log is None:
            _log = QueryLog()
        return _log
