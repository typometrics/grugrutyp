#!/usr/bin/env python3
"""Chunk and embed the guidelines for the chat's retrieval (`backend/grugrutyp/guidelines.py`).

    scripts/fetch_guidelines.sh
    .venv/bin/python scripts/build_guideline_index.py            # chunks + embeddings
    .venv/bin/python scripts/build_guideline_index.py --no-embed # chunks only (BM25 fallback)
    .venv/bin/python scripts/build_guideline_index.py --query "complétives" --scheme SUD

Writes data/guidelines/index.json (the chunks) and index.npy (float16 embeddings, one
row per chunk). Re-run after fetching; then restart the API (the index is cached).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from grugrutyp.engine.neo4j_engine import load_env  # noqa: E402
from grugrutyp import guidelines as g  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-embed", action="store_true")
    ap.add_argument("--query")
    ap.add_argument("--scheme", default="SUD")
    args = ap.parse_args()
    load_env()

    if args.query:
        for chunk in g.retrieve(args.query, args.scheme, k=6):
            print(f"- {chunk.collection:9} {chunk.title}  {chunk.url}")
        return 0

    import numpy as np

    chunks = g.all_chunks()
    by = {}
    for c in chunks:
        by[c.collection] = by.get(c.collection, 0) + 1
    print(f"{len(chunks)} chunks: {by}")
    # The running API reloads when index.json changes (guidelines._index), so the
    # embeddings are written first and both files are replaced atomically.
    if args.no_embed:
        g.INDEX_NPY.unlink(missing_ok=True)
    else:
        vectors: list[list[float]] = []
        batch = 64
        for start in range(0, len(chunks), batch):
            vectors += g.embed([c.text[:6000] for c in chunks[start:start + batch]], timeout=60)
            print(f"  embedded {len(vectors)}/{len(chunks)}", flush=True)
        tmp = g.INDEX_NPY.with_name("index.tmp.npy")
        np.save(tmp, np.asarray(vectors, dtype="float16"))
        tmp.replace(g.INDEX_NPY)
    tmp = g.INDEX_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps([asdict(c) for c in chunks], ensure_ascii=False), encoding="utf-8")
    tmp.replace(g.INDEX_JSON)
    print(f"wrote {g.INDEX_JSON.name}" + ("" if args.no_embed else f" and {g.INDEX_NPY.name}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
