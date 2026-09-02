# Where our analysis departs from the raw data

The canonical text behind the **Data choices** tab of the site's about dialog — the
two must change together. Raw UD/SUD releases are not analysis-ready: some treebanks
duplicate each other, some "languages" are not one language, and some classifications
in our own configuration were wrong or misleading. Every departure we make is listed
here; anything not listed is served as the release ships it.

## Deduplicated treebanks

Excluded from a language's merged point (still importable and individually
searchable) — `data/meta/measure_exclusions.tsv`:

| excluded | why |
|---|---|
| Chinese-GSDSimp | the same 4,997 sentences as Chinese-GSD, re-scripted (traditional → simplified); keeping both counted one corpus twice — 80% of "Chinese" |
| Japanese-BCCWJLUW, -GSDLUW, -PUDLUW | the same texts as BCCWJ/GSD/PUD re-tokenized under the long-unit-word standard; keeping both counted every Japanese sentence twice under two segmentations |
| French-PoitevinDIVITAL | Poitevin is a distinct Oïl variety, not modern French; inside the merged French point it silently shifted the value. Pending its own language point |

## Corrected classifications (they were factually wrong)

- **Macedonian** was filed as Hellenic; it is South Slavic → Baltoslavic.
- **Madi and Paumarí** are Arawan, not Tupian/Arawakan.
- **Xavánte and Borôro** are Macro-Jê, not Tupian.
- **Vietnamese** is Austroasiatic and **Thai** is Kra-Dai; neither belongs under
  Sino-Austronesian on any hypothesis.
- **Spanish and Swedish Sign Language** were filed as Romance and Germanic; sign
  languages are not genetically related to the surrounding spoken language → a `Sign`
  group of their own.
- **Haitian Creole and Naija** were filed under their lexifiers' branches (Italic,
  Germanic); creoles get a `Creole` group. Naija's area also moved from Europe to
  Africa.
- **Persian, Pashto, Zazaki, the three Kurdish varieties, Nayini and Soi** carried
  genus "Other" and appeared in the legend as bare "Indo-European"; they are the
  **Iranian** branch, now named like Indo-Aryan is. **Armenian** (×4 stages) and
  **Albanian** (+Gheg) likewise became their own named branches — each *is* a primary
  IE branch.
- **Telugu-English, Turkish-English, Turkish-German and Maghrebi-Arabic-French** are
  code-switching corpora that were filed under one parent's family; they now carry an
  honest `Code-switching` label. They remain plotted — a mixed-code corpus answers
  some questions and poisons others, and the label lets you decide which.

## Deliberate oddities we keep (know what you are reading)

- **A "language" point merges all its treebanks by summing counts.** Registers,
  genres and centuries are merged together: "Latin" spans classical to medieval,
  "English" includes learner speech and child-directed speech. Click a dot to see the
  per-treebank values — when they disagree by more than the error bar, the merged
  number describes the corpus mix, not the language.
- **Historical stages are separate points** (Old French, Ancient Greek, Latin, Old
  Church Slavonic…) and are *not yet* visually flagged as historical. Around 24 of
  ~190 languages are non-contemporary; keep it in mind when reading correlations.
- **"Agglutinating"** appears in the family view next to genetic families. This is a
  deliberate typological override for Japanese, Korean, Buryat, Chukchi, Xibe and
  Yupik (and only those), inherited from the original typometrics.
- **"Sino-Austronesian"** groups Sinitic with Austronesian after Sagart's hypothesis
  — a curation choice of the original site, kept; the languages that never belonged
  under it (Vietnamese, Thai) have been moved out.
- **All Indo-European branches plot royalBlue** by design, so IE reads as one block
  against the rest of the world; use the legend to isolate a single branch, or the
  genus view for branch-level colours.
- **Esperanto, Hittite, Phrygian** stay as plain "Indo-European" (constructed /
  fragmentary-Anatolian / fragmentary), pending a better idea.

## What this does NOT change

Counts, queries and the per-treebank numbers are untouched by everything above —
the departures only decide *which treebanks enter a language's point* and *what the
legend calls things*. The measure semantics themselves (virtual root, `1=`
subsumption, sampling, escalation) are documented in the technical tab and in
`docs/measures-mapping.md` / `docs/sampling.md`.
