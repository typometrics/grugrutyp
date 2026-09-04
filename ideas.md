# ideas for grugrutyp

This file is the **inbox**: only ideas that are not yet tracked elsewhere live here.
The working tracker is `todo.md` (phases, checkboxes, decisions); design rationale is in
`docs/`.

*Cleaned 2026-09-01. Everything written here before that date was either shipped (the
site itself, search-to-trees, on-the-fly measures, Menzerath, clustering, the admin
console, accounts, the per-axis LLM drafts and the side chat) or moved into `todo.md`
(uploads → 6.4, the LLM roadmap → 6.5/6.6, research goals → Phase 5, cutover → Phase 4).
2026-09-02: "make this into an MC" confirmed as an MCP server → tracked as todo 6.7;
the no-LLM plot statistics shipped the same day → `docs/plot-statistics.md`.*

## open ideas

* **Facet a measure by a clustering key — small multiples.** The search tab already
  clusters matchings by a key like `X.upos` or `e.label`. The same key on a plot axis
  would generate a whole *family* of measures in one stroke: one strip per value —
  subject direction faceted by governor POS, say. The per-(treebank, value) counts are
  exactly what cluster mode returns; what is missing is the fan-out/caching plumbing and
  a small-multiples display.


