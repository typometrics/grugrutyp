# grugrutyp — todo

Detailed task list for `plan.md`. `[x]` = done, `[~]` = partially done (the gap is
spelled out), `[ ]` = open.
Phase gates are hard: do not start a phase before the previous one's **exit criterion**.

---

## Phase −1 — analysis (done)

- [x] Analyse `datapreparation/` intake → `docs/data-intake.md`
- [x] Analyse the live site's API, data model and frontend → `docs/current-typometrics.md`
- [x] Read *Graph Databases for Fast Queries in UD Treebanks* → `docs/neo4j-encoding.md`
- [x] Read the grex paper, formalise the query pair → `docs/query-pairs.md`
- [x] Transcribe the Grew query language → `docs/grew-query-language.md`
- [x] Map the 12 precomputed measures onto query pairs → `docs/measures-mapping.md`
- [x] Specify the Grew→Cypher translation → `docs/grew-to-cypher.md`
- [x] `plan.md`, `setup.md`, `todo.md`
- [x] Install `grew` 1.21.0 + `grewpy_backend` 0.6.2 under `/opt/opam` (oracle)
- [x] Pull `neo4j:5.26-community`
- [x] Download UD 2.18 (684 056 893 B) and SUD 2.18 (587 560 508 B) → `data/raw/`

---

## Phase 0 — foundation

### 0.1 Repo hygiene
- [x] `git init`; `.gitignore` with `.env`, `*.env`, `data/`, `logs/`, `.venv/`,
      `node_modules/`, `dist/`, `__pycache__/` — **before the first commit**
- [x] `CLAUDE.md`: venv path, test command, model-routing table (`setup.md` §4),
      "never edit `djangotypometrics/` or `quasartypometrics/`"
- [x] `.venv` + `requirements.txt` (fastapi, uvicorn, neo4j, lark, pydantic, pytest,
      httpx, conllu)
- [x] `models.yaml` + `scripts/cheap.py` (`setup.md` §4)

### 0.2 Data intake
- [x] `scripts/fetch_treebanks.sh` — download, resume, sha256, `--check` for new releases
- [x] record `.sha256` for the two downloaded archives
- [x] `scripts/unpack.sh` → `data/treebanks/v2.18/{UD,SUD}_<Lang>-<Corpus>/`
- [x] copy `languageCodes.tsv`, `myLanguageCodes.tsv`, `languageGroups.tsv` →
      `data/meta/`; extend to every 2.18 language; import fails loudly on an unknown one
- [x] `data/MANIFEST.json`: per treebank source, sha256, n_sents, n_tokens, timestamp,
      importer revision

### 0.3 Neo4j
- [x] generate the password → `.env` (`600`); container per `setup.md` §5, bound to
      `127.0.0.1`, heap 8G / pagecache 4G, `db.transaction.timeout=60s`
- [x] `scripts/schema.cypher` — constraints + indexes from `docs/neo4j-encoding.md` §2
- [x] `scripts/import_neo4j.py`
  - [x] CoNLL-U reader: multiword tokens, empty nodes (skip), `#` metadata
  - [x] decompose deprel → `deprel`, `rel_1`, `rel_2`, `rel_deep` (UD *and* SUD configs)
  - [x] `Word` nodes with `idx`, FEATS and MISC as properties; `:Root` label
  - [x] `IN_SENTENCE`, `DEPREL`, `SUCCESSOR`, `MWT` edges
  - [x] per-sentence precomputation: `conllu`, `n_tokens`, `height`, `is_projective`,
        `is_tree` (`docs/data-intake.md` §4)
  - [x] batched `UNWIND` writes; idempotent per treebank (delete-then-insert)
  - [x] `--treebanks`, `--slice dev`, `--all`, `--jobs N`
- [x] import the 20-treebank dev slice, both schemes (`plan.md` §4)

**Exit:** ✅ `tests/test_import.py` asserts, per treebank, that `count(:Word)` equals
tokens **+ sentences** (Grew's `__0__` root node), `count(:Sentence)` equals the sentence
count, and that the precomputed `height` / `is_tree` / `is_projective` match a fresh
recomputation for every sentence.

---

## Phase 1 — the Grew→Cypher translator (the hard part)

### 1.1 Parser
- [x] lark grammar for `pattern` / `with` / `without` / `global`, comments (`%`)
- [x] node clauses: `=`, `<>`, `|`, `*`, `!f`, `re"…"`, `/…/i`, quoted values,
      disjunction of whole feature structures
- [x] edge clauses: plain, disjunction, negation `^`, regex, named `e:`, feature form
      `1=comp,2=obl`, `->>`, `* -[r]->`, `X -[r]-> *`
- [x] order/distance: `<`, `<<`, `delta()`, `length()` with all 5 comparators
- [x] comparisons: `X.f = Y.f`, `X.f <> Y.f`, `X.f = "s"`, `X.f = re"…"`, `!X.f`,
      `e1.label = e2.label`
- [x] `global { is_tree | is_forest | is_cyclic | is_projective }` and `is_not_*`
- [x] `meta.*` clauses
- [x] `$` non-injective suffix
- [x] AST dataclasses
- [x] `unparse` + round-trip test `parse(unparse(parse(s))) == parse(s)` over every
      construct the differential suite covers. Canonical, not faithful: comments dropped,
      spacing fixed — that is what makes it usable as a cache key

### 1.2 Validator
- [x] binding table: which identifiers a request binds
- [~] reject unsupported constructs with a *pointing* error: `UnsupportedConstruct`
      carries a message and a suggestion (unknown edge feature, unsupported `global`,
      unqueryable `meta.*`) but **no line/column** — only syntax errors have a position.
      Lexicons and `DEPS` are rejected by the grammar, without a helpful message
- [x] query-pair rule: every free identifier of Q is bound by S (`docs/query-pairs.md` §3),
      enforced in `combine()`; the error names the offending node and what S does bind
- [x] reject a bare `pattern` block in a subquery

### 1.3 Emitter
- [x] node clauses → `MATCH` + `WHERE`, all literals as parameters
- [x] `X [f <> v]` → `X.f IS NOT NULL AND X.f <> $v` (divergence #1)
- [x] regex normalisation: POSIX/PCRE → Cypher `=~`, anchoring, `(?i)` (divergence #2)
- [x] edge clauses per `docs/grew-to-cypher.md` §2
- [x] `idx` arithmetic for `<`, `<<`, `delta`, `length`
- [x] same-sentence constraint via `IN_SENTENCE` to a shared `_s`
- [x] **`with { C }` → `AND EXISTS { C }`** (not inlined — `docs/grew-to-cypher.md` §5)
- [x] `without { C }` → `AND NOT EXISTS { C }`
- [x] injectivity guards `X <> Y`, skipped for `$`-suffixed ids
- [x] `global` → `_s.is_projective` / `_s.is_tree` properties
- [x] three return modes: `count`, `aggregate`, `search`

### 1.4 Tests — the reason this phase exists
- [x] `tests/test_translate.py`: one unit test per row of `docs/grew-to-cypher.md` §§1–5,
      asserting the emitted Cypher and parameters
- [x] `tests/test_differential.py`: `neo4j_count(tb, req) == grewpy_count(tb, req)` for
      every construct × {`SUD_English-GUM`, `SUD_Japanese-GSD`, `SUD_Wolof-WTB`}
- [x] a `grewpy` fixture that sets `OPAMROOT=/opt/opam` and starts the backend once
- [x] close every row of the divergence table (§7) — fixed, or covered by an
      explicit accepted-difference test with a comment saying why
- [ ] property-based test: random small requests, differential-checked *(not done)*

**Exit:** the differential suite is green. **Nothing downstream may start before this.**
A wrong count does not look wrong — it looks like a typological finding.

---

## Phase 2 — intermediate deliverable: query → trees

- [x] `GET  /api/treebanks` → name, scheme, language, family, n_sents, n_tokens
- [x] `POST /api/validate` → parse errors with position, for live editor feedback
- [x] `POST /api/search` `{scheme, treebank, request, skip, limit}` →
      `{total, hits:[{sent_id, matched_nodes, conllu}]}`
- [~] hit cap (`MAX_LIMIT = 100`) and a Neo4j-level `db.transaction.timeout=120s`;
      no friendly timeout message yet
- [x] Quasar 2 app scaffold, `/grugrutyp/` base path
- [~] treebank picker (searchable, family shown per option but **not grouped**), scheme toggle
- [~] query editor: monospace, inline errors with line/column, example gallery.
      **No syntax highlighting** — it is a plain `q-input` textarea
- [x] `reactive-dep-tree` integration, matched nodes highlighted
- [~] pagination and copy-CoNLL-U button; the header shows total matchings but **not**
      the distinct sentence count
- [x] deploy: nginx location block + `grugrutyp-api.service` (`setup.md` §6)

**Exit:** a linguist answers a real question through the browser, no terminal.

---

## Phase 3 — query pairs, measures, plots

### 3.1 Backend
- [x] measure spec model: `MeasureSpec{kind, scope, response, expression, label}` +
      `SamplingPolicy{token_budget, min_scope, ci_tolerance, min_hits}` (`measure.py`)
- [x] `Sentence.bucket` (deterministic blake2b of sent_id) + index — `docs/sampling.md`
- [x] token-budget sampling: `pct = min(100, ceil(100 * budget / n_tokens))`, default
      budget 100k tokens. Measured on the dev slice: cold 11.4s -> 3.5s, i.e. 3.3x, close
      to the 3.5x projection
- [x] adaptive escalation — grew into the three-trigger policy (`n_scope`, interval
      width, `n_hit`), bounded to 10× the budget, judged per language on summed counts;
      giants (>1M tokens) defer to the refine button instead (`docs/sampling.md` §5)
- [x] the same sample serves S, Q and both axes: the percentage is decided once per
      treebank and escalation, if any, re-runs *every* axis. Otherwise a point would
      describe two different sub-corpora
- [x] query hash over `unparse(parse(text))`, so a comment, a reflowed line or a changed
      space no longer re-runs 705 treebanks for a query that has not changed. An
      unparsable scope falls back to its raw text — `validate()` reports syntax errors
      with a position, and a hash over broken text can only miss, never hit wrongly
- [x] `POST /api/measure` → **SSE stream**, one event per treebank, language merge in
      the `done` event; the stream also feeds the query log
- [x] Wilson score interval per point, exact at the 0 and 100 ends
- [x] cache table — SQLite `counts_v2`, keyed additionally on `sample_pct` and the
      treebank's `imported_at` revision (a re-import must not serve stale counts)
- [x] worker pool over treebanks (8), **smallest first**. It was largest-first on the
      makespan argument, which optimises the wrong thing when the endpoint streams: the
      first eight tasks were the eight biggest treebanks, so nothing reached the plot for
      minutes. Measured 0 of 352 treebanks after 102s; smallest-first gives 281 and 148
      languages in the same 102s
- [x] aggregate mode: `avg|sum|min|max` over `delta(X,Y)`, `abs(delta(X,Y))`,
      `length(X,Y)`, `X.<numeric feature>`, `sentence.*`. **`median` and `stddev` are
      rejected on purpose** — neither can be merged from per-treebank values into a
      language value without the raw distribution (`aggregate.py`)
- [~] **benchmark**: first numbers taken 2026-08-28 on the dev slice, warm cache,
      one query at a time:

      | query | SUD_English-GUM (257k tok) | SUD_Russian-SynTagRus (1.5M tok) |
      |---|---|---|
      | `pattern { GOV -[1=subj]-> DEP }` | 0.65 s | 3.93 s |
      | + `with { GOV << DEP }` | 0.56 s | 3.54 s |
      | noun–adj with order filter | 0.11 s | 1.29 s |
      | `with` introducing a new node | 0.53 s | 1.35 s |
      | `without` introducing a new node | 0.56 s | 1.53 s |

      Roughly linear in treebank size, ~2.5 s per million tokens. UD+SUD 2.18 is ~64 M
      tokens, so **one full pass ≈ 160 s serial, ×2 for a query pair ≈ 5 min cold**.
      That is too slow to feel interactive, and it is why the cache, sampling
      (`docs/sampling.md`) and the SSE stream are not optional. Corrected corpus size:
      **Counted after the full import, 2026-08-29: 75.9 M syntactic words over 705
      treebanks** (4.64 M sentences, 193 languages, 78 GB on disk). The earlier 64 M and
      109 M figures were both estimates from file sizes, which count comment lines,
      multiword-token lines and empty nodes. At the 100 k budget that is 28.3 M scanned,
      a 2.7× speed-up over 177 sampled treebanks — less than the 3.5× projected, because
      the largest treebank is 3.5 M rather than the 6.9 M the estimate suggested.

### 3.1b Decisions taken with Kim, 2026-08-28

* **Points are per language, as on the current site** — 193 points, not 705.
  Merging is done by **summing counts**, never by averaging percentages: a 2 k-token
  treebank must not weigh the same as a 1.5 M-token one, and summing is also what
  `statConll.py` effectively did (it concatenated a language's files before counting).
  Keep the per-treebank `(n_scope, n_hit)` in the cache and merge at display time, so
  Phase 5's treebank-quality checking can still drill down without a re-query.
* **One annotation scheme at a time**, switchable. `1=subj` and `nsubj` are not the same
  measure, so a plot only means something within one scheme. Presets carry both variants;
  a free-typed query that names a relation absent from the target scheme should warn.
* **Layout**: X and Y axis panels side by side in a sticky top bar, each with its Scope
  and Response editors and a live `n_scope` preview on the currently selected treebank;
  the plot takes the full width below. Collapsing the Y panel gives the 1-D strip plot.
* **Vocabulary**: the editors are **Scope (S)** and **Response (Q)**, following
  Herrera et al. 2024 §3.2 — see `docs/query-pairs.md` §1.

### 3.2 Frontend
- [x] measure builder: per axis a **Scope (S)** and a **Response (Q)** editor with a live
      exact preview on one treebank (`AxisPanel.vue`, `POST /measure/preview`)
- [x] preset library loading into the editors — grouped picker in `AxisPanel.vue`,
      15 presets incl. the Menzerath group; the picker shows the preset's name only
      until the first edit, because a stale name is a caption that lies
- [x] language-level merge by summing counts; per-treebank list in the point dialog
- [x] 1-D strip (collapse the Y panel) and 2-D scatter, chart.js; colour + marker from
      `data/meta/appearance.tsv`, with a **colour-by** selector over all six views
- [x] progressive rendering as SSE events arrive; provisional points carry no interval,
      because a confidence interval that narrows while you watch is worse than none
- [x] min-`n_scope` slider (replaces `axminocc`), applied client-side so it is instant,
      and it reports how many languages it removed rather than dropping them silently
- [x] point → sentence list → trees — the point dialog's **S** and **S ∧ Q** buttons
      open the query in the search tab, per treebank or across the whole language;
      *the feature the current site cannot have, and the main reason for on-the-fly*
- [x] shareable URL: the whole measure definition, base64 in the fragment, auto-runs on
      open. A measure defined by two free-text Grew requests has no name, so there is
      nothing to cite unless the definition travels
- [x] export PNG and TSV
- [x] axis captions derive from the query when no preset named one -- a preset's name
      outliving the query it described is a caption that lies, and a reader cannot notice

### 3.4 Language configuration — admin-editable, release-proof

Kim, 2026-08-28: *"this was done by a google sheet that was queried. ideally the config
could be done by something similar on grugrutyp, modifiable by admins. the problem to
address is that each version there are new languages appearing — and sometimes languages
disappearing."* Analysis and design: `docs/language-config.md`.

- [x] `scripts/xlsx2config.py` — the spreadsheet's four tabs → `data/meta/*.tsv`,
      **column by column**. The old hand export flattened five groupings into one string
      and was three revisions stale; both are recorded in the doc, §2
- [x] `backend/grugrutyp/langconfig.py` — views, appearance with a walk-up fallback,
      accent-folding name match, `audit()`
- [x] `lcode` column + resolve by ISO code before name — the identifier UD keeps stable
      across a rename, so a rename stops being a lost language
- [x] `scripts/config_audit.py` — release diff, rename detection (ISO code → curated name
      → string similarity), `--backfill-lcodes`, `--apply-renames`
- [x] catch up 2.12 → 2.18: 25 renames applied, 10 new languages added, 3 departed kept.
      `config_audit.py` exits 0 on 2.18, and `missing_families()` is empty for all 705
- [x] `meta.py` reads the config instead of its own hardcoded colour dict
- [x] **`GET /api/config/audit`** and an admin page whose front door is the release diff —
      `AdminView.vue`, reachable at `/grugrutyp/admin` (2026-08-30)
- [x] **admin editing** of `languages.tsv` / `appearance.tsv`: a table UI, write back to
      the TSV, `git commit` per change so the history stays greppable by language.
      Rename confirmations carry the orphan row's curation to the new name; rows are
      never deleted
- [x] auth for the admin routes — a token in `.env` (`GRUGRUTYP_ADMIN_TOKEN`), checked
      constant-time; one admin needs a password, not a login system. An OAuth admin flag
      can replace the dependency later (Phase 6.3) without touching the routes
- [x] **"colour by" control** in the plot UI — shipped with 3.2's plot (the selector over
      all six views); listed here from before they merged
- [ ] run `config_audit.py` from `scripts/unpack.sh` so a new release reports its drift at
      intake instead of at plot time
- [x] **decided 2026-08-30**: the TSVs are authoritative and the sheet retires — an admin
      console and an upstream spreadsheet is two sources of truth. `xlsx2config.py` stays
      for a one-off re-import if ever wanted; note the sheet still holds pre-2026-08-30
      colours (Germanic olive), so a re-import must be diffed, not applied blind

*Ordering and the admin/user split for this section now live in **Phase 6** (6.1, 6.2b).*

### 3.5 Upload your own treebank

From `ideas.md`; the blocker is configuration, not import — an uploaded treebank has no
config row, so no group, no colour, no legend entry. See `docs/language-config.md` §6.

- [ ] `POST /api/upload` — a CoNLL-U file or a zip, validated (parses, projectivity and
      tree checks run, deprels belong to the declared scheme)
- [ ] import into Neo4j under a `user:<id>` namespace, quota'd, with a TTL; the importer
      already takes a plain directory
- [ ] a config row asked for at upload time (language, group, or "compare only, no group"),
      feeding the same `languages.tsv` machinery
- [ ] the uploaded treebank appears in the plot as a distinct marker next to its language's
      other treebanks — this is also the Phase 5 treebank-quality comparison, arrived at
      from the other end
- [ ] privacy: uploads are the first user data grugrutyp would hold. Decide retention and
      whether they are visible to other users **before** building it

*Sequenced as **Phase 6.4** (after accounts); the temp/separate-DB questions are answered
there.*

### 3.3 Regression against the old site
- [x] `scripts/regression_2_12.py` prints the full comparison; `tests/test_regression.py`
      asserts only the **systematic** part. Per-language tolerance is deliberately not
      asserted: the tables are 2.12 and the database is 2.18, so that would be asserting
      that UD stopped changing
- [x] **Result on the complete corpus, exact (no sampling), 2026-08-29: median delta
      +0.00 over 512 language-relation pairs**, 466/512 within 5 points.

      | relation | languages in common | median | mean abs | within 5 pts |
      |---|---|---|---|---|
      | `subj` | 107 | +0.00 | 1.27 | 99 |
      | `comp:obj` | 114 | −0.00 | 0.99 | 106 |
      | `mod` | 114 | +0.00 | 1.68 | 105 |
      | `udep` | 103 | +0.00 | 1.26 | 96 |
      | `comp:obl` | 74 | +0.00 | 3.80 | 60 |

      No systematic offset anywhere: no inverted direction, no `idx` off-by-one, no stray
      root node in a scope. `comp:obl` is the loosest, which is expected — it is the rarest
      of the five and the one whose annotation moved most between 2.12 and 2.18
- [x] found and fixed by doing this: `skipFuncs`/`skipLangs` are **not** the five-relation
      defaults in the signature -- `maincomputation()` overrides them with `['root']` and
      `[]`. And the old tables *exclude* root attachments, where my own doc claimed they
      included them. Two presets were measuring the wrong denominator
      (`docs/measures-mapping.md` §2 point 1, corrected in place with the correction noted)
- [~] one outlier worth Kim's eye: **Beja `subj` 29.74 (2.12) -> 0.21 (2.18)**.
      `SUD_Beja-Autogramm` is a new treebank and 0.21% is the linguistically expected
      value for a Cushitic SOV language, so this looks like the treebank changing rather
      than us -- but it is the kind of thing worth a second opinion

**Exit:** head-initiality `subj` vs `comp:obj` reproduces the live site's plot shape;
regression tests pass within tolerance.

---

## Phase 4 — parity and cutover

- [x] preset library for every A/B measure of `docs/measures-mapping.md` — verified
      2026-09-01: all four A measures and all four B measures are presets; the `-cfc`
      variants are one edit away by design (that is what editable presets are for)
- [ ] the remaining C/D measures as batch-computed `derived` tables: `flexibility`
      (a function over head-initiality results, §4), the Menzerath a/b/c *fits*
      (the presets plot the raw quantities, not the fitted curves), Bakker comparison
- [x] port `Presentation.vue`'s measure explanations — done as preset
      descriptions/notes (the per-measure section) plus two about-dialog tabs:
      "Reading plots" (the interpretation section: 1-D/2-D reading, cloud shapes as
      implicational universals) and the Papers list (Glossa 2021, Depling 2023
      flexibility, Qualico 2021 Menzerath, grex, TLT 2025)
- [x] "similar plot" (DTW, `similarGraph.py`) — **dropped, 2026-09-01** (Kim can veto):
      it searched for the most similar plot within the fixed universe of the 12
      precomputed measures, and grugrutyp has no fixed universe — measures are
      free-form queries. If wanted later it belongs in Phase 5 as tooling over the
      cached measure results, and the DTW / Gale–Shapley code is among the orphaned
      scripts anyway
- [x] full 2.18 import, 2026-08-29: 705 treebanks, 193 languages, 75.9 M syntactic
      words, 78 GB on disk
- [ ] load test; Neo4j backup/restore procedure
- [ ] **ask Kim** where the 9 orphaned analysis scripts are
      (`docs/measures-mapping.md` §5)
- [ ] side-by-side review with Kim before any switch of `/`

---

## Publication — github.com/typometrics

Gate: **after the first version is verified** (differential suite green, tree rendering
confirmed, a linguist has used it). Kim's instruction, 2026-08-28.

- [x] `git init`, `.gitignore` in place before the first commit, no secrets or data tracked
      (50 files; `.env`, `data/raw/`, `data/treebanks/`, `data/neo4j/`, `logs/`,
      `node_modules/`, `dist/`, `.venv/` all excluded)
- [x] initial local commit
- [x] **one repo for now** (published 2026-09-01 as the monorepo). The translator can
      still be extracted later with `git filter-repo`, history intact, if it grows an
      audience of its own — nothing about publishing forecloses the split
- [x] `gh` 2.46 installed via apt; Kim authenticated with the device flow
- [x] licence: AGPL-3.0, already in the tree as `LICENSE` — consistent with the current
      typometrics code
- [x] PDFs in `docs/`: gitignored from the start, verified never tracked in any commit;
      `docs/references.md` carries the citations
- [x] history scrubbed by inspection: no `.env`, no secrets, no PDFs anywhere in the
      history; pack is 192 KiB
- [x] README badges / install instructions that work off this machine (2026-09-01:
      clone-based quick start, requirements, shields; machine paths and systemd
      references moved behind pointers to `setup.md`)
- [x] **pushed 2026-09-01**: <https://github.com/typometrics/grugrutyp>, branch `main`
      (renamed from `master`), 53 commits. NB the admin page's config commits are local
      until pushed — push occasionally to keep GitHub current

---

## Phase 5 — research goals

- [ ] grex P-pattern extraction: feature space over gov/dep/grandparent/siblings/
      grandchildren, sparse logistic regression, regularisation-path ranking, G-test,
      coverage/precision (`docs/query-pairs.md` §5)
- [ ] per-treebank ranked rule lists, browsable, with example sentences
- [ ] treebank quality check: measure vector vs same-language and neighbour-language
      treebanks, outliers ranked by deviation ÷ confidence width
- [ ] "strangeness report" for a language: top-k deviations from its family, with
      examples, exportable as a paper draft
- [ ] compare a measure across corpus versions (2.12 vs 2.18) — annotation drift detector

---

## Phase 6 — users, personalisation, admin (Kim's batch, ideas.md 2026-08-30)

The batch asks for: a per-user colour/group table, admin editing with a release-update
workflow (LLM-assisted?), a login system (Google/GitHub), saved queries and settings,
user treebank upload, plain-text→Grew for a few privileged users, and a query log with an
admin view. All of it is doable. The order below is governed by one observation: **only
saved-queries-sync, upload and plain-text→Grew need accounts at all** — the per-user
table needs a browser, and the admin goal needs *one* authenticated admin, which is a
password, not a login system. So the two highest-value items ship first and OAuth waits
until a feature actually consumes it.

### 6.1 Personal appearance table, in the browser — needs nothing, ships first
*(shipped 2026-08-30: `AppearanceCustomize.vue`, the "customise" button in plot options)*

- [x] a "customise" table over the served config: per language, colour / marker / group
      label override, per view; stored in `localStorage` as a **diff** against the site
      configuration, merged client-side. Site defaults stay untouched
- [x] export/import of the override set (TSV: view/language/label/color/marker), so a
      customisation can travel between browsers now and into an account later (6.3)
- [x] a visible "reset to site configuration" — per row and per view
- [x] decided: share links keep encoding the *site* configuration (a private palette in
      every link bloats it and makes figures irreproducible for the recipient); the
      dialog says so

### 6.2 Query logging — cheap, but it is a policy reversal, so it is a decision

Cross-cutting already wants structured logging of every query with its wall clock (for
performance). An admin-readable log of query *text* is different: the share link was
deliberately built on the URL fragment **to keep requests out of server logs**
(`PlotView.encodeState`). Logging them server-side reverses that on purpose.

- [x] **decided 2026-08-30** (Kim: "start 1 2 3 already", green-lighting the
      recommendation): query text + target + timings + outcome are logged, with **no
      IP/user binding**, disclosed in the about dialog's technical tab; failures logged
      too — a syntax error many users hit is a UI bug wearing a user's name
- [x] `querylog.py`: SQLite next to the measure cache, 180-day retention pruned on
      startup, `record()` never raises; `/search` and `/measure` instrumented (a
      client-abandoned measure logs as `client disconnected`); admin view in 6.2b

### 6.2b Admin console behind simple auth — goal 1 of the login idea, without OAuth

The release-update problem needs one trusted admin, not a user base. nginx basic auth or
a token in `/etc/grugrutyp/env` (the open question in 3.4) is enough; the OAuth admin
flag can replace it later (6.3) without redoing the pages behind it.

*(core shipped 2026-08-30: `admin.py` + `AdminView.vue` at `/grugrutyp/admin`; the tab appears
once that address is visited, the token is what gates the API)*

- [x] pick the simple auth (3.4): `GRUGRUTYP_ADMIN_TOKEN` in `.env`
- [x] admin page whose front door is the release diff — audit tab with confirm-rename
      and classify buttons feeding the editors
- [x] table editing of `languages.tsv` / `appearance.tsv`, git commit per change (3.4)
- [~] the version-update workflow as one screen: audit → renames confirmable → new
      languages classified in place is done; `fetch --check` / `unpack` stay CLI
      buttons-to-be (they are hours-long jobs, and a web button on an hours-long job
      needs progress plumbing that does not exist yet)
- [ ] LLM assist for the new languages: it **proposes** group/genus/colour/short name
      modelled on configured siblings — exactly what the 2.18 catch-up did by hand — and
      the admin approves row by row. It never writes the TSV itself: groupings are
      curation decisions (`docs/language-config.md`), and a wrong grouping does not fail,
      it just plots a lie
- [x] the query-log view (6.2), admin-only, filterable by kind, expandable query text
- [x] this settles the parked question: the TSVs become authoritative, the sheet retires
      (3.4's last item) — an admin console *and* an upstream spreadsheet is two sources
      of truth

### 6.3 Accounts — OAuth only, and only bundled with the first feature that needs them

Goal 2 (find your queries again, keep settings) is already 80% covered: a share link
reproduces the whole plot, and 6.1 keeps settings. What an account adds is sync and a
named list. So: build accounts **together with** saved queries, not as empty
infrastructure first.

*(built 2026-09-01; providers decided with Kim: **Google + GitHub + ORCID** — ORCID as
the researcher option; eduGAIN/CLARIN and the EUDI wallet are the documented future
European options. Design, privacy rules and OAuth-app registration steps:
`docs/accounts.md`. Ships dark until the OAuth apps are registered in `.env`.)*

- [x] Google + GitHub + ORCID OAuth (authlib), signed session cookie, SQLite user table
      (`users.py`). **No password accounts, ever** — identity is the provider's *stable*
      subject, never an email or login name
- [x] saved queries: a name + the share-link payload per user — one serialisation, two
      transports; plot share menu → Save query / My queries
- [x] an `is_admin` account flag opens `/admin` without the token (the token stays as
      bootstrap and break-glass); `llm_allowed` is the 6.5 allowlist, toggled per person
      on the admin Users tab
- [ ] the 6.1 overrides attach to the account on first login (the TSV export format is
      the migration; not wired yet)
- [x] **all three OAuth apps registered by Kim, 2026-09-01** — Google (published in
      production, with `privacy.html` / `terms.html` created to satisfy the console),
      GitHub (org-owned under github.com/typometrics), ORCID (public API). All three
      offered live

### 6.4 Upload your own treebank — the 3.5 list stands, now gated by accounts

The batch's two open questions, answered:

- *"can this be done temporarily?"* — yes: TTL + per-user quota; the importer already
  rebuilds and deletes per treebank, so expiry is a delete, not a migration
- *"in a separate database?"* — **Neo4j community edition runs exactly one database per
  instance**, so "separate database" means a second container. Not up front: the
  `user:<id>` namespace + TTL in the main DB (already 3.5's design) keeps uploads out of
  everyone else's queries via the same treebank filters that already scope every Cypher
  query. A second container only if isolation turns out to matter in practice
- privacy/retention stays the gate, decided before building (3.5)

### 6.5 Plain text → Grew query pairs, for a few privileged users — last, on purpose

Doable, and the honesty harness already exists: generate → `validate()` (which reports
unbound nodes and unsupported constructs with positions) → exact preview counts on one
treebank → the user confirms before any 705-treebank fan-out. But it is the only feature
that spends money per use, so it comes last and gated:

- [ ] needs 6.3 (allowlist of accounts) + a per-user budget + every translation logged
- [ ] wait for a few weeks of 6.2 query-log data first — what people actually try to ask
      is the spec for the prompt
- [ ] the model-routing table already says Grew→Cypher semantics is not a cheap-model
      task; assume the same for NL→Grew and budget for the strong model — which is the
      reason for the allowlist, not an implementation detail

**Order: 6.1 → 6.2 decision → 6.2b → (6.3 + saved queries) → 6.4 → 6.5.**
6.1 and 6.2b carry no dependency on each other and could swap; everything after 6.3
depends on 6.3.

---

## Status refresh, 2026-08-29 (answering "is todo up to date?" — it was not)

Shipped since the full-import entry above, in rough order:

- [x] language-level sampling and escalation (one rate per language, judged on summed
      counts, bounded 10×) — `docs/sampling.md` §3
- [x] process-wide cap of 8 concurrent DB queries: concurrent users share, not stack
- [x] preset warm cache (`scripts/warm_cache.py`); SUD fully warmed, UD in its tail —
      re-run after every import
- [x] grew.fr clustering in search: two clusterings × (no/key/whether), pivot grid
- [x] whole-language and multi-treebank search, paged as one corpus
- [x] mirror order operators `>>` and `>` (verified against the grewpy oracle)
- [x] UI: logo/antiqua theme, dark mode, per-tab URLs, stale-plot instead of auto-
      recompute, find-language rings, SVG export, square plot, 1-D ungrouped + KDE,
      structured examples library, about dialog, Y-axis edge handle
- [x] **Menzerath measures** (Kim, ideas.md): `scripts/backfill_menzerath.py` wrote
      `subtree_size` / `n_children` / `n_left` / `n_right` on every Word; presets carry
      a Menzerath group; `docs/menzerath.md`, `tests/test_menzerath.py`
- [ ] still parked on Kim: calcul-server disk/RAM check; GitHub push credentials for
      the typometrics org; admin-config auth choice

## Status refresh, 2026-08-30

- [x] **fit axes**: a plot option zooming a percentage axis to the distribution (a POS
      share maxing at 27% gets an axis to 30); in share links; exports follow
- [x] **expensive escalation deferred**: the automatic ×10 rescan of the giants (the
      whole tail of a cold run — German-HDT's escalated pass averaged 86 s/query) is now
      a proposal — a small refine button in the progress line — for languages still
      sampled at the escalation ceiling (>1 M tokens, 11 languages in SUD 2.18); smaller
      languages refine themselves. Recalibrated same day from a 300 k cut that flagged
      27 languages per rare measure — `docs/sampling.md` §5
- [x] **all Indo-European branches royalBlue** (Kim's rule; Germanic was olive, Italic
      brown, Baltoslavic purple). The upstream Google Sheet still has the old colours —
      a re-export would revert this, one more reason for Phase 6.2b's "TSVs become
      authoritative"
- [x] **Phase 6.1** personal appearance table (browser-local diff over the site config,
      TSV export/import, per-view reset)
- [x] **Phase 6.2** query log (text + timings + outcome, no IPs, 180-day retention,
      disclosed in the about dialog)
- [x] **Phase 6.2b** admin console at `/grugrutyp/admin`: token auth, release-audit front door
      with confirm-rename / classify, TSV editing with one git commit per change,
      query-log view. Open: LLM propose, fetch/unpack from the page

---

## Cross-cutting, do not defer

- [ ] every Cypher literal is a parameter — never string interpolation
- [ ] Neo4j reachable only on `127.0.0.1`; no credentials in git; heap capped
- [x] structured logging of every query with its wall clock, to find the slow shapes —
      `querylog.py` (2026-08-30); the text is logged too, per Phase 6.2's decision
- [ ] `docs/` stays current: when a design decision changes, the doc changes in the same
      commit
