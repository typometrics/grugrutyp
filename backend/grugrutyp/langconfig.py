"""Language configuration: display names, groupings, plot colours and markers.

The data comes from `data/meta/*.tsv`, extracted from Kim's configuration spreadsheet by
`scripts/xlsx2config.py`. Rationale and the full column semantics are in
`docs/language-config.md`. What matters here:

* A language belongs to **several** groupings at once -- genetic group, genus, sub-genus,
  a coarse "simple group", a geographic area, and a typological class. The old site
  flattened them into one string and could therefore offer exactly one colouring. We keep
  the columns, so "colour by" becomes a control instead of a deployment.
* `appearance.tsv` is keyed on group *labels*, and the labels of a fine view are not all
  present in it. Lookup therefore walks from the most specific label to the least
  (`typology -> genus -> group -> simple_group -> Other`) rather than failing to black.
  Hindi keeps Indo-European blue even though nothing colours `Indo-Aryan` specifically.
* Nothing here raises on an unknown language. A missing entry is a *reportable* condition
  (`audit()`), not a crash -- but it is never silent either, which is the failure mode the
  old setup had.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from .meta import DATA_ROOT, CORPUS_VERSION

META_DIR = DATA_ROOT / "meta"

UNKNOWN = "unknown"
FALLBACK_GROUP = "Other"
DEFAULT_COLOR = "darkGrey"
DEFAULT_MARKER = "circle"

# `genus` is a real sub-branch except for this value, which the sheet uses to mean "inside
# this group but not in any of the named branches". As a label it says nothing, so views
# that would show it fall back to the group.
GENUS_NONE = "Other"

# view name -> the columns to try, most specific first.
# `family` reproduces the granularity the current site plots at; the others are the extra
# views the spreadsheet has always contained but the export threw away.
VIEWS: dict[str, tuple[str, ...]] = {
    "family": ("typology", "genus", "group"),
    "group": ("group",),
    "genus": ("genus", "group"),
    "simple_group": ("simple_group",),
    "area": ("area",),
    "typology": ("typology", "group"),
}
DEFAULT_VIEW = "family"

# Order in which appearance.tsv is consulted for a *genetic* view: most specific first, so
# a fine label inherits its parent's colour rather than going grey.
APPEARANCE_CHAIN = ("typology", "genus", "group", "simple_group")

# `area` is geographic, so genetic inheritance is meaningless for it: every European
# language would take its own family's colour while sharing the label `E`, and the legend
# would show one of those colours for all of them. Views listed here get a generated
# palette instead, keyed on the label so it stays stable between runs.
NON_GENETIC_VIEWS = {"area"}

# Chart.js colour names, chosen to stay distinguishable next to each other and to avoid
# the ones `appearance.tsv` already uses for families.
PALETTE = (
    "royalBlue", "orange", "forestGreen", "mediumVioletRed", "cadetBlue",
    "brown", "purple", "olive", "teal", "crimson", "darkSeaGreen", "goldenRod",
)
PALETTE_MARKERS = ("circle", "triangle", "rect", "star", "cross", "rectRot", "crossRot")


def _palette_for(label: str) -> Appearance:
    """A stable colour and marker for a label nobody has styled.

    Deterministic, not sequential: the same area must keep the same colour whichever
    subset of languages happens to be on the plot, or two screenshots of the same data
    would not be comparable.
    """
    digest = int(hashlib.blake2b(label.encode("utf-8"), digest_size=4).hexdigest(), 16)
    return Appearance(
        label=label,
        color=PALETTE[digest % len(PALETTE)],
        marker=PALETTE_MARKERS[(digest // len(PALETTE)) % len(PALETTE_MARKERS)],
    )


@dataclass(frozen=True)
class LanguageRow:
    """One row of `languages.tsv` -- every grouping known for one language."""

    language: str
    group: str = ""
    genus: str = ""
    subgenus: str = ""
    simple_group: str = ""
    area: str = ""
    typology: str = ""
    # The ISO code of the treebanks this row describes. Not in Kim's spreadsheet, which
    # keys on the language name -- and that is precisely what breaks every release, since
    # UD renames directories (`Wu` -> `Shanghainese`, `Oriya` -> `Odia`) while keeping the
    # code. Filled in by `scripts/config_audit.py --backfill-lcodes` and by the admin page
    # as each rename is confirmed; once populated, a rename is a no-op instead of a
    # vanished language. See `docs/language-config.md` section 4.
    lcode: str = ""

    def label(self, view: str = DEFAULT_VIEW) -> str:
        for column in VIEWS.get(view, VIEWS[DEFAULT_VIEW]):
            value = getattr(self, column, "")
            if value and not (column == "genus" and value == GENUS_NONE):
                return value
        return UNKNOWN


@dataclass(frozen=True)
class Appearance:
    label: str
    color: str
    marker: str


def _fold(name: str) -> str:
    """`Ancient_Greek`, `AncientGreek`, `Xavánte`/`Xavante`, `Gwichʼin`/`Gwichin` all key
    the same row.

    Accent folding is not cosmetic: the spreadsheet spells languages the way a linguist
    writes them (`Apurinã`, `Mundurukú`, `Macro-Jê`) while UD spells its directories in
    ASCII (`Apurina`, `Munduruku`). Without folding, 10 languages of 2.18 silently lose
    their grouping.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", stripped.lower())


def _read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    if not lines:
        return []
    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        if not line.strip():
            continue
        values = line.split("\t")
        values += [""] * (len(headers) - len(values))
        rows.append({h: v.strip() for h, v in zip(headers, values)})
    return rows


@lru_cache(maxsize=1)
def languages() -> dict[str, LanguageRow]:
    """Folded language name -> its groupings."""
    out: dict[str, LanguageRow] = {}
    for row in _read_tsv(META_DIR / "languages.tsv"):
        if not row.get("language"):
            continue
        entry = LanguageRow(**{k: row.get(k, "") for k in LanguageRow.__annotations__})
        out[_fold(entry.language)] = entry
    return out


@lru_cache(maxsize=1)
def appearances() -> dict[str, Appearance]:
    """Folded group label -> colour and marker."""
    out: dict[str, Appearance] = {}
    for row in _read_tsv(META_DIR / "appearance.tsv"):
        label = row.get("group", "")
        if not label:
            continue
        out[_fold(label)] = Appearance(
            label=label,
            color=row.get("color") or DEFAULT_COLOR,
            marker=row.get("marker") or DEFAULT_MARKER,
        )
    return out


@lru_cache(maxsize=1)
def display_names() -> dict[str, str]:
    """ISO code -> the name to print.

    `iso639.tsv` is the reference list and is not meant to be edited; `language_names.tsv`
    is the curated override, and wins. The rule the sheet states for itself is that a
    display name must not contain spaces, because the old pipeline used TSV columns and a
    space-separated legend.
    """
    names = {row["code"]: row["name"] for row in _read_tsv(META_DIR / "iso639.tsv") if row.get("code")}
    names.update(
        {row["code"]: row["name"] for row in _read_tsv(META_DIR / "language_names.tsv") if row.get("code")}
    )
    return names


@lru_cache(maxsize=1)
def by_lcode() -> dict[str, LanguageRow]:
    """ISO code -> row, for the rows that carry one."""
    return {row.lcode: row for row in languages().values() if row.lcode}


@lru_cache(maxsize=8)
def disk_lcodes(version: str = CORPUS_VERSION) -> dict[str, str]:
    """Language name on disk -> its ISO code, read from the CoNLL-U filenames.

    UD names its files `<lcode>_<corpus>-ud-<split>.conllu`, so the code is free to
    obtain. A handful of treebanks (the Autogramm ones, `French-ParisStories`,
    `French-Rhapsodie`) do not follow the convention; they simply get no code, and fall
    back to name matching.
    """
    from .meta import treebanks

    out: dict[str, str] = {}
    for tb in treebanks(version).values():
        files = tb.conllu_files()
        if not files:
            continue
        code = files[0].name.split("_")[0]
        # Real codes are short and lowercase; `ParisStories` and `annodis.er.conllu` are not.
        if code.isalpha() and code.islower() and 2 <= len(code) <= 3:
            out.setdefault(tb.language, code)
    return out


@lru_cache(maxsize=1)
def measure_exclusions() -> frozenset[tuple[str, str]]:
    """(language, corpus) pairs excluded from MEASURE merging.

    These treebanks stay searchable and importable -- the exclusion only keeps them out
    of a language's summed point, where they provably double-count: Chinese-GSDSimp is
    GSD re-scripted, the Japanese *LUW treebanks are the same texts re-tokenized
    (audit 2026-09-02, typology §2). Applied in `runner.select()`.
    """
    path = META_DIR / "measure_exclusions.tsv"
    if not path.exists():
        return frozenset()
    return frozenset(
        (row["language"], row["corpus"])
        for row in _read_tsv(path)
        if row.get("language") and row.get("corpus")
    )


def reload() -> None:
    """Drop every cached table so the next read sees the file as it is now.

    The caches exist because the TSVs are read on every plot; they become stale the
    moment the admin page writes one. Called by the admin routes after each write --
    a config edit that only takes effect on the next service restart would look like a
    failed edit.
    """
    for cached in (languages, appearances, display_names, by_lcode, measure_exclusions):
        cached.cache_clear()


def lookup(language: str, lcode: str = "") -> LanguageRow | None:
    """Find a language's row, by ISO code first and by name second.

    Code first is what makes the configuration survive a release: `Shanghainese` has no
    row of its own, but it is `wuu`, and the row that used to be called `Wu` is `wuu` too.
    """
    if lcode:
        found = by_lcode().get(lcode)
        if found:
            return found
    return languages().get(_fold(language))


def _resolve(language: str, lcode: str = "") -> LanguageRow | None:
    """`lookup`, filling the ISO code in from disk when the caller does not know it."""
    return lookup(language, lcode or disk_lcodes().get(language, ""))


def label_of(language: str, view: str = DEFAULT_VIEW, lcode: str = "") -> str:
    row = _resolve(language, lcode)
    return row.label(view) if row else UNKNOWN


def appearance_of(language: str, view: str = DEFAULT_VIEW, lcode: str = "") -> Appearance:
    """Colour and marker for a language under a given view.

    Three ways to get there, tried in order:

    1. the view's own label is styled in `appearance.tsv` -- use the curated colour;
    2. the view is genetic, so walk up to the parent grouping. Hindi's label is
       `Indo-Aryan`, which nobody styles, but `Indo-European` is styled and is the right
       answer -- the legend stays specific while the palette stays legible;
    3. otherwise a generated palette keyed on the label, so that a non-genetic view like
       `area` colours by area rather than by family.
    """
    row = _resolve(language, lcode)
    table = appearances()
    if row is None:
        fallback = table.get(_fold(FALLBACK_GROUP))
        return Appearance(UNKNOWN, fallback.color if fallback else DEFAULT_COLOR, DEFAULT_MARKER)

    label = row.label(view)
    exact = table.get(_fold(label))
    if exact:
        return Appearance(label, exact.color, exact.marker)

    if view in NON_GENETIC_VIEWS:
        return _palette_for(label) if label != UNKNOWN else Appearance(
            label, DEFAULT_COLOR, DEFAULT_MARKER
        )

    for column in APPEARANCE_CHAIN:
        value = getattr(row, column, "")
        if not value or (column == "genus" and value == GENUS_NONE):
            continue
        found = table.get(_fold(value))
        if found:
            return Appearance(label, found.color, found.marker)

    fallback = table.get(_fold(FALLBACK_GROUP))
    return Appearance(
        label,
        fallback.color if fallback else DEFAULT_COLOR,
        fallback.marker if fallback else DEFAULT_MARKER,
    )


def legend(view: str = DEFAULT_VIEW, present: list[str] | None = None) -> list[dict]:
    """The plot legend: one entry per distinct label, with its colour and marker.

    `present` restricts it to the languages actually plotted -- a legend listing 190
    languages' worth of groups when 12 are on screen is noise.
    """
    names = present if present is not None else [row.language for row in languages().values()]
    seen: dict[str, dict] = {}
    for name in names:
        look = appearance_of(name, view)
        entry = seen.setdefault(
            look.label, {"label": look.label, "color": look.color, "marker": look.marker, "n": 0}
        )
        entry["n"] += 1
    return sorted(seen.values(), key=lambda e: (-e["n"], e["label"]))


# --------------------------------------------------------------------------- audit


@dataclass
class Audit:
    """What a new UD release did to the configuration.

    This is the whole reason the config is a first-class object rather than three TSVs
    nobody looks at. Each release adds languages and occasionally renames or drops one,
    and none of that raises an error by itself -- an unconfigured language just plots grey
    in the corner. `scripts/config_audit.py` prints this; the admin page shows it.
    """

    version: str
    unconfigured: list[str] = field(default_factory=list)  # on disk, no row
    orphaned: list[str] = field(default_factory=list)  # row, not on disk
    unstyled: list[str] = field(default_factory=list)  # label with no appearance entry
    incomplete: list[str] = field(default_factory=list)  # row present, columns empty
    renames: list[dict] = field(default_factory=list)  # probable unconfigured <- orphaned

    @property
    def clean(self) -> bool:
        return not (self.unconfigured or self.unstyled or self.incomplete)

    def to_dict(self) -> dict:
        return {**asdict(self), "clean": self.clean}


# Below this similarity, a pairing is more likely to mislead than to help, and the admin
# is better off classifying the language from scratch.
RENAME_THRESHOLD = 0.72


def _suggest_renames(
    unconfigured: list[str],
    orphaned: list[str],
    lcodes: dict[str, str] | None = None,
) -> list[dict]:
    """Pair each newly-unconfigured language with the orphan it probably used to be.

    Most of what a UD release presents as "new languages" is not new at all: 2.18 renamed
    `Wu` to `Shanghainese`, `Oriya` to `Odia`, `Kurmanji` to `Northern_Kurdish`,
    `ClassChinese` to `Classical_Chinese` and twenty more in the same vein. Reported as
    two flat lists, that is 35 languages to classify by hand; reported as pairs, it is
    mostly confirmations, and the few genuinely new languages stand out.

    The pairing is a suggestion and is never applied automatically -- `Naga`/`Tangkhul`
    and `Bokota`/`Buglere` are right, but only a linguist can say so.
    """
    remaining = list(orphaned)
    out = []
    configured = languages()
    lcodes = lcodes or {}

    # First pass: an exact ISO-code match is not a guess, so take those before the fuzzy
    # matcher gets a chance to pair the names off against something merely similar.
    for name in list(unconfigured):
        code = lcodes.get(name)
        if not code:
            continue
        for candidate in list(remaining):
            if configured[_fold(candidate)].lcode == code:
                remaining.remove(candidate)
                out.append({"language": name, "was": candidate, "confidence": 1.0, "via": "lcode"})
                break

    # Second pass: the curated name table already records what this code used to be
    # called. `wuu` is `Wu` in `language_names.tsv` and `Shanghainese` on disk, so the
    # bridge between the two names is sitting right there -- it just was never consulted.
    paired = {entry["language"] for entry in out}
    names = display_names()
    for name in unconfigured:
        if name in paired:
            continue
        old_name = names.get(lcodes.get(name, ""), "")
        if not old_name:
            continue
        for candidate in list(remaining):
            if _fold(candidate) == _fold(old_name):
                remaining.remove(candidate)
                out.append(
                    {"language": name, "was": candidate, "confidence": 0.95, "via": "iso-name"}
                )
                break

    paired = {entry["language"] for entry in out}
    for name in unconfigured:
        if name in paired:
            continue
        folded = _fold(name)
        best, score = None, 0.0
        for candidate in remaining:
            ratio = difflib.SequenceMatcher(None, folded, _fold(candidate)).ratio()
            # A short name fully contained in a longer one (`Naga` in `TangkhulNaga`,
            # `Komi` in `KomiZyrian`) scores badly on ratio but is a strong signal.
            other = _fold(candidate)
            if folded in other or other in folded:
                ratio = max(ratio, 0.8)
            if ratio > score:
                best, score = candidate, ratio
        if best and score >= RENAME_THRESHOLD:
            remaining.remove(best)
            out.append(
                {"language": name, "was": best, "confidence": round(score, 3), "via": "name"}
            )
    return sorted(out, key=lambda e: (-e["confidence"], e["language"]))


def audit(version: str = CORPUS_VERSION, present: list[str] | None = None) -> Audit:
    """Compare the configuration against the languages actually present.

    `present` defaults to the languages on disk for `version`; the API passes the ones in
    the database instead, so the report describes what a user can actually plot.
    """
    if present is None:
        from .meta import treebanks

        present = sorted({tb.language for tb in treebanks(version).values()})

    lcodes = disk_lcodes(version)
    configured = languages()
    resolved = {name: _resolve(name, lcodes.get(name, "")) for name in present}

    unconfigured = sorted(name for name, row in resolved.items() if row is None)
    matched = {row.language for row in resolved.values() if row is not None}
    orphaned = sorted(row.language for row in configured.values() if row.language not in matched)

    incomplete, unstyled = [], set()
    table = appearances()
    for name, row in sorted(resolved.items()):
        if row is None:
            continue
        if not row.group and not row.simple_group:
            incomplete.append(name)
        if not any(
            getattr(row, column, "") and _fold(getattr(row, column)) in table
            for column in APPEARANCE_CHAIN
        ):
            unstyled.add(row.label())

    return Audit(
        version=version,
        unconfigured=unconfigured,
        orphaned=orphaned,
        unstyled=sorted(unstyled),
        incomplete=incomplete,
        renames=_suggest_renames(unconfigured, orphaned, lcodes),
    )
