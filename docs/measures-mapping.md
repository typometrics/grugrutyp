# Can the current typometrics measures be reproduced by Grew query pairs?

Answers `ideas.md`: *"analyze which of the pre-computed measures we have today in
typometrics can be reproduced by grew queries. analyze what to do about this."*

Sources: `datapreparation/statConll.py`, `djangotypometrics/typometricsapp/tsv2json.py`,
the TSV headers in `djangotypometrics/{s,}ud-treebanks-v2.12-analysis/`.

Verdict column:
**A** = exact (S, Q) ratio pair · **B** = needs the *aggregate* mode
(mean of a numeric expression) · **C** = derived in Python from several A/B results ·
**D** = not query-shaped, keep a batch job.

---

## 1. Measures exposed by the current API

| API type | file | what it is | verdict |
|---|---|---|---|
| `distribution` | `f.tsv` | % of dependencies bearing relation *r* | **A** |
| `head-initiality` | `positive-direction.tsv` (UD) / `head_initiality_comb.tsv` (SUD) | % of *r*-dependencies where the dependent follows the governor | **A** |
| `head-initiality-cfc` | `posdircfc.tsv` / `direction-cfc_extend.tsv` | same, split by govPOS-*r*-depPOS | **A** |
| `freq-cfc` | `cfc.tsv` / `distribution-cfc_extend.tsv` | % of dependencies that are govPOS-*r*-depPOS | **A** |
| `distance` | `f-dist.tsv` | mean signed linear distance dep−gov for relation *r* | **B** |
| `distance-abs` | `f-dist-abs.tsv` | mean absolute distance | **B** |
| `distance-cfc` | `cfc-dist.tsv` | mean signed distance by govPOS-*r*-depPOS | **B** |
| `treeHeight` | `height.tsv` | mean tree height per sentence | **B** (sentence-scope) |
| `flexibility` | `flexibility_rel.tsv` | word-order flexibility per relation | **C** |
| `flexibility-cfc` | `flexibility_cfc_all.tsv` | same by govPOS-*r*-depPOS | **C** |
| `menzerath` | `abc.languages.*_typometricsformat.tsv` | fitted a/b/c of the Menzerath–Altmann law, in 30+ variants | **D** |
| `flex_compare_Bakker` | `bak_vs_typo.tsv` | 3 columns comparing to Bakker's typology | **D** (external data) |

Not exposed by the API but present in the analysis folders: `cat.tsv` (POS distribution,
**A**), `cf.tsv`, `fc.tsv` (**A**), `cf-dist.tsv` (**B**), `f-dist-noroot.tsv`,
`abs-f-dist-noroot.tsv` (**B**).

**Score: 6 of 12 exposed measures are exact query pairs (A); 4 more are one small
extension away (B); 2 are genuinely different objects (D).**

---

## 2. The A measures, written out

`r` is any relation, `C`/`C'` any UPOS.

```grew
%%% distribution — f.tsv[r]
S: pattern { GOV -> DEP }
Q: with    { GOV -[1=r]-> DEP }

%%% head-initiality — positive-direction.tsv[r]
S: pattern { GOV -[1=r]-> DEP }
Q: with    { GOV << DEP }

%%% head-initiality-cfc — posdircfc.tsv["C-r-C'"]
S: pattern { GOV [upos=C]; GOV -[1=r]-> DEP [upos=C'] }
Q: with    { GOV << DEP }

%%% freq-cfc — cfc.tsv["C-r-C'"]
S: pattern { GOV -> DEP }
Q: with    { GOV [upos=C]; GOV -[1=r]-> DEP [upos=C'] }

%%% cat.tsv[C]
S: pattern { X }
Q: with    { X [upos=C] }
```

### Three semantic mismatches to be explicit about

1. **Root dependencies are counted, in both systems.** `statConll.py` computes direction
   as `100 * |{d ∈ dists : d > 0}| / |dists|` with `d = ni - gi`, *including* root
   dependencies where `gi = 0`; a root's dependent always has `d > 0`, so roots inflate
   head-initiality. Grew does the same thing, because it materialises a virtual root node
   `__0__` at position 0 and makes the root dependency a real edge from it — so our
   encoding materialises it too (`neo4j-encoding.md` §2 dev. 4).

   The consequence is that the scope `pattern { GOV -[1=r]-> DEP }` **includes** root
   attachments, and `pattern { X }` counts tokens *plus* sentences. A measure that wants
   only word-to-word dependencies must exclude them explicitly:

   ```grew
   pattern { GOV -[1=subj]-> DEP }
   without { GOV [form="__0__"] }
   ```

   The old pipeline instead dropped `root` wholesale via `skipFuncs` (see point 2), which
   is a different exclusion — it removes the `root` *relation*, not root-attached
   dependencies of other relations. Both effects must be replayed when comparing numbers.

2. **Skipped relations.** `makeStatsThreaded(skipFuncs=['root','compound','fixed','flat','conj'])`
   silently drops those five relations from *every* table, and
   `skipLangs=['kk','sa','ug','lt','be','cop','ta']` drops seven languages. Grew queries
   have no such exclusions. Any comparison must re-apply them, and grugrutyp should
   surface them as an explicit, user-visible filter instead of a hidden constant.

3. **Simple vs full relation names.** `statConll.py` counts each dependency under *both*
   its simple function (`comp`) and its syntactic function (`comp:obj`), via
   `relationsplit` and the `@`-split. In Grew this is free and principled:
   `-[1=comp]->` is the simple function, `-[1=comp, 2=obj]->` the syntactic one,
   `-[deep=agent]->` the deep one (`grew-query-language.md` §1). One less hand-rolled
   string parser.

---

## 3. The B measures: the *aggregate* mode

`f-dist.tsv[r]` is `mean(ni - gi)` over all *r*-dependencies. Not a ratio, so not a query
pair — but it is the same scope query with a different reduction:

```
measure = mean over matchings of S of  delta(GOV, DEP)
```

In our Neo4j encoding `delta(GOV,DEP)` is `DEP.idx - GOV.idx`, so this is literally

```cypher
MATCH (GOV:Word {treebank:$tb})-[:DEPREL {rel_1:$r}]->(DEP:Word)
RETURN avg(DEP.idx - GOV.idx) AS value, count(*) AS n
```

So **B costs one extra field in the measure spec** (`aggregate: avg|median|stddev` and a
numeric expression) and no new query machinery. Supported expressions for v1.5:
`delta(X,Y)`, `abs(delta(X,Y))`, `length(X,Y)`, and `X.<numeric feature>`.

`treeHeight` is the exception inside B: its scope is *sentences*, not dependency
matchings, and the value (depth of the deepest node) is not a per-matching expression.
It needs either a sentence-level scope with a path-length aggregate, or — much cheaper —
precomputation of `height` as a property on the `Sentence` node at import time. **Do the
latter**; also precompute `n_tokens` and `is_projective` there. Then

```cypher
MATCH (s:Sentence {treebank:$tb}) RETURN avg(s.height)
```

and `is_projective` additionally gives us `global { is_projective }` for free
(`grew-query-language.md` §7), which the Cypher translator otherwise cannot express.

---

## 4. The C and D measures

### C — flexibility

`flexibility_rel.tsv` and `flexibility_cfc_all.tsv` are word-order flexibility per
relation. Given the head-initiality value `p(r)` for a relation, flexibility is a function
of how far `p` is from 0/100 — the tables' values (e.g. Amharic `subj` = 28.9 with
head-initiality nearby) are consistent with a rescaled `min(p, 100−p)`, but **the
producing script is not in this tree** (see §5), so the exact formula is unverified.

Action: flexibility is a **derived** measure — Python over the A results. Reimplement it
from the definition in the papers, then check the reimplementation against the 2.12 TSV
before trusting it. Do not port a formula we cannot read.

### D — Menzerath–Altmann and Bakker

`abc.languages.*_typometricsformat.tsv` holds fitted parameters `a`, `b`, `c` of the
Menzerath–Altmann law over ~30 subsets (`left/right/any` of root × relation subsets),
plus `nb_*` counts. This is a curve fit over the distribution of constituent lengths, not
a pattern-count ratio. It stays a **batch job**: a script that walks the treebanks (or
queries Neo4j for the length distributions) and fits the curve.

`bak_vs_typo.tsv` compares to Bakker's flexibility typology — external data, keep as a
static table.

---

## 5. Missing provenance — act on this

Of the 22 TSVs in `sud-treebanks-v2.12-analysis/`, `datapreparation/statConll.py`
produces the 13 in its `types` list. The other nine —
`abc.languages.*`, `bak_vs_typo`, `flexibility_rel`, `flexibility_cfc_all`,
`head_initiality_comb`, `direction-cfc_extend`, `distribution-cfc_extend`,
`f-dist-abs`, `height` — have **no generating script in `/home/typometrics`**.

Consequences:

* the SUD default measures (`head-initiality`, `head-initiality-cfc`, `freq-cfc`) that
  the live site serves are the ones we *cannot* regenerate;
* they cannot be moved to 2.18 by anyone, with or without grugrutyp;
* `head_initiality_comb.tsv` vs `positive-direction.tsv` differ in more than the file
  name (the former has an extra `comp:arg` column and blank-not-`nan` empties), so the
  UD and SUD "head-initiality" measures are not currently computed the same way.

**Action:** ask Kim / the co-authors where those scripts live before deciding to
reimplement. Meanwhile grugrutyp's A/B measures regenerate all of them from first
principles anyway, which is the real fix.

---

## 6. Recommendation

1. **Do not port the TSV pipeline.** Ship the A measures as query pairs in v1; they cover
   the measures people actually plot on the live site.
2. **Add the aggregate mode early** (v1.5) — it is a few lines of Cypher and it covers all
   the distance measures plus tree height.
3. **Keep the 2.12 TSVs as a regression fixture.** For each A/B measure, compare the new
   per-language value against the old table (after re-applying `skipFuncs`/`skipLangs` and
   accounting for the root artefact in §2.1). Agreement within tolerance is the strongest
   correctness evidence we can get for the whole stack — importer, translator and all.
4. **Menzerath and Bakker stay as batch tables**, surfaced through the same plotting UI as
   a third measure kind, so nothing disappears from the site.
5. Treat the missing scripts (§5) as a blocking question for Kim, not for the build.
