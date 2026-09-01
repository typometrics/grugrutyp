# Sub-corpus sampling

Answers Kim's question: *"would it be possible to reduce over-represented languages to a
sub corpus, or having them all in the database and only query on a subcorpus to make this
reasonably fast?"*

**Answer: the second — keep everything, query a slice.** Measured, not assumed.

## 1. The problem

UD + SUD 2.18 is **75.9 M syntactic words across 705 treebanks**, and the distribution is
brutally skewed:

| treebank | tokens |
|---|---|
| SUD_German-HDT | 3.46 M |
| UD_German-HDT | 3.46 M |
| SUD_Czech-PDTC | 3.44 M |
| UD_Czech-PDTC | 3.44 M |
| SUD_Russian-Taiga | 1.76 M |
| … | |
| median treebank | 20.7 k |

> **Corrected 2026-08-29**, once the full import finished and the numbers could be counted
> rather than projected. Earlier drafts said 109 M, and before that 64 M; both were
> estimates from file sizes and line counts, which include comment lines, multiword-token
> lines and empty nodes. The figure that matters for query cost is **syntactic words**,
> which is what the graph holds and what `Treebank.n_tokens` reports. The largest treebank
> is also half what the estimate suggested, which is why the sampling speed-up below is
> smaller than projected: there is less extreme skew to exploit.

Query time is linear in treebank size. A 1-D measure needs two counts per treebank; a 2-D
plot needs four. The two German-HDT treebanks and the two Czech-PDTC ones are 13.8 M words
between them — **18 % of the whole corpus in four treebanks**, against a median of 20.7 k.

That cost buys nothing. A typological plot places each language at one point on a 0–100 %
axis. The precision of that point depends on the number of **matchings in the scope**, not
on corpus size, and it stops improving long before 3 M words.

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

A fixed percentage would over-sample the giants and destroy the small languages. Instead,
each **language** gets a target token budget; the sample percentage is derived from it and
applied to every treebank of the language (2026-08-29, Kim: "I don't want to keep the
treebanks separate anymore … those should be randomly sampled over the whole language, so
to stem from different treebanks depending on their size"):

```python
pct = min(100, ceil(100 * TARGET_TOKENS / language.n_tokens))   # runner.evaluate_language
```

Because the bucket filter (§4) is a deterministic per-sentence hash, one rate across the
language's treebanks **is** a uniform random sample over the language: French at 15 %
draws half its sample from GSD because GSD is half of French. The earlier per-treebank
budget did not have this property — it merged a 3 % slice of German-HDT with 100 % of
German-GSD by summing raw counts, which weighted GSD thirtyfold.

Languages below the budget are queried in full — no sampling, no loss. Only the giants get
cut, and they get cut to the point where they are still the most precise points on the
plot.

Measured over the imported corpus, not projected:

| budget | tokens scanned | speed-up | treebanks sampled |
|---|---|---|---|
| **100 k** | **28.3 M (37.3 %)** | **2.7×** | **177 of 705** |

**Default: 100 k**, user-adjustable, with "no sampling" always available. Combined with
the per-treebank cache and an 8-worker pool this is what makes a cold full pass tolerable;
a warm one is instant.

Sampling is the *second* lever, and it is worth keeping that in proportion: 2.7× is real
but it is not what makes the tool usable. The cache is (§6), and after it the ordering of
the fan-out — `runner.select` returns **smallest treebank first**, which took the time
before the first hundred languages appear from minutes to seconds.

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
5. **Shared across a language's treebanks.** The language value merges by summing raw
   counts, so every treebank of the language runs at the same percentage (§3), and if the
   language escalates, all of its treebanks escalate together.

## 5. When sampling must be switched off

Sampling trades precision for speed, and for **rare phenomena there is no precision to
trade**. A scope like `comp:obl@agent` or a specific `Case` value may have only a few
dozen occurrences in 100 k tokens.

So the rule is adaptive, not fixed. **A rare phenomenon in a big language escalates to a
larger sample automatically.** The escalation happens per language, not globally, so one
rare-in-Czech phenomenon does not slow down the other 192 — and it is judged on the
**language's summed counts**, so a small treebank inside a large language does not trigger
a rescan on its own sliver of the sample. It is also **bounded**: escalation goes to ten
times the ordinary budget, not to 100 % (`SamplingPolicy.escalated_pct`,
`docs/performance.md` §5 — unbounded escalation was scanning German-HDT in full for
phenomena the budget had deliberately cut it out of).

### Three triggers, because there are three ways a sample fails

The obvious rule — "re-run at 100 % if `n_scope` < threshold" — is not enough, and neither
is the interval width on its own. Implemented in `measure.SamplingPolicy.escalate`:

```
run every treebank of the language at the language's budgeted percentage
sum the counts; on the sums:
if  n_scope < min_scope       ->  escalate     (default 30)
if  ci_width > ci_tolerance   ->  escalate     (default 2 points)
if  n_hit   < min_hits        ->  escalate     (default 10)
escalation re-runs the whole language at min(100%, ten times the budget)
  -- automatically only for languages at or under auto_escalation_tokens (default:
     the escalation budget, 1 M); a bigger language is still a sample even at the
     ceiling, so it keeps its sampled value, marked `refinable`, and the plot
     proposes the fuller pass instead of incurring it
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

### Expensive escalations are proposed, not incurred (2026-08-30)

Bounding escalation to ten times the budget was not enough. Measured in the cache after
the first weeks of real use: SUD_German-HDT at its escalated 27 % averaged **86 s per
query, worst 269 s**; SUD_Czech-CAC at 21 % peaked at 270 s, SUD_Russian-SynTagRus at
29 % at 169 s. Whenever a measure's response was rare, the policy quietly rescanned the
three giant languages at ~1 M tokens each — and that pass, cold on these disks, *was* the
multi-minute tail of the run (Kim, 2026-08-30: "the computation for czech german russian
took again forever").

So automatic escalation is now also bounded **by language size**: a language at or under
`auto_escalation_tokens` (default: the escalation budget itself, `SamplingPolicy`) still
escalates by itself — one bounded pass that reaches its full corpus, and a proposal for
it would be noise. A bigger language is still a *sample* even at the escalation ceiling;
that is the mark of the giants, and exactly where the rescan is the multi-minute tail. It
keeps its sampled value, its points are flagged `refinable` through the merge, and the
plot shows a small **refine** button in the progress line (the explanation is its
tooltip). Refining re-runs *only their treebanks* at ten times the plot's budget —
exactly the pass that used to run unasked — and replaces those points in place. The
result lands in the ordinary cache, so refining is paid for once per measure.

> **Recalibrated the same day.** The first cut deferred any language whose rescan would
> read over 300 k tokens. That put 31 of SUD 2.18's languages in the proposal pool, and a
> measure with a rare response flagged ~27 of them at once (Kim: "every query i try now").
> The current rule defers 11 at most — Czech 4.2 M down to Latin 1.0 M — and the mid-size
> languages went back to refining themselves: a slightly slower run beats a banner that
> cries wolf.

The flag is honest in both directions: an unrefined giant is marked imprecise rather than
plotted as if exact, and the refine button disappears only when the refined counts come
back clean.

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
* an escalation too expensive to run unasked becomes a **proposal**: the languages are
  named in a banner and refined only when the user presses the button (see above);
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
* The measure API applying the budget, the bounded language-level escalation, and the UI
  coverage control — **built** (`runner.evaluate_language`, `/measure`).
* **The tree search at `/grugrutyp/` does no sampling at all.** Every count and every
  matching it shows is exact and full-corpus. Sampling only ever applies to the
  many-treebank measure fan-out.
* The full 2.18 re-import (2026-08-29) gave every sentence the hash-based `bucket`;
  sampled numbers are trustworthy since then.
