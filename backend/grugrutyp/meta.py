"""grugrutyp's settings for the corpus: data root, live release, import selection.

The treebank registry and everything about *languages* -- display names, groupings,
colours, markers -- live in the standalone package `udcorpus` (`corpus/`, read
`corpus/README.md`); `langconfig.py` and this module re-export it. What stays here is
grugrutyp's own: where its data directory is, which release is live (`.env`), and the
dev slice the importer offers.

The groupings encode curation decisions -- "Agglutinating" and "Semitic" sit alongside
genetic groupings on purpose, because the plots use them as visual classes. Do not "fix"
them without asking Kim; see `docs/language-config.md`.
"""

from __future__ import annotations

import os
from pathlib import Path

DATA_ROOT = Path(os.environ.get("GRUGRUTYP_DATA", "/home/typometrics/grugrutyp/data"))


def _version_from_dotenv() -> str | None:
    """GRUGRUTYP_VERSION as written in `.env`.

    Read here, not left to `load_env()`: `main.py` imports this module (via langconfig)
    before anything loads `.env`, so the `.env` line used to be silently ignored and the
    hard-coded default below was the real switch. The version and NEO4J_URI must move
    together at a release cutover (docs/data-intake.md), so both now live in `.env`.
    """
    path = Path(__file__).resolve().parents[2] / ".env"
    try:
        for line in path.read_text().splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key.strip() == "GRUGRUTYP_VERSION":
                return value.strip()
    except OSError:
        pass
    return None


CORPUS_VERSION = (
    os.environ.get("GRUGRUTYP_VERSION") or _version_from_dotenv() or "2.18"
)

# The registry itself -- directory names, files, ISO codes, the per-language measure
# selection -- is udcorpus's (corpus/udcorpus/treebanks.py). grugrutyp only tells it where
# the data is and which release is live; everything below re-exports.
import udcorpus.config  # noqa: E402  (grugrutyp/__init__.py put corpus/ on sys.path)

udcorpus.config.configure(data_dir=DATA_ROOT, version=CORPUS_VERSION)

from udcorpus.treebanks import (  # noqa: E402,F401
    UNKNOWN_FAMILY,
    Treebank,
    lcode_of as _lcode_of,
    measure_selection,
    missing_families,
    treebanks,
)


# A typologically spread development slice: 20 languages across families, word orders and
# scripts, small enough to import in minutes. Used by --slice dev (plan.md phase 0).
DEV_SLICE = [
    "English-GUM",
    "French-GSD",
    "Spanish-AnCora",
    "German-GSD",
    "Russian-SynTagRus",
    "Japanese-GSD",
    "Korean-Kaist",
    "Chinese-GSDSimp",
    "Arabic-PADT",
    "Hebrew-HTB",
    "Hindi-HDTB",
    "Turkish-IMST",
    "Finnish-TDT",
    "Wolof-WTB",
    "Naija-NSC",
    "Indonesian-GSD",
    "Vietnamese-VTB",
    "Basque-BDT",
    "Irish-IDT",
    "Coptic-Scriptorium",
]


def resolve(
    names: list[str] | None = None,
    slice_name: str | None = None,
    scheme: str | None = None,
    version: str = CORPUS_VERSION,
) -> list["Treebank"]:
    """Turn CLI selectors into a concrete treebank list."""
    available = treebanks(version)

    if names:
        chosen = []
        for name in names:
            if name in available:
                chosen.append(available[name])
                continue
            # Allow bare `French-GSD` to mean both schemes.
            matches = [tb for tb in available.values() if f"{tb.language}-{tb.corpus}" == name]
            if not matches:
                raise KeyError(f"unknown treebank: {name}")
            chosen.extend(matches)
    elif slice_name == "dev":
        chosen = [
            tb
            for tb in available.values()
            if f"{tb.language}-{tb.corpus}" in set(DEV_SLICE)
        ]
    else:
        chosen = list(available.values())

    if scheme:
        chosen = [tb for tb in chosen if tb.scheme == scheme.upper()]
    return sorted(chosen, key=lambda tb: tb.name)
