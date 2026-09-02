# ideas for grugrutyp

This file is the **inbox**: only ideas that are not yet tracked elsewhere live here.
The working tracker is `todo.md` (phases, checkboxes, decisions); design rationale is in
`docs/`.

*Cleaned 2026-09-01. Everything written here before that date was either shipped (the
site itself, search-to-trees, on-the-fly measures, Menzerath, clustering, the admin
console, accounts, the per-axis LLM drafts and the side chat) or moved into `todo.md`
(uploads → 6.4, the LLM roadmap → 6.5/6.6, research goals → Phase 5, cutover → Phase 4).*

## open ideas

* **Built-in statistics on the scatter plot, no LLM, no login** (Kim, 2026-09-01).
  A button that computes and shows, in a popup: correlation (Pearson + Spearman),
  a regression line drawn on the plot, maybe cloud-shape diagnostics (empty-corner /
  triangle tests for implicational readings). With short fixed text bricks explaining
  what each number means. Deterministic and free, so available to every visitor —
  deliberately not an LLM feature.

* **Facet a measure by a clustering key — small multiples.** The search tab already
  clusters matchings by a key like `X.upos` or `e.label`. The same key on a plot axis
  would generate a whole *family* of measures in one stroke: one strip per value —
  subject direction faceted by governor POS, say. The per-(treebank, value) counts are
  exactly what cluster mode returns; what is missing is the fan-out/caching plumbing and
  a small-multiples display.

* **"make this into an MC"** — kept verbatim from the original notes because the intent
  is unclear (question pending). If "MC" meant an **MCP server**: expose `/search` and
  `/measure` as tools any LLM client (Claude, etc.) can call, so grugrutyp becomes
  usable from a chat outside the site — the mirror image of the built-in chatbot, and
  cheap to build on the existing API.
