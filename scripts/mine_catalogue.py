#!/usr/bin/env python3
"""Run the Tier-2 pattern-mining catalogue through the ordinary measure runner.

    .venv/bin/python scripts/mine_catalogue.py --list
    .venv/bin/python scripts/mine_catalogue.py --only so-order
    setsid nohup .venv/bin/python scripts/mine_catalogue.py \
        > logs/mine-catalogue.log 2>&1 < /dev/null &

Design: `docs/pattern-mining.md` ch. 6. Entries come from
`data/mining/catalogue.json` -- selection is by argument, each entry carries its
rationale and verification status. Every measure runs exactly like a live plot
request (same sampling budget, same bounded escalation, same cache -- so a later
interactive plot of the same pair is instant), and the language merge follows the
plot rule: counts summed over a language's treebanks, never percentages averaged.

Output: `data/mining/tier2/<key>.tsv`, one row per language, columns compatible
with `measures.<scheme>.tsv` so mine_shapes.py can ingest both.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from grugrutyp.measure import MeasureSpec, SamplingPolicy, wilson  # noqa: E402
from grugrutyp.runner import RunOptions, run  # noqa: E402

MINING = ROOT / "data" / "mining"
TIER2 = MINING / "tier2"


def other_miner_running() -> bool:
    out = subprocess.run(["pgrep", "-af", "mine_cfc_matrix.py"],
                         capture_output=True, text=True).stdout
    return any("mine_cfc_matrix.py" in l and "pgrep" not in l for l in out.splitlines())


def run_entry(entry: dict, workers: int) -> None:
    spec = MeasureSpec(scope=entry["scope"], response=entry["response"], kind="ratio")
    options = RunOptions(scheme="SUD", workers=workers, policy=SamplingPolicy())
    started = time.time()

    per_lang: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])  # scope, hit, tbs, refinable
    failed: list[str] = []
    for group in run([spec], options):
        point = group[0]
        if point.error:
            failed.append(point.treebank)
            continue
        slot = per_lang[point.language]
        slot[0] += point.n_scope
        slot[1] += point.n_hit
        slot[2] += 1
        slot[3] |= point.refinable

    rows = []
    for lang in sorted(per_lang):
        n_scope, n_hit, n_tbs, refinable = per_lang[lang]
        if n_scope == 0:
            continue
        lo, hi = wilson(n_hit, n_scope)
        rows.append(f"{lang}\t{n_scope}\t{n_hit}\t{100 * n_hit / n_scope:.4f}"
                    f"\t{lo:.3f}\t{hi:.3f}\t{int(bool(refinable))}\t{n_tbs}")

    out = TIER2 / f"{entry['key']}.tsv"
    out.write_text(
        "language\tn_scope\tn_hit\tvalue\tci_low\tci_high\trefinable\tn_treebanks\n"
        + "\n".join(rows) + "\n"
    )
    print(f"[{entry['key']:<28}] {len(rows):3d} languages, {len(failed)} failed tbs, "
          f"{time.time() - started:7.1f}s -> {out.name}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", help="run only this key (repeatable)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--workers", type=int, default=2)  # background job: warm_cache's rule
    ap.add_argument("--anyway", action="store_true",
                    help="run even while the Tier-1 scan is hogging the disk")
    args = ap.parse_args()

    catalogue = json.loads((MINING / "catalogue.json").read_text())["entries"]
    if args.list:
        for e in catalogue:
            print(f"{e['key']:<28} ch.{e['chapter']}  {e['rationale'][:80]}")
        return 0
    if args.only:
        wanted = set(args.only)
        catalogue = [e for e in catalogue if e["key"] in wanted]
        unknown = wanted - {e["key"] for e in catalogue}
        if unknown:
            print(f"unknown keys: {', '.join(sorted(unknown))}")
            return 1

    if other_miner_running() and not args.anyway:
        print("REFUSING: mine_cfc_matrix.py is scanning (single-scan discipline, "
              "docs/pattern-mining.md ch. 11). Use --anyway to override.", flush=True)
        return 1

    TIER2.mkdir(exist_ok=True)
    # validate everything before the first fan-out: discovering a bad entry on
    # treebank 300 wastes minutes and leaves partial output (runner.run's own rule)
    for entry in catalogue:
        MeasureSpec(scope=entry["scope"], response=entry["response"], kind="ratio").validate()
    for entry in catalogue:
        run_entry(entry, args.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
