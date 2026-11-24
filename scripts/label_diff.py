#!/usr/bin/env python3
"""What did a new release change under our queries? Diff the label inventory.

Counts (head UPOS, deprel without `@deep`) over the first file of a fixed spread of
treebanks in two unpacked releases and prints every pair whose count moved by at least
`--min`. Run it after `unpack.sh`, before trusting any preset or Finding on the new data:
a relabelling does not make a query fail, it makes languages quietly drop out.
docs/data-intake.md §2b has the 2.18 → 2.19 result.

    .venv/bin/python scripts/label_diff.py 2.18 2.19 [--scheme SUD] [--min 150]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from grugrutyp.conllu import read_conllu  # noqa: E402

SPREAD = [
    "French-GSD", "English-EWT", "Japanese-GSD", "Hindi-HDTB", "German-GSD",
    "Russian-SynTagRus", "Chinese-GSD", "Arabic-PADT", "Turkish-IMST", "Finnish-TDT",
    "Korean-Kaist", "Wolof-WTB", "Basque-BDT", "Indonesian-GSD", "Persian-Seraji",
    "Czech-PDT", "Spanish-AnCora", "Tamil-TTB", "Hebrew-HTB", "Irish-IDT",
]


def inventory(version: str, scheme: str, max_sents: int) -> Counter:
    counts: Counter = Counter()
    for name in SPREAD:
        files = sorted((ROOT / "data" / "treebanks" / f"v{version}" / f"{scheme}_{name}").glob("*.conllu"))
        if not files:
            print(f"  (v{version}: no {scheme}_{name})", file=sys.stderr)
            continue
        for i, sent in enumerate(read_conllu(files[0])):
            if i >= max_sents:
                break
            upos = {w.idx: w.upos for w in sent.words}
            upos[0] = "ROOT"
            for w in sent.words:
                counts[(upos.get(w.head, "?"), w.deprel.split("@")[0])] += 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--scheme", default="SUD", choices=["SUD", "UD"])
    ap.add_argument("--min", type=int, default=150, help="smallest absolute change to report")
    ap.add_argument("--max-sents", type=int, default=3000)
    args = ap.parse_args()
    a = inventory(args.old, args.scheme, args.max_sents)
    b = inventory(args.new, args.scheme, args.max_sents)
    moved = [(b[k] - a[k], k) for k in set(a) | set(b) if abs(b[k] - a[k]) >= args.min]
    for diff, (head, rel) in sorted(moved):
        print(f"{head:>6} {rel:<18} {args.old}={a[(head, rel)]:>7} {args.new}={b[(head, rel)]:>7} {diff:+}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
