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

## Order of work, when picked up

1. Importer writes `subtree_size`, `n_children`, `n_left`, `n_right` (and a backfill
   script for the current import, from the stored per-sentence conllu — no re-download).
2. Nothing else: presets "Mean constituent size (Menzerath)" for the plot and a
   clustering example for the search tab, added to the libraries.
3. Later, if wanted: `slope` aggregation; `dep_rank` edge property for the position
   tables.
