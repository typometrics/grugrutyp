# udcorpus — UD/SUD treebanks in, languages and counts out

This folder is everything needed to go from the public Universal Dependencies releases to
**one number per language**, without the grugrutyp web application, its database or any
third-party Python package:

1. download a release (UD and SUD), verify it, unpack it;
2. decide which files make up which language, and which are left out and why;
3. give every language a stable identity and its groupings (family, area, typology…) and
   plot colours, and notice when a new release breaks that;
4. count something over the trees, the way grugrutyp does, and get the same number.

It is the ingestion half of [grugrutyp](https://typometrics.elizia.net/grugrutyp/), cut
out so it can be read, run and tested on its own. grugrutyp imports this package; nothing
here imports grugrutyp.

Requirements: Python ≥ 3.10, `bash`, `curl`, `tar`, `sha256sum`. Tests need `pytest`.
About 1.3 GB of downloads and 6 GB unpacked per release.

```bash
cd corpus
./fetch_treebanks.sh --check                         # what is the latest release?
./fetch_treebanks.sh --version 2.19 --ud-handle 11234/1-6316
./unpack.sh --version 2.19
python -m udcorpus.treebanks --scheme SUD            # languages -> treebanks
python -m udcorpus.audit                             # is every language configured?
python -m udcorpus.measure head-initial --rel subj --scheme SUD > subj.tsv
python -m pytest tests                               # 29 tests, no download needed
```

By default data goes to `corpus/data/` (`raw/` for archives, `treebanks/v2.19/` unpacked).
Inside the grugrutyp repository it goes to the repository's `data/` instead. Either way
`--data DIR` (shell) or `UDCORPUS_DATA=DIR` (both) overrides it.

---

## Glossary, for a programmer

| term | meaning |
|---|---|
| **treebank** | a corpus of sentences, each annotated as a dependency tree. One directory, e.g. `UD_French-GSD` = language *French*, corpus *GSD*. A language usually has several. |
| **UD** | [Universal Dependencies](https://universaldependencies.org): ~400 treebanks, ~200 languages, one annotation scheme, a release every six months (2.19 = November 2026). |
| **SUD** | [Surface-Syntactic UD](https://surfacesyntacticud.org): the same treebanks converted automatically to a scheme where function words (prepositions, auxiliaries, conjunctions) are heads rather than dependents. Typometrics measures run on SUD by default, because its head–dependent directions are more comparable across languages. A SUD release follows each UD release with the same version number. |
| **CoNLL-U** | the file format: one word per line, 10 tab-separated columns, a blank line between sentences, `# sent_id = …` / `# text = …` comments. [Spec](https://universaldependencies.org/format.html). |
| **word / token** | a line with an integer ID. `3-4` lines are *multiword tokens* (French *du* = *de le*): kept aside, not words. `5.1` lines are *empty nodes* (enhanced annotation): skipped. |
| **HEAD** | the ID of the word this word depends on (its *governor*); `0` means it is the root of the sentence. |
| **deprel** | the label of that dependency: `nsubj`, `obj` (UD) or `subj`, `comp:obj` (SUD). Labels have parts: `comp:obl@agent` is `1=comp, 2=obl, deep=agent`. A query for relation `subj` means "first part is `subj`", so it also matches `subj:pass` and `subj@expl`. `udcorpus.conllu.decompose_deprel` does the split. |
| **UPOS** | the word's universal part of speech: `NOUN`, `VERB`, `ADP` (adposition)… |
| **virtual root `__0__`** | the query engine grugrutyp copies ([Grew](https://grew.fr)) adds a node 0 to every sentence, with form `__0__`, and treats the root attachment as a real edge from it. So "every dependency" counts the root attachment unless you exclude it; this matters only for measures over *all* relations (see `measure.py`). |
| **head-initial** | the governor comes before the dependent in the sentence (`HEAD < ID`). "60% of subjects are head-initial" = 60% of subjects follow their verb. |
| **language point** | the value plotted for one language: counts summed over all its selected treebanks, then turned into a percentage. Never an average of per-treebank percentages: a 27k-word treebank must not weigh as much as a 400k-word one. |

---

## 1. Download and unpack

`fetch_treebanks.sh` downloads four archives into `<data>/raw/`: the SUD treebanks, the UD
treebanks, and UD's tools and documentation. On first download it records a `.sha256`
next to each archive; on every later run it **verifies** against it, so a remote file that
changed under a fixed version number is an error, not a silent update. Downloads resume
(`curl -C -`). It also writes `SOURCES-v<version>.txt` with the URLs used.

* The **SUD** URL is derived from the version: `https://grew.fr/download/sud-treebanks-v2.19.tgz`.
* The **UD** URL is not: the LINDAT repository gives every release its own *handle*, which
  you must look up on <https://universaldependencies.org/download.html> and pass as
  `--ud-handle`. 2.18 = `11234/1-6149`, 2.19 = `11234/1-6316`.
* `--check` only reports the newest release advertised on both landing pages. Nothing
  upgrades automatically: a new release changes annotations (see §6), so moving to it is
  a decision.

`unpack.sh --version 2.19` extracts both archives into `<data>/treebanks/v2.19/`, stripping
their top directory, so the `UD_*` and `SUD_*` treebank directories sit side by side.
2.19: 402 UD and 401 SUD treebanks (the UD one without a SUD twin is `Portuguese-CINTIL`).

## 2. Which files, which language

`udcorpus.treebanks` reads the release directory:

* a treebank directory is named `<UD|SUD>_<Language>-<Corpus>`; anything else (UD ships a
  few non-treebank folders) is ignored. The language keeps its underscores: `Ancient_Greek`,
  `Old_French`.
* **all** `*.conllu` files of a treebank are taken — `train`, `dev` and `test` together. The
  split exists to train parsers; for counting it is meaningless.
* `measure_selection(scheme)` gives, per language, the treebanks summed into its point:
  one scheme only (the UD and SUD versions of a corpus are two annotations of the same
  text, never added together), minus `meta/measure_exclusions.tsv`.

`meta/measure_exclusions.tsv` (18 rows) removes treebanks that would distort a language's
point: exact duplicates under another script or tokenization (`Chinese-GSDSimp`, the
Japanese `*LUW` treebanks), learner corpora (non-native production: `English-ESL`,
`Czech-CzeSL`, `Korean-KSL`…), child language (`English-CHILDES`), constructed teaching
sentences, and historical stages filed under the modern language (`Italian-Old`,
`French-ALTS`). Each row says why. Excluded treebanks still exist in `treebanks()`; they
are only kept out of measures.

On 2.19 SUD: 383 of the 401 treebanks enter measures, for 226 languages — the same 383
grugrutyp's plots run over.

```bash
python -m udcorpus.treebanks --scheme SUD           # one line per language: family, corpora
python -m udcorpus.treebanks --scheme UD --files    # ... and every file
```

```python
from udcorpus.treebanks import measure_selection
from udcorpus.conllu import read_conllu
for language, tbs in measure_selection("SUD").items():
    for tb in tbs:
        for path in tb.conllu_files():
            for sentence in read_conllu(path):   # streaming; ~6 GB never sits in memory
                ...
```

## 3. Language identity

UD **renames languages between releases** (`Wu` → `Shanghainese`, `Oriya` → `Odia`,
`Kurmanji` → `Northern_Kurdish`, two dozen in 2.18 alone) but keeps the ISO 639 code, which
is the prefix of the file names: `UD_French-GSD/fr_gsd-ud-train.conllu` → `fr`. So a
language is looked up **by ISO code first, by name second** (`languages.lookup`). A dozen
treebanks name their files freely and have no code; they are matched by name.

Names are compared *folded* (`languages.fold`): accents, case, spaces and underscores
removed, because the metadata spells `Xavánte`, `Apurinã`, `Old French` where UD's
directories say `Xavante`, `Apurina`, `Old_French`.

## 4. Groupings and colours

The metadata, all small tab-separated text files under version control (`git diff` shows
exactly what changed):

| file | columns | what |
|---|---|---|
| `meta/languages.tsv` | language, group, genus, subgenus, simple_group, area, typology, lcode, historical | one row per language: its groupings (229 rows) |
| `meta/appearance.tsv` | group, color, marker | plot colour and marker per group label |
| `meta/language_names.tsv` | code, name | curated display names; wins over the next |
| `meta/iso639.tsv` | code, name | the ISO 639 reference list, not edited |
| `meta/measure_exclusions.tsv` | corpus, language, reason | §2 |
| `meta/spreadsheet/` | | the Google Sheet these were first extracted from (`tools/xlsx2config.py`); the TSVs are now the curated source |
| `meta/legacy/` | | the 2.12-era site's flattened tables, not read by any code, kept for provenance |

A language carries **several groupings at once**, and a plot can colour by any of them
(a *view*, `languages.VIEWS`):

| view | French | Japanese |
|---|---|---|
| `family` (default) | Italic | Japonic |
| `group` | Indo-European | KJ |
| `genus` | Italic | Japonic |
| `simple_group` | Indo-European | Other |
| `area` | E | As |
| `typology` | Indo-European | Agglutinating |

`genus = Other` means "none of the named branches" and falls back to the group. The
`historical` flag marks non-contemporary doculects (Latin, Old French…), drawn hollow and
excludable.

Colour lookup **walks up** rather than failing: a label with no `appearance.tsv` row
(`Indo-Aryan`) takes its parent's colour (`Indo-European`), along
`typology → genus → group → simple_group → Other`. The `area` view is geographic, not
genetic, so it gets a generated palette keyed on the label instead.

These groupings are curation decisions — `Agglutinating` next to genetic families is on
purpose. Change them with the people who made them, not to tidy them.

## 5. After every new release: the audit

Nothing in this pipeline raises an error when a release adds or renames a language: an
unconfigured language simply has no group and plots grey. The audit turns that into a list:

```bash
python -m udcorpus.audit                    # exit status 0 = CLEAN, 1 = action needed
python -m udcorpus.audit --json
python -m udcorpus.audit --backfill-lcodes  # write ISO codes into languages.tsv (safe)
python -m udcorpus.audit --apply-renames --min-confidence 0.85
```

It reports languages on disk with no row, rows absent from the release (kept: languages
come back), labels with no colour, rows with no grouping, and **probable renames**, found
in three passes: same ISO code, then the curated name table (`language_names.tsv` says
`wuu` = `Wu`, the disk says `wuu` = `Shanghainese`), then string similarity. The last is
a guess and is never applied silently (2.19 proposed `Nanai ← Nayini`, a Tungusic and an
Iranian language; rejected). 2.19 added 33 languages and renamed none; all are configured.

## 6. Reproducing a grugrutyp number

`udcorpus.measure` computes the classic typometrics axis, *head-initiality of a
relation*, straight from the files:

```bash
python -m udcorpus.measure head-initial --rel subj --scheme SUD               # all languages
python -m udcorpus.measure head-initial --rel comp:obj --scheme SUD --language French Wolof
python -m udcorpus.measure head-initial --rel nsubj --scheme UD --budget 100000
python -m udcorpus.measure head-initial --rel any --scheme SUD                # every dependency
```

Output, one row per language: `language family treebanks n_tokens sample_pct n_scope n_hit
value ci_low ci_high`, where `value = 100 × n_hit / n_scope` and `ci_*` is the Wilson 95%
interval (`stats.wilson`). It is the grugrutyp preset *Head-initiality of a relation*
(scope `GOV -[1=subj]-> DEP`, response `GOV << DEP`) — see the docstring of `measure.py`
for the exact matching rules.

**Sampling.** grugrutyp reads big languages on a reproducible sample: a language with more
than the token budget (100,000 by default) is read on the k% of its sentences whose
`sample_bucket(sent_id) < k`, with `k = ceil(100 × budget / tokens)` (`stats.sample_pct`),
the same k for all its treebanks. `--budget 100000` does exactly that. Without `--budget`
every sentence is read, which is what grugrutyp shows for a point it *escalated* to the
full corpus because the sample was too imprecise.

**Checked against grugrutyp, 2026-11-24, release 2.19** (grugrutyp's cached counts for the
preset vs this module, `--budget 100000`):

| scheme | language | sample | n_hit / n_scope | value % | |
|---|---|---|---|---|---|
| SUD `subj` | Wolof | 100% | 410 / 4,722 | 8.6828 | identical |
| SUD `subj` | Coptic | 100% | 6,097 / 9,273 | 65.7500 | identical |
| SUD `subj` | Basque | 83% | 1,478 / 7,443 | 19.8576 | identical |
| SUD `subj` | Irish | 60% | 5,414 / 6,079 | 89.0607 | identical |
| SUD `subj` | French (7 treebanks) | 17% | 483 / 6,992 | 6.9079 | identical |
| SUD `subj` | Japanese | 7% | 2 / 4,280 | 0.0467 | identical |
| UD `nsubj` | Wolof | 100% | 9 / 4,679 | 0.1923 | identical |
| UD `nsubj` | Coptic | 100% | 913 / 9,002 | 10.1422 | identical |
| UD `nsubj` | Basque | 83% | 1,328 / 7,194 | 18.4598 | identical |
| UD `nsubj` | Irish | 60% | 4,684 / 5,367 | 87.2741 | identical |

Same counts, not just the same percentages — which also confirms the file selection, the
exclusions, the token totals behind the sample rate, and the sentence hashing.

What this module does not reproduce: grugrutyp's other measures are arbitrary Grew
queries (word order between two dependents, morphology, subtree sizes, aggregates…).
`conllu.py` gives everything needed to write them — words, heads, labels, features,
`menzerath_features` (subtree sizes, dependent counts), `tree_height`, `is_projective` —
but the query language itself is grugrutyp's.

**Releases change annotations.** Example: SUD 2.19 relabelled the complement of every
function word from `comp:obj` to plain `comp`. `--rel comp:obj` therefore counts verbal
objects only on 2.19, but verbal objects *plus* adposition complements on 2.18 (when the
governor is not restricted). Compare numbers within one release, or check the label
inventories first.

## 7. Layout

```
corpus/
  README.md            this file
  pyproject.toml       pip install -e .  (optional; or run from this folder)
  fetch_treebanks.sh   download + verify a release
  unpack.sh            unpack into <data>/treebanks/v<version>/
  meta/                the language metadata (§4), curated
  tools/xlsx2config.py one-off: the original spreadsheet -> meta/*.tsv
  udcorpus/
    config.py          data dir, meta dir, version (configure() / UDCORPUS_* / defaults)
    conllu.py          streaming reader, deprel decomposition, tree properties, sample_bucket
    treebanks.py       the release on disk, files, measure_selection()   [CLI]
    languages.py       identity, groupings, views, colours, audit()
    audit.py           the release audit                                 [CLI]
    stats.py           Wilson interval, sample rate
    measure.py         reference measure: head-initiality                [CLI]
  tests/               pytest; tiny fake release in tests/fixtures/ (no download)
```

`config` settings: `configure(data_dir=, meta_dir=, version=)` in code, or the environment
variables `UDCORPUS_DATA`, `UDCORPUS_META`, `UDCORPUS_VERSION`. The default version is the
highest `treebanks/v*` directory present.

License: AGPL-3.0, as grugrutyp. Contact: Kim Gerdes.
