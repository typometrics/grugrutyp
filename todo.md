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
- [ ] round-trip test `parse(unparse(ast)) == ast` — there is no `unparse` yet

### 1.2 Validator
- [x] binding table: which identifiers a request binds
- [~] reject unsupported constructs with a *pointing* error: `UnsupportedConstruct`
      carries a message and a suggestion (unknown edge feature, unsupported `global`,
      unqueryable `meta.*`) but **no line/column** — only syntax errors have a position.
      Lexicons and `DEPS` are rejected by the grammar, without a helpful message
- [ ] query-pair rule: every free identifier of Q is bound by S (`docs/query-pairs.md` §3)
      — **not implemented**; an unbound identifier in Q silently declares a new node
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
- [ ] measure spec model: `{kind: ratio|aggregate, scope, subquery|expression, min_n}`
- [ ] normalised query hash (AST-based, so whitespace/comments don't miss the cache)
- [ ] `POST /api/measure` → **SSE stream**, one event per treebank:
      `{treebank, value, n_scope, n_hit, ci_low, ci_high}`
- [ ] Wilson score interval per point
- [ ] cache table `(treebank, corpus_version, query_hash) → (n_scope, n_hit, computed_at)`;
      SQLite first, Postgres if contention appears
- [ ] worker pool over treebanks; cap concurrent Cypher statements
- [ ] aggregate mode: `avg|median|stddev` over `delta(X,Y)`, `abs(delta(X,Y))`,
      `length(X,Y)`, `X.<numeric feature>` (`docs/measures-mapping.md` §3)
- [ ] **benchmark on day 1 of this phase**: 250 treebanks × 2 counts, wall clock, cold
      and warm. If cold is > 60 s, batch with `UNION ALL` before building any UI on it.

### 3.2 Frontend
- [ ] measure builder: two Grew editors (scope, subquery), live `n_scope` preview on one
      treebank before committing to a full run
- [ ] 1-D strip/dot plot; 2-D scatter; colour + marker by family from
      `data/meta/languageGroups.tsv` (carry over `groupColors`/`groupMarkers`)
- [ ] progressive rendering as SSE events arrive, with a progress bar
- [ ] min-`n_scope` slider (replaces `axminocc`), error bars toggle
- [ ] point → sentence list → trees (reuses Phase 2) — *this is the feature the current
      site cannot have, and the main reason to prefer on-the-fly*
- [ ] shareable URL encoding the measure pair; export PNG/SVG/TSV

### 3.3 Regression against the old site
- [ ] `tests/test_regression.py`: for each A/B measure, new value vs the 2.12 TSV, after
      re-applying `skipFuncs`/`skipLangs` and accounting for the root artefact
      (`docs/measures-mapping.md` §2)
- [ ] document every systematic difference found — each one is either a bug in the new
      code or a bug in the old numbers, and both matter

**Exit:** head-initiality `subj` vs `comp:obj` reproduces the live site's plot shape;
regression tests pass within tolerance.

---

## Phase 4 — parity and cutover

- [ ] preset library for every A/B measure of `docs/measures-mapping.md`
- [ ] Menzerath + Bakker as batch-computed `derived` tables in the same UI
- [ ] port `Presentation.vue`'s measure explanations (the only real documentation)
- [ ] "similar plot" (DTW, `similarGraph.py`) — port or drop, decide explicitly
- [ ] full 2.18 import, all ~250 treebanks × 2 schemes; watch disk (~45 GB)
- [ ] load test; Neo4j backup/restore procedure
- [ ] **ask Kim** where the 9 orphaned analysis scripts are
      (`docs/measures-mapping.md` §5)
- [ ] side-by-side review with Kim before any switch of `/`

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

## Cross-cutting, do not defer

- [ ] every Cypher literal is a parameter — never string interpolation
- [ ] Neo4j reachable only on `127.0.0.1`; no credentials in git; heap capped
- [ ] structured logging of every query with its wall clock, to find the slow shapes
- [ ] `docs/` stays current: when a design decision changes, the doc changes in the same
      commit
