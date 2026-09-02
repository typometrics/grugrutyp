# Statistics on the scatter plot

The "statistics" button on the plot tab (2-D plots with ≥3 languages). Entirely
frontend: `src/stats.js` computes, `PlotStatistics.vue` shows, nothing leaves the
browser. Kim's requirement (ideas.md, 2026-09-01) is that this is for **every
visitor** — no account, and deliberately **no LLM**: these are the deterministic
numbers, the chat's `analyse these results` is the interpretive layer on top.

## Decisions

1. **The unit is the language, unweighted.** One observation per plotted point,
   whatever the corpus size behind it — the same principle the plot itself follows
   (a language point already sums its treebanks). Weighting by tokens would let
   German-HDT decide the correlation.

2. **Pearson and Spearman, both with two-sided p.** p comes from the t
   approximation with df = n−2 (Spearman over average ranks, so ties are handled) —
   the same default scipy uses. `scripts/stats_check.py` is the verification: it
   runs the actual `stats.js` under node against scipy on datasets with
   correlation, anticorrelation, independence, forced ties and a tiny n, and
   compares r, ρ, both p-values, slope, intercept and R². A wrong statistic does
   not look wrong — it looks like a typological finding — so rerun it after any
   change to `stats.js`.

3. **The OLS line is drawn on the plot only on request** (a checkbox in the
   dialog), refits live as points stream in, and appears in the SVG and PNG
   exports — a line visible on screen but missing from the paper figure would
   violate the exporter's own rule ("if the two disagree, the exporter is wrong").
   Solid dark red, distinguishable from the dashed diagonal.

4. **The cloud-shape diagnostic is a median-split quadrant count.** Under
   independence each corner holds about a quarter of the languages; a corner at
   ≤ max(1, 5%) with at least 12 split languages is flagged with its one-way
   implicational reading ("high X implies high Y" when high-X-low-Y is empty).
   Chosen over triangle-fitting because it is explainable in one sentence; points
   exactly on a median are excluded rather than assigned arbitrarily.

5. **The Galton caveat is part of the interface, not a footnote.** Languages are
   not independent samples — related languages inherit their patterns together —
   so the p-values shown are optimistic, and the dialog says so, pointing at the
   legend (click families to isolate them) as the practical check. Family-aware
   inference (mixed models, phylogenetic regression) is out of scope for a
   browser popup; if it ever comes, it is a backend feature.
