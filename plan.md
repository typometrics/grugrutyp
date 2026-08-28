# grugrutyp — build plan

The next generation of <https://typometrics.elizia.net>. Reads `ideas.md`; assumes the
analyses in `docs/`.

## 1. The idea in one paragraph

Today's typometrics plots **precomputed** measures: a fixed set of ~12 tables, each a
language × option matrix, produced by an offline script that nobody can fully reproduce
any more. grugrutyp replaces the fixed set with a **query pair**: the user writes a Grew
*scope* query S and a *subquery* Q, and for every treebank the system reports
`100 × #(S∧Q)/#(S)`. One pair is a 1-D measure; two pairs are the x and y of a scatter
plot. The measure space stops being a menu and becomes a language.

## 2. Design decisions (settled)

| decision | choice | why |
|---|---|---|
| query engine | **Neo4j + a Grew→Cypher translator** | 30–600× faster than Grew-match (`docs/neo4j-encoding.md`); a plot needs ~500 counts, so engine speed is the product |
| encoding | property-based + `IN_SENTENCE` edges + `idx` + decomposed edge labels | `docs/neo4j-encoding.md` §2 |
| grew / grewpy | installed, but **as a test oracle only** | differential testing is what makes "we support Grew" true (`docs/grew-to-cypher.md` §9) |
| compute | on-the-fly, streamed, with a persistent `(treebank, query-hash)` cache | interactivity without recomputation |
| backend | FastAPI + Python 3.12 | `ideas.md`; async fan-out over treebanks fits SSE streaming |
| frontend | Quasar 2 / Vue 3, new app | existing app is Quasar 1 / Vue 2, EOL |
| trees | `reactive-dep-tree` (Kirian Guiller) | `ideas.md`; renders CoNLL-U directly |
| deployment | `typometrics.elizia.net/grugrutyp/`, own systemd unit, own port | the live site is untouched until we choose to switch (`ideas.md`) |
| granularity | computed per **treebank**, **plotted per language** | Kim, 2026-08-28: one point per language, as today. Merging **sums the counts**, never averages the percentages — a 27k-token treebank must not weigh as much as a 400k one. Per-treebank counts stay in the cache, so Phase 5's quality checking can drill down without re-querying |
| vocabulary | **scope (S)** and **response pattern (Q)** | the grex paper's own terms (Herrera et al. 2024 §3.2); "query" and "subquery" say nothing |
| language config | five groupings in `data/meta/*.tsv`, keyed by **ISO code** | the old Google-Sheet export was lossy and stale, and name-keying loses a language every time UD renames a directory (`docs/language-config.md`) |

## 3. Architecture

```
                       nginx  typometrics.elizia.net
        ┌──────────────────────┴────────────────────────┐
        /                                      /grugrutyp/
   existing Quasar 1 SPA                  new Quasar 2 SPA (static)
   /typometricsapp/ → uwsgi :7001         /grugrutyp/api/ → FastAPI :8020
        │                                        │
   Django + TSVs                           ┌─────┴──────┐
   (untouched)                             │  cache DB  │  SQLite → Postgres if needed
                                           └─────┬──────┘
                                                 │
                                      ┌──────────┴──────────┐
                                      │  Grew→Cypher        │
                                      │  translator         │
                                      └──────────┬──────────┘
                                                 │ bolt://127.0.0.1:7687
                                           Neo4j (docker)
                                           UD + SUD 2.18
```

```
grugrutyp/
├── ideas.md  plan.md  setup.md  todo.md
├── docs/                    ← the analyses; all design rationale lives here
├── data/
│   ├── raw/                 ← downloaded .tgz + .sha256
│   ├── treebanks/v2.18/     ← unpacked CoNLL-U
│   ├── meta/                ← languageCodes.tsv, languageGroups.tsv (curated, carried over)
│   └── MANIFEST.json
├── scripts/
│   ├── fetch_treebanks.sh   ← download, verify, --check for new releases
│   ├── unpack.sh
│   └── import_neo4j.py      ← CoNLL-U → Neo4j, idempotent, per treebank
├── backend/
│   └── grugrutyp/
│       ├── main.py          ← FastAPI app
│       ├── translate/       ← lexer, parser (lark), AST, validator, cypher emitter
│       ├── engine/          ← Neo4jEngine, GrewpyEngine (oracle), shared protocol
│       ├── measures/        ← ratio / aggregate / derived
│       ├── cache.py
│       └── meta.py          ← treebank registry, language families
├── frontend/                ← Quasar 2 SPA
└── tests/
    ├── test_translate.py    ← unit: one per construct in docs/grew-to-cypher.md
    ├── test_differential.py ← neo4j count == grewpy count, over a treebank matrix
    └── test_regression.py   ← new measures vs the 2.12 TSVs
```

## 4. Phases

### Phase 0 — foundation (~1 day)

Neo4j in docker; `fetch_treebanks.sh` + `unpack.sh`; `import_neo4j.py` importing a
**20-treebank development slice** (typologically spread: English-GUM, French-GSD,
Spanish-AnCora, German-HDT, Japanese-GSD, Korean-Kaist, Chinese-GSDSimp, Arabic-PADT,
Hebrew-HTB, Hindi-HDTB, Turkish-IMST, Finnish-TDT, Russian-SynTagRus, Wolof-WTB,
Naija-NSC, Indonesian-GSD, Vietnamese-VTB, Basque-BDT, Irish-IDT, Coptic-Scriptorium),
both schemes. Schema + indexes from `docs/neo4j-encoding.md` §2.

**Exit:** `MATCH (w:Word {treebank:"SUD_French-GSD"}) RETURN count(w)` matches
`wc -l` on the CoNLL-U.

### Phase 1 — the translator (~3 days, the hard part)

Parser → AST → validator → Cypher emitter, per `docs/grew-to-cypher.md`. Then the
**differential test harness**: every construct × 3 typologically different treebanks,
`neo4j_count == grewpy_count`.

**Exit:** the differential suite is green, and the divergence table in
`docs/grew-to-cypher.md` §7 is closed or each row has an explicit accepted-difference test.

*Do not start Phase 2 before this is green.* Everything downstream is arithmetic on these
counts; a wrong count is a wrong typological claim, and it will not look wrong.

### Phase 2 — the intermediate deliverable: query → trees (~2 days)

The `universal.grew.fr`-like tool from `ideas.md`: pick scheme + treebank, write one Grew
request, get the matching sentences drawn as dependency trees with the matched nodes
highlighted.

* `POST /api/search` → `{sent_id, matched_nodes, conllu}[]`, paginated
* Quasar 2 page: scheme/treebank picker, query editor with error display, result list,
  `reactive-dep-tree` per hit
* Deployed at `/grugrutyp/`

**Exit:** a linguist can answer a real question with it without touching a terminal.
This is also the debugging tool for everything after it — when a measure looks wrong, this
is how you find out why.

### Phase 3 — query pairs and plots (~4 days) — **done, except the aggregate mode**

* ✅ `POST /api/measure` — SSE, `start` / one `point` per treebank / `done` with the
  language merge
* ✅ persistent cache keyed `(treebank, version, **revision**, query_hash, sample_pct)`.
  `revision` is the treebank's `imported_at`: a re-import must not serve counts taken
  against the old contents
* ✅ min-`n_scope` filter (replaces `axminocc`), Wilson intervals, and it reports what it
  removed rather than dropping silently
* ✅ 1-D strip and 2-D scatter, colour/marker from `data/meta/appearance.tsv`, with a
  **colour-by** control over all five groupings the config has always held
* ✅ shareable URL: the whole measure definition in the fragment, auto-runs on open
* ❌ the *aggregate* mode (`avg(delta(GOV,DEP))`) — **not built**. `Neo4jEngine.aggregate`
  exists; the measure layer and the UI do not use it. This is the gap between 6 and 10 of
  the current site's twelve measures (`docs/measures-mapping.md` §3), and the next thing
  to build

**Exit: met.** `scripts/regression_2_12.py` gives a **median delta of +0.00** over 89
language-relation pairs, with 82/89 inside 5 points, on `subj` and `comp:obj` (SUD) and
`nsubj`/`obj` (UD). Per-language differences are 2.12-vs-2.18 annotation drift and are not
asserted; the systematic part is, and it is clean.

### Phase 4 — parity and cutover (~3 days)

* preset library reproducing the A/B measures of `docs/measures-mapping.md`
* Menzerath + Bakker as batch tables surfaced through the same UI (kind `derived`)
* port `Presentation.vue`'s explanatory text — it is the only documentation of what the
  measures mean
* full 2.18 import (all ~250 treebanks × 2 schemes)
* **only then** consider switching `/` to grugrutyp; `ideas.md` says thorough testing first

### Phase 5 — the research goals (later)

* **grex P-patterns.** Fix (S, Q), learn the predictor P per treebank by sparse logistic
  regression over the grandparent/siblings/grandchildren space
  (`docs/query-pairs.md` §5). Output: a ranked, human-readable rule list per language.
* **Treebank quality checking.** For a new treebank, compare its measure vector to (a)
  other treebanks of the same language, (b) neighbouring languages. Outliers are candidate
  annotation errors. The per-point confidence intervals from Phase 3 are what make this
  statistically honest.
* **Strangeness detection.** Rank a language's measures by deviation from its family's
  distribution; export the top-k with example sentences as a paper draft.

## 5. Risks

| risk | severity | mitigation |
|---|---|---|
| translator silently wrong on some construct | **critical** | Phase 1 differential harness against grewpy; refuse to translate anything unproven rather than guess |
| 500 Cypher counts per plot too slow | high | cache; measure early (Phase 3 day 1) with the real 20-treebank slice; fall back to per-treebank `UNION ALL` batching |
| Neo4j 45 GB / memory pressure on a shared box | med | staged import; `docker run` with an explicit heap cap; the box has 31 GB RAM and runs ~10 other services |
| users write catastrophic queries | med | statement timeout in Neo4j, per-request cap, `EXPLAIN` before running |
| missing generating scripts for 9 of the 2.12 TSVs | med | blocks *comparison*, not the build — regenerate from first principles, ask Kim in parallel (`docs/measures-mapping.md` §5) |
| UD 2.19 changes guidelines mid-project | low | version namespace in the DB; never auto-upgrade |

## 6. What is deliberately *not* in v1

Graph rewriting (GRS), enhanced dependencies, Grew lexicons, treebank editing, user
accounts, and any change to the live site.
