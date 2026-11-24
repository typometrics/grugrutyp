# Data intake

> **Since 2026-11-24 the download, unpack, file selection and language metadata are the
> standalone package `udcorpus` in [`corpus/`](../corpus/README.md)**, written for a reader
> who will never run grugrutyp. Its README is the reference for §2's first two steps and
> for §3; this document keeps grugrutyp's side (the Neo4j import, one store per release,
> what a release changed under our queries) and the history.

Answers `ideas.md`: *"analyze how data intake is done in datapreparation/. download new
data from here … new versions should be taken by script and deployed"*.

## 1. How it is done today

`datapreparation/` contains no download step at all. The treebanks were unpacked by hand
(`datapreparation/sud-treebanks-v2.6/`, and 2.8/2.11/2.12 analysis folders appear only as
their *outputs* in `djangotypometrics/`). The pipeline is:

```
sud-treebanks-vX/**/*.conllu
        │
        │  conll.py            CoNLL-U → Tree (dict: nodeidx → {t, tag, gov:{govidx:label}, …})
        │  statConll.py        multiprocessing.Pool over languages
        ▼
sud-treebanks-vX-analysis/*.tsv      one file per measure, rows = languages
        │
        │  (copied by hand into djangotypometrics/)
        ▼
Django reads them at import time with pandas
```

Key details of `statConll.py`:

* `getAllConllFiles(basefolder, groupByLanguage=True)` — **merges every treebank of a
  language into one bucket**, keyed by the language code from the directory name. All
  treebank identity is lost here.
* `makeStatsThreaded(skipFuncs=['root','compound','fixed','flat','conj'], skipLangs=['kk','sa','ug','lt','be','cop','ta'])`
  — hard-coded exclusions applied to every measure.
* One pass over every tree accumulates 13 measure dictionaries at once
  (`types` list, line 142); distances are accumulated as lists then averaged.
* Output columns are the union of keys seen in any language, so the TSVs are wide and
  sparse (`nan` everywhere).

Problems: no reproducibility (no version pin, no checksum, no script), no treebank
granularity, hidden exclusions, and a hand-copy step between producing the TSVs and
serving them. Nine of the served TSVs have **no generating script in the tree at all**
(`measures-mapping.md` §5).

## 2. What grugrutyp does instead

No intermediate TSV layer. CoNLL-U goes straight into Neo4j; measures are computed by
query at request time and cached by `(treebank, query-hash)`.

```
corpus/fetch_treebanks.sh    → data/raw/{ud,sud}-treebanks-v2.18.tgz  (+ .sha256)
corpus/unpack.sh             → data/treebanks/v2.18/{UD,SUD}_<Lang>-<Corpus>/*.conllu
scripts/import_neo4j.py      → Neo4j                      (idempotent, per treebank)
```

### Sources, verified reachable 2026-08-28

| set | URL | size |
|---|---|---|
| SUD 2.18 | `https://grew.fr/download/sud-treebanks-v2.18.tgz` | 587 560 508 B |
| UD 2.18 | `https://lindat.mff.cuni.cz/repository/server/api/core/bitstreams/handle/11234/1-6149/ud-treebanks-v2.18.tgz` | 684 056 893 B |
| UD tools 2.18 | same handle, `ud-tools-v2.18.tgz` | — |
| UD docs 2.18 | same handle, `ud-documentation-v2.18.tgz` | — |
| SUD 2.19 | `https://grew.fr/download/sud-treebanks-v2.19.tgz` | 559 748 475 B |
| UD 2.19 | handle `11234/1-6316`, `ud-treebanks-v2.19.tgz` (+ tools, docs) | 693 376 253 B |

2.19 (fetched 2026-11-23): 402 UD + 401 SUD treebanks, 226 languages. The one UD treebank
with no SUD twin is `Portuguese-CINTIL`.

Landing pages: <https://surfacesyntacticud.org/data/> and
<https://universaldependencies.org/download.html>.

**The LINDAT handle `11234/1-6149` is version-specific.** A newer release gets a new
handle, so `fetch_treebanks.sh` must take the handle as a parameter and record it, not
guess it. SUD's URL is predictable from the version number; UD's is not.

### Version discovery

`fetch_treebanks.sh --check` scrapes the two landing pages for the highest `vX.Y` and
reports whether a newer release than the pinned one exists. It never auto-upgrades: a new
UD release changes annotation guidelines, and every stored measure value would silently
become incomparable. Upgrading is a deliberate act — see §2a.

### 2a. Upgrading to a new release: one Neo4j store per release (2.18 → 2.19, 2026-11-23)

This section used to say that a new release becomes a new *version namespace inside the
same database*, so that 2.18 and 2.19 "coexist and can be diffed". **That was never
true of the code, and doing it would have doubled every count.** Only the `Treebank` node
carries `version`; `Sentence`, `Word` and `Mwt` carry the bare treebank *name*, and:

* the importer deletes `MATCH (n:Word {treebank: $tb})` — every version's nodes at once;
* the Cypher emitter matches `(:Word {treebank: $tb})` — no version;
* `Neo4jEngine.treebanks()` returns every `Treebank` node with `n_sents > 0` — no version.

Importing 2.19 into the live store would therefore have wiped 2.18 treebank by treebank
under a serving site, and left both `Treebank` nodes per name pointing at one set of words:
the fan-out would count each treebank twice. Nothing fails; every percentage is merely
built on doubled counts.

So a release gets **its own Neo4j container and store**:

| release | container | bolt | store |
|---|---|---|---|
| 2.18 | `grugrutyp-neo4j` | `127.0.0.1:7687` | `data/neo4j/` |
| 2.19 | `grugrutyp-neo4j-219` | `127.0.0.1:7688` | `data/neo4j-2.19/` |

The procedure, which also gives a zero-downtime cutover and a one-line rollback:

1. `fetch_treebanks.sh --version X --ud-handle H`, `unpack.sh --version X`.
2. `GRUGRUTYP_VERSION=X scripts/config_audit.py` until CLEAN. Read its rename guesses:
   in 2.19 it proposed `Nanai ← Nayini` (Tungusic vs Iranian, string similarity only).
3. Start a new container on the next port with its own `data/neo4j-X/`, at reduced memory
   (heap 4G, page cache 4G) so the import does not push the live store into swap.
4. `NEO4J_URI=bolt://127.0.0.1:<port> GRUGRUTYP_VERSION=X import_neo4j.py --all
   --keep-going --strict --version X`. The live site is untouched throughout.
5. Differential suite against the new store (`NEO4J_URI` + `GRUGRUTYP_VERSION` in the
   environment), then regenerate the served derived tables (`menzerath_fit.py`,
   `mal_udw26.py`) against it.
6. **Cutover:** in `.env` set `NEO4J_URI` and `GRUGRUTYP_VERSION` together, restart
   `grugrutyp-api`. The measure cache keys on the version, so no stale count is served.
7. Recreate the new container at full memory (heap 6G, page cache 8G); stop the old one
   with `--restart no` but **keep its store** until the new release has been in service
   for a while. Rollback = revert the two `.env` lines and start the old container.

`.env`'s `GRUGRUTYP_VERSION` used to be ignored by the API — `main.py` imports `meta`
before anything loads `.env`, so the hard-coded default in `meta.py` was the real switch.
`meta.py` now reads the key from `.env` itself (environment first, then `.env`, then the
default), so step 6 is genuinely two lines.

Diffing two releases means querying two stores, not one; nothing in the API does that yet.

### 2b. What SUD 2.19 changed under our queries (measured 2026-11-23)

Label inventory, (head UPOS, deprel without `@deep`), 2.18 vs 2.19, over the first file of
20 typologically spread SUD treebanks (≤3,000 sentences each):

| head | 2.18 | 2.19 | cases in the sample |
|---|---|---|---|
| ADP | `comp:obj` | **`comp`** | 44,645 → 38 / 0 → 44,718 |
| SCONJ | `comp:obj` | **`comp`** | 7,009 → 278 / 0 → 6,784 |
| PART, ADV, CCONJ | `comp:obj` | **`comp`** | ~2,650 moved |
| NOUN, ADJ | `mod`, `det` | **`mod:poss`** (new) | ~4,200 possessors |
| NUM | — | **`mod:clf`** (new) | 181 |
| VERB | `comp:obj` | `comp:obj` | unchanged (−0.8%) |

**The complement of every function word lost its `:obj`.** Consequences:

* A query naming `comp:obj` under a function word (`GOV [upos=ADP]; GOV -[1=comp,2=obj]->`)
  matches almost nothing on 2.19. It does not fail; the languages just disappear. Write
  `-[1=comp]->` there: it matches both releases. Fixed in the Finding
  `adp-forbidden-middle` and in `scripts/welcome_plot.py`.
* A query whose object pattern leaves the head **unconstrained** —
  `V -[1=comp,2=obj]-> O` with no `upos` on V and no subject/aux/oblique that forces V to be
  verbal — **counted adpositional complements as objects on 2.18** (twice as many as verbal
  objects in the sample). On 2.19 the same text means verbal objects only. Affected: the
  `vo-score` preset (its UDW26 check passed because the test languages are harmonic), the
  Finding `weight-almond` and the catalogue's `dir-obj-w1/w2/w3/heavy`. Their 2.18 numbers
  are not comparable with 2.19 ones, and the weight finding must be re-verified on 2.19.
* `[1=mod]` still subsumes `mod:poss` and `mod:clf`; `[1=det]` loses the possessors that
  moved to `mod:poss`.

Re-run the diff at every release, before trusting any preset or Finding on the new data:
`scripts/label_diff.py 2.18 2.19` produced the table above.

### Idempotence and integrity

* Download with `curl -C -` (resumable), then verify against a `.sha256` recorded on first
  successful fetch. Re-running with an unchanged remote is a no-op.
* Import is per treebank and transactional: `MERGE` on `(:Treebank {name, version})`,
  delete-then-insert its sentences. Re-importing one treebank never touches others.
* A `data/MANIFEST.json` records, per treebank: source archive, sha256, n_sentences,
  n_tokens, import timestamp, importer git revision.

## 3. Naming and metadata

*Historical (2026-08). The metadata now lives in `corpus/meta/` and is described in
`corpus/README.md` §3–§5; `docs/language-config.md` keeps the design history.*

Directory names are `SUD_French-GSD` / `UD_French-GSD` → `Treebank.name = "SUD_French-GSD"`,
`.scheme = "SUD"`, `.language = "French"`, `.corpus = "GSD"`.

Language code, family and genus come from the existing curated files, which are worth
keeping — they encode Kim's grouping decisions, not something derivable:

* `djangotypometrics/languageCodes.tsv` + `myLanguageCodes.tsv` (code → name)
* `djangotypometrics/languageGroups.tsv` (name → genus, e.g. `Indo-European-Romance`)

These drive the plot colours and markers (`tsv2json.groupColors` / `groupMarkers`). Copy
them into `data/meta/`, and add the 2.18 languages that are missing from them — the import
must **fail loudly** on an unknown language rather than silently plotting it black, which
is what happens today.

## 4. Per-sentence precomputation at import

Computed once during import and stored on the `Sentence` node, because they are either
impossible or expensive to express in Cypher (`grew-to-cypher.md` §7):

| property | why |
|---|---|
| `conllu` | raw text of the sentence, for the tree viewer |
| `n_tokens` | denominators, sentence-length measures |
| `height` | `treeHeight` measure (`measures-mapping.md` §3) |
| `is_projective` | `global { is_projective }` |
| `is_tree` | guard against malformed treebanks — and a quality signal in its own right |

## 5. Storage budget

| item | size |
|---|---|
| the two archives | 1.2 GB |
| unpacked CoNLL-U (UD+SUD 2.18) | ~6 GB |
| Neo4j, property-based encoding (~6× CoNLL-U) | ~30 GB |
| + `conllu` property on sentences | ~6 GB |
| **total** | **~45 GB** |

`/home` has 1.1 TB free. Fine, but import in stages (see `plan.md`): a ~20-treebank
development slice first, all of 2.18 once the importer is proven.
