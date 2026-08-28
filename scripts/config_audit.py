#!/usr/bin/env python3
"""Report what a UD release did to the language configuration, and repair what is safe.

Every release adds languages and renames a few, and neither raises an error on its own --
an unconfigured language just plots grey in a corner of the scatter, which is exactly the
kind of failure nobody notices. Run this after every `scripts/unpack.sh`.

    python3 scripts/config_audit.py                  # report
    python3 scripts/config_audit.py --json           # same, for the admin page
    python3 scripts/config_audit.py --backfill-lcodes  # record ISO codes (safe, idempotent)
    python3 scripts/config_audit.py --apply-renames --min-confidence 0.85

`--backfill-lcodes` writes the ISO code of every configured language that is present on
disk into `data/meta/languages.tsv`. It changes no grouping. It is worth running once,
because after it the *next* release's renames resolve by code and stop being a problem at
all -- see `docs/language-config.md` section 4.

`--apply-renames` rewrites the `language` column of rows the audit paired with a new name.
It is a convenience for the one-time 2.12 -> 2.18 catch-up and is deliberately not the
default: `Naga` <- `Tangkhul` and `Bokota` <- `Buglere` are correct, but only a linguist
can confirm that, and a wrong pairing silently mis-classifies a language.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from grugrutyp import langconfig as lc  # noqa: E402

LANGUAGES_TSV = lc.META_DIR / "languages.tsv"
COLUMNS = list(lc.LanguageRow.__annotations__)


def _load_rows() -> list[dict[str, str]]:
    lines = LANGUAGES_TSV.read_text(encoding="utf-8").strip().split("\n")
    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        values = line.split("\t")
        values += [""] * (len(headers) - len(values))
        row = dict(zip(headers, values))
        rows.append({column: row.get(column, "") for column in COLUMNS})
    return rows


def _save_rows(rows: list[dict[str, str]]) -> None:
    out = ["\t".join(COLUMNS)]
    out += ["\t".join(row.get(column, "") for column in COLUMNS) for row in rows]
    LANGUAGES_TSV.write_text("\n".join(out) + "\n", encoding="utf-8")


def backfill_lcodes() -> int:
    lcodes = lc.disk_lcodes()
    # Language on disk -> code, keyed the way the config is keyed.
    by_fold = {lc._fold(name): code for name, code in lcodes.items()}
    rows, changed = _load_rows(), 0
    for row in rows:
        if row.get("lcode"):
            continue
        code = by_fold.get(lc._fold(row["language"]))
        if code:
            row["lcode"] = code
            changed += 1
    if changed:
        _save_rows(rows)
    return changed


def apply_renames(audit: lc.Audit, min_confidence: float) -> list[tuple[str, str]]:
    accepted = [r for r in audit.renames if r["confidence"] >= min_confidence]
    if not accepted:
        return []
    wanted = {r["was"]: r["language"] for r in accepted}
    rows = _load_rows()
    done = []
    for row in rows:
        new = wanted.get(row["language"])
        if new:
            done.append((row["language"], new))
            row["language"] = new
    if done:
        _save_rows(rows)
    return done


def report(audit: lc.Audit) -> None:
    paired_new = {r["language"] for r in audit.renames}
    paired_old = {r["was"] for r in audit.renames}

    print(f"language configuration vs UD/SUD {audit.version}")
    print(f"  configured languages : {len(lc.languages())}")
    print(f"  languages on disk    : {len(lc.disk_lcodes()) or '?'} with an ISO code")
    print()

    if audit.renames:
        print(f"probable renames ({len(audit.renames)}) -- confirm, then --apply-renames:")
        for r in audit.renames:
            print(f"  {r['language']:<34} <- {r['was']:<22} {r['confidence']:.2f} ({r['via']})")
        print()

    new = [n for n in audit.unconfigured if n not in paired_new]
    if new:
        print(f"unconfigured, no candidate ({len(new)}) -- these need a group:")
        for name in new:
            print(f"  {name}")
        print()

    gone = [n for n in audit.orphaned if n not in paired_old]
    if gone:
        print(f"configured but absent from this release ({len(gone)}) -- keep, they may return:")
        print("  " + ", ".join(gone))
        print()

    if audit.unstyled:
        print(f"labels with no colour/marker ({len(audit.unstyled)}):")
        print("  " + ", ".join(audit.unstyled))
        print()
    if audit.incomplete:
        print(f"rows with no grouping at all ({len(audit.incomplete)}):")
        print("  " + ", ".join(audit.incomplete))
        print()

    print("CLEAN" if audit.clean else "ACTION NEEDED")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--backfill-lcodes", action="store_true")
    ap.add_argument("--apply-renames", action="store_true")
    ap.add_argument("--min-confidence", type=float, default=0.85)
    args = ap.parse_args()

    if args.backfill_lcodes:
        n = backfill_lcodes()
        print(f"recorded {n} ISO codes in {LANGUAGES_TSV.relative_to(ROOT)}")
        lc.languages.cache_clear()
        lc.by_lcode.cache_clear()

    audit = lc.audit()

    if args.apply_renames:
        done = apply_renames(audit, args.min_confidence)
        for old, new in done:
            print(f"renamed {old} -> {new}")
        if done:
            lc.languages.cache_clear()
            lc.by_lcode.cache_clear()
            audit = lc.audit()

    if args.json:
        print(json.dumps(audit.to_dict(), indent=2, ensure_ascii=False))
    else:
        report(audit)
    return 0 if audit.clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
