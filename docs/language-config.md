# Language configuration

How typometrics decides that French is brown, that Japanese is a red cross, and that
`Xavánte` and `Xavante` are the same language. Answers Kim's note:

> *"this was used somewhere to take groups and short names etc for each language. this was
> done by a google sheet that was queried. ideally the config could be done by something
> similar on grugrutyp, modifiable by admins. the problem to address is that each version
> there are new languages appearing — and sometimes languages disappearing."*

## 1. What the spreadsheet actually holds

`docs/Typometrics configuration.xlsx` is a download of the Google Sheet. Four tabs:

| tab | rows | what it is |
|---|---|---|
| **language to group** | 186 | one row per language, with **five independent groupings** |
| **appearance** | 29 | group label → plot colour and marker |
| **my languages** | 72 | ISO code → the curated short display name |
| **all language codes** | 8 035 | the ISO 639 reference list; the tab says "normally, there's no need to edit this sheet" |

The `language to group` tab is richer than anything the site has ever shown:

| column | example (French) | example (Japanese) | what it is |
|---|---|---|---|
| `Group` | Indo-European | KJ | genetic group |
| `Genus` | Italic | Japonic | branch inside the group; `Other` means "none of the named branches" |
| `Column 1` → `subgenus` | — | — | one level finer, used only for Iranian / Armenian / Albanian / Anatolian |
| `Simple Group` | Indo-European | Other | a coarse 10-value grouping |
| `Area` | E | As | geographic: `Af As E ME I SA O Arct` |
| `Column 2` → `typology` | — | Agglutinating | a **typological** class that cuts across genetics |

The sheet's own note next to the appearance tab says what this is for:

> *"it's imaginable to add other useful 'views' = useful color configurations for
> typological observations"*

## 2. Two things were wrong with the old arrangement

**It was lossy.** Somebody exported the sheet into `languageGroups.tsv` by flattening the
five groupings into one string — `Indo-European` + `Germanic` → `Indo-European-Germanic`,
with `Genus = Other` collapsing to the bare group and `Column 2` overriding everything
(`Japanese` → `Agglutinating`). That flattening cannot be undone, so the site can offer
exactly one colouring, and the "other useful views" the sheet was designed for never
happened.

**It was stale.** The sheet has since split `Agglutinating` into `Turkic` / `Uralic` /
`Mongolic` / `Tungusic`, added `Caucasian`, `Chibchan`, `Na-Dene`, `South-American` and
`Other`, and recoloured several groups — `Niger-Congo` from black to `forestGreen`,
`Dravidian` from black to `MediumVioletRed`, `Sino-Austronesian` from `limeGreen` to
`darkSeaGreen`. None of that reached the deployed `languageGroups.tsv`, which still
carries the older state. Nobody noticed, because **a stale grouping does not raise an
error — it just draws the wrong colour.**

That is the general shape of every failure in this area, and the reason the configuration
is now a first-class object with an audit rather than three TSVs nobody looks at.

## 3. What grugrutyp does instead

`scripts/xlsx2config.py` reads the four tabs into `data/meta/`, **column by column**:

```
data/meta/languages.tsv        language, group, genus, subgenus, simple_group, area, typology, lcode
data/meta/appearance.tsv       group, color, marker
data/meta/language_names.tsv   code, name          (curated, overrides the reference)
data/meta/iso639.tsv           code, name          (reference, not edited)
```

Text, small, version-controlled: `git diff` shows exactly what a re-export changed.
`backend/grugrutyp/langconfig.py` reads them.

### Views

Because the columns survive, "colour by" is a control rather than a deployment:

| view | label for French | label for Japanese |
|---|---|---|
| `family` *(default — the granularity the current site plots at)* | Italic | Agglutinating |
| `group` | Indo-European | KJ |
| `genus` | Italic | Japonic |
| `simple_group` | Indo-European | Other |
| `area` | E | As |
| `typology` | Indo-European | Agglutinating |

### Colour resolution walks up, it does not fail down

`appearance.tsv` is keyed on group labels, and a fine view produces labels nobody has
styled — `Indo-Aryan`, `Celtic`, `Hellenic`, `Koreanic`, `Guaicuruan`. Looking those up
directly would drop them to grey, which is worse than the old behaviour. So the lookup
walks from the most specific grouping to the least:

```
typology → genus → group → simple_group → Other
```

Hindi's label is `Indo-Aryan` and its colour is Indo-European blue, because nothing styles
`Indo-Aryan` but `Indo-European` is styled. The legend stays specific; the palette stays
legible.

### Name folding

The spreadsheet spells languages the way a linguist writes them — `Apurinã`, `Mundurukú`,
`Macro-Jê`, `Gwichʼin`, `Xavánte` — while UD spells its directories in ASCII with
underscores — `Apurina`, `Munduruku`, `Gwichin`, `Xavante`. `_fold()` strips accents,
underscores and case, so all of those match. Without it, **10 languages of 2.18 silently
lose their grouping.**

## 4. The release problem, and the fix

This is the part Kim asked about. Comparing the configuration against UD/SUD 2.18 as it
stood before this work:

* **35 languages on disk with no configuration row** — they would all plot grey;
* **28 configured languages absent from the release.**

Read as two flat lists that is 63 items of manual work. But most of it is not new
languages at all — it is UD **renaming directories**:

```
Shanghainese ← Wu          Odia ← Oriya            Northern_Kurdish ← Kurmanji
Chukchi ← Chukot           Old_Occitan ← OldProvençal    Alemannic ← SwissGerman
Naga ← Tangkhul            Ika ← Arhuaco           Bokota ← Buglere        …
```

**The ISO code is the identifier UD keeps stable across a rename**, and it is free to
obtain: UD names its files `<lcode>_<corpus>-ud-<split>.conllu`. So:

1. `languages.tsv` gained an `lcode` column, and `lookup()` resolves **by code first,
   name second**. Once a row has a code, a rename is a no-op — the row keeps matching.
2. `scripts/config_audit.py --backfill-lcodes` filled it in for every configured language
   present on disk. One-time, safe, changes no grouping.
3. For the catch-up from the name-keyed past, `config_audit.py` pairs the two lists in
   three passes — exact ISO code, then the *curated name table* (`language_names.tsv`
   already says `wuu` is `Wu`, and disk says `wuu` is `Shanghainese`, so the bridge was
   sitting there unconsulted), then string similarity as a last resort.

That reduced the 35 to **10 genuinely new languages** and the 28 to **3 genuinely gone**
(`Khunsari`, `Nayini`, `Soi` — Iranian minority languages dropped after 2.12).

The renames were applied; the 10 new languages were added following the conventions
already in the file, each modelled on a sibling that was already there:

| language | group / genus | modelled on |
|---|---|---|
| Assamese, Nepali, Punjabi | Indo-European / Indo-Aryan | Hindi, Bhojpuri |
| Zazaki | Indo-European / Other / Iranian | Persian |
| MiddleArmenian | Indo-European / Other / Armenian | Armenian |
| Brahui | Dravidian | Tamil |
| Gorontalo | Sino-Austronesian | Indonesian |
| Kadiweu | Guaicuruan (South-American) | Guarani |
| OldGeorgian | Caucasian | Georgian |
| Ruuli | Niger-Congo | Yoruba |

These are uncontroversial genetic facts, but they are *additions to a curated file* —
worth a glance from Kim, which is why they are listed rather than merely committed.
The three departed languages are **kept**: a language dropped from one release often
returns, and deleting the row would throw away curation for nothing.

`config_audit.py` now exits 0 on 2.18. Run it after every `scripts/unpack.sh`; it is the
thing that turns a silent grey dot into a message.

## 5. Why not keep the Google Sheet

Kim's phrasing was "ideally the config could be done by something similar on grugrutyp,
modifiable by admins" — *similar*, on grugrutyp. Keeping the sheet itself would mean an
external dependency, an API key, and a live fetch on the plot path. Against that, the
sheet's actual virtues are a table UI, multiple editors, and revision history.

The plan is to keep the virtues without the dependency: **an admin page over the same
tables**, backed by the TSVs, with the audit as its front page — the release diff is the
thing an admin actually needs to see, and it is precisely what a spreadsheet cannot show.
Git supplies the revision history, and better: a `git diff` on `languages.tsv` names the
language and the column that changed.

`xlsx2config.py` stays, so a fresh export of the sheet can be re-imported at any time and
diffed against what is deployed. Nothing here forecloses going back.

Tasks: `todo.md` Phase 3.4.

## 6. Uploading your own treebank

`ideas.md` also asks to let a user upload their own treebank and compare it against the
rest — for a language not in UD, or a revised annotation of one that is. It lands in this
document because the blocker is configuration, not import: an uploaded treebank has no
row, so it has no group, no colour and no legend entry, and the audit is exactly the
mechanism that should catch that and ask.

Sketched in `todo.md` Phase 3.5; the import path itself is already generic
(`scripts/import_neo4j.py` takes a directory).

## Measure exclusions (audit 2026-09-02)

`data/meta/measure_exclusions.tsv` lists (corpus, language) pairs excluded from
**measure merging only** — they stay importable and individually searchable. The four
initial rows are provable double-counting: `Chinese-GSDSimp` is GSD re-scripted
(identical 4,997 sentences), and the Japanese `*LUW` treebanks are the same texts
re-tokenized under the long-unit-word standard, so every Japanese sentence was counted
twice under two segmentations. Applied in `runner.select()` for both full-scheme runs
and explicit treebank lists (language restrictions, refine) so a restricted plot
cannot disagree with the full one; `langconfig.reload()` picks up edits like any other
TSV.
