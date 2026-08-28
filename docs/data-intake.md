# Data intake

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
scripts/fetch_treebanks.sh   → data/raw/{ud,sud}-treebanks-v2.18.tgz  (+ .sha256)
scripts/unpack.sh            → data/treebanks/v2.18/{UD,SUD}_<Lang>-<Corpus>/*.conllu
scripts/import_neo4j.py      → Neo4j                      (idempotent, per treebank)
```

### Sources, verified reachable 2026-08-28

| set | URL | size |
|---|---|---|
| SUD 2.18 | `https://grew.fr/download/sud-treebanks-v2.18.tgz` | 587 560 508 B |
| UD 2.18 | `https://lindat.mff.cuni.cz/repository/server/api/core/bitstreams/handle/11234/1-6149/ud-treebanks-v2.18.tgz` | 684 056 893 B |
| UD tools 2.18 | same handle, `ud-tools-v2.18.tgz` | — |
| UD docs 2.18 | same handle, `ud-documentation-v2.18.tgz` | — |

Landing pages: <https://surfacesyntacticud.org/data/> and
<https://universaldependencies.org/download.html>.

**The LINDAT handle `11234/1-6149` is version-specific.** A newer release gets a new
handle, so `fetch_treebanks.sh` must take the handle as a parameter and record it, not
guess it. SUD's URL is predictable from the version number; UD's is not.

### Version discovery

`fetch_treebanks.sh --check` scrapes the two landing pages for the highest `vX.Y` and
reports whether a newer release than the pinned one exists. It never auto-upgrades: a new
UD release changes annotation guidelines, and every stored measure value would silently
become incomparable. Upgrading is a deliberate act that produces a **new version
namespace** in the database (`Treebank.version`), so 2.18 and 2.19 results coexist and can
be diffed — which is itself a useful typological/quality signal.

### Idempotence and integrity

* Download with `curl -C -` (resumable), then verify against a `.sha256` recorded on first
  successful fetch. Re-running with an unchanged remote is a no-op.
* Import is per treebank and transactional: `MERGE` on `(:Treebank {name, version})`,
  delete-then-insert its sentences. Re-importing one treebank never touches others.
* A `data/MANIFEST.json` records, per treebank: source archive, sha256, n_sentences,
  n_tokens, import timestamp, importer git revision.

## 3. Naming and metadata

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
