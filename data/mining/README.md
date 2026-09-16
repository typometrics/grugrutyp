# data/mining/ — pattern-mining artefacts

Design and chapter todos: `docs/pattern-mining.md`. Everything here is **derived and
rebuildable**; nothing is served by the site, and nothing lands in the measure cache.

| path | producer | what |
|---|---|---|
| `cfc/<treebank>.json` | `scripts/mine_cfc_matrix.py` | Tier-1 per-treebank dump: (gupos, rel1, rel2, dupos) → n, n_right, Σdelta, Σ\|delta\|. Complete (root edges kept, marked `__0__`); `imported_at` recorded for staleness |
| `lang_cfc.<scheme>.tsv` | same, `--merge-only` | language-level sums (counts, never percentages) |
| `excluded_rels.tsv` | hand | relations excluded at mining time (scheme-fixed / non-headed) |
| `measures.<scheme>.tsv` | `scripts/mine_shapes.py` | language × measure long table with counts + Wilson CI |
| `oned.<scheme>.tsv` | same | 1-D battery per measure |
| `shapes.<scheme>.tsv` | same | pair battery, every scored pair, components kept separate |
| `ranked.<scheme>.md` | same | human-readable top-k — **hypotheses, not claims** |
| `catalogue.json` | hand | Tier-2 (S, Q) catalogue with per-entry rationale + verification status |
| `tier2/<key>.tsv` | `scripts/mine_catalogue.py` | one Tier-2 measure per file, language-level |
| `findings.json` | hand-curated from the above | the site's Findings tab (`GET /findings`): title, why-it-matters prose, full plot state per entry |
