# grugrutyp

Grew queries over UD and SUD treebanks, backed by Neo4j.

The next generation of [typometrics](https://typometrics.elizia.net). Where the current
site plots a fixed menu of ~12 precomputed measures, grugrutyp lets a linguist define a
measure as a **pair of Grew queries** — a scope `S` and a subquery `Q` — and plots
`100 × #(S∧Q)/#(S)` for every treebank.

```grew
% scope: all subject relations
pattern { GOV -[1=subj]-> DEP }
% subquery: the subject follows its governor
with { GOV << DEP }
```

One pair is a one-dimensional typological measure; two pairs are the axes of a scatter
plot. The measure space stops being a menu and becomes a language.

## Status

| phase | what | state |
|---|---|---|
| 0 | data intake, Neo4j schema, CoNLL-U importer | **done** (20-treebank dev slice imported) |
| 1 | Grew → Cypher translator + differential tests vs Grew | **done**, suite green |
| 2 | query → matching trees, deployed at `/grugrutyp/` | **done** |
| 3 | query pairs, measures, 1-D and 2-D plots | not started |
| 4 | parity with the current site, full 2.18 import, cutover | not started |
| 5 | grex rule extraction, treebank quality checking | not started |

The live site at `/` is untouched and keeps working.

## Read this first

| document | what it answers |
|---|---|
| [ideas.md](ideas.md) | the original brief |
| [plan.md](plan.md) | architecture, phases, decisions, risks |
| [setup.md](setup.md) | how to run the build process, secrets, model routing |
| [todo.md](todo.md) | the detailed task list |
| [docs/current-typometrics.md](docs/current-typometrics.md) | how the existing site works, and its six real limitations |
| [docs/grew-query-language.md](docs/grew-query-language.md) | the Grew request language |
| [docs/query-pairs.md](docs/query-pairs.md) | the (S, Q) measure, from the grex paper |
| [docs/neo4j-encoding.md](docs/neo4j-encoding.md) | the graph encoding, and how it departs from the published one |
| [docs/grew-to-cypher.md](docs/grew-to-cypher.md) | the translation spec and every known divergence |
| [docs/measures-mapping.md](docs/measures-mapping.md) | which existing measures survive as query pairs |
| [docs/data-intake.md](docs/data-intake.md) | download, unpack, import |

## Quick start

```bash
cd /home/typometrics/grugrutyp
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

./scripts/fetch_treebanks.sh && ./scripts/unpack.sh
docker start grugrutyp-neo4j
.venv/bin/python scripts/import_neo4j.py --slice dev

.venv/bin/pytest tests/test_translate.py -q
OPAMROOT=/opt/opam PATH=/opt/opam/grew/bin:$PATH .venv/bin/pytest tests/ -q

systemctl start grugrutyp-api
cd frontend && npm install && npm run build
```

Then <https://typometrics.elizia.net/grugrutyp/>.

## Why the counts can be trusted

The translator is validated against **Grew itself**. `tests/test_differential.py` runs
every supported construct over three typologically different treebanks and asserts that
our Cypher returns exactly what `grewpy` returns. This is the reason `grew` and
`grewpy_backend` are installed on the box even though Neo4j is the production engine.

It has already paid for itself. Three findings that no amount of reading would have
produced:

* Grew materialises a **virtual root node `__0__`** in every sentence, and the root
  dependency is a real edge from it. Our first encoding dropped both, so every count was
  short by one node and one edge per sentence.
* Grew's `re"…"` is a **whole-string** match. An early version of the emitter wrapped
  patterns in `.*`, silently turning every regex into a substring search.
* Grew's **injectivity spans the whole request**, including `with` and `without` blocks,
  not just the `pattern` block.

The published Grew→Cypher translation scheme
([Deworetzki & Ljunglöf 2025](docs/)) does not handle any of these, because the paper
measures execution *time* rather than agreement. That is fine for a benchmark and fatal
for a tool whose output is a statistic. See
[docs/neo4j-encoding.md §1](docs/neo4j-encoding.md).
