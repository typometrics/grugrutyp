"""Which treebanks exist, which CoNLL-U files they consist of, which language they belong to.

A release unpacks into one directory per treebank, UD and SUD side by side:

    treebanks/v2.19/UD_French-GSD/fr_gsd-ud-{train,dev,test}.conllu
    treebanks/v2.19/SUD_French-GSD/fr_gsd-sud-{train,dev,test}.conllu

The directory name is `<scheme>_<Language>-<Corpus>`; the language keeps its underscores
(`Ancient_Greek`). **Every `*.conllu` file of a treebank is taken** -- train, dev and test
together: the split exists for parser training and means nothing to a corpus count.

For measures, a language is the sum of its treebanks in one scheme, minus the pairs in
`meta/measure_exclusions.tsv` (treebanks that duplicate another one's text, and learner
corpora); see `measure_selection()`. Excluded treebanks are still listed by `treebanks()` --
they are excluded from measures, not from existence.

    python -m udcorpus.treebanks                     # summary of the release on disk
    python -m udcorpus.treebanks --scheme SUD --files  # every language -> its files
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import config

_TREEBANK_DIR = re.compile(r"^(UD|SUD)_([A-Za-z_]+?)-([A-Za-z0-9]+)$")

UNKNOWN_FAMILY = "unknown"


@dataclass(frozen=True)
class Treebank:
    name: str  # SUD_French-GSD
    scheme: str  # SUD | UD
    language: str  # French  (underscores kept: Ancient_Greek)
    corpus: str  # GSD
    family: str  # the language's label in the default view, "unknown" if unconfigured
    path: Path
    lcode: str = ""  # fr -- from the CoNLL-U filenames, "" for the few that do not follow

    @property
    def color(self) -> str:
        from .languages import appearance_of

        return appearance_of(self.language, lcode=self.lcode).color

    @property
    def marker(self) -> str:
        from .languages import appearance_of

        return appearance_of(self.language, lcode=self.lcode).marker

    def conllu_files(self) -> list[Path]:
        return sorted(self.path.glob("*.conllu"))


@lru_cache(maxsize=8)
def _treebanks(root: Path, version: str) -> dict[str, Treebank]:
    if not root.is_dir():
        raise FileNotFoundError(f"no treebanks at {root} -- run unpack.sh")

    # `lookup`, not `label_of`: the latter fills a missing ISO code in from disk, which
    # would call back into this function while it is still building its cache.
    from .languages import UNKNOWN, lookup

    found: dict[str, Treebank] = {}
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        match = _TREEBANK_DIR.match(entry.name)
        if not match:
            continue
        scheme, language, corpus = match.groups()
        lcode = lcode_of(entry)
        row = lookup(language, lcode)
        found[entry.name] = Treebank(
            name=entry.name,
            scheme=scheme,
            language=language,
            corpus=corpus,
            family=row.label() if row else UNKNOWN,
            path=entry,
            lcode=lcode,
        )
    return found


def treebanks(version: str | None = None) -> dict[str, Treebank]:
    """Treebank directory name -> Treebank, for one release (default: see `config`)."""
    version = version or config.default_version()
    return _treebanks(config.treebanks_root(version), version)


def reload() -> None:
    _treebanks.cache_clear()


def lcode_of(directory: Path) -> str:
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


def missing_families(version: str | None = None) -> list[str]:
    """Languages present on disk with no row in `meta/languages.tsv`.

    An unconfigured language does not fail -- it plots grey, indistinguishable from a
    genuine isolate. `python -m udcorpus.audit` says what to do about it, including which
    entries are renames rather than new languages.
    """
    return sorted(
        {tb.language for tb in treebanks(version).values() if tb.family == UNKNOWN_FAMILY}
    )


def measure_selection(scheme: str, version: str | None = None) -> dict[str, list[Treebank]]:
    """Language -> the treebanks whose counts are summed into that language's point.

    One scheme only (a UD and an SUD treebank of the same text are two annotations of
    it, not two corpora), minus `meta/measure_exclusions.tsv`. This is exactly the
    selection grugrutyp's plots use.
    """
    from .languages import measure_exclusions

    excluded = measure_exclusions()
    out: dict[str, list[Treebank]] = {}
    for tb in treebanks(version).values():
        if tb.scheme != scheme.upper() or (tb.language, tb.corpus) in excluded:
            continue
        out.setdefault(tb.language, []).append(tb)
    return {language: sorted(tbs, key=lambda t: t.name) for language, tbs in sorted(out.items())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", help="release, e.g. 2.19 (default: highest on disk)")
    ap.add_argument("--scheme", choices=["SUD", "UD"], default="SUD")
    ap.add_argument("--files", action="store_true", help="list every CoNLL-U file")
    args = ap.parse_args()

    version = args.version or config.default_version()
    every = treebanks(version)
    selection = measure_selection(args.scheme, version)
    n_selected = sum(len(v) for v in selection.values())
    n_scheme = sum(1 for tb in every.values() if tb.scheme == args.scheme)
    print(f"release {version} at {config.treebanks_root(version)}")
    print(f"  {sum(1 for t in every.values() if t.scheme == 'UD')} UD, "
          f"{sum(1 for t in every.values() if t.scheme == 'SUD')} SUD treebank directories")
    print(f"  {args.scheme}: {n_selected} of {n_scheme} treebanks enter measures, "
          f"{len(selection)} languages")
    missing = missing_families(version)
    if missing:
        print(f"  {len(missing)} languages have no configuration row -- run python -m udcorpus.audit")
    print()
    for language, tbs in selection.items():
        print(f"{language}\t{tbs[0].family}\t" + ", ".join(tb.corpus for tb in tbs))
        if args.files:
            for tb in tbs:
                for path in tb.conllu_files():
                    print(f"    {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
