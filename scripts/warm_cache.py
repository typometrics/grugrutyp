#!/usr/bin/env python3
"""Precompute every preset measure, so preset plots serve from cache.

    .venv/bin/python scripts/warm_cache.py                # both schemes, all presets
    .venv/bin/python scripts/warm_cache.py --scheme SUD
    nohup .venv/bin/python scripts/warm_cache.py > logs/warm.log 2>&1 &

This is the honest answer to "make it fast" on this hardware (`docs/performance.md`): the
corpus is static between releases, so there is no reason any preset should ever be
computed while a person is watching. A cold full pass costs what it costs -- pay it here,
overnight or after an import, and the plot page then answers presets instantly.

Runs through the same `runner.run` path as the API, so everything is cached exactly as a
live request would cache it: same budget, same bounded escalation, same cache keys
(including the treebank's import revision -- re-run this after any re-import).

Deliberately **2 workers**, not the API's 8. This is a background job on a disk-bound
box; it should not saturate the array that the live site is also reading.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from grugrutyp import presets  # noqa: E402
from grugrutyp.measure import MeasureSpec, SamplingPolicy  # noqa: E402
from grugrutyp.runner import RunOptions, run  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scheme", choices=["SUD", "UD"], action="append", dest="schemes")
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    schemes = args.schemes or ["SUD", "UD"]

    grand_start = time.time()
    for scheme in schemes:
        for preset in presets.for_scheme(scheme):
            if not preset["available"]:
                continue
            spec = MeasureSpec(
                scope=preset["scope"],
                response=preset["response"],
                kind="aggregate" if preset["kind"] == "aggregate" else "ratio",
                expression=preset["expression"],
                aggregation=preset["aggregation"],
            )
            options = RunOptions(
                scheme=scheme,
                workers=args.workers,
                policy=SamplingPolicy(),  # the defaults a live request uses
            )
            started = time.time()
            done = cached = failed = 0
            for group in run([spec], options):
                done += 1
                cached += group[0].cached
                failed += bool(group[0].error)
            fresh = done - cached
            print(
                f"[{scheme}] {preset['key']:<24} {done:3d} treebanks "
                f"({fresh:3d} computed, {cached:3d} already cached, {failed} failed) "
                f"{time.time()-started:7.1f}s",
                flush=True,
            )

    print(f"\ndone in {(time.time()-grand_start)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
