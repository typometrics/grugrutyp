#!/usr/bin/env python3
"""Turn `docs/Typometrics configuration.xlsx` into the TSVs under `data/meta/`.

The current typometrics keeps its language configuration -- display names, genetic
groupings, plot colours and markers -- in a Google Sheet that somebody exported by hand
into three TSVs (`languageCodes.tsv`, `myLanguageCodes.tsv`, `languageGroups.tsv`).
`docs/Typometrics configuration.xlsx` is a download of that sheet.

Two things make the hand export a problem, and both are why this script exists:

1. **It is lossy.** The sheet holds five independent groupings per language (genetic
   group, genus, sub-genus, simple group, area, typological class). The export flattened
   them into one string (`Indo-European-Germanic`), which cannot be un-flattened.
2. **It is stale.** The sheet has since split `Agglutinating` into `Turkic` / `Uralic` /
   `Mongolic` / `Tungusic` and recoloured several groups; the deployed
   `languageGroups.tsv` still carries the older state. Nobody noticed, because a stale
   grouping does not raise an error -- it just draws the wrong colour.

So grugrutyp reads the columns, not the flattening. Run this once after each edit of the
sheet; the outputs are text, small, and version-controlled, so `git diff` shows exactly
what a re-export changed.

    python3 scripts/xlsx2config.py [--xlsx PATH] [--out data/meta]

No third-party dependency: an .xlsx is a zip of XML, and we need four sheets from it.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

# sheet name -> (output file, [(column letter, output header)])
# Column letters are how the spreadsheet addresses them, so a reviewer can open the file
# next to this table and check it. Headers are renamed to snake_case on the way out;
# `Column 1` and `Column 2` are the sheet's own unnamed columns -- see docs/language-config.md.
EXPORTS = {
    "language to group": (
        "languages.tsv",
        [
            ("A", "language"),
            ("B", "group"),
            ("C", "genus"),
            ("D", "subgenus"),
            ("E", "simple_group"),
            ("F", "area"),
            ("G", "typology"),
        ],
    ),
    "appearance": ("appearance.tsv", [("A", "group"), ("B", "color"), ("C", "marker")]),
    "my languages": ("language_names.tsv", [("A", "code"), ("B", "name")]),
    "all language codes": ("iso639.tsv", [("A", "code"), ("B", "name")]),
}


def col_index(ref: str) -> int:
    """`A1` -> 0, `AB7` -> 27."""
    letters = "".join(ch for ch in ref if ch.isalpha())
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def read_sheets(xlsx: Path) -> dict[str, list[list[str]]]:
    with zipfile.ZipFile(xlsx) as zf:
        shared = [
            "".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t"))
            for si in ET.fromstring(zf.read("xl/sharedStrings.xml")).findall("m:si", NS)
        ]
        rels = {
            rel.get("Id"): rel.get("Target")
            for rel in ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        }
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))

        sheets: dict[str, list[list[str]]] = {}
        for sheet in workbook.find("m:sheets", NS):
            target = rels[sheet.get(f"{{{NS['r']}}}id")].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            rows = []
            for row in ET.fromstring(zf.read(target)).iter(f"{{{NS['m']}}}row"):
                cells: dict[int, str] = {}
                for cell in row.findall("m:c", NS):
                    value = cell.find("m:v", NS)
                    if value is None or value.text is None:
                        continue
                    text = shared[int(value.text)] if cell.get("t") == "s" else value.text
                    # A cell holding only whitespace is empty for our purposes; the sheet
                    # has a few, left over from editing.
                    if text.strip():
                        cells[col_index(cell.get("r"))] = text.strip()
                if cells:
                    rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
            sheets[sheet.get("name")] = rows
        return sheets


def write_tsv(path: Path, headers: list[str], rows: list[list[str]]) -> int:
    lines = ["\t".join(headers)]
    lines += ["\t".join(row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--xlsx", type=Path, default=ROOT / "docs" / "Typometrics configuration.xlsx")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "meta")
    args = ap.parse_args()

    sheets = read_sheets(args.xlsx)
    args.out.mkdir(parents=True, exist_ok=True)

    for sheet_name, (filename, columns) in EXPORTS.items():
        if sheet_name not in sheets:
            raise SystemExit(f"{args.xlsx}: no sheet named {sheet_name!r}")
        wanted = [col_index(letter) for letter, _ in columns]
        headers = [header for _, header in columns]

        rows = []
        for row in sheets[sheet_name][1:]:  # the sheet's own header row is replaced
            values = [row[i] if i < len(row) else "" for i in wanted]
            # The sheets carry stray notes to the right of the data; a row with no value
            # in the first column is one of those, not a language.
            if values[0]:
                rows.append(values)

        n = write_tsv(args.out / filename, headers, rows)
        print(f"{sheet_name:22s} -> {filename:20s} {n:5d} rows")


if __name__ == "__main__":
    main()
