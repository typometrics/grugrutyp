#!/usr/bin/env python3
"""Nightly backup of grugrutyp's irreplaceable state (audit 2026-09-02, §3).

Irreplaceable means: not reconstructible from git or a re-import. That is exactly
three files — `users.sqlite` (accounts, saved queries, admin/LLM flags),
`querylog.sqlite` (the operational history), and `data/MANIFEST.json` (what the
current import was built from). The measures cache and the Neo4j store are expensive
but reconstructible; the TSVs live in git.

SQLite files are snapshotted with the backup API (consistent even mid-write under
WAL), then everything is gzipped into a dated directory; generations older than
KEEP_DAYS are pruned.

Run by /etc/cron.d/grugrutyp-backup. The whole box is one RAID array, so the local
generations protect against deletion and corruption, not disk loss; the off-box leg
mirrors them to calcul (Kim's storage convention: everything under /bigstorage/kim)
and engages by itself once the public half of /root/.ssh/id_ed25519_grugrutyp_backup
is authorised for kim@calcul — until then the rsync is skipped with a log line, never
an error.
"""

from __future__ import annotations

import gzip
import shutil
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKUP_ROOT = Path("/var/backups/grugrutyp")
KEEP_DAYS = 14

REMOTE = "kim@calcul-kimgerdes.lisn.upsaclay.fr"
REMOTE_PATH = "/bigstorage/kim/backups/elizia/grugrutyp/"
SSH_KEY = Path("/root/.ssh/id_ed25519_grugrutyp_backup")


def push_offbox() -> None:
    """Mirror the local generations to calcul (pruning included, via --delete)."""
    ssh = f"ssh -i {SSH_KEY} -o BatchMode=yes -o ConnectTimeout=10"
    probe = subprocess.run(
        [*ssh.split(), REMOTE, f"mkdir -p {REMOTE_PATH}"],
        capture_output=True, text=True, timeout=30,
    )
    if probe.returncode != 0:
        print(f"off-box skipped (key not authorised on calcul yet?): {probe.stderr.strip()}")
        return
    sync = subprocess.run(
        ["rsync", "-a", "--delete", "-e", ssh, f"{BACKUP_ROOT}/", f"{REMOTE}:{REMOTE_PATH}"],
        capture_output=True, text=True, timeout=300,
    )
    if sync.returncode != 0:
        print(f"off-box rsync FAILED: {sync.stderr.strip()}", file=sys.stderr)
    else:
        print(f"off-box: mirrored to {REMOTE}:{REMOTE_PATH}")

SQLITE_FILES = [
    REPO / "data" / "cache" / "users.sqlite",
    REPO / "data" / "cache" / "querylog.sqlite",
]
PLAIN_FILES = [REPO / "data" / "MANIFEST.json"]


def snapshot_sqlite(source: Path, target: Path) -> None:
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)


def main() -> int:
    today = BACKUP_ROOT / date.today().isoformat()
    today.mkdir(parents=True, exist_ok=True)
    for path in SQLITE_FILES:
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            continue
        raw = today / path.name
        snapshot_sqlite(path, raw)
        with open(raw, "rb") as fin, gzip.open(f"{raw}.gz", "wb") as fout:
            shutil.copyfileobj(fin, fout)
        raw.unlink()
    for path in PLAIN_FILES:
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            continue
        with open(path, "rb") as fin, gzip.open(today / f"{path.name}.gz", "wb") as fout:
            shutil.copyfileobj(fin, fout)

    cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
    for generation in BACKUP_ROOT.iterdir():
        if not generation.is_dir():
            continue
        try:
            stamp = datetime.fromisoformat(generation.name)
        except ValueError:
            continue
        if stamp < cutoff:
            shutil.rmtree(generation)

    kept = sorted(g.name for g in BACKUP_ROOT.iterdir() if g.is_dir())
    print(f"{date.today().isoformat()}: backed up to {today}; generations: {len(kept)}")
    push_offbox()
    return 0


if __name__ == "__main__":
    sys.exit(main())
