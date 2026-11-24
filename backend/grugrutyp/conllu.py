"""CoNLL-U reading -- re-exported from `udcorpus.conllu` (corpus/udcorpus/), plus the one
grugrutyp-specific constant the Neo4j importer needs.

The reader moved into the standalone `udcorpus` package on 2026-11-24 (`corpus/README.md`).
"""

from __future__ import annotations

from . import meta as _meta  # noqa: F401 -- puts corpus/ on sys.path via the package init

from udcorpus.conllu import (  # noqa: E402,F401
    DEPREL,
    DEPS,
    FEATS,
    FORM,
    HEAD,
    ID,
    LEMMA,
    MISC,
    UPOS,
    XPOS,
    Mwt,
    Sentence,
    Word,
    decompose_deprel,
    is_projective,
    is_tree,
    menzerath_features,
    read_conllu,
    sample_bucket,
    sentence_from_conllu,
    tree_height,
)

# Property names we must not clash with when flattening FEATS/MISC onto the Word node.
RESERVED_WORD_PROPS = frozenset(
    {
        "treebank", "sent_id", "idx", "form", "lemma", "upos", "xpos", "head", "deprel",
        # Menzerath features precomputed at import (docs/menzerath.md); a hypothetical
        # conllu FEAT of the same name must not overwrite them.
        "subtree_size", "n_children", "n_left", "n_right",
    }
)
