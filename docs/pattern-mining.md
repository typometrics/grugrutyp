# Pattern mining: searching measure space for quantitative universals

Kim's ask (2026-09-04): *"what are ways to use the current tools to discover astonishing
patterns in our data? how to identify interesting patterns like in typometrics, ie. near
empty regions, that are not trivial? how computationally expensive would it be to go
search? make proposals of how to find new quantitative universals."*

Background: the typometrics paper (Gerdes, Kahane & Chen, Glossa — `references.md`
should gain the full citation) defines a quantitative universal as **a claim about the
shape of the language cloud** in measure space: empty and near-empty zones, inequalities,
interval constraints. It catalogues five shapes — **triangle** (X ≥ Y), **crescent**
(strictness implication), **Z** (weak tendency on one axis amplified on the other),
**almond** (mutual interval prediction), **near-uniform** (no universal) — and its
conclusion explicitly opens the field to *systematic* search: "we are interested in the
whole distribution of languages in a scatter plot", including configurations beyond
single dependency links (the subject–object relative order is named as future work).

grugrutyp removes exactly the two limits that made the 2018 study a hand process: the
measure set is now a query language, and every count carries its `n_scope`, `n_hit` and
a Wilson interval. This document is the design for the search.

## Decisions

| decision | choice | why |
|---|---|---|
| scheme | **SUD only** for all mined measures | Kim, 2026-09-04: "measures should mainly be done on SUD. it exists for exactly that reason." UD at most as an occasional sanity check; never a headline filter or research axis |
| unit | language (counts summed over its treebanks), per-treebank counts retained | same rule as the plots (`plan.md` §2); treebank level is kept for replication checks (ch. 4) |
| sampling | Tier-1 batch pass runs **exact** (no sampling); Tier-2 measures run at the standard budget with escalation slots capped | one full scan amortised over thousands of measures beats thousands of sampled fan-outs; bespoke measures reuse the runner and its cache |
| mining outputs | flat files under `data/mining/`, never in the measure cache | the cache is keyed by query hash and serves the live site; mining tables are derived artefacts, rebuildable |
| role of the miner | **hypothesis generator**, not hypothesis test | with ~10⁵ pairs and ~35 effective lineages, p-values are decoration; confirmation is by held-out data (ch. 5, 10) |

---

## 1. From hand-drawn shapes to a mined catalogue

**Goal.** Reproduce, at machine scale, the move the paper made by hand: enumerate
measures, plot pairs, notice shapes, name universals. Output: a ranked catalogue of
candidate quantitative universals, each with its shape type, its exceptions named, and
the triviality checks it survived.

**Hypothesis.** The 2018 paper found five shape types in ~40 hand-picked direction
measures. A sweep over thousands of measures will (a) refind every published pattern
(sanity), (b) find instances of the known shapes nobody looked at, and (c) with luck,
find shape types not in the catalogue — the "attractors" and asymmetric-dispersion
configurations the conclusion gestures at.

**Expected difficulties.** The failure mode is not finding too little, it is drowning:
thousands of statistically "significant" shapes, most of them boring for one of five
identifiable reasons (ch. 4). The intellectual content of this project is the filter,
not the search.

**Time.** The whole programme in this doc: ~2 weeks of build spread over its chapters,
plus batch compute measured in nights. Each chapter carries its own estimate.

**Todo.**
- [ ] agree this doc's chapter order as the build order (Kim)
- [ ] add the Glossa citation to `references.md`
- [ ] pick the first target venue/format for the catalogue (paper? interactive page on
      the site? both?) — it shapes how much of ch. 10 to build early

## 2. The measure matrix

**Goal.** A `language × measure` matrix — values, plus `n_scope`/`n_hit` per cell so
every downstream statistic can be CI-aware. Three tiers by cost:

* **Tier 0 — free.** Whatever the measure cache already holds (presets, everything
  users have plotted). Read-only join of cache rows with the language merge.
* **Tier 1 — one clustered pass.** A bespoke read-only Cypher scan per treebank over
  all word-to-word dependencies, grouped by `(gov.upos, rel_1, rel_2, dep.upos,
  direction)`, also accumulating `Σdelta` and `Σ|delta|`. One scan yields, after
  marginalisation in Python: every relation-direction measure (`f.tsv`,
  `positive-direction` analogues), every cfc-direction measure (`posdircfc`), relation
  and cfc frequency shares, and the signed/absolute distance measures — i.e. the entire
  direction × cfc block of measure space, at both `rel_1` and `rel_1:rel_2`
  granularity, exact, in a single disk pass. The dump is **complete**: root edges
  (`gov.idx = 0`) are kept, marked `__0__` — the dependent-side upos marginal is then
  the POS distribution for free, and the root exclusion
  (`measures-mapping.md` §2 point 1) stays an explicit choice at merge/mining time.
  Scheme-fixed directions (`conj`, `fixed`, `flat`, `goeswith`, `punct`,
  `reparandum`, `dep`, `list`, `orphan`, `dislocated`…) likewise excluded at mining
  time, never at scan time.
* **Tier 2 — bespoke measures.** Everything that is not a function of the Tier-1
  counters: multi-node configurations (ch. 6.1), weight-conditioned direction (6.2),
  FEATS-conditioned direction (6.3), aggregates and Menzerath axes (6.4). These go
  through the ordinary `(S, Q)` runner — sampled, cached, escalation-capped — from a
  catalogue file, batch-driven like `warm_cache.py`.

**Hypothesis.** Tier 1 alone yields on the order of 300–1000 usable columns (measures
with ≥ 40 languages above thresholds); Tier 2 adds a curated 100–500. That is enough
for every chapter downstream.

**Expected difficulties.**
* The scan is cold-disk-bound (`performance.md`: the store does not fit in the page
  cache; parallelism makes it *worse*). Run sequentially, smallest treebank first,
  `setsid nohup`, resumable per treebank.
* A treebank being re-imported mid-scan would poison counts silently; refuse to start
  if an importer is running, and record `imported_at` per dump so staleness is
  detectable (`CLAUDE.md` hard rule).
* Low-frequency cells: a cfc triple with 7 occurrences in one language is a noise
  generator. Thresholds (`n_scope ≥ 30` per language, ≥ 40 languages per measure) are
  the first filter, and they must be applied per measure, not globally.
* Neo4j aggregation memory on German-HDT-sized treebanks: grouping keys are bounded
  (≤ ~18 upos × ~40 rel_1 × few rel_2 × 18 upos), so this should be fine — verify on
  the dev slice first.

**Time.** Builder script ~half a day. The SUD pass: one scan over ~38 M edges on cold
spinning disks — estimated 1–4 h; measure, don't trust the estimate. Tier-2 catalogue
runs: minutes per measure warm, 5–15 min cold; a 200-measure catalogue is 1–3 nights,
cached permanently after that.

**Todo.**
- [ ] `scripts/mine_cfc_matrix.py`: per-treebank clustered scan → `data/mining/cfc/`
      (JSON per treebank: counts, `imported_at`, schema version)
- [ ] refuse to run while an import is in flight; log like the other long jobs
- [ ] verify on the dev slice against known 2.12/preset values (spot check ≥ 3
      languages × 3 measures against the live runner)
- [ ] run the full SUD pass; record wall time in this doc
- [ ] merge step: treebank dumps → language-level matrix
      (`data/mining/matrix.sud.parquet` or `.tsv`) with n_scope/n_hit per cell
- [ ] Tier-2 catalogue format (`data/mining/catalogue.gql`? yaml of (S,Q) pairs with
      provenance) + batch driver reusing `runner.evaluate_language`
- [ ] Tier 0: dump the existing cache through the same merge for immediate play

## 3. Shape statistics

**Goal.** For every measure pair (and every single measure, ch. 8), a battery of cheap
statistics that detect the paper's shapes plus the ones it hints at:

| shape | statistic |
|---|---|
| triangle (X ≥ Y) | violation mass: Σ over languages of max(0, y−x), CI-discounted; fraction below diagonal |
| crescent / empty region | largest empty axis-aligned rectangle (side-bounded); grid-cell density deficit vs permutation |
| Z | fit two thresholds (a, b): occupancy of the four outer zones vs the central band; reinforcement factor (ch. 7) |
| almond | max |y−x| band width; interval-prediction score: how much knowing x narrows y |
| quadrant / implicational | median-split quadrant deficit (already in `stats.js`, ported to Python) |
| correlation | Pearson, Spearman, and family-aggregated r (`plot-statistics.md`) |
| 1-D | Hartigan dip statistic (bimodality), per-pole mean/SD asymmetry, gap width |

All of it runs on the in-memory matrix; per pair it is sub-millisecond at n ≈ 150
languages.

**Hypothesis.** The five published shapes are recoverable by these statistics on the
published measure pairs — that is the acceptance test for the battery.

**Expected difficulties.** Emptiness statistics are scale-sensitive (a 0–100 axis where
all mass sits in [0,20] makes every rectangle over [40,100] "empty"). Normalise per
plot: statistics computed on ranks *and* on raw values, and an empty region only counts
inside the convex hull-ish support of the marginals. Also: points are not equally
certain — every emptiness/violation statistic must have a CI-aware variant (a language
only testifies where its interval actually lies; ch. 4, filter 5).

**Time.** ~1 day for the battery + tests, including reproducing Figures 3, 18, 23, 27
of the paper as fixture cases (from Tier-1 matrix values, SUD).

**Todo.**
- [ ] `scripts/mine_shapes.py` (or a small `backend/grugrutyp/mining/` module if the
      site later serves results): battery over all pairs of a matrix file
- [ ] fixture test: the paper's five figures come out as their shape types
- [ ] CI-aware variants of triangle violation and emptiness
- [ ] output: one row per (pair, statistic) in `data/mining/shapes.sud.tsv`

## 4. The triviality gauntlet

**Goal.** Encode "not trivial" as executable filters. A pattern is *astonishing*
precisely when it survives every null model that encodes what we already believe.
In kill order:

1. **Arithmetic coupling.** If Q₂'s matchings are largely a subset of Q₁'s (`comp`
   direction vs `comp:obj` direction; a measure vs its own marginal), the shape is
   bookkeeping. Detectable *exactly* from the Tier-1 dump (subrelation counts are
   available) or, for Tier-2 pairs, by one overlap query `#(S₁∧S₂)` per language.
   Compute the shape the mixture arithmetic alone predicts; only the excess counts.
2. **Independence null.** Permute y across languages (within-plot), 1000×; keep only
   shapes beyond the permutation distribution of the same statistic.
3. **Phylogeny and area (Galton).** Re-test on (a) family medians — the
   `plot-statistics.md` machinery — and (b) a bootstrap drawing one language per
   genus, plus a macro-area balance check. An empty corner that only exists because no
   Slavic language lives there is a fact about the sample. Effective n is ~30–40
   lineages; every claim is reported at lineage level.
4. **Annotation artefacts.** Scheme-fixed directions excluded (ch. 2); known noisy
   relations (`expl`, `dislocated`-adjacent phenomena — see the paper §2) flagged;
   treebank-level replication: a language point that is load-bearing for a shape must
   be consistent across its own treebanks (per-treebank counts exist for exactly this).
   Genre splits (spoken/written) where the language has both. *(UD-vs-SUD replication
   deliberately demoted — Kim, 2026-09-04: least interesting; SUD is the measurement
   scheme.)*
5. **Power.** A language testifies to emptiness only if its Wilson interval could have
   placed it inside the empty region. Regions "kept empty" by wide-interval points are
   unproven, not empty. Report, per empty region: how many languages could have
   entered it and didn't.

Plus the **boringness filter**, which kills correct-but-known findings: residualise
every direction measure against global head-direction (first principal component of
the direction block) and re-run the shape battery on residuals. What survives is, by
construction, not expressible as "yet another correlate of head-initiality" — see
ch. 9.

**Hypothesis.** Filters 1–3 kill > 90 % of raw "significant" shapes; the survivor list
is small enough (10²) for human + LLM triage.

**Expected difficulties.** Filter 1 needs care to not over-kill: two measures can
overlap arithmetically *and* carry independent signal (subject direction vs object
direction share the clause). The filter subtracts the predicted shape, it does not
disqualify the pair. Filter 3's genus assignments come from `languages.tsv` groupings
(five views — use `genus`, fall back to `group`), which are curation decisions; the
bootstrap must not crash on unconfigured languages (they plot grey; here they simply
count as their own lineage). Macro-areas are not currently a column — check whether
`area` in `languages.tsv` is populated well enough; if not, that is a config task, not
a code task.

**Time.** ~1–2 days. Permutation nulls at 1000× over ~10⁵ pairs vectorise to minutes.

**Todo.**
- [ ] mixture-arithmetic coupling check from Tier-1 marginals; overlap query helper
      for Tier-2 pairs
- [ ] permutation null, vectorised, per statistic
- [ ] lineage bootstrap + family-median replication (reuse `langconfig` views)
- [ ] audit `languages.tsv` `area` column coverage; report to Kim if it needs curation
- [ ] CI/power report per empty region
- [ ] excluded-relations list as data (`data/mining/excluded_rels.tsv`), not code

## 5. Ranking, error control, confirmation

**Goal.** One scalar "surprise" score per surviving pattern to sort the catalogue, and
an honest protocol for promotion from *mined* to *claimed*.

Score = product (or a learned/weighted combination — start simple) of: emptiness excess
over permutation null × lineage-bootstrap survival rate × (1 − arithmetic-predicted
share) × power (how many tight-CI languages could have violated). FDR handled by
permutation-based q-values *at lineage level*; but the real control is the protocol:

* **generation**: everything in this doc runs on SUD 2.18;
* **confirmation**: a promoted claim is re-tested automatically on the next UD/SUD
  release and on languages added since (the Phase 5 drift detector is the same
  machinery);
* **inspection**: every claim's exceptional languages are drilled to example sentences
  via `/search` — an outlier is a discovery or an annotation bug, and only the trees
  decide which. (Phase 5's treebank quality checking is this same computation read
  from the other end.)

**Hypothesis.** Of order 10–30 patterns survive to the catalogue with scores clearly
above the bulk; if *nothing* beats the known head-direction structure, that is itself a
publishable negative (the paper's "near-uniform" honesty, scaled up).

**Expected difficulties.** Score design is where subjectivity hides; keep every
component reported separately so the ranking can be re-weighted without re-mining.
LLM triage (`analyze()`) is commentary, never a gate — the numbers gate, the model
narrates.

**Time.** ~1 day, mostly plumbing and a review session over the first ranked list.

**Todo.**
- [ ] scoring + ranked report (`data/mining/ranked.sud.md`, one section per candidate:
      plot link via the shareable-URL fragment, statistics, filters passed, exceptions)
- [ ] wire top-k into `analyze()` for prose drafts (allowlisted path, batch of ~50)
- [ ] promotion protocol written down in this doc after the first run teaches us what
      it should say

## 6. New measure families (Tier 2)

### 6.1 Multi-node configurations — starting with the SO universal

**Goal.** The paper's conclusion names it: subject–object relative order is not a
single dependency link, and was left uncomputed. It is one query pair now:

```grew
S: pattern { V -[1=subj]-> S; V -[1=comp,2=obj]-> O }
Q: with    { S << O }
```

Plot against subject direction and object direction; look for the shape Greenberg's
Universal 1 predicts (SO dominance ~universal). Same move for: auxiliary–verb–object
nesting, double objects, adposition–noun–genitive chains, "at most one dependent left
of the finite verb" (a V2 diagnostic), subject inversion under fronted material.

**Hypothesis.** SO ≥ ~50 % nearly everywhere (Universal 1 quantified), with the
interesting content in the *exceptions* and in the shape against VS/VO rates — is the
SO rate flat (grammaticalised) or does it degrade continuously with subject postposing?

**Difficulties.** Injectivity and clause-boundary subtleties (two objects of different
verbs must not pair); the differential harness must cover each new construct before its
counts are believed (`CLAUDE.md` hard rule 2). Rare configurations trip escalation —
batch with capped slots and accept `refinable`.

**Time.** Catalogue of ~20 configurations: 1 day to write + differential-check, 1–2
nights to run.

**Todo.**
- [ ] write the configuration catalogue with per-entry rationale
- [ ] differential-test each construct combination used
- [ ] run; feed the matrix; SO-universal section in the ranked report

### 6.2 Weight-hierarchy universals

**Goal.** The paper observed postposition rates PRON 39.3 % ≤ NOUN 65.2 % ≤ clausal
79.3 % but tested only the first triangle. Test each leg pairwise, then make weight
continuous with `subtree_size`: direction of a relation as a monotone function of
constituent weight, per language — "heavier goes later" as a *family* of quantitative
universals, with its failure languages named.

**Hypothesis.** Monotone in nearly every language for `comp`-like relations; the
astonishing finding would be a language where it reverses (or a relation where the
hierarchy inverts systematically — candidates: strongly head-final languages, where
"heavy early" has been claimed).

**Difficulties.** `subtree_size` conditioning needs threshold buckets (`=` works
today; ranges may need a small translator extension — check before building around
it). Buckets must be chosen once, globally, or the measure isn't comparable across
languages.

**Time.** Half a day + one night of runs.

**Todo.**
- [ ] check `>=`/range support for numeric counters in the translator; extend if cheap
- [ ] bucket scheme (e.g. 1, 2–3, 4–7, 8+) decided and recorded here
- [ ] pairwise legs (PRON/NOUN/clause) as presets, then the bucketed family

### 6.3 Feature-conditioned direction

**Goal.** Split direction measures by FEATS nobody has conditioned on at scale:
`Definite`, `Case`, `PronType`, `Person`, `Polarity`, `Tense` on the dependent or
governor. Differential-placement universals ("if definiteness moves the object at all,
it moves it in one direction only").

**Hypothesis.** At least one robust cross-linguistic asymmetry exists outside the
known pronominality one (6.2 is its weight reading); definiteness on objects is the
best-documented candidate.

**Difficulties.** FEATS coverage is wildly uneven across treebanks — a language
without `Definite` annotation is *missing*, not a counterexample; the per-language
denominator check must distinguish "feature absent from annotation" (feature never
occurs in the treebank) from "phenomenon absent". Tier-1's dump does not carry FEATS;
these are Tier-2 measures, and the catalogue must query feature presence first
(`feature_keys()` + a per-treebank presence count) to scope each measure to languages
that annotate it.

**Time.** 1 day + nights.

**Todo.**
- [ ] per-treebank FEATS-coverage table (one clustered query per feature of interest)
- [ ] catalogue entries gated on coverage; run; report

### 6.4 Direction × distance and Menzerath axes

**Goal.** Cross the ratio block with the aggregate block: mean signed/absolute
dependency distance per relation (free from Tier 1's Σdelta), `avg(DEP.subtree_size)`,
Menzerath quantities, tree height, projectivity rate (`Sentence.is_projective`) — vs
direction and flexibility measures. Candidate shapes: is the distance–direction almond
tighter than head-direction predicts? Does projectivity rate bound word-order
looseness (a crescent against direction-balance)?

**Hypothesis.** Distance asymmetry (right dependencies longer than left ones) is
near-universal and *graded* by head-direction; deviations flag either discoveries or
tokenisation artefacts.

**Difficulties.** Mixing units (0–100 % vs words) — shape statistics must run on ranks
for mixed pairs. Aggregates have no Wilson interval; use per-treebank spread as the
uncertainty proxy.

**Time.** Half a day (most axes already exist as presets or Tier-1 marginals).

**Todo.**
- [ ] distance marginals from Tier-1 dump wired into the matrix
- [ ] projectivity-rate measure (sentence-scope) added to the catalogue
- [ ] rank-based battery path for mixed-unit pairs

## 7. The reinforcement-factor sweep

**Goal.** The paper computes a *strictness reinforcement factor* twice by hand
(adpositions: 9/1.5 = 6; auxiliaries: 5/2 = 2.5). Compute it for **every** relation
against global head-direction: fit the central band and outer zones of the Z per
relation, report the amplification ratio. Output: a ranking of relations by how
strongly they amplify a language's word-order tendency.

**Hypothesis.** Function-word-headed relations (SUD's `antiadpositions`… i.e. ADP,
AUX, cop, mark-like configurations under SUD headedness) amplify most — "the more
grammaticalised the relation, the stronger the reinforcement" as a new quantitative
universal *type*. Lexical modifier relations (`mod`-like) amplify least.

**Expected difficulties.** Threshold fitting on ~150 points is noisy; fit by
maximising zone-emptiness significance, and report the factor with a bootstrap CI, not
as a number that looks more exact than it is. Some relations have no Z at all — the
sweep must say "no Z-shape" rather than emit a meaningless factor.

**Time.** Half a day on top of ch. 3's battery; runs on the Tier-1 matrix.

**Todo.**
- [ ] Z-fit + factor with bootstrap CI in the battery
- [ ] sweep over all rel_1 (and promising rel_1:rel_2), ranked table in the report
- [ ] grammaticalisation reading written up against the ranking (Kim)

## 8. The 1-D sweep

**Goal.** Universal 19 turned out to be a claim about *asymmetric dispersion* (ADJ:
left pole mean 3.8 SD 9.1, right pole mean 83.4 SD 14.2). Sweep every relation and cfc
direction distribution for: bimodality (dip test), forbidden middles (gap statistics),
per-pole dispersion asymmetry ("strict at one pole, loose at the other"), and the
genuinely continuous cases (pronominal objects) — each a Universal-19-style claim.

**Hypothesis.** Relations sort into a small number of 1-D profile types; the profile
type is predictable from the relation's semantics (grammaticalised → bimodal-strict;
modifier-like → continuous). That mapping is itself a universal.

**Expected difficulties.** n ≈ 150 makes dip tests weak; lineage weighting matters
even more in 1-D (half the sample is IE — a "mode" can be a family). Run every 1-D
statistic on the lineage-bootstrap too.

**Time.** Half a day; runs on the Tier-1 matrix.

**Todo.**
- [ ] 1-D battery + lineage bootstrap
- [ ] profile-type clustering of relations; table in the report

## 9. Residual universals

**Goal.** The most likely place for something *astonishing*: remove the dominant
head-direction axis (first PC of the direction block, computed on lineage-balanced
data) and re-run the entire shape search on residuals. Any empty region or inequality
that survives is by construction not expressible in the classical head-initiality
vocabulary.

**Hypothesis.** At least the pronominality/weight axis (ch. 6.2) emerges as a second,
partially independent dimension; the open question is whether a *third* structured
dimension exists. Even a clean "no third axis" is a result (the dimensionality of
word-order typology, measured).

**Expected difficulties.** PCA on percentages near 0/100 is distorted — work in logit
space with CI-aware shrinkage (empirical-Bayes shrink each language's value toward the
grand mean by its interval width, or the PC directions chase sampling noise in small
languages). Missing cells (languages without a measure) need masked PCA, not
imputation-by-zero.

**Time.** 1 day.

**Todo.**
- [ ] logit + shrinkage transform; masked/weighted PCA; scree report
- [ ] shape battery on residuals; residual section in the ranked report
- [ ] dimensionality statement drafted from the scree + residual findings

## 10. Claim objects and replication

**Goal.** A promoted universal is a *file*, not a sentence: measure pair (the (S,Q)
texts), region/claim type, parameters, exception languages with CIs, filters passed
with their numbers, corpus version, and the shareable plot URL. Machine-re-testable on
every release.

**Hypothesis.** Re-running the claim set on each UD/SUD release converts the miner
from a one-off paper into an observatory: claims strengthen, weaken, or break with
data growth, and *that trajectory* is publishable (and doubles as annotation-drift
detection, Phase 5).

**Expected difficulties.** None technical — the discipline of actually writing claims
as files instead of prose. Format bikeshedding is capped at one hour.

**Time.** Half a day.

**Todo.**
- [ ] claim schema (`data/mining/claims/*.yaml`) + re-test runner
- [ ] the first mined survivors written as claim files
- [ ] hook into the release process (`fetch_treebanks.sh --check` era): new release →
      re-test → diff report

## 11. Execution plan and runtime discipline

**Goal.** Run everything above without hurting the live site or violating the
project's hard rules.

Order of work (dependency order, also roughly value order):

1. ch. 2 Tier 1 (matrix builder + SUD pass) — everything else feeds on it
2. ch. 3 battery + ch. 4 filters 1–3 — first ranked list within a day of the pass
3. ch. 7, 8 (run on the matrix, cheap, high yield)
4. ch. 4 filters 4–5, ch. 5 ranking/report
5. ch. 6 Tier-2 families (6.1 SO first — it is the paper's own named open problem)
6. ch. 9 residuals, ch. 10 claims

Runtime discipline:

* long jobs: `setsid nohup … > logs/<name>.log 2>&1 < /dev/null &`, resumable,
  smallest treebank first; **never in parallel with an import**; check for a running
  importer before starting (and the importer's own guard already 404s mid-rebuild
  treebanks for API paths — the miner must apply the same `n_sents > 0` rule via
  `engine.treebanks()`)
* single-threaded scans (spinning disks; parallelism is a pessimisation —
  `performance.md`)
* every Cypher literal a parameter (hard rule 3); mining Cypher is read-only
* nothing lands in the measure cache from mining scripts; flat files under
  `data/mining/` only
* Tier-2 batches run with `auto_escalation_slots` at its default and accept
  `refinable` — exactness is bought only for promoted claims (ch. 10 re-test runs
  exact)

**Time summary.**

| block | build | compute |
|---|---|---|
| Tier-1 pass (ch. 2) | 0.5 d | 1–4 h, once |
| battery + filters + ranking (3, 4, 5) | 2–3 d | minutes–1 h per full sweep |
| 1-D + reinforcement sweeps (7, 8) | 1 d | minutes |
| Tier-2 families (6.x) | 2–3 d | 2–4 nights |
| residuals (9) | 1 d | minutes |
| claims + replication (10) | 0.5 d | per release |

**Todo.**
- [ ] `data/mining/` created with a README pointing here
- [ ] first ranked report reviewed with Kim; decide what ch. 5's promotion protocol
      says; update this doc in the same commit as any design change (hard rule 4)
