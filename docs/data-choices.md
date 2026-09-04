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

### Not native adult production (2026-09-04 survey)

A language point should describe that language as its native adult speakers write and
speak it. These treebanks are excellent data for other questions:

| excluded | why |
|---|---|
| English-CHILDES | transcripts of child–adult interaction **including child utterances** — and 27% of all English tokens |
| English-ESLSpok | spoken L2 English (NICT JLE) |
| Greek-GLCII | Greek Learner Corpus II — L2 written production |
| Italian-Valico | Italian as a second language (Valico) |
| Korean-KSL | L2 Korean — 25% of the Korean tokens |
| Chinese-CFL | essays by learners of Mandarin as a foreign language |
| Chinese-Beginner | graded A1/A2 pedagogical example sentences — constructed teaching material |
| Swedish-SweLL | learner Swedish |

### A different historical stage inside a modern language

| excluded | why |
|---|---|
| French-ALTS | sixteenth-century legal French from Normandy and the Channel Islands |
| Italian-Old | Dante's *Comedy* (c. 1306–1321), Old Florentine — 12% of "Italian" |
| Swedish-Old | Old Swedish |

Each deserves its own language point, exactly as Old French and Middle French have one;
until then they are out of the modern language's number rather than silently inside it.

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
  Church Slavonic…) and are now **marked**: a `historical` column in `languages.tsv`
  flags 27 non-contemporary doculects, they plot as **hollow markers**, the tooltip
  says "historical stage — not a living variety", and a *Contemporary only* toggle
  hides them in one click. The toggle feeds the statistics popup too, since a lineage
  (Latin → Old French → Middle French → French) otherwise enters a correlation as
  four independent observations.
- **"Agglutinating" is a view, not the default label.** The tag covers all 46
  canonically agglutinative languages (Turkic, Uralic, Japonic, Koreanic, Mongolic,
  Tungusic, Dravidian, Kartvelian, Basque, Chukotko-Kamchatkan, Eskimo-Aleut,
  agglutinating Bantu and Austronesian) — extended from the inherited six on
  2026-09-04. It is read by the **typology** view; the default family view stays
  genetic, so Uralic, Turkic and Dravidian keep their own legend entries. Colouring a
  plot by morphological type is one dropdown away.
- **Narrow-genre treebanks are kept, not excluded** — French-FQB (questions only,
  71% subject inversion against 4% for the rest of French), English- and Turkish-Atis
  (flight-booking commands), Old_East_Slavic-Birchbark (letters),
  Portuguese-PetroGold (petroleum documents), Ancient_Greek-PTNK (a translation from
  Hebrew). These *are* the language, sampled from one narrow genre; the treebank
  spread in the tooltip and the point dialog is where that shows.
- **Dialect atlases are kept**: all four Hausa treebanks are dialects (Northern,
  Southern, Eastern, Western), and Greek carries Cretan, Lesbian and Messinian
  alongside the standard corpora. Excluding one would be arbitrary — the spread
  reports the variation instead.
- **Some languages are mostly one stage or one genre.** "Sanskrit" is 99% Vedic
  (206k tokens against 1.8k of classical UFAL); "Romanian" is 61% the *Nonstandard*
  corpus (Old Romanian, chat and folklore deliberately collected as non-standard);
  "Tagalog" is 1,831 tokens in total, half of them constructed grammar-book examples,
  which is worth remembering whenever Tagalog appears as a striking outlier.
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

## The basic tree only (2026-09-02)

UD releases carry a second annotation layer — the *enhanced* graph (extra edges for
control, coordination distribution, relative pronouns, plus "empty" nodes for elided
material). **We import and count the basic tree only.** On an enhanced treebank the
same query in grew-match can return nearly double our count (measured: `1=aux` on
English-GUM, 16,859 enhanced vs 8,257 basic). Neither number is wrong; they count
different graphs — ours is the one the typometrics tradition and the SUD scheme are
defined over.
