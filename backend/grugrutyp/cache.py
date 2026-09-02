"""Persistent measure cache.

`docs/sampling.md` section 6 ranks the levers: the cache is the big one. Sampling makes
the *first* run of a measure tolerable; the cache makes every run after it free, and a
typologist re-runs the same measure constantly -- adjusting the other axis, changing the
minimum-occurrence threshold, coming back the next day.

SQLite, one file, WAL. The access pattern is a few hundred point reads and writes per
plot from one process; Postgres would buy contention handling nobody needs yet.

The key is `(treebank, version, revision, query_hash, sample_pct)`, and every part earns
its place:

* `sample_pct` -- asking for an exact number must never be answered from a sampled one.
* `version` -- 2.19 will change the counts, and the old ones must not survive the upgrade
  silently.
* `revision` -- the treebank's `imported_at`. A re-import changes the data without
  changing the release, so without this a corrected treebank would keep serving its old
  numbers forever. It also closes the narrow race where a query lands while the importer
  is deleting a treebank's nodes: whatever that query cached is keyed to the *previous*
  import stamp and is discarded the moment the rebuild finishes.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

from .meta import CORPUS_VERSION, DATA_ROOT

DEFAULT_PATH = Path(os.environ.get("GRUGRUTYP_CACHE", DATA_ROOT / "cache" / "measures.sqlite"))

# The key knows the corpus (version), the import (revision) and the request
# (query_hash) -- it does NOT know the translator. A change to what the emitter
# generates for the same request text leaves stale rows reachable, and they do not look
# stale: they look like counts. After any semantically visible emitter change, purge the
# affected rows by recomputing their query_hash and deleting -- done once for the
# numeric-counter fix, see docs/menzerath.md "The counters as pattern constraints".
SCHEMA = """
CREATE TABLE IF NOT EXISTS counts_v2 (
    treebank    TEXT    NOT NULL,
    version     TEXT    NOT NULL,
    revision    TEXT    NOT NULL,
    query_hash  TEXT    NOT NULL,
    sample_pct  INTEGER NOT NULL,
    n_scope     INTEGER NOT NULL,
    n_hit       REAL    NOT NULL,  -- the numerator: a count, or an aggregate sum
    seconds     REAL    NOT NULL DEFAULT 0,
    computed_at TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (treebank, version, revision, query_hash, sample_pct)
) WITHOUT ROWID;

-- Rows for a superseded import are dead weight, never a wrong answer -- they simply stop
-- being reachable. `prune()` removes them; nothing depends on it running.
CREATE INDEX IF NOT EXISTS counts_v2_revision ON counts_v2 (treebank, revision);

DROP TABLE IF EXISTS counts;
"""


class MeasureCache:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or DEFAULT_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # One connection per thread: the worker pool that fans out over treebanks writes
        # from several at once, and a sqlite3 connection is not shareable across them.
        self._local = threading.local()
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return conn

    def get(
        self,
        treebank: str,
        query_hash: str,
        sample_pct: int,
        version: str = CORPUS_VERSION,
        revision: str = "",
    ) -> tuple[int, int] | None:
        row = self._connect().execute(
            "SELECT n_scope, n_hit FROM counts_v2 "
            "WHERE treebank=? AND version=? AND revision=? AND query_hash=? AND sample_pct=?",
            (treebank, version, revision, query_hash, sample_pct),
        ).fetchone()
        return (row[0], row[1]) if row else None

    def put(
        self,
        treebank: str,
        query_hash: str,
        sample_pct: int,
        n_scope: int,
        n_hit: int,
        seconds: float = 0.0,
        version: str = CORPUS_VERSION,
        revision: str = "",
    ) -> None:
        self._connect().execute(
            "INSERT INTO counts_v2 (treebank, version, revision, query_hash, sample_pct,"
            " n_scope, n_hit, seconds, computed_at)"
            " VALUES (?,?,?,?,?,?,?,?, datetime('now')) "
            "ON CONFLICT(treebank, version, revision, query_hash, sample_pct) DO UPDATE SET "
            "n_scope=excluded.n_scope, n_hit=excluded.n_hit, seconds=excluded.seconds, "
            "computed_at=excluded.computed_at",
            (treebank, version, revision, query_hash, sample_pct, n_scope, n_hit, seconds),
        )

    def invalidate_version(self, version: str) -> int:
        cur = self._connect().execute("DELETE FROM counts_v2 WHERE version=?", (version,))
        return cur.rowcount

    def prune(self, current: dict[str, str]) -> int:
        """Drop rows whose treebank has since been re-imported.

        Purely housekeeping: a superseded row is unreachable, not wrong. `current` maps
        treebank name to its live `imported_at`.
        """
        if not current:
            return 0
        conn = self._connect()
        removed = 0
        for name, revision in current.items():
            cur = conn.execute(
                "DELETE FROM counts_v2 WHERE treebank=? AND revision<>?", (name, revision)
            )
            removed += cur.rowcount
        return removed

    def stats(self) -> dict:
        row = self._connect().execute(
            "SELECT count(*), count(DISTINCT query_hash), sum(seconds) FROM counts_v2"
        ).fetchone()
        return {
            "rows": row[0] or 0,
            "measures": row[1] or 0,
            "seconds_saved": round(row[2] or 0.0, 1),
            "path": str(self.path),
        }


_cache: MeasureCache | None = None


def get_cache() -> MeasureCache:
    global _cache
    if _cache is None:
        _cache = MeasureCache()
    return _cache
