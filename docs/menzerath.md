# Can the Menzerath measures run as Grew queries?

Kim's question (ideas.md, 2026-08-29), about
[typometrics/UDW26-Menzerath](https://github.com/typometrics/UDW26-Menzerath)
(Faghiri, Gerdes & Kahane 2026, *Verifying the Menzerath-Altmann law in the verbal
domain in 180 languages*).

## What the pipeline measures

For every verb: the number of direct dependents (per side, and by position L2 L1 V R1 R2),
and the **size of each dependent's subtree** in words. MAL is "the longer the construct,
the shorter its constituents": mean constituent size should *fall* as the number of
dependents grows. β comes from a log-log regression of mean size against dependent count.

## Verdict: not in Grew alone — yes with two importer properties

Grew has no aggregation and no subtree arithmetic, and the paper's pipeline is custom
Python over CoNLL for exactly that reason. Our measure layer is *almost* there: the
missing quantities are per-node numbers, and we already precompute per-sentence numbers
(`sentence.height`, `sentence.length`) at import. The same move covers Menzerath:

| new Word property | meaning | cost |
|---|---|---|
| `subtree_size` | tokens in the node's projection (itself + all descendants) | one tree walk per sentence at import |
| `n_children` (+ `n_left`, `n_right`) | direct dependents, total and per side | out-degree, trivial |

Because FEATS are flattened onto nodes, these become ordinary features the moment they
exist — **no changes to the translator, measure layer, or cache**:

* aggregate axis: scope `pattern { V [upos=VERB]; V -> DEP }`,
  expression `DEP.subtree_size`, aggregation `avg` → mean constituent size per language;
* search clustering: cluster by `V.n_children` (or `V.n_right`) → the per-n table of the
  paper's helix analysis, straight out of the database; double-cluster with a whether
  (`DEP << V`) to split left/right constituents.

The position dimension (L1 vs L2…) would need a rank-among-siblings property on the
`DEPREL` edge (`dep_rank`), same import-time move, lower priority.

## β itself

β per language is a regression coefficient, which no sum-of-counts aggregation gives —
but a `slope()` aggregation is *mergeable*: accumulate (n, Σx, Σy, Σxy, Σx²) over
matchings with x = log `V.n_children`, y = log `DEP.subtree_size`, sum the five across
treebanks, divide once at the end — exactly the pattern `avg` already uses. That is a
per-matching regression rather than the paper's regression over per-n means; a variant,
not a replica. The replica stays a two-step: clustered counts out of the API, regression
client-side.

## Order of work — status 2026-08-29

1. **Done.** `conllu.menzerath_features` (unit-tested, cycle-safe) runs in the importer,
   and `scripts/backfill_menzerath.py` writes the same values onto the current import
   from the stored conllu — resumable, does not touch `imported_at` (counts are
   unchanged, so the measure cache survives). Measured ~3.8k words/s ≈ 5.5 h for the
   full corpus. Verified on French-ParTUT: `avg(DEP.subtree_size)` over
   `pattern { V [upos=VERB]; V -> DEP }` returns 6.70 words over 6 563 matchings with
   zero translator changes.
2. **Done.** Presets "Mean constituent size (Menzerath)" and "Mean dependents per verb"
   (group *Menzerath*), plus two clustering examples in the search library
   (`V.n_children`; `DEP.subtree_size` × whether `DEP << V`). Run `warm_cache.py` after
   the backfill so the preset plots serve from cache.
3. **Deferred, with a concrete blocker.** A `slope()` aggregation is mergeable in
   principle (five sufficient statistics), but the measure cache stores exactly one REAL
   numerator per row — slope needs five, so it is a cache-schema change, not an
   aggregation entry. `dep_rank` (position tables) likewise waits for a reason to pay an
   edge-property backfill.
