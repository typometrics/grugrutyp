# grugrutyp

Grew queries over UD and SUD treebanks, backed by Neo4j.

The next generation of [typometrics](https://typometrics.elizia.net). Where the current
site plots a fixed menu of ~12 precomputed measures, grugrutyp lets a linguist define a
measure as a **pair of Grew queries** — a **scope `S`** and a **response pattern `Q`**,
the vocabulary of the grex paper — and plots `100 × #(S∧Q)/#(S)` for every language.

```grew
% scope: all subject relations
pattern { GOV -[1=subj]-> DEP }
% response: the subject follows its governor
with { GOV << DEP }
```

One pair is a one-dimensional typological measure; two pairs are the axes of a scatter
plot. The measure space stops being a menu and becomes a language.

## Status

| phase | what | state |
|---|---|---|
| 0 | data intake, Neo4j schema, CoNLL-U importer | **done** — all 705 treebanks of 2.18 imported: 75.9 M syntactic words, 4.64 M sentences, 193 languages |
| 1 | Grew → Cypher translator + differential tests vs Grew | **done** — 132/132 differential tests green |
| 2 | query → matching trees, deployed at `/grugrutyp/` | **done** |
| 3 | query pairs, measures, 1-D and 2-D plots | **done** — SSE measure endpoint, sampling, cache, scatter UI, ratio **and** aggregate measures; regression against the 2.12 tables shows a median delta of **+0.00** over 512 language-relation pairs |
| 4 | parity with the current site, full 2.18 import, cutover | full import **done**; cutover awaits Kim's review |
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
| [docs/references.md](docs/references.md) | the two papers this is built on, with links |
| [docs/sampling.md](docs/sampling.md) | why big treebanks are queried on a slice, and what it costs in precision |
| [docs/language-config.md](docs/language-config.md) | where language groupings and plot colours come from, and how they survive a new UD release |

## Licence

AGPL-3.0, matching the existing typometrics code base (see the header on
`datapreparation/statConll.py`). Full text in [LICENSE](LICENSE).

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

After a new release, always:

```bash
.venv/bin/python scripts/config_audit.py     # what the release did to the language config
```

An unconfigured language does not fail — it plots grey. See
[docs/language-config.md](docs/language-config.md).

Then <https://typometrics.elizia.net/grugrutyp/>.

## Why the counts can be trusted

The translator is validated against **Grew itself**. `tests/test_differential.py` runs
every supported construct over three typologically different treebanks and asserts that
our Cypher returns exactly what `grewpy` returns. This is the reason `grew` and
`grewpy_backend` are installed on the box even though Neo4j is the production engine.

It has already paid for itself. Five findings that no amount of reading would have
produced:

* Grew materialises a **virtual root node `__0__`** in every sentence, and the root
  dependency is a real edge from it. Our first encoding dropped both, so every count was
  short by one node and one edge per sentence.
* Grew's `re"…"` is a **whole-string** match. An early version of the emitter wrapped
  patterns in `.*`, silently turning every regex into a substring search.
* Grew's **injectivity spans the whole request**, including `with` and `without` blocks,
  not just the `pattern` block.
* Anonymous edge variables must be unique across the *whole* translation. Reusing `_e1`
  inside an `EXISTS` subquery makes Cypher bind the same relationship as the outer
  `MATCH`, so the query returns 0 instead of erroring — silent, and invisible without an
  oracle.
* The old site's tables **exclude** root attachments (`statConll.py` runs with
  `skipFuncs=['root']`), so three presets were measuring a denominator ~5% too large.
  Found by the 2.12 regression comparison, not by reading — a uniform 5% shift moves every
  language together and the plot still looks entirely reasonable
  ([docs/measures-mapping.md §2](docs/measures-mapping.md)).

The published Grew→Cypher translation scheme
([Deworetzki & Ljunglöf 2025](docs/references.md)) does not handle any of these, because the paper
measures execution *time* rather than agreement. That is fine for a benchmark and fatal
for a tool whose output is a statistic. See
[docs/neo4j-encoding.md §1](docs/neo4j-encoding.md).
