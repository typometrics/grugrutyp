#!/usr/bin/env python3
"""Backfill Menzerath features onto every Word of the current import.

    setsid nohup .venv/bin/python scripts/backfill_menzerath.py \
        > logs/menzerath.log 2>&1 < /dev/null &

Writes `subtree_size`, `n_children`, `n_left`, `n_right` (see `docs/menzerath.md`) onto
each Word, recomputed from the sentence's conllu stored in the database -- the same
`menzerath_features` the importer now runs, so a backfilled treebank and a freshly
imported one are byte-identical. No re-download, no re-import.

Deliberately does NOT touch `imported_at`: no count changes, so every cached measure
stays valid. Resumable via `logs/menzerath_backfill.json`, plus a one-word probe so a
treebank imported after the importer change (or already backfilled) is skipped without
scanning it. Smallest treebank first, like the runner: the long tail of small treebanks
completes early and a crash near the end loses only giants that a resume redoes.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from grugrutyp.conllu import menzerath_features, sentence_from_conllu  # noqa: E402

MANIFEST = ROOT / "logs" / "menzerath_backfill.json"
BATCH_SENTENCES = 400
TX_TIMEOUT = 1800  # like the importer: property writes under API load take what they take
MAX_ATTEMPTS = 3

# The words are reached through their sentence (sentence_unique seeks on (treebank,
# sent_id)), not through the 9.3 GB word_unique index -- the same lesson as the
# importer's deletes: per-word index seeks against a cold index are the slow shape.
WRITE_BATCH = """
UNWIND $rows AS row
MATCH (w:Word {treebank: $tb})-[:IN_SENTENCE]->(s:Sentence {treebank: $tb, sent_id: row.sid})
SET w += coalesce(row.feats[toString(w.idx)], {})
"""


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def load_manifest() -> set[str]:
    if MANIFEST.exists():
        return set(json.loads(MANIFEST.read_text()).get("done", []))
    return set()


def mark_done(done: set[str]) -> None:
    MANIFEST.write_text(json.dumps({"done": sorted(done)}, indent=1))


def already_filled(session, name: str, probe_sent_id: str) -> bool:
    """One indexed point-lookup: does word 1 of the first sentence carry the property?"""
    row = session.run(
        "MATCH (w:Word {treebank: $tb, sent_id: $sid, idx: 1}) RETURN w.subtree_size AS s",
        tb=name, sid=probe_sent_id,
    ).single()
    return bool(row) and row["s"] is not None


def backfill_treebank(driver, name: str, force: bool = False) -> tuple[int, int]:
    """Returns (sentences written, words touched -- approximate, from the payloads)."""
    n_sents = n_words = 0
    batch: list[dict] = []

    def flush(write_session) -> None:
        nonlocal batch
        if not batch:
            return
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                with write_session.begin_transaction(timeout=TX_TIMEOUT) as tx:
                    tx.run(WRITE_BATCH, rows=batch, tb=name)
                    tx.commit()
                break
            except Exception:
                if attempt == MAX_ATTEMPTS:
                    raise
                time.sleep(5 * attempt)
        batch = []

    with driver.session() as read_session, driver.session() as write_session:
        stream = read_session.run(
            "MATCH (s:Sentence {treebank: $tb}) RETURN s.sent_id AS sid, s.conllu AS conllu",
            tb=name,
        )
        first = stream.peek()
        if first is None:
            return (0, 0)
        # The probe reads the FIRST sentence, and writes land in stream order --
        # a treebank that died mid-backfill probes as filled while its tail is
        # missing. A retry therefore rewrites in full (SET is idempotent).
        if not force and already_filled(write_session, name, first["sid"]):
            return (-1, 0)  # sentinel: nothing to do
        for record in stream:
            sentence = sentence_from_conllu(record["conllu"])
            if sentence is None:
                continue
            feats = {
                str(idx): values
                for idx, values in menzerath_features(sentence).items()
            }
            batch.append({"sid": record["sid"], "feats": feats})
            n_sents += 1
            n_words += len(feats)
            if len(batch) >= BATCH_SENTENCES:
                flush(write_session)
        flush(write_session)
    return (n_sents, n_words)


def main() -> int:
    load_env(ROOT / ".env")
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )
    with driver.session() as session:
        treebanks = [
            (r["name"], r["n_tokens"])
            for r in session.run(
                "MATCH (t:Treebank) WHERE t.n_sents > 0 "
                "RETURN t.name AS name, t.n_tokens AS n_tokens ORDER BY t.n_tokens"
            )
        ]

    done = load_manifest()
    todo = [(name, n) for name, n in treebanks if name not in done]
    print(f"{len(treebanks)} treebanks, {len(done)} already done, {len(todo)} to go", flush=True)

    started = time.time()
    for position, (name, n_tokens) in enumerate(todo, 1):
        t0 = time.time()
        try:
            n_sents, n_words = backfill_treebank(driver, name, force=True)
        except Exception as exc:  # keep going; the manifest lets a rerun retry it
            print(f"[{position}/{len(todo)}] {name}: FAILED {type(exc).__name__}: {exc}", flush=True)
            continue
        done.add(name)
        mark_done(done)
        note = "already filled" if n_sents < 0 else f"{n_sents} sents, {n_words} words"
        print(
            f"[{position}/{len(todo)}] {name:<40s} {note:>28s} {time.time()-t0:7.1f}s",
            flush=True,
        )

    print(f"\ndone in {(time.time()-started)/60:.1f} min", flush=True)
    driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
