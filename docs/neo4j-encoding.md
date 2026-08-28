# Encoding UD/SUD treebanks in Neo4j

Summary of Deworetzki & Ljunglöf, *Graph Databases for Fast Queries in UD Treebanks*
(TLT 2025, pages 32–43 — see `references.md`), plus the encoding grugrutyp actually adopts.

## 1. What the paper shows

* UD treebanks can be stored as **labelled property graphs** in Neo4j, and Grew-match
  queries mechanically translated into Cypher.
* Two encodings are compared:
  * **property-based** — word attributes are properties on the `Word` node;
  * **node-based** — every attribute *value* becomes its own shared node
    (`(:Word)-[:UPOS]->(:Upos {value:"NOUN"})`), deduplicated across the whole database.
* Measured against Grew-match 1.16.1 on 10 treebanks:
  * Neo4j needs on average **~1 % of Grew-match's query time** (30×–600× faster).
  * Per million tokens: Grew-match **28 s**, Neo4j property-based **0.28 s**,
    node-based **0.31 s**.
  * Node-based is usually 1.5–3× faster than property-based, but *slower* for queries
    that lean on word order (NPN: 1.5–2.5× slower), because it must hop through
    attribute nodes instead of scanning.
  * One pathological case: Hindi interrogatives, ~17 s in **both** encodings — a big
    lemma disjunction plus a `without` over a subtree, which defeats the global indexes.
* Storage cost: property-based ≈ **6×** the CoNLL-U size, node-based ≈ **10×**.
  All UD treebanks ≈ 32 M tokens ≈ 2.9 GB CoNLL-U → 14 GB (property) / 22 GB (node).
* Encoding time is linear: ~1 min/M tokens (property), 2–3 min/M tokens (node).
* Execution time is linear in corpus size for both encodings.
* Their importer: <https://github.com/Niklas-Deworetzki/neo4j-ud-importer>

### Their schema

| element | encoding |
|---|---|
| word | `(:Word)` node, `form`/`lemma`/`upos`/`xpos` + each FEATS pair as properties |
| dependency | `(:Word)-[:DEPREL {deprel:"nsubj"}]->(:Word)` |
| root | the root `Word` also carries the label `:Root` |
| sentence | `(:Sentence)` node with metadata as properties, `-[:DEPREL {deprel:"root"}]->` the root word |
| word order | `(:Word)-[:SUCCESSOR]->(:Word)` between adjacent words |
| multiword token | `(:Mwt)-[:MWT]->(:Word)` for each spanned word |

### Their translation rules (§4)

| Grew | Cypher |
|---|---|
| every node identifier in `pattern` | one `MATCH (X:Word)` |
| `X -[aux]-> Y` | `MATCH (X)-[:DEPREL {deprel:"aux"}]->(Y)` |
| `X < Y` | `MATCH (X)-[:SUCCESSOR]->(Y)` |
| `X << Y` | `MATCH (X)-[:SUCCESSOR]->+(Y)` |
| `X [upos="NOUN"]` (property enc.) | `MATCH (X {upos:"NOUN"})` |
| `X [lemma="der"\|"die"]` | `WHERE X.lemma IN ["der","die"]` |
| `with { ... }` | inlined as extra `MATCH`es; its identifiers stay out of `RETURN` |
| `without { ... }` | `AND NOT EXISTS { ... }` in the `WHERE` |
| root | `MATCH (X:Root)` |
| **same-sentence constraint** | `MATCH (X)-[:DEPREL]-+(Y)` between otherwise unrelated nodes |

That last row is the subtle one: Grew-match implicitly scopes a request to a single
sentence, Neo4j does not, so unconnected pattern nodes must be tied together explicitly.

### What the reference implementation actually does

Their code and query set were read, not just the paper:
<https://github.com/Niklas-Deworetzki/neo4j-ud-importer> (Kotlin, `neo4corpus.jar`,
invoked as `java -jar neo4corpus.jar --database neo4j --host localhost --port 7687 CORPUS`).

From `src/main/kotlin/corpus/Encoding.kt`:

```kotlin
WORD_NODE_LABEL             = "Word"
POSITION_PROPERTY           = "position"      // ← they DO store a position
INVENTORY_PROPERTY          = "value"         // node-based encoding
DEPENDENCY_RELATION_TYPE    = "DEPREL"
DEPENDENCY_RELATION_PROPERTY= "deprel"
ROOT_NODE_LABEL             = "Root"
SUCCESSOR_RELATIONSHIP_TYPE = "SUCCESSOR"
REGION_LEFT_BOUND_PROPERTY  = "begin"
REGION_RIGHT_BOUND_PROPERTY = "end"
COLUMNS_ENCODING_STRING     = {FORM, LEMMA, UPOS, XPOS}
COLUMNS_ENCODING_MAP        = {FEATS, MISC}
REGION_ANNOTATIONS_STORED_AS_PROPERTY = {sent_id, id, text, text_en}
```

Regions (sentence, MWT, paragraph, document) are encoded as nodes with `begin`/`end`
bounds, and paragraph/document encoding is optional. Docker with APOC.

Their `experiments/queries/<treebank>/{grew,property,node}` holds each benchmark query in
all three forms. Reading them changed three of our decisions:

1. **They have `position` but never use it for order.** `N < P` translates to
   `MATCH (N)-[:SUCCESSOR]->(P)`, not to arithmetic on `position`. Our `idx` deviation
   (§2, dev. 2) is therefore a real departure, and it is what makes `delta`/`length` —
   which their translation does not cover at all — expressible.

2. **They drop Grew's virtual root node.** Grew's `R -[root]-> V` becomes
   `MATCH (V:Root)`. That is fine for *their* four queries, where `R` is functionally
   determined by `V`, but it is not count-equivalent in general: `pattern { X -> Y }`
   loses one matching per sentence. We keep the root node instead — see §2, dev. 4.

3. **They emit no injectivity guards and no same-sentence constraint.** Their
   `existential` query binds `E`, `X`, `Y` with no `X <> Y`, while Grew matches
   injectively by default. All four benchmark queries happen to be fully connected
   patterns, so the missing same-sentence join never bites either. Both omissions
   over-count on disconnected or repeated-node patterns.

None of this is a criticism of the paper — it measures *execution time*, and for that
purpose the translations are fine. But it does mean **the published translation scheme is
not count-equivalent to Grew**, so it cannot be adopted wholesale for a tool whose output
is a statistic. Hence the differential harness (`grew-to-cypher.md` §9).

### Their own suggested improvement (§6.2)

Adding a **direct edge from each word to its sentence node** sped up the pathological
Hindi query by up to 100×. They did not evaluate it further. grugrutyp adopts it —
see §2.

## 2. The encoding grugrutyp adopts

**Property-based, plus four deliberate deviations.** Rationale:

* property-based costs 60 % of the storage of node-based and is far simpler to
  translate to and to reason about;
* the node-based speed advantage (1.5–3×) is irrelevant next to the 100× we already win
  over Grew-match, and it *loses* on word-order queries — and grugrutyp's whole point is
  word-order typology;
* we keep the door open: the translator emits from an AST, so a node-based emitter can be
  added later behind the same interface.

### Deviation 1 — explicit `IN_SENTENCE` edge

```cypher
(:Word)-[:IN_SENTENCE]->(:Sentence)
```

Replaces the `(X)-[:DEPREL]-+(Y)` same-sentence trick with a two-hop join. This is the
optimisation the authors flagged as worth up to 100× on the queries where the paper's
scheme collapses. It also makes "count sentences" and "count matchings per sentence"
cheap, which the paper never needed but grugrutyp does (see `query-pairs.md`).

### Deviation 2 — `idx` property and no reliance on `SUCCESSOR` for `<<`

Every `Word` gets `idx` (1-based position in the sentence). Then:

| Grew | our Cypher |
|---|---|
| `X < Y` | `X.idx + 1 = Y.idx` (same sentence already enforced) |
| `X << Y` | `X.idx < Y.idx` |
| `delta(X,Y) = k` | `Y.idx - X.idx = k` |
| `length(X,Y) = k` | `abs(Y.idx - X.idx) = k` |

An integer comparison beats a variable-length path traversal by a wide margin, and it
makes `delta`/`length` — which the paper does not translate at all — trivial.
`SUCCESSOR` edges are still created (cheap, useful for tree reconstruction and for
n-gram style queries), but the translator does not use them for `<<`.

### Deviation 3 — decomposed edge labels

Grew stores a dependency label as a feature structure, and queries in **both** schemes
depend on it (`comp:obl@agent` = `1=comp, 2=obl, deep=agent`;  `aux:pass` = `1=aux,
2=pass`, see `grew-query-language.md` §1). A single `deprel` string property cannot answer
`X -[1=comp]-> Y` or `X -[1=aux]-> Y` without a `STARTS WITH` hack that breaks on `comp`
vs `compound`. So a `DEPREL` edge carries:

```
deprel : "comp:obl@agent"     -- the full surface label, for display
rel_1  : "comp"               -- feature 1
rel_2  : "obl"                -- feature 2 (absent if none)
rel_deep : "agent"            -- SUD deep feature (absent if none)
```

The decomposition is identical for UD — `aux:pass` → `rel_1=aux, rel_2=pass`, and the
same for `nsubj:pass`, `obl:arg`, `acl:relcl`, `flat:name`, `det:poss` and every other UD
subrelation. Only the `@deep` suffix is SUD-specific.

### Deviation 4 — keep Grew's virtual root node

Grew materialises a node `__0__` in every sentence and makes the root dependency a real
edge from it. Verified directly against `grewpy`:

```python
>>> Corpus("SUD_Wolof-WTB").get(sent_id).json_data()["nodes"]
{"0": {"form": "__0__"}, "1": {"form": "Jimbulang", "upos": "NOUN", ...}, ...}
```

Without it, our counts came out short by exactly one node and one edge per sentence
(`pattern { X -> Y }`: 42 151 vs Grew's 44 258 on SUD_Wolof-WTB; 44 258 − 42 151 = 2107 =
the sentence count). So we import a `Word` node with `idx = 0`, `form = "__0__"`, and a
`DEPREL {deprel:"root"}` edge from it to the sentence's root word.

It is deliberately **not** given `SUCCESSOR` edges: it is not part of the word order.
The real root word keeps the `:Root` label as well, so `X [!upos]` style filtering and
`MATCH (:Root)` both remain available.

The cost is that `pattern { X }` counts tokens *plus* sentences. That is Grew's answer,
and matching Grew is the contract — a query copied from grew-match or
universal.grew.fr must give the same number here. A measure that wants only real words
says so (`X [form <> "__0__"]`, or any `upos` constraint, which `__0__` never satisfies).

### Full schema

```
(:Treebank {name, scheme, version, language, language_code, family, n_sents, n_tokens})
(:Sentence {sent_id, text, treebank, n_tokens, is_projective})
(:Word {treebank, sent_id, idx, form, lemma, upos, xpos, <FEATS...>, <MISC...>})
(:Word:Root)                                   -- the root word of each sentence

(:Sentence)-[:IN_TREEBANK]->(:Treebank)
(:Word)-[:IN_SENTENCE]->(:Sentence)
(:Word)-[:DEPREL {deprel, rel_1, rel_2, rel_deep}]->(:Word)     -- governor -> dependent
(:Word)-[:SUCCESSOR]->(:Word)
(:Mwt {form, from, to})-[:MWT]->(:Word)
```

**Edge direction is governor → dependent**, matching Grew's `GOV -[rel]-> DEP`.

`treebank` is denormalised onto `Word` and `Sentence` because every grugrutyp query is
scoped to one treebank, and a property filter that an index can serve is much cheaper
than a join per word.

### Indexes and constraints

```cypher
CREATE CONSTRAINT sent_unique IF NOT EXISTS
  FOR (s:Sentence) REQUIRE (s.treebank, s.sent_id) IS UNIQUE;
CREATE CONSTRAINT word_unique IF NOT EXISTS
  FOR (w:Word) REQUIRE (w.treebank, w.sent_id, w.idx) IS UNIQUE;
CREATE INDEX word_tb_upos  IF NOT EXISTS FOR (w:Word) ON (w.treebank, w.upos);
CREATE INDEX word_tb_lemma IF NOT EXISTS FOR (w:Word) ON (w.treebank, w.lemma);
CREATE INDEX word_tb_form  IF NOT EXISTS FOR (w:Word) ON (w.treebank, w.form);
CREATE INDEX deprel_rel1   IF NOT EXISTS FOR ()-[r:DEPREL]-() ON (r.rel_1);
CREATE INDEX deprel_full   IF NOT EXISTS FOR ()-[r:DEPREL]-() ON (r.deprel);
```

## 3. Sizing for grugrutyp

UD 2.18 + SUD 2.18 together are roughly **2 × 32 M tokens = 64 M tokens**. At the
paper's 6× property-based overhead that is **≈ 30 GB**. `/home` has 1.1 TB free, so this
fits, but it is not free — see `plan.md` for the staged-import strategy (start with ~20
treebanks, then all).

Estimated import time at 1 min/M tokens: **~1 h for both schemes**, parallelisable.

## 4. Open questions the paper leaves

* No evaluation of `with`-heavy queries, which is grugrutyp's dominant shape.
* No treatment of `delta`/`length`/edge-span operators — we design those ourselves (§2).
* Enhanced dependencies (`DEPS`) are ignored. grugrutyp ignores them too for v1.
* Nothing about running *many small* queries over *many* corpora, which is our access
  pattern (250 treebanks × 2 counts per plot). The right lever there is one Cypher
  statement per treebank with `UNION ALL`, or a single statement parameterised over the
  treebank list — to be benchmarked, see `todo.md`.
