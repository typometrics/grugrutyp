"""Language configuration -- re-exported from `udcorpus.languages` (corpus/udcorpus/).

The code and the TSVs it reads (`corpus/meta/`) moved into the standalone `udcorpus`
package on 2026-11-24, so that ingestion and metadata attribution can be handed to
someone who will never run grugrutyp (`corpus/README.md`). This module keeps every
grugrutyp import working unchanged. The rationale for the groupings and the curation
rules are still in `docs/language-config.md`.

The metadata directory is read at call time (`meta_dir()`); to point it elsewhere (a test,
a scratch copy) call `udcorpus.config.configure(meta_dir=...)` -- assigning a module
constant here would change nothing.
"""

from __future__ import annotations

from . import meta as _meta  # noqa: F401 -- configures udcorpus (data root, live release)

from udcorpus.languages import (  # noqa: E402,F401
    APPEARANCE_CHAIN,
    DEFAULT_COLOR,
    DEFAULT_MARKER,
    DEFAULT_VIEW,
    FALLBACK_GROUP,
    GENUS_NONE,
    NON_GENETIC_VIEWS,
    PALETTE,
    PALETTE_MARKERS,
    RENAME_THRESHOLD,
    UNKNOWN,
    VIEWS,
    Appearance,
    Audit,
    LanguageRow,
    _fold,
    _read_tsv,
    _resolve,
    _suggest_renames,
    appearance_of,
    appearances,
    audit,
    by_lcode,
    disk_lcodes,
    display_names,
    fold,
    label_of,
    languages,
    legend,
    lookup,
    measure_exclusions,
    meta_dir,
    read_tsv,
    reload,
    row_for,
)
