"""Treebank registry: what exists on disk.

Everything about *languages* -- display names, groupings, colours, markers -- lives in
`langconfig.py`, which reads `data/meta/`. This module only knows what directories exist
and which language each belongs to; it asks `langconfig` for the rest, lazily, to keep the
two importable in either order.

The groupings encode curation decisions -- "Agglutinating" and "Semitic" sit alongside
genetic groupings on purpose, because the plots use them as visual classes. Do not "fix"
them without asking Kim; see `docs/language-config.md`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_ROOT = Path(os.environ.get("GRUGRUTYP_DATA", "/home/typometrics/grugrutyp/data"))
CORPUS_VERSION = os.environ.get("GRUGRUTYP_VERSION", "2.18")

_TREEBANK_DIR = re.compile(r"^(UD|SUD)_([A-Za-z_]+?)-([A-Za-z0-9]+)$")

UNKNOWN_FAMILY = "unknown"


@dataclass(frozen=True)
class Treebank:
    name: str  # SUD_French-GSD
    scheme: str  # SUD | UD
    language: str  # French  (underscores kept: Ancient_Greek)
    corpus: str  # GSD
    family: str
    path: Path
    lcode: str = ""  # fr -- from the CoNLL-U filenames, "" for the few that do not follow

    @property
    def color(self) -> str:
        from .langconfig import appearance_of

        return appearance_of(self.language, lcode=self.lcode).color

    @property
    def marker(self) -> str:
        from .langconfig import appearance_of

        return appearance_of(self.language, lcode=self.lcode).marker

    def conllu_files(self) -> list[Path]:
        return sorted(self.path.glob("*.conllu"))


@lru_cache(maxsize=8)
def treebanks(version: str = CORPUS_VERSION) -> dict[str, Treebank]:
    root = DATA_ROOT / "treebanks" / f"v{version}"
    if not root.is_dir():
        raise FileNotFoundError(f"no treebanks at {root} -- run scripts/unpack.sh")

    # `lookup`, not `label_of`: the latter fills a missing ISO code in from disk, which
    # would call back into this function while it is still building its cache.
    from .langconfig import UNKNOWN, lookup

    found: dict[str, Treebank] = {}
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        match = _TREEBANK_DIR.match(entry.name)
        if not match:
            continue
        scheme, language, corpus = match.groups()
        row = lookup(language, _lcode_of(entry))
        found[entry.name] = Treebank(
            name=entry.name,
            scheme=scheme,
            language=language,
            corpus=corpus,
            family=row.label() if row else UNKNOWN,
            path=entry,
            lcode=_lcode_of(entry),
        )
    return found


def _lcode_of(directory: Path) -> str:
    """`UD_French-GSD/fr_gsd-ud-train.conllu` -> `fr`.

    The ISO code is the only identifier UD keeps stable when it renames a treebank
    directory, so it is worth carrying. A dozen treebanks (the Autogramm ones,
    `French-ParisStories`, `French-Rhapsodie`) name their files freely; those get "".
    """
    for path in sorted(directory.glob("*.conllu")):
        code = path.name.split("_")[0]
        if code.isalpha() and code.islower() and 2 <= len(code) <= 3:
            return code
        return ""
    return ""


def missing_families(version: str = CORPUS_VERSION) -> list[str]:
    """Languages present on disk with no row in `data/meta/languages.tsv`.

    An unconfigured language does not fail -- it plots grey, indistinguishable from a
    genuine isolate, which is exactly the silent failure `docs/data-intake.md` section 3
    warns about. The importer reports this list; `scripts/import_neo4j.py --strict`
    refuses to run while it is non-empty. `scripts/config_audit.py` says what to do about
    it, including which entries are renames rather than new languages.
    """
    return sorted(
        {tb.language for tb in treebanks(version).values() if tb.family == UNKNOWN_FAMILY}
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
) -> list[Treebank]:
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
