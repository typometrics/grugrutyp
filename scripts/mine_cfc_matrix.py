#!/usr/bin/env python3
"""Tier-1 pattern-mining pass: the full direction/cfc/distance block in one disk scan.

    .venv/bin/python scripts/mine_cfc_matrix.py --scheme SUD            # scan + merge
    .venv/bin/python scripts/mine_cfc_matrix.py --treebank SUD_French-GSD
    .venv/bin/python scripts/mine_cfc_matrix.py --merge-only
    setsid nohup .venv/bin/python scripts/mine_cfc_matrix.py --scheme SUD \
        > logs/mine-cfc.log 2>&1 < /dev/null &

Design: `docs/pattern-mining.md` ch. 2. One read-only aggregation per treebank over all
DEPREL edges, grouped by (gov upos, rel_1, rel_2, dep upos), accumulating the matching
count, the right-branching count, and the signed/absolute idx-delta sums. Everything the
old site's f/positive-direction/posdircfc/cfc/f-dist tables held — exact, at both rel_1
and rel_1:rel_2 granularity — comes out of this one scan by marginalisation.

The dump is COMPLETE: root edges (the virtual `__0__` governor, `docs/neo4j-encoding.md`
§2 dev. 4) are kept and marked with gupos `__0__`, so the dependent-side upos marginal is
the POS distribution and the root exclusion stays an explicit choice at mining time
(`docs/measures-mapping.md` §2 point 1), not something baked into the data.

Discipline (docs/pattern-mining.md ch. 11): refuses to run while an importer is alive; a
read landing mid-rebuild returns a plausible wrong count, not an error. Sequential,
smallest treebank first, resumable: a treebank is re-scanned only when its `imported_at`
changed. Giant treebanks are scanned in sentence-bucket chunks so no single implicit
transaction approaches the server's timeout.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from grugrutyp.engine.neo4j_engine import get_engine  # noqa: E402

MINING_DIR = ROOT / "data" / "mining"
DUMP_DIR = MINING_DIR / "cfc"

# One implicit transaction per statement; the container's db.transaction.timeout is 300 s
# (see the DELETE_CHUNK story in CLAUDE.md). Measured on the first full pass
# (2026-09-05): a cold scan runs at ~2.3k tokens/s -- Spanish-AnCora (560k) took 248 s
# and Icelandic-IcePaHC (985k) blew the timeout. So the single-shot ceiling is 400k
# tokens, everything above goes in sentence-bucket chunks, and a chunk that still times
# out is split in half recursively down to single buckets.
CHUNK_TOKEN_THRESHOLD = 400_000
BUCKETS_PER_CHUNK = 10

SCAN_ALL = """
MATCH (g:Word {treebank: $tb})-[r:DEPREL]->(d:Word)
RETURN CASE WHEN g.idx = 0 THEN '__0__' ELSE coalesce(g.upos, '_') END AS gupos,
       coalesce(r.rel_1, r.deprel) AS rel1,
       coalesce(r.rel_2, '') AS rel2,
       coalesce(d.upos, '_') AS dupos,
       count(*) AS n,
       sum(CASE WHEN g.idx < d.idx THEN 1 ELSE 0 END) AS n_right,
       sum(d.idx - g.idx) AS sum_delta,
       sum(abs(d.idx - g.idx)) AS sum_abs_delta
"""

SCAN_BUCKET_CHUNK = """
MATCH (s:Sentence {treebank: $tb})
WHERE s.bucket >= $lo AND s.bucket < $hi
MATCH (d:Word)-[:IN_SENTENCE]->(s)
MATCH (g:Word)-[r:DEPREL]->(d)
RETURN CASE WHEN g.idx = 0 THEN '__0__' ELSE coalesce(g.upos, '_') END AS gupos,
       coalesce(r.rel_1, r.deprel) AS rel1,
       coalesce(r.rel_2, '') AS rel2,
       coalesce(d.upos, '_') AS dupos,
       count(*) AS n,
       sum(CASE WHEN g.idx < d.idx THEN 1 ELSE 0 END) AS n_right,
       sum(d.idx - g.idx) AS sum_delta,
       sum(abs(d.idx - g.idx)) AS sum_abs_delta
"""


def importer_running() -> bool:
    out = subprocess.run(
        ["pgrep", "-af", "import_neo4j.py"], capture_output=True, text=True
    ).stdout
    return any("import_neo4j.py" in line and "pgrep" not in line for line in out.splitlines())


def dump_path(name: str) -> Path:
    return DUMP_DIR / f"{name}.json"


def _run_rows(driver, query: str, **params) -> list[dict]:
    """One statement, fully materialised: either the complete row list comes back or
    the exception does. Nothing may merge a partial stream -- a timeout mid-iteration
    followed by a retry would silently double-count whatever had already arrived."""
    with driver.session() as session:
        return [row.data() for row in session.run(query, **params)]


def scan_treebank(engine, tb) -> dict:
    """One treebank -> aggregated rows. Chunked by sentence bucket when large; a chunk
    that still hits the server's transaction timeout is split in half, down to single
    buckets."""
    from neo4j.exceptions import ClientError

    acc: dict[tuple, list[int]] = {}

    def merge(rows: list[dict]) -> None:
        for row in rows:
            key = (row["gupos"], row["rel1"], row["rel2"], row["dupos"])
            slot = acc.setdefault(key, [0, 0, 0, 0])
            slot[0] += row["n"]
            slot[1] += row["n_right"]
            slot[2] += row["sum_delta"]
            slot[3] += row["sum_abs_delta"]

    driver = engine._driver
    chunked = tb.n_tokens > CHUNK_TOKEN_THRESHOLD
    if not chunked:
        try:
            merge(_run_rows(driver, SCAN_ALL, tb=tb.name))
        except ClientError:
            print(f"  [timeout] {tb.name}: single-shot -> bucket chunks", flush=True)
            acc.clear()
            chunked = True
    if chunked:
        def scan_range(lo: int, hi: int) -> None:
            try:
                merge(_run_rows(driver, SCAN_BUCKET_CHUNK, tb=tb.name, lo=lo, hi=hi))
            except ClientError:
                if hi - lo <= 1:
                    raise
                mid = (lo + hi) // 2
                print(f"  [timeout] {tb.name}: buckets {lo}-{hi} -> split", flush=True)
                scan_range(lo, mid)
                scan_range(mid, hi)

        for lo in range(0, 100, BUCKETS_PER_CHUNK):
            scan_range(lo, min(lo + BUCKETS_PER_CHUNK, 100))

    return {
        "treebank": tb.name,
        "scheme": tb.scheme,
        "language": tb.language,
        "n_sents": tb.n_sents,
        "n_tokens": tb.n_tokens,
        "imported_at": tb.imported_at,
        "columns": ["gupos", "rel1", "rel2", "dupos", "n", "n_right", "sum_delta", "sum_abs_delta"],
        "rows": [list(key) + vals for key, vals in sorted(acc.items())],
    }


def is_current(tb) -> bool:
    path = dump_path(tb.name)
    if not path.exists():
        return False
    try:
        head = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    return head.get("imported_at") == tb.imported_at and head.get("rows")


def merge(scheme: str) -> Path:
    """Sum treebank dumps into one language-level table (plan.md: counts, never
    percentages, so a 27k-token treebank does not weigh like a 400k one)."""
    acc: dict[tuple, list[int]] = {}
    n_dumps = 0
    for path in sorted(DUMP_DIR.glob(f"{scheme}_*.json")):
        dump = json.loads(path.read_text())
        n_dumps += 1
        lang = dump["language"]
        for gupos, rel1, rel2, dupos, n, n_right, s_d, s_ad in dump["rows"]:
            key = (lang, gupos, rel1, rel2, dupos)
            slot = acc.setdefault(key, [0, 0, 0, 0])
            slot[0] += n
            slot[1] += n_right
            slot[2] += s_d
            slot[3] += s_ad
    out = MINING_DIR / f"lang_cfc.{scheme.lower()}.tsv"
    with out.open("w") as fh:
        fh.write("language\tgupos\trel1\trel2\tdupos\tn\tn_right\tsum_delta\tsum_abs_delta\n")
        for key, vals in sorted(acc.items()):
            fh.write("\t".join([*key, *map(str, vals)]) + "\n")
    print(f"[merge] {n_dumps} dumps -> {out} ({len(acc)} language-level rows)", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scheme", choices=["SUD", "UD"], default="SUD")
    ap.add_argument("--treebank", help="scan exactly this treebank, then merge")
    ap.add_argument("--merge-only", action="store_true")
    ap.add_argument("--no-merge", action="store_true")
    args = ap.parse_args()

    MINING_DIR.mkdir(exist_ok=True)
    DUMP_DIR.mkdir(exist_ok=True)

    if args.merge_only:
        merge(args.scheme)
        return 0

    if importer_running():
        print("REFUSING to scan: import_neo4j.py is running (counts would be silently "
              "wrong, CLAUDE.md).", flush=True)
        return 1

    engine = get_engine()
    catalogue = [t for t in engine.treebanks() if t.scheme == args.scheme]
    if args.treebank:
        catalogue = [t for t in catalogue if t.name == args.treebank]
        if not catalogue:
            print(f"unknown or mid-import treebank: {args.treebank}", flush=True)
            return 1
    catalogue.sort(key=lambda t: t.n_tokens)  # smallest first: results appear early

    todo = [t for t in catalogue if not is_current(t)]
    print(f"[scan] {len(catalogue)} {args.scheme} treebanks, {len(todo)} to scan "
          f"({sum(t.n_tokens for t in todo) / 1e6:.1f} M tokens)", flush=True)

    t_all = time.time()
    for i, tb in enumerate(todo, 1):
        if importer_running():
            print("[scan] importer appeared mid-run -- stopping cleanly.", flush=True)
            return 1
        t0 = time.time()
        dump = scan_treebank(engine, tb)
        tmp = dump_path(tb.name).with_suffix(".json.tmp")
        tmp.write_text(json.dumps(dump))
        tmp.replace(dump_path(tb.name))
        print(f"[scan] {i}/{len(todo)} {tb.name}: {tb.n_tokens:,} tokens, "
              f"{len(dump['rows'])} cells, {time.time() - t0:.1f}s", flush=True)

    print(f"[scan] done in {(time.time() - t_all) / 60:.1f} min", flush=True)
    if not args.no_merge:
        merge(args.scheme)
    return 0


if __name__ == "__main__":
    sys.exit(main())
