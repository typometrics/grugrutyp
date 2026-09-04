"""Per-language reference tables: numbers we did not compute from the treebanks.

Two kinds of thing land here and they behave identically on a plot:

* **external typologies** — Bakker's word-order flexibility (`bakker.tsv`), and any
  WALS-style feature someone imports later. Comparing our measures against an
  independent classification is a large part of what the old site's D-class tables were
  for (`bak_vs_typo.tsv`);
* **our own batch results** that are not query pairs — the fitted Menzerath a/b/c
  (`menzerath_abc.tsv`), which no aggregation over matchings can produce.

A table is a TSV in `data/meta/` whose first column is `language`; every other column
that parses as a number becomes a plottable axis named `<table>.<column>`. Language
names are folded the same way `langconfig` folds them, so `OldFrench`, `Old_French` and
`Old French` all find the row.

These axes carry no scope, no sample and no interval: the value is simply what the
table says. That is why `MeasureSpec.kind == "table"` skips the database entirely and
why the plot exempts such an axis from the minimum-scope filter -- there is no scope to
be below.
"""

from __future__ import annotations

from functools import lru_cache

from .langconfig import META_DIR, _fold, _read_tsv

# Tables offered as axes. Explicit rather than "every TSV in the directory": the
# directory also holds the configuration (languages, appearance, exclusions), which is
# not measurement data and must not turn up in an axis picker.
TABLES = {
    "bakker": {
        "file": "bakker.tsv",
        "title": "Bakker's flexibility typology",
        "note": (
            "External data, 24 languages: Bakker's word-order flexibility score and the "
            "'Bakker-like' extension, alongside the 2.12 site's own flexibility for "
            "comparison. Plot one against our flexibility measure to see how the two "
            "traditions line up."
        ),
    },
    "menzerath_abc": {
        "file": "menzerath_abc.tsv",
        "title": "Menzerath–Altmann fitted parameters",
        "note": (
            "Our own fits of y = a·x^b·e^(−c·x) over the verbal domain, one row per "
            "language (scripts/menzerath_fit.py). `b` is the exponent typically cited: "
            "negative means constituents shrink as the construct grows, which is the "
            "law's prediction. `r2` and `coverage` say how much to trust a row."
        ),
    },
}


@lru_cache(maxsize=1)
def tables() -> dict[str, dict[str, dict[str, float]]]:
    """`{table: {folded language: {column: value}}}` for every configured table."""
    out: dict[str, dict[str, dict[str, float]]] = {}
    for name, spec in TABLES.items():
        path = META_DIR / spec["file"]
        if not path.exists():
            continue
        rows: dict[str, dict[str, float]] = {}
        for row in _read_tsv(path):
            language = (row.get("language") or "").strip()
            if not language:
                continue
            values = {}
            for column, cell in row.items():
                if column == "language":
                    continue
                try:
                    values[column] = float(cell)
                except (TypeError, ValueError):
                    continue
            if values:
                rows[_fold(language)] = values
        if rows:
            out[name] = rows
    return out


@lru_cache(maxsize=1)
def columns() -> dict[str, list[str]]:
    """`{table: [numeric column, ...]}` -- what an axis picker may offer."""
    out = {}
    for name, rows in tables().items():
        seen: list[str] = []
        for values in rows.values():
            for column in values:
                if column not in seen:
                    seen.append(column)
        out[name] = seen
    return out


def split(expression: str) -> tuple[str, str]:
    """`"bakker.bakker_flexibility"` -> `("bakker", "bakker_flexibility")`."""
    table, _, column = expression.strip().partition(".")
    return table.strip(), column.strip()


def validate(expression: str) -> None:
    """Raise with the available names, so a typo is answered rather than plotted."""
    table, column = split(expression)
    available = columns()
    if table not in available:
        raise ValueError(
            f"unknown reference table '{table}'. Available: "
            f"{', '.join(sorted(available)) or 'none'}."
        )
    if column not in available[table]:
        raise ValueError(
            f"'{table}' has no numeric column '{column}'. Available: "
            f"{', '.join(available[table])}."
        )


def value_for(expression: str, language: str) -> float | None:
    """The table's value for one language, or None when it does not list it."""
    table, column = split(expression)
    return tables().get(table, {}).get(_fold(language), {}).get(column)


def reload() -> None:
    tables.cache_clear()
    columns.cache_clear()
