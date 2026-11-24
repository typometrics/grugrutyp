# grugrutyp

Next generation of typometrics: instead of ~12 precomputed measure tables, the user writes
a **Grew query pair** — a **scope S** and a **response pattern Q**, the grex paper's terms
— and gets `100 × #(S∧Q)/#(S)` per language. Read `plan.md` first, then `docs/`.

## Hard rules

1. **Never edit `/home/typometrics/djangotypometrics/` or `/home/typometrics/quasartypometrics/`.**
   They serve the live site at <https://typometrics.elizia.net/>. grugrutyp lives beside
   them at `/grugrutyp/` and stays there until Phase 4 says otherwise.
2. **Nothing downstream of the translator may be built on unverified counts.**
   `tests/test_differential.py` must be green first. A wrong count does not look wrong --
   it looks like a typological finding.
3. **Every Cypher literal is a parameter.** Never string-interpolate into a query.
4. When a design decision changes, the doc in `docs/` changes in the same commit.

## Commands

```bash
cd /home/typometrics/grugrutyp

# dependencies: install from the lock (pip freeze snapshot), not bare requirements.txt
.venv/bin/pip install -r requirements.lock

# tests
.venv/bin/pytest -q -m "not slow"                               # unit + measure layer
.venv/bin/pytest tests/test_translate.py -q                     # unit, no services needed
OPAMROOT=/opt/opam PATH=/opt/opam/grew/bin:$PATH \
  .venv/bin/pytest tests/test_differential.py -q                # vs the grewpy oracle (SUD)
GRUGRUTYP_DIFF_SCHEME=ud OPAMROOT=/opt/opam PATH=/opt/opam/grew/bin:$PATH \
  .venv/bin/pytest tests/test_differential.py -q                # the UD leg (separate process: grewpy holds one config)

# data -- download, unpack, language config: corpus/ (udcorpus, corpus/README.md)
./corpus/fetch_treebanks.sh --check                             # is there a newer release?
./corpus/unpack.sh --version 2.19                               # (scripts/*.sh are wrappers)
.venv/bin/python scripts/config_audit.py                        # = python -m udcorpus.audit on the live release
(cd corpus && ../.venv/bin/python -m pytest -q tests)           # udcorpus's own tests, no data needed
.venv/bin/python scripts/import_neo4j.py --slice dev            # 20-treebank dev slice
.venv/bin/python scripts/import_neo4j.py --all --keep-going     # 803 treebanks (2.19), ~8 h
#   a NEW release goes into its own container/store, never the live one: docs/data-intake.md §2a
.venv/bin/python scripts/label_diff.py 2.18 2.19                # what the release relabelled (§2b)
#   resume after a crash without redoing what landed:
.venv/bin/python scripts/import_neo4j.py --all --keep-going \
    --skip-imported-since 2026-08-28T17:16:00

# compare against the current site's 2.12 numbers
.venv/bin/python scripts/regression_2_12.py --scheme SUD

# services
systemctl restart grugrutyp-api      # FastAPI on 127.0.0.1:8020
docker restart grugrutyp-neo4j-219   # the live store since 2026-11-24: bolt://127.0.0.1:7688, data/neo4j-2.19/
#   .env NEO4J_URI + GRUGRUTYP_VERSION select the store; meta.py reads the version from .env
#   ALWAYS `docker stop -t 300`: the default 10 s kills Neo4j mid-flush, and the next start
#   then spends many minutes in recovery + index cleanup with the site down (2026-11-24)
#   recreate (memory change): --user 7474:7474 skips the image's slow chown -R; 6G heap / 8G cache
cd frontend && npm run build         # -> frontend/dist, served by nginx at /grugrutyp/
cd frontend && npm run dev           # vite on :9000, proxies /grugrutyp/api to :8020
```

Long jobs: `setsid nohup <cmd> > logs/<name>.log 2>&1 < /dev/null &`. Run interactive
sessions inside `tmux` — a translator session runs for hours.

## Layout

| path | what |
|---|---|
| `docs/` | all design rationale, and the measured facts behind it |
| `corpus/` | **standalone** ingestion + language metadata (`udcorpus`, stdlib only): fetch, unpack, file selection, ISO-code identity, groupings, audit, a reference measure. No grugrutyp import inside it; handed to people who never run grugrutyp. `corpus/README.md` |
| `corpus/meta/` | languages.tsv, appearance.tsv, language_names.tsv, iso639.tsv, measure_exclusions.tsv |
| `scripts/` | import into Neo4j, mining, derived tables (fetch/unpack/config_audit are wrappers into corpus/) |
| `backend/grugrutyp/translate/` | Grew grammar -> AST -> validator -> Cypher emitter |
| `backend/grugrutyp/engine/` | Neo4j query engine |
| `backend/grugrutyp/measure.py` | Wilson intervals, sampling policy, language merging |
| `backend/grugrutyp/runner.py` | fan-out over treebanks, escalation, cache |
| `backend/grugrutyp/langconfig.py`, `conllu.py` | re-exports of `udcorpus.languages` / `udcorpus.conllu`; `meta.py` configures udcorpus (data root, live version) |
| `backend/grugrutyp/main.py` | FastAPI |
| `frontend/` | Quasar 2 / Vue 3 (Vite), `reactive-dep-tree` for trees |
| `tests/` | unit + differential-vs-Grew |

## Things that are true and non-obvious

* Grew materialises a virtual root node `__0__` per sentence and the root dependency is a
  real edge from it. We do too — otherwise counts are short by one node and one edge per
  sentence. `pattern { X }` therefore counts tokens **plus** sentences.
* Grew's `re"…"` is a **whole-string** match, exactly like Cypher `=~`. Do not wrap
  patterns in `.*`.
* `with { … }` compiles to `EXISTS { … }`, not to inlined MATCHes: inlining multiplies the
  matching count and the ratio would exceed 100%.
* Injectivity spans the whole request, including `with`/`without` blocks.
* An edge label is a feature structure in **both schemes**, not just SUD. `-[1=comp]->`
  subsumes every `comp:*` in SUD, and `-[1=aux]->` subsumes every `aux:*` (`aux:pass`,
  `aux:caus`, …) in UD — same for `nsubj:pass`, `obl:arg`, `flat:name` and every other UD
  subrelation. Only the `@deep` part is SUD-specific.
  The importer decomposes both: `deprel` / `rel_1` / `rel_2` / `rel_deep`.
* The import's list-scan Cypher is deliberate and measured; see the comment on
  `WRITE_BATCH` before "optimising" it.
* **The box has 7200 rpm spinning disks (`HGST HUS726020AL`, RAID1), and the 73 GB store
  does not fit in the 18 GB page cache.** Warm a query is 0.6-2 s; cold it is 55 s. That
  single fact dominates every performance question — not CPU, not the query design, and
  certainly not parallelism, which makes it worse. `docs/performance.md`.
* **One Neo4j store per UD release.** Word and Sentence nodes carry only the treebank
  *name*, not the version: importing a second release into the live store would delete
  the first treebank by treebank and leave two Treebank nodes per name, doubling every
  count. docs/data-intake.md §2a.
* **SUD 2.19 relabelled every function word's complement `comp:obj` → `comp`.** Write
  `-[1=comp]->` under ADP/SCONJ (matches every release), and constrain the head of
  `-[1=comp,2=obj]->` to a verb, or 2.18 data counts adposition complements as objects.
  docs/data-intake.md §2b.
* **Never run the differential suite, or trust any count, while an import is running.**
  The importer rebuilds a treebank in place, and a read landing mid-rebuild returns a
  count over whatever has been written so far -- it does not fail. Measured: the suite
  gave 2 silent mismatches against a database being rewritten, and 132/132 on the same
  data once idle. `/search` and `/measure/preview` now 404 on a treebank whose rebuild is
  in flight; the measure fan-out was already safe via `treebanks()`' `n_sents > 0` filter.
* The import batches its deletes **from Python**, not with `CALL { … } IN TRANSACTIONS`.
  That construct is only legal in an implicit transaction, which takes the server's
  `db.transaction.timeout` (60s when this was learned; the container now runs 300s —
  the lesson stands either way) — and every dev-slice treebank blew through it while
  the API was serving. It looked survivable only because `IN TRANSACTIONS` commits as
  it goes, so each timed-out attempt left less to delete and a retry finished the job.
  Read the comment on `DELETE_CHUNK` before changing it back.
* **The old site's tables exclude root attachments** (`statConll.py`, `skipFuncs=['root']`).
  It makes no difference to a scope naming a relation -- a `subj` edge never comes from
  `__0__` -- but `pattern { X }` and `pattern { GOV -> DEP }` need the exclusion written
  in, or the denominator is ~5% too large. `docs/measures-mapping.md` §2 point 1.
* Merging treebanks into a language point **sums the counts**; it never averages the
  percentages. A 27k-token treebank must not weigh as much as a 400k one.
* **The unit of sampling and escalation is the language, not the treebank**
  (`runner.evaluate_language`): one percentage from the language's total tokens, applied
  to every one of its treebanks, escalation judged on the summed counts. Summing raw
  counts taken at *different* rates would weight the small treebanks of a language far
  above their share — do not reintroduce per-treebank rates. `docs/sampling.md` §3.
* The measure cache key includes the treebank's `imported_at`. Do not remove it: without
  it a re-import serves counts taken against the old data.
* Escalation from a sample has **three** triggers, and `n_hit < min_hits` is the one that
  is easy to leave out: 3 hits in a 50,000 scope has a *narrower* interval than the
  tolerance while being a 58% relative error.
* Language groupings, colours and markers live in `corpus/meta/*.tsv`, read by
  `udcorpus.languages` (re-exported as `grugrutyp.langconfig`). `data/meta/` now holds only
  grugrutyp's result tables (bakker, mal_udw26, menzerath_abc), read by `reference.py`.
  `backend/grugrutyp/__init__.py` puts `corpus/` on `sys.path` (no pip install: the venv is
  shared by every checkout). Point tests at scratch metadata with
  `udcorpus.config.configure(meta_dir=...)`, not by patching a module constant. A language carries **five** groupings, not one; the
  old site flattened them and could therefore offer a single colouring. Resolution is by
  **ISO code first, name second**, because UD renames directories between releases and
  keeps the code. Run `scripts/config_audit.py` after every `unpack.sh` — an
  unconfigured language does not fail, it plots grey. `docs/language-config.md`.
* Do not hand-edit `corpus/meta/languages.tsv` groupings without reading that doc: the
  groupings are curation decisions, and "Agglutinating" sitting next to "Semitic" is
  deliberate.

## Model routing

`./scripts/cheap.py --model <name>` (see `models.yaml`, `setup.md` §4):

| task | model |
|---|---|
| bulk Python / boilerplate behind an existing test | `deepseek-chat` |
| Vue / Quasar components, CSS | `qwen3-coder-plus` |
| one hard debugging problem | `deepseek-reasoner` |
| Grew→Cypher semantics, statistics, phase gates | **do it yourself** |
