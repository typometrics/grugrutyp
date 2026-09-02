# Plain language → Grew query pairs (Phase 6.5)

An allowlisted user describes a measure in words; an LLM drafts the (S, Q) pair; the
draft lands **in the editors**, validated and previewed, and nothing touches the corpus
until the user presses Plot. Built 2026-09-01 on Kim's go.

## 1. The harness is the feature

The model is the replaceable part. What makes this safe to offer is everything around it:

* **Nothing unvalidated is ever returned.** Every candidate goes through the same
  `MeasureSpec.validate()` as a hand-typed query. An invalid one is sent back to the
  model once, with the validator's own error; a second failure returns the error, never
  the query (`nl2grew.translate`, pinned by `tests/test_nl2grew.py`).
* **Triple-gated spending**: a signed-in account, the per-person `llm_allowed` flag an
  admin sets by hand, and a daily quota (`GRUGRUTYP_LLM_DAILY`, default 50).
* **A proposal, not an action.** The draft fills the axis editors through the same code
  path as a preset: live-previewed on one treebank, editable, and only a Plot press
  fans out.
* Translations are logged like every query (text, model, outcome — never who asked);
  the per-user accounting lives only in the quota table.

## 2. Which model — measured, not chosen

`scripts/nl2grew_bench.py`: each preset's description (concretised where the caption was
deliberately parameterised) goes to the candidate; the answer must **validate**, and must
match the reference query's **counts on SUD/UD English-GUM** — same counts on 250k tokens
is semantic identity for our purposes. `value≈` is the honest softer tier: the *plotted
value* within 0.5 points, which forgives different-but-defensible conventions that carry
the same number.

30 cases (15 presets × 2 schemes), 2026-09-01:

| model | valid | counts = | value ≈ | avg s |
|---|---|---|---|---|
| gpt-5.4-nano | 25/30 | 6/30 | 7/30 | 1.4 |
| gpt-5.4-mini | 29/30 | 14/30 | 18/30 | 1.4 |
| **gpt-5.4** | **30/30** | **16/30** | **24/30** | **1.5** |
| gpt-5.5 | 30/30 | 18/30 | 24/30 | 4.5 |
| gpt-5.6-luna | 29/30 | 16/30 | 23/30 | 3.5 |
| gpt-5.6-sol | 30/30 | 17/30 | 24/30 | 3.9 |
| gpt-5.6-terra | 29/30 | 17/30 | 22/30 | 4.5 |

**Default: `gpt-5.4`** (`GRUGRUTYP_LLM_MODEL` in `.env`) — it ties the best value-accuracy
at a third of the latency of everything above it. The 5.6 family (Kim asked) buys nothing
here: same accuracy band, 2–3× slower. Nano is not usable; mini is the fallback if cost
ever matters.

**The residual misses are conventions, not misunderstandings.** All six of gpt-5.4's
value-misses are defensible readings: it excluded root edges from mean dependency length
(more principled than our reference, arguably), and it averaged tree height per
*sentence* — which is what the old site's `statConll.py` did; our preset's own note
admits our per-token weighting is the deviant. This is exactly why the draft lands in an
editor with a preview instead of running blind: conventions are the user's call.

Two earlier findings that shaped the prompt (first run scored 13–33% before them):

* the UD subtype trap: a plain `-[nsubj]->` misses `nsubj:pass`; the prompt now mandates
  the subsuming `1=` form in both schemes;
* parameterised captions ("…bearing THIS relation") make a model invent placeholders —
  one wrote `-[1=$REL]->`, another correctly refused and asked which. Bench inputs are
  now phrased as a user would phrase them.

Re-run the benchmark whenever the prompt, the presets, or the model roster changes:

```bash
.venv/bin/python scripts/nl2grew_bench.py --models gpt-5.4,<candidate> \
    --failures /tmp/misses.json
```

## 3. Wiring

| piece | where |
|---|---|
| prompt + pipeline | `backend/grugrutyp/nl2grew.py` (system prompt distilled from `docs/grew-query-language.md`, `docs/query-pairs.md`, `docs/measures-mapping.md` — change those, change it) |
| endpoint | `POST /llm/translate` in `main.py` |
| quota | `users.py` `llm_uses` table, UTC days |
| UI | the ✨ button on each axis panel (`AxisPanel.vue`), visible only to allowlisted accounts |
| keys | `OPENAI_API_KEY`, `GRUGRUTYP_LLM_MODEL`, `GRUGRUTYP_LLM_DAILY`, optional `GRUGRUTYP_LLM_BASE` for any OpenAI-compatible endpoint |

## 4. Chat and analysis (Phase 6.6)

`chat()` may end a turn in a **proposal** (two axes + optional language restriction);
`analyze()` takes the plotted table and returns prose **plus up to three follow-up
proposals** — zoom into a family, a complementary measure for an outlier, a
single-language check — so an analysis ends in things to click, not just read. All
proposals, chat or analysis, go through `_clean_proposal()` → `MeasureSpec.validate()`,
invalid output goes back to the model exactly once, and after a second failure the
analysis keeps its prose and silently drops what did not validate: the commentary is
the primary value. Nothing runs without the human pressing "load & plot".
