#!/usr/bin/env python3
"""Import CoNLL-U treebanks into Neo4j using the grugrutyp encoding.

Idempotent per treebank: re-importing one treebank deletes and rebuilds only its own
nodes, and never touches any other.

    ./scripts/import_neo4j.py --slice dev
    ./scripts/import_neo4j.py --treebanks SUD_French-GSD UD_French-GSD
    ./scripts/import_neo4j.py --all --jobs 4

See docs/neo4j-encoding.md for the schema and docs/data-intake.md for the pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from neo4j import GraphDatabase  # noqa: E402

from grugrutyp import meta  # noqa: E402
from grugrutyp.conllu import (  # noqa: E402
    RESERVED_WORD_PROPS,
    Sentence,
    decompose_deprel,
    is_projective,
    is_tree,
    read_conllu,
    sample_bucket,
    tree_height,
)

BATCH_SENTENCES = 500


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


# --------------------------------------------------------------------------------------
# Cypher
# --------------------------------------------------------------------------------------

# Delete label by label, straight off the `treebank` index. Driving the deletion from the
# Sentence nodes instead -- one `MATCH (w:Word {treebank, sent_id})` per sentence -- was
# measured at 71s against 2.6s here for SUD_Wolof-WTB, because the per-sentence lookup
# runs 2107 separate index seeks whose results overlap the rows being deleted.
#
# Batched here rather than with `CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 5000 ROWS`,
# which is the obvious way to write it and was the first version. The problem is not the
# batching, it is the timeout: that construct is only legal in an *implicit* transaction,
# and an implicit transaction takes the server's `db.transaction.timeout` (60s, and rightly
# so -- it is what stops a runaway API query). Re-importing a treebank of any size while
# the API is serving reliably exceeded it, and every dev-slice treebank failed its first
# attempt. It looked survivable only because `IN TRANSACTIONS` commits as it goes, so each
# timed-out attempt left less to delete and a retry eventually finished the job.
#
# Driving the loop from Python gives each chunk its own explicit transaction, which *can*
# carry the import timeout. Same index seek, same 5000-row batches, bounded work per
# statement, and a failure means a failure instead of silent partial progress.
DELETE_LABELS = ("Word", "Mwt", "Sentence")
DELETE_CHUNK = """
MATCH (n:{label} {{treebank: $tb}})
WITH n LIMIT $limit
DETACH DELETE n
RETURN count(*) AS n
"""
DELETE_CHUNK_ROWS = 5000

# One statement per batch: the whole sentence -- words, deps, successors, mwts -- is built
# in a single round trip, resolving `idx -> node` with a list scan over the sentence's own
# nodes. Measured at 5.9s for SUD_Wolof-WTB (44k tokens), i.e. ~7.5k tokens/s.
#
# The list scan looks quadratic and wrong. It is not: sentences average ~21 words, so each
# scan is over a 21-element list, and there is no APOC-free way to build a dynamic
# idx -> node map in Cypher anyway.
WRITE_BATCH = """
UNWIND $sentences AS sent
CREATE (s:Sentence)
SET s = sent.props
WITH s, sent
MATCH (t:Treebank {name: $tb, version: $version})
CREATE (s)-[:IN_TREEBANK]->(t)
WITH s, sent

CALL (s, sent) {
    UNWIND sent.words AS w
    CREATE (n:Word)
    SET n = w.props
    CREATE (n)-[:IN_SENTENCE]->(s)
    WITH n, w
    FOREACH (_ IN CASE WHEN w.is_root THEN [1] ELSE [] END | SET n:Root)
    RETURN collect({idx: w.props.idx, node: n}) AS nodes
}

CALL (nodes, sent) {
    UNWIND sent.deps AS d
    WITH nodes, d,
         [x IN nodes WHERE x.idx = d.head | x.node][0] AS gov,
         [x IN nodes WHERE x.idx = d.dep  | x.node][0] AS dep
    WHERE gov IS NOT NULL AND dep IS NOT NULL
    CREATE (gov)-[r:DEPREL]->(dep)
    SET r = d.props
    RETURN count(*) AS n_deps
}

CALL (nodes, sent) {
    UNWIND sent.succ AS p
    WITH nodes, p,
         [x IN nodes WHERE x.idx = p[0] | x.node][0] AS a,
         [x IN nodes WHERE x.idx = p[1] | x.node][0] AS b
    WHERE a IS NOT NULL AND b IS NOT NULL
    CREATE (a)-[:SUCCESSOR]->(b)
    RETURN count(*) AS n_succ
}

CALL (nodes, sent) {
    UNWIND sent.mwts AS m
    CREATE (mw:Mwt)
    SET mw = m.props
    WITH mw, m, nodes
    UNWIND range(m.props.from, m.props.to) AS i
    WITH mw, [x IN nodes WHERE x.idx = i | x.node][0] AS w
    WHERE w IS NOT NULL
    CREATE (mw)-[:MWT]->(w)
    RETURN count(*) AS n_mwt
}

RETURN count(*) AS n
"""

UPSERT_TREEBANK = """
MERGE (t:Treebank {name: $name, version: $version})
SET t.scheme = $scheme, t.language = $language, t.corpus = $corpus,
    t.family = $family, t.n_sents = $n_sents, t.n_tokens = $n_tokens,
    t.imported_at = $imported_at
"""


# --------------------------------------------------------------------------------------
# Sentence -> parameter dict
# --------------------------------------------------------------------------------------


def sentence_payload(sentence: Sentence, treebank_name: str) -> dict:
    sent_props = {
        "treebank": treebank_name,
        "sent_id": sentence.sent_id,
        "text": sentence.text,
        "conllu": sentence.conllu,
        "n_tokens": sentence.n_tokens,
        "height": tree_height(sentence),
        "is_tree": is_tree(sentence),
        "is_projective": is_projective(sentence),
        # Reproducible sub-corpus sampling; see docs/sampling.md.
        "bucket": sample_bucket(sentence.sent_id),
    }

    # Grew materialises a per-sentence virtual root node `__0__` at position 0, and the
    # root dependency is a real edge from it. Verified by inspecting a grewpy Graph:
    #   {"nodes": {"0": {"form": "__0__"}, "1": {...}}}
    # Without it our counts are short by exactly one node and one edge per sentence, and
    # every query a user copies from grew-match would give a different answer here.
    # It is deliberately NOT linked by SUCCESSOR: it is not part of the word order.
    words: list[dict] = [
        {
            "props": {
                "treebank": treebank_name,
                "sent_id": sentence.sent_id,
                "idx": 0,
                "form": "__0__",
            },
            "is_root": False,
        }
    ]
    deps: list[dict] = []
    succ: list[list[int]] = []

    for word in sentence.words:
        props = {
            "treebank": treebank_name,
            "sent_id": sentence.sent_id,
            "idx": word.idx,
            "form": word.form,
        }
        if word.lemma is not None:
            props["lemma"] = word.lemma
        if word.upos is not None:
            props["upos"] = word.upos
        if word.xpos is not None:
            props["xpos"] = word.xpos
        # FEATS and MISC are flattened onto the node -- that is what makes
        # `X [Number=Sing]` a plain property lookup. Reserved names are prefixed rather
        # than dropped, so no annotation is silently lost.
        for source in (word.feats, word.misc):
            for key, value in source.items():
                props[f"misc_{key}" if key in RESERVED_WORD_PROPS else key] = value

        words.append({"props": props, "is_root": word.head == 0})

        edge = decompose_deprel(word.deprel)
        if edge:
            deps.append({"head": word.head, "dep": word.idx, "props": edge})

    for a, b in zip(sentence.words, sentence.words[1:]):
        succ.append([a.idx, b.idx])

    mwts = [
        {
            "props": {
                "treebank": treebank_name,
                "sent_id": sentence.sent_id,
                "form": mwt.form,
                "from": mwt.start,
                "to": mwt.end,
            }
        }
        for mwt in sentence.mwts
    ]

    return {"props": sent_props, "words": words, "deps": deps, "succ": succ, "mwts": mwts}


# --------------------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------------------


# The container runs with `db.transaction.timeout=60s`, which is right for the API -- a
# runaway user query should die. Import statements are a different kind of work: a delete
# over a 200k-token treebank legitimately takes minutes, and more so while the API is
# serving queries against the same database. Import sessions therefore raise the ceiling
# for themselves rather than the server raising it for everybody.
IMPORT_TX_TIMEOUT = 1800  # seconds

# A timeout under contention is transient by definition: the same statement succeeds when
# the load drops. Retrying the whole treebank is safe because the import is
# delete-then-insert and therefore idempotent.
MAX_ATTEMPTS = 3


def _session(driver):
    return driver.session(default_access_mode="WRITE")


def _run(session, statement: str, **params):
    """One statement in its own explicit transaction, with the import timeout.

    **Not for the DELETE statements.** They use `CALL { … } IN TRANSACTIONS`, which Neo4j
    only accepts in an implicit (auto-commit) transaction -- wrapping them here fails with
    `TransactionStartFailed`. They do not need the raised timeout anyway: that construct
    commits every 5000 rows, so no single transaction is long-lived. It is only the write
    batch that runs as one transaction and can exceed the server's 60s ceiling.
    """
    tx = session.begin_transaction(timeout=IMPORT_TX_TIMEOUT)
    try:
        result = tx.run(statement, **params)
        summary = result.consume()
        tx.commit()
        return summary
    except Exception:
        tx.close()
        raise


def _delete_treebank(session, name: str) -> int:
    """Remove a treebank's nodes, one bounded transaction at a time.

    Each chunk is its own explicit transaction with the import timeout, so a large
    treebank cannot trip the server's 60s ceiling however long the whole deletion takes.
    """
    removed = 0
    for label in DELETE_LABELS:
        statement = DELETE_CHUNK.format(label=label)
        while True:
            summary = _run(session, statement, tb=name, limit=DELETE_CHUNK_ROWS)
            deleted = summary.counters.nodes_deleted
            removed += deleted
            if deleted < DELETE_CHUNK_ROWS:
                break
    return removed


def import_treebank(driver, treebank: meta.Treebank, version: str) -> dict:
    """Import one treebank, retrying on a transient failure.

    Leaves the treebank's `n_sents` at 0 until the rebuild finishes, which is what keeps a
    half-imported treebank out of every query -- see `Neo4jEngine.treebanks`. A crash mid
    import therefore fails safe: the treebank disappears from the site until it is
    re-imported, rather than serving partial counts.
    """
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _import_once(driver, treebank, version)
        except Exception as exc:  # noqa: BLE001 -- retried, then reported and skipped
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                delay = 30 * attempt
                print(
                    f"  {treebank.name}: attempt {attempt} failed ({type(exc).__name__}), "
                    f"retrying in {delay}s",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(delay)
    raise last_error  # type: ignore[misc]


def _import_once(driver, treebank: meta.Treebank, version: str) -> dict:
    started = time.time()
    name = treebank.name

    with _session(driver) as session:
        _delete_treebank(session, name)
        _run(
            session,
            UPSERT_TREEBANK,
            name=name,
            version=version,
            scheme=treebank.scheme,
            language=treebank.language,
            corpus=treebank.corpus,
            family=treebank.family,
            n_sents=0,
            n_tokens=0,
            imported_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )

        n_sents = n_tokens = 0
        batch: list[dict] = []

        def flush() -> None:
            if batch:
                _run(session, WRITE_BATCH, sentences=batch, tb=name, version=version)
                batch.clear()

        for conllu_file in treebank.conllu_files():
            for sentence in read_conllu(conllu_file):
                batch.append(sentence_payload(sentence, name))
                n_sents += 1
                n_tokens += sentence.n_tokens
                if len(batch) >= BATCH_SENTENCES:
                    flush()
        flush()

        _run(
            session,
            UPSERT_TREEBANK,
            name=name,
            version=version,
            scheme=treebank.scheme,
            language=treebank.language,
            corpus=treebank.corpus,
            family=treebank.family,
            n_sents=n_sents,
            n_tokens=n_tokens,
            imported_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )

    return {
        "treebank": name,
        "scheme": treebank.scheme,
        "language": treebank.language,
        "family": treebank.family,
        "n_sents": n_sents,
        "n_tokens": n_tokens,
        "seconds": round(time.time() - started, 1),
    }


def apply_schema(driver) -> None:
    statements = (ROOT / "scripts" / "schema.cypher").read_text()
    with driver.session() as session:
        for statement in statements.split(";"):
            body = "\n".join(
                line for line in statement.splitlines() if not line.strip().startswith("//")
            ).strip()
            if body:
                session.run(body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--treebanks", nargs="+", help="explicit treebank names")
    parser.add_argument("--slice", dest="slice_name", choices=["dev"], help="a named subset")
    parser.add_argument("--all", action="store_true", help="every treebank on disk")
    parser.add_argument("--scheme", choices=["UD", "SUD"], help="restrict to one scheme")
    parser.add_argument("--version", default=meta.CORPUS_VERSION)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="refuse to run while any language lacks a family in languageGroups.tsv",
    )
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument(
        "--skip-imported-since",
        metavar="TIMESTAMP",
        help=(
            "skip treebanks whose Treebank node reports imported_at >= TIMESTAMP "
            "(ISO, e.g. 2026-08-29T02:00:00). Resumes a full import after a crash without "
            "redoing what already landed"
        ),
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="report a treebank that fails all its attempts and carry on to the next",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )

    apply_schema(driver)
    if args.schema_only:
        print("schema applied")
        return 0

    if not (args.treebanks or args.slice_name or args.all):
        parser.error("one of --treebanks / --slice / --all is required")

    missing = meta.missing_families(args.version)
    if missing:
        print(
            f"WARNING: {len(missing)} languages have no entry in languageGroups.tsv and "
            f"will plot as '{meta.UNKNOWN_FAMILY}':\n  " + ", ".join(missing),
            file=sys.stderr,
        )
        if args.strict:
            print("refusing to import under --strict", file=sys.stderr)
            return 1

    chosen = meta.resolve(
        names=args.treebanks,
        slice_name=args.slice_name,
        scheme=args.scheme,
        version=args.version,
    )
    if args.skip_imported_since:
        # `n_sents > 0` matters as much as the timestamp: the importer zeroes it before
        # deleting, so a treebank interrupted mid-rebuild carries a fresh imported_at and
        # no data. Skipping on the timestamp alone would leave it permanently empty.
        with driver.session() as session:
            done = {
                row["name"]
                for row in session.run(
                    "MATCH (t:Treebank) WHERE t.version = $v AND t.n_sents > 0 "
                    "AND t.imported_at >= $since RETURN t.name AS name",
                    v=args.version,
                    since=args.skip_imported_since,
                )
            }
        before = len(chosen)
        chosen = [tb for tb in chosen if tb.name not in done]
        print(f"skipping {before - len(chosen)} treebanks imported since {args.skip_imported_since}")

    print(f"importing {len(chosen)} treebanks (v{args.version})")

    manifest_path = ROOT / "data" / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    failed: list[str] = []
    for position, treebank in enumerate(chosen, 1):
        try:
            stats = import_treebank(driver, treebank, args.version)
        except Exception as exc:  # noqa: BLE001
            failed.append(treebank.name)
            print(f"[{position:>3}/{len(chosen)}] {treebank.name:<40} FAILED: {exc}",
                  file=sys.stderr, flush=True)
            if not args.keep_going:
                raise
            continue
        manifest.setdefault(args.version, {})[treebank.name] = stats
        print(
            f"[{position:>3}/{len(chosen)}] {stats['treebank']:<40} "
            f"{stats['n_sents']:>7} sents {stats['n_tokens']:>9} tokens "
            f"{stats['seconds']:>7}s",
            flush=True,
        )
        # Written as we go, not at the end: a six-hour import that crashes at treebank 600
        # must not also lose the record of the first 599.
        if position % 25 == 0:
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    if failed:
        print(f"\n{len(failed)} treebanks failed: " + ", ".join(failed), file=sys.stderr)
    driver.close()
    print(f"\nmanifest written to {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
