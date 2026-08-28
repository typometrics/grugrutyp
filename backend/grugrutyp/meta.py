"""Treebank registry: what exists on disk, and what we know about each language.

The language -> family mapping is carried over verbatim from the current typometrics
(`languageGroups.tsv`). It encodes curation decisions -- "Agglutinating" and "Semitic"
sit alongside genetic groupings on purpose, because the plots use them as visual classes.
Do not "fix" it without asking Kim.
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

# Carried over from tsv2json.py so the new plots keep the old visual language.
GROUP_COLORS = {
    "Indo-European-Romance": "brown",
    "Indo-European-Baltoslavic": "purple",
    "Indo-European-Germanic": "olive",
    "Indo-European": "royalBlue",
    "Austronesian": "limeGreen",
    "Sino-Austronesian": "limeGreen",
    "Agglutinating": "red",
    "Semitic": "orange",
    "Afroasiatic": "orange",
    "Niger-Congo": "black",
    "Tupian": "cadetBlue",
}
GROUP_MARKERS = {
    "Indo-European-Romance": "triangle",
    "Indo-European-Baltoslavic": "triangle",
    "Indo-European-Germanic": "triangle",
    "Indo-European": "triangle",
    "Austronesian": "star",
    "Sino-Austronesian": "star",
    "Agglutinating": "cross",
    "Semitic": "crossRot",
    "Afroasiatic": "crossRot",
    "Tupian": "star",
}
UNKNOWN_FAMILY = "unknown"
DEFAULT_COLOR = "black"
DEFAULT_MARKER = "circle"


@dataclass(frozen=True)
class Treebank:
    name: str  # SUD_French-GSD
    scheme: str  # SUD | UD
    language: str  # French  (underscores kept: Ancient_Greek)
    corpus: str  # GSD
    family: str
    path: Path

    @property
    def color(self) -> str:
        return GROUP_COLORS.get(self.family, DEFAULT_COLOR)

    @property
    def marker(self) -> str:
        return GROUP_MARKERS.get(self.family, DEFAULT_MARKER)

    def conllu_files(self) -> list[Path]:
        return sorted(self.path.glob("*.conllu"))


@lru_cache(maxsize=1)
def language_families() -> dict[str, str]:
    """Normalised language name -> family, from data/meta/languageGroups.tsv."""
    path = DATA_ROOT / "meta" / "languageGroups.tsv"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").strip().split("\n"):
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0]:
            out[_normalise(parts[0])] = parts[1].strip()
    return out


def _normalise(language: str) -> str:
    """`Ancient_Greek`, `AncientGreek` and `ancient greek` all key the same entry."""
    return re.sub(r"[^a-z]", "", language.lower())


@lru_cache(maxsize=8)
def treebanks(version: str = CORPUS_VERSION) -> dict[str, Treebank]:
    root = DATA_ROOT / "treebanks" / f"v{version}"
    if not root.is_dir():
        raise FileNotFoundError(f"no treebanks at {root} -- run scripts/unpack.sh")

    families = language_families()
    found: dict[str, Treebank] = {}
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        match = _TREEBANK_DIR.match(entry.name)
        if not match:
            continue
        scheme, language, corpus = match.groups()
        found[entry.name] = Treebank(
            name=entry.name,
            scheme=scheme,
            language=language,
            corpus=corpus,
            family=families.get(_normalise(language), UNKNOWN_FAMILY),
            path=entry,
        )
    return found


def missing_families(version: str = CORPUS_VERSION) -> list[str]:
    """Languages present on disk with no entry in languageGroups.tsv.

    2.18 added ~80 languages since the 2.12 the current site was built on. They plot
    black/circle, i.e. indistinguishable from the genuinely-isolate languages, which is
    exactly the silent failure docs/data-intake.md section 3 warns about. The importer
    reports this list; `scripts/import_neo4j.py --strict` refuses to run while it is
    non-empty.
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
