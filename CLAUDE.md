# grugrutyp

Next generation of typometrics: instead of ~12 precomputed measure tables, the user writes
a **Grew query pair** (scope S + subquery Q) and gets `100 × #(S∧Q)/#(S)` per treebank.
Read `plan.md` first, then `docs/`.

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

# tests
.venv/bin/pytest tests/test_translate.py -q                     # unit, no services needed
OPAMROOT=/opt/opam PATH=/opt/opam/grew/bin:$PATH \
  .venv/bin/pytest tests/test_differential.py -q                # vs the grewpy oracle

# data
./scripts/fetch_treebanks.sh --check                            # is there a newer release?
./scripts/unpack.sh
.venv/bin/python scripts/import_neo4j.py --slice dev            # 20-treebank dev slice
.venv/bin/python scripts/import_neo4j.py --all                  # ~250 x 2, hours

# services
systemctl restart grugrutyp-api      # FastAPI on 127.0.0.1:8020
docker restart grugrutyp-neo4j       # bolt://127.0.0.1:7687
cd frontend && npm run build         # -> frontend/dist, served by nginx at /grugrutyp/
cd frontend && npm run dev           # vite on :9000, proxies /grugrutyp/api to :8020
```

Long jobs: `setsid nohup <cmd> > logs/<name>.log 2>&1 < /dev/null &`. Run interactive
sessions inside `tmux` — a translator session runs for hours.

## Layout

| path | what |
|---|---|
| `docs/` | all design rationale, and the measured facts behind it |
| `scripts/` | fetch / unpack / import into Neo4j |
| `backend/grugrutyp/translate/` | Grew grammar -> AST -> validator -> Cypher emitter |
| `backend/grugrutyp/engine/` | Neo4j query engine |
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
* 78 of 2.18's languages have no entry in `data/meta/languageGroups.tsv` and plot as
  `unknown`. `--strict` refuses to import until that is fixed.

## Model routing

`./scripts/cheap.py --model <name>` (see `models.yaml`, `setup.md` §4):

| task | model |
|---|---|
| bulk Python / boilerplate behind an existing test | `deepseek-chat` |
| Vue / Quasar components, CSS | `qwen3-coder-plus` |
| one hard debugging problem | `deepseek-reasoner` |
| Grew→Cypher semantics, statistics, phase gates | **do it yourself** |
