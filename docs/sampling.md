# Sub-corpus sampling

Answers Kim's question: *"would it be possible to reduce over-represented languages to a
sub corpus, or having them all in the database and only query on a subcorpus to make this
reasonably fast?"*

**Answer: the second — keep everything, query a slice.** Measured, not assumed.

## 1. The problem

UD + SUD 2.18 is **109 M tokens across 705 treebanks**, and the distribution is brutally
skewed:

| treebank | tokens |
|---|---|
| UD_Czech-PDTC | 6.95 M |
| SUD_Czech-PDTC | 6.36 M |
| SUD_German-HDT | 4.08 M |
| UD_German-HDT | 4.03 M |
| SUD_Russian-Taiga | 2.60 M |
| … | |
| median treebank | ~35 k |

Query time is linear in treebank size (~2.7 s per million tokens, warm). A 1-D measure
needs two counts per treebank; a 2-D plot needs four. So a cold full pass is on the order
of **10 minutes** — and Czech alone costs more than the smallest 400 treebanks combined.

That cost buys nothing. A typological plot places each language at one point on a 0–100 %
axis. The precision of that point depends on the number of **matchings in the scope**, not
on corpus size, and it stops improving long before 6 M tokens.

## 2. Measured: precision vs speed

`SUD_Russian-SynTagRus` (1.5 M tokens), head-initiality of `subj`
(`pattern { GOV -[1=subj]-> DEP } with { GOV << DEP }`), Wilson 95 % intervals:

| sample | n_scope | n_hit | value | 95 % CI | time (both counts) |
|---|---|---|---|---|---|
| 100 % | 120 203 | 35 691 | **29.69 %** | 29.43 – 29.95 | 8.32 s |
| 25 % | 29 914 | 8 863 | 29.63 % | 29.11 – 30.15 | 2.82 s |
| 10 % | 12 044 | 3 644 | 30.26 % | 29.44 – 31.08 | 0.80 s |
| 5 % | 6 081 | 1 863 | 30.64 % | 29.49 – 31.81 | 0.40 s |
| 1 % | 1 174 | 352 | 29.98 % | 27.43 – 32.67 | 0.21 s |

At **10 %** the estimate is 0.57 points off the full-corpus value with a ±0.8-point
interval, for **10× the speed**. On an axis spanning 0–100 %, that error is roughly one
pixel. Even the 1 % sample lands within 0.3 points — it just cannot *prove* it did, which
is exactly what the confidence interval is for.

## 3. The design: a token budget, not a fixed percentage

A fixed percentage would over-sample the giants and destroy the small treebanks. Instead,
each treebank gets a **target token budget**; the sample percentage is derived from it:

```python
pct = min(100, ceil(100 * TARGET_TOKENS / treebank.n_tokens))
```

Treebanks below the budget are queried in full — no sampling, no loss. Only the giants get
cut, and they get cut to the point where they are still the most precise points on the
plot.

Projected over the full 109 M-token corpus:

| budget | tokens scanned | speed-up | treebanks sampled |
|---|---|---|---|
| 500 k | 70.7 M (64.6 %) | 1.5× | 43 of 705 |
| 200 k | 47.5 M (43.4 %) | 2.3× | 139 of 705 |
| **100 k** | **31.0 M (28.3 %)** | **3.5×** | **203 of 705** |

**Default: 100 k**, user-adjustable, with "no sampling" always available. Combined with
the per-treebank cache and an 8-worker pool, a cold full pass goes from ~10 minutes to
well under a minute; a warm one is instant.

## 4. How the sample is taken

At import, every sentence gets `bucket = blake2b(sent_id) % 100`
(`grugrutyp.conllu.sample_bucket`). A k % sample is then one extra conjunct:

```cypher
WHERE _s.bucket < $k AND ...
```

served by `CREATE INDEX sentence_bucket FOR (s:Sentence) ON (s.treebank, s.bucket)`.

Four properties this has to have, and why:

1. **Deterministic.** A hash of `sent_id`, never `rand()`. The same query must give the
   same number twice, cached values must stay meaningful, and re-running a published
   result must reproduce it.
2. **Sentence-level, never matching-level.** A sentence is the unit Grew matches within;
   splitting one would change the counts.
3. **Shared between S and Q.** Both halves of a query pair run against the same sentence
   set, so the ratio stays a ratio. This is automatic: Q is a filter on S's matchings.
4. **Shared between the x and y axes.** A 2-D point must come from one sub-corpus, or the
   two coordinates describe different samples of the language.

## 5. When sampling must be switched off

Sampling trades precision for speed, and for **rare phenomena there is no precision to
trade**. A scope like `comp:obl@agent` or a specific `Case` value may have only a few
dozen occurrences in 100 k tokens.

So the rule is adaptive, not fixed. **Yes — a rare phenomenon in a big treebank escalates
to the full corpus automatically.** The escalation happens per treebank, not globally, so
one rare-in-Czech phenomenon does not slow down the other 704.

### Three triggers, because there are three ways a sample fails

The obvious rule — "re-run at 100 % if `n_scope` < threshold" — is not enough, and neither
is the interval width on its own. Implemented in `measure.SamplingPolicy.escalate`:

```
run at the budgeted percentage
if  n_scope < min_scope       ->  escalate to 100 %     (default 30)
if  ci_width > ci_tolerance   ->  escalate to 100 %     (default 2 points)
if  n_hit   < min_hits        ->  escalate to 100 %     (default 10)
after escalation, if n_scope is still under min_scope -> drop the point, and say so
```

Each catches something the others cannot see:

1. **`n_scope`** — too little to plot at all. This is the role `axminocc` plays on the
   current site, but applied to a number we actually know rather than a hidden threshold.

2. **`ci_width`** — `n_scope` is the *denominator*, and a scope can be perfectly common
   while the value is imprecise. 1 000 subjects split 50/50 passes any threshold on
   `n_scope` and still lands ±3.1 points, which is visible on the axis. Tolerance defaults
   to ~2 points, which is not.

3. **`n_hit`** — and this is the one that is easy to get wrong. **An earlier draft of this
   document claimed the interval-width rule covered rare phenomena. It does not.** Take
   the motivating example: 50 000 subjects of which 3 are post-verbal. Its Wilson interval
   is 0.002 %–0.018 %, which is *narrower* than the tolerance, so rule 2 never fires —
   while being a ninefold range and a 58 % relative error. A count of *n* has a relative
   standard error of about `1/√n`: 3 hits is ±58 %, 10 hits ±32 %. On a linear 0–100 axis
   none of that is visible, but it is visible in the tooltip, in an exported table, and in
   the sentence a paper writes about it.

   This clause subsumes the zero-hit case, which needed catching for its own reason:
   "this language never does X" and "we did not sample enough to see X" are different
   claims, and only the full corpus separates them.

The cost of rule 3 is bounded and self-limiting: a phenomenon rare enough to trigger it is
rare enough that the full-corpus query returns almost nothing to count.

Always report `n_scope`, `n_hit` and the interval alongside the value, so a point computed
from 200 matchings is visibly less certain than one from 200 000. This is strictly better
than today's site, which drops low-frequency languages against a hidden threshold and
shows every surviving point as if it were equally certain.

### The user stays in control

Sampling is an optimisation, never a silent one:

* a **corpus-coverage control** with `exact (no sampling)` always available, and the
  budget adjustable — a paper-ready number should be computed exactly;
* every plot states its budget, and any point that was escalated to 100 % is marked, so
  a mixed plot is never mistaken for a uniform one;
* the cache key includes the sample percentage, so an exact run never returns a sampled
  number from cache;
* `exact` is the default for a **single-treebank** query — sampling only exists to make
  the ~705-treebank fan-out interactive, and there is nothing to gain on one treebank.

## 6. Sampling is not the only lever

Ranked by how much they buy:

1. **Cache** `(treebank, version, query_hash, sample_pct) → (n_scope, n_hit)`. The second
   run of any measure is free. This is the big one; sampling only helps the first run.
2. **Sampling** (this document): 3.5× on the cold pass.
3. **Parallel fan-out** over treebanks: ~8× on this box, and it composes with the above.
4. **SSE streaming**: does not reduce total time at all, but the plot fills in as results
   land, so the *perceived* wait is the time to the first few treebanks.

Do not treat sampling as a substitute for the cache. It is what makes the uncached case
tolerable.

## 7. Status

* `Sentence.bucket` is written by the importer and indexed — **done**.
* The measure API applying the budget, the adaptive escalation, and the UI control —
  **Phase 3, not built yet.**
* **The tree search at `/grugrutyp/` does no sampling at all.** Every count and every
  matching it shows today is exact and full-corpus. Sampling only ever applies to the
  many-treebank measure fan-out, which does not exist yet.
* The treebanks imported before this was added carry a `bucket` assigned by a one-off
  backfill; they will get the hash-based value on the next re-import. Re-import before
  trusting a sampled number.
