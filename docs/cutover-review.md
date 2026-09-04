# Side-by-side review before the cutover

The last gate of Phase 4: *"side-by-side review with Kim before any switch of `/`."*
This is the material for that conversation — what matches, what deliberately does not,
what the new site can do that the old one cannot, and what would have to be true before
`/` changes hands. Nothing here switches anything; the decision is Kim's.

## 1. Do the numbers agree?

`scripts/regression_2_12.py`, SUD, the three relations where the comparison is
unambiguous (a per-relation ratio cannot be affected by the root-node convention):

| relation | languages compared | median Δ | mean \|Δ\| | within 5 points |
|---|---|---|---|---|
| `subj` | 107 | **+0.00** | 1.22 | 100 / 107 |
| `comp:obj` | 114 | **+0.00** | 0.98 | 106 / 114 |
| `mod` | 114 | **+0.00** | 1.67 | 105 / 114 |

**Median Δ +0.00 over 335 language-relation pairs.** That is the number that matters:
a systematic offset would mean a convention mismatch on our side, and there is none.
The spread is six releases of annotation drift (2.12 → 2.18), which is expected and not
ours to explain.

The handful of movers are individually explicable and worth a glance rather than a
worry: Xavánte (+23, 197 matchings), Mbyá Guaraní (+16, 154), Beja (−20 — 2.18 ships a
*different* Beja treebank, Autogramm, 99.8% subject-first), Coptic and Old Church
Slavonic (−10 to −12, both heavily re-annotated since 2.12).

## 2. Is every old measure available?

| old measure | class | where it lives now |
|---|---|---|
| head-initiality (`f`), per relation and per POS-relation-POS | A | presets *Head-initiality of a relation / of all dependencies / by POS-relation-POS* |
| distribution (`f.tsv`, `cfc`, `cat`) | A | presets *Relative frequency of a relation / of a configuration / Share of a part of speech* |
| dependency distance (`f-dist`, `f-dist-abs`) | B | presets *Mean dependency distance / length* (aggregate axes) |
| sentence length, tree height | B | presets *Mean sentence length / Mean tree height* |
| projectivity | B | preset *Projective dependencies* |
| flexibility (`flexibility_rel`, `flexibility_cfc_all`) | C | `kind="flexibility"` axis + two presets; formula recovered from the 2.12 tables (exact on 43,966 cells), ρ 0.949 against the old table |
| Menzerath a/b/c | D | `data/meta/menzerath_abc.tsv` via a reference axis — **plus** the newer UDW26 measures (β, LMAL/RMAL, compliance), verified against the paper |
| Bakker comparison | D | `data/meta/bakker.tsv` via a reference axis |

Nothing from the old twelve is missing. Two are better than parity: flexibility now has
a verified definition rather than an unread script, and Menzerath now carries the
published paper's measures rather than only the legacy fit.

## 3. What the old site cannot do

Worth stating, because it is the reason for the project: any Grew query pair rather
than twelve fixed tables; search-to-trees; per-treebank drill-down and spread; honest
intervals with escalation; six colourings; share links that reproduce a figure; SVG/PNG
export; accounts, saved queries and an admin console; an LLM assistant for drafting
queries; and cross-plotting of everything above with external tables (Bakker, WALS
later).

## 4. Deliberate departures needing sign-off

These change published numbers relative to the old site, on purpose. All are documented
in `docs/data-choices.md` and visible in the *Data choices* tab:

* **duplicate treebanks dropped** from language merging — Chinese-GSDSimp, the three
  Japanese `*LUW`;
* **non-native and wrong-stage data dropped** — CHILDES (27% of English), the learner
  corpora (ESLSpok, GLCII, Valico, KSL, CFL, SweLL, Beginner), and the historical
  corpora sitting inside modern languages (French-ALTS, Italian-Old, Swedish-Old,
  French-Poitevin);
* **classification fixes** — Macedonian to Baltoslavic, Vietnamese to Austroasiatic,
  Thai to Kra-Dai, sign languages and creoles to their own groups, Iranian/Armenian/
  Albanian named as branches, code-switching corpora labelled as such;
* **the family view is genetic**; "Agglutinating" moved to the typology view, where it
  now covers all 46 agglutinative languages instead of six;
* **historical doculects are marked** (hollow markers, one-click filter).

If any of these is wrong, it is one line in a TSV and a re-plot.

## 5. Before `/` changes hands

Open, in the order they would block a cutover:

1. **Neo4j backup/restore** — deferred pending Kim's choice of destination. The state
   backups (accounts, query log, manifest) already run nightly to calcul; the 78 GB
   store does not. A cutover without it means the live site has no recovery path.
2. **A rollback plan** — trivial in principle (nginx serves the old SPA from
   `quasartypometrics/dist/spa`; the switch is a `root`/`alias` line and a reload), but
   it should be written down and rehearsed once before it is needed.
3. **The legacy URL surface** — the old site's deep links (`/?measures=…`) do not exist
   here. Either a redirect shim or an accepted break; worth a decision rather than a
   surprise.
4. **Load** is not a blocker: at ten concurrent measure streams the interactive
   endpoints stay near a second and excess is shed (`docs/performance.md`).

## 6. What I would suggest

Cut over `/` only after (1) and (2). Everything else — parity, measures, performance,
the audit's findings — is closed. A soft launch (keep `/grugrutyp/` live, point `/` at
it, keep the old site one nginx line away for a month) makes the decision reversible,
which given six releases of annotation drift is worth more than any amount of further
checking.
