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

## The counters as pattern constraints (2026-09-02)

`subtree_size`, `n_children`, `n_left`, `n_right` are also testable with `=` in any
block: `with { S.subtree_size = 2 }` restricts a scope to two-token subjects. This
came out of a chat failure: the model proposed exactly that query, the emitter bound
the value as the **string** "2" against the **integer** property, and Cypher's typed
equality silently matched nothing corpus-wide — a dead axis that looked like a
typological finding of zero. The emitter now binds integer parameters for these four
properties (`NUMERIC_NODE_PROPS` in `translate/cypher.py`; test
`test_numeric_counters_bind_as_integers`). Verified on SUD English-GUM: 2-token
subjects 5.0% inverted (139/2 776), 3-token 7.2% (84/1 164).

Alongside it, the LLM path gained a feature-name gate (`nl2grew._check_features`):
a name no treebank has ever carried (`S.depth`, `S.weight`) is bounced back to the
model with the inventory error, exactly like a validation failure. Hand-typed queries
keep the database-free `validate()`; their protection remains the live preview and
the dead-axis banner.

**The cache aftermath, same day.** The first (broken) run had cached its zeros, and
the measure-cache key — treebank, corpus version, import revision, query hash — does
not know the *translator*: after the emitter fix, a replot served 191 languages of
stale zero from cache and computed only the escalated handful fresh. Stale rows from
a semantic emitter change do not look stale, they look like counts. The remedy is a
targeted purge (recompute the affected specs' `query_hash`, delete those rows —
740 rows here, found via the query log; a blanket version bump would have thrown
away the whole warm cache, which on these disks is worth hours). The rule now lives
on the schema in `cache.py`: emitter semantics changed → purge the affected hashes
in the same sitting.

## The a/b/c fits (2026-09-04)

`scripts/menzerath_fit.py` fits the Menzerath–Altmann law per language,

    y(x) = a · x^b · e^(−c·x)      x = dependents of the verb, y = mean constituent size

closing the gap the preset library left: the presets plot the raw quantities, never the
fitted curve. Output: `data/meta/menzerath_abc.tsv` (193 languages, one row per side).

**Method.** One grouped query per treebank returns the joint distribution of
(`V.n_children` × `DEP.subtree_size`), so the per-x mean constituent size is exact
rather than estimated; the fit is then ordinary least squares on
`ln y = ln a + b·ln x − c·x`, weighted by the number of constituents behind each mean.
No optimiser, no starting point, nothing to converge. Sampled at the standard
100k-tokens-per-language budget — a cold full pass is hours on this array, and three
parameters need the distribution's shape, not every token. Each row carries `coverage`:
if a treebank's query fails twice (the retry halves the sample rate first), the language
is still fitted but the row says from how much of its corpus, because a partial fit that
looks complete is the one failure mode this project is organised against.

**Result.** 193 languages fitted, no failures, full coverage. Of the 134 with R² ≥ 0.5,
**103 (77%) have b < 0** — mean constituent size falls as the verb takes more
dependents, which is the Menzerath prediction. Median R² is 0.755.

**Not a replica of the old site's columns, and deliberately so.** Correlating against
`abc.languages.v2.12_sud_typometricsformat.tsv` (113 shared languages, `*_any_root_any`):

| parameter | legacy range | ours | Spearman |
|---|---|---|---|
| a | 1.05 – 12.65 | 0.89 – 9.24 | **+0.66** |
| b | 1.31 – 15.26 (all positive) | −1.37 – 0.65 | −0.23 |
| c | 1.44 – 16.87 (all positive) | −0.46 – 0.23 | −0.08 |

`a` behaves like the same quantity; `b` and `c` do not — theirs are positive and an
order of magnitude larger, ours are the exponents of the standard form. So the legacy
columns are a **different parameterisation**, not a different corpus, and the doc's own
rule applies: do not port a formula we cannot read. Ours is the textbook MAL form,
verified by its fit quality and by the sign of `b` across 134 languages; the legacy
numbers stay unreproduced until someone who knows that pipeline says what its a/b/c are.
**Question for Kim** (a co-author of the UDW26 paper): what are the old `a`, `b`, `c`?
