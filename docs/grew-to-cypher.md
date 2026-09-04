# Grew → Cypher translation spec

The design contract for `backend/grugrutyp/translate/`. Extends
Deworetzki & Ljunglöf §4 (see `neo4j-encoding.md`) to the constructs grugrutyp needs.
Target schema is the one in `neo4j-encoding.md` §2.

## 0. Pipeline

```
grew request text
  → lexer/parser (lark)        → AST
  → validator                  → binding table, well-formedness errors
  → emitter                    → Cypher + parameter dict
```

The AST is the interchange point: a second emitter (node-based encoding, or a grewpy
fallback) can be added without touching the parser. Every literal goes into the
**parameter dict**, never into the query string — both to let Neo4j cache query plans
across treebanks and to make injection structurally impossible.

## 1. Node clauses

Every identifier in a `pattern` block becomes one `MATCH` plus a treebank filter:

```cypher
MATCH (X:Word {treebank:$tb})
```

| Grew | Cypher |
|---|---|
| `X [upos=VERB]` | `MATCH (X:Word {treebank:$tb, upos:$p0})` |
| `X [Mood=Ind\|Imp]` | `WHERE X.Mood IN $p0` |
| `X [Tense <> Fut]` | `WHERE X.Tense <> $p0` — see §7 on absent features |
| `X [Number]`, `X [Number=*]` | `WHERE X.Number IS NOT NULL` |
| `X [!Person]` | `WHERE X.Person IS NULL` |
| `X [lemma=re"s.*"]` | `WHERE X.lemma =~ $p0` |
| `X [Gloss=/.*POSS.*/i]` | `WHERE X.Gloss =~ '(?i)' + $p0` |
| `X [upos=VERB,VerbForm=Part] \| [upos=ADJ]` | `WHERE (X.upos=$p0 AND X.VerbForm=$p1) OR (X.upos=$p2)` |
| root node | `MATCH (X:Word:Root {treebank:$tb})` |

Regex dialect: Grew's `re"…"` is POSIX, `/…/` is PCRE, Cypher's `=~` is Java/ICU.
**Anchoring is the same in both** — Grew's regexes are whole-string matches, exactly like
Cypher's `=~` — so the pattern passes through unchanged. This was measured, not assumed;
see §7 row 2. The only adjustment is PCRE's `i` flag, which becomes an inline `(?i)`.

## 2. Edge clauses

```
X -[nsubj]-> Y      →  MATCH (X)-[:DEPREL {deprel:$p0}]->(Y)
X -> Y              →  MATCH (X)-[:DEPREL]->(Y)
X -[nsubj|obj]-> Y  →  MATCH (X)-[e:DEPREL]->(Y) WHERE e.deprel IN $p0
X -[^nsubj|obj]-> Y →  MATCH (X)-[e:DEPREL]->(Y) WHERE NOT e.deprel IN $p0
X -[re".*subj"]-> Y →  MATCH (X)-[e:DEPREL]->(Y) WHERE e.deprel =~ $p0
X -[1=comp,2=obl]-> Y → MATCH (X)-[:DEPREL {rel_1:$p0, rel_2:$p1}]->(Y)
X -[1=comp,!deep]-> Y → MATCH (X)-[e:DEPREL {rel_1:$p0}]->(Y) WHERE e.rel_deep IS NULL
e: X -[nsubj]-> Y   →  MATCH (X)-[e:DEPREL {deprel:$p0}]->(Y)      -- e usable later
X ->> Y             →  MATCH (X)-[:DEPREL*1..]->(Y)
* -[nsubj]-> Y      →  MATCH ()-[:DEPREL {deprel:$p0}]->(Y)
Y -[nsubj]-> *      →  MATCH (Y)-[:DEPREL {deprel:$p0}]->()
```

A bare label like `nsubj` is matched against `deprel` (full surface label), **not**
`rel_1`. `-[1=comp]->` is the way to ask for the simple function. This mirrors Grew,
where `-[comp]->` in the `sud` config means exactly `1=comp` with no `2`; so:

> **Divergence, decided:** Grew's `-[comp]->` under the `sud` config matches only
> `comp` with no subrelation. Our `deprel:"comp"` does the same. `-[comp:obj]->` →
> `deprel:"comp:obj"`. Consistent.

## 3. Order and distance — the `idx` shortcut

```
X < Y             →  WHERE X.idx + 1 = Y.idx
X << Y            →  WHERE X.idx < Y.idx
delta(X,Y) = k    →  WHERE Y.idx - X.idx = $k          (=,<,<=,>,>= all pass through)
length(X,Y) = k   →  WHERE abs(Y.idx - X.idx) = $k
```

Cheaper and more expressive than the paper's `-[:SUCCESSOR]->+` (§2 of
`neo4j-encoding.md`). Valid only because the same-sentence constraint (§4) always holds.

## 4. The same-sentence constraint

Grew scopes a request to one graph = one sentence. Neo4j does not. Rule:

> For every request, pick the first-declared node variable as the **anchor** `A`. Emit
> `MATCH (A)-[:IN_SENTENCE]->(_s:Sentence)` once, and for every other top-level node
> variable `V` emit `MATCH (V)-[:IN_SENTENCE]->(_s)` with **the same** `_s`.

Nodes already tied to `A` by an edge clause are in the same sentence transitively, but
emitting the `IN_SENTENCE` hop for all of them anyway is what makes the index work — this
is the paper's own §6.2 optimisation. Cost is one extra relationship traversal per node.

Inside a `without` block, the local variables join `_s` too.

## 5. `with` and `without`

```
with { C }     →  AND EXISTS     { <clauses of C> }
without { C }  →  AND NOT EXISTS { <clauses of C> }
```

`with` needs care: Grew's `with` is a **filter** — it must not multiply matchings
(`query-pairs.md` §3). Inlining its `MATCH`es *does* multiply them. Therefore:

> **`with { C }` is emitted as `AND EXISTS { <C> }`, not as inline MATCHes.**

This diverges from the paper (which inlines `with` and merely omits its identifiers from
`RETURN` — correct for *finding* results, wrong for *counting* them). Since grugrutyp's
primary operation is `count`, `EXISTS` is the correct emission. A node introduced inside
`with` is then invisible outside it, which matches Grew's scoping.

**Optimisation, and a trap.** A block that introduces no new node and no edge clause is a
pure boolean filter, so it collapses to a plain conjunct instead of an `EXISTS` — much
cheaper, and the common case (`with { GOV << DEP }`). For `without`, that plain form must
be wrapped in `coalesce(…, false)`: in Grew a constraint over an undefined feature simply
does not hold, so the matching survives, whereas Cypher's `NOT null` is null and would
drop it.

**Anonymous edge variables must be unique across the whole translation**, not per block.
Reusing `_e1` inside an `EXISTS` subquery makes Cypher bind the same relationship as the
outer `MATCH`; the subquery then cannot match anything and the count silently becomes 0.
See §7 row 13.

## 6. Counting and returning

```cypher
-- count mode (query pairs)
MATCH ... WHERE ... RETURN count(*) AS n

-- aggregate mode (distance measures, measures-mapping.md §3)
MATCH ... WHERE ... RETURN avg(DEP.idx - GOV.idx) AS value, count(*) AS n

-- search mode (tree viewer, grex feature extraction)
MATCH ... WHERE ...
RETURN _s.sent_id AS sent_id, [X.idx, Y.idx] AS nodes
ORDER BY sent_id SKIP $skip LIMIT $limit
```

Search mode returns only sentence ids + matched positions; the CoNLL-U of those sentences
is fetched separately (§8) so the payload stays small and the tree renderer gets the
original text, not a graph reassembled from the database.

Injectivity: Grew is injective by default, Cypher relationship-uniqueness is not
node-uniqueness. Emit a guard for every pair of distinct node variables — including pairs
that straddle a `with`/`without` boundary. Since all matched nodes share a sentence and
`idx` is unique within it, the guard is `X.idx <> Y.idx`, which is cheaper than comparing
node identity and means the same thing. Identifiers written `Y$` are excluded.

## 7. Known divergences, ranked by risk

| # | issue | status | resolution |
|---|---|---|---|
| 1 | `X [Tense <> Fut]`: Grew requires the feature to be **defined** and different; `NOT X.Tense = $v` would also admit undefined | **closed** | emit `X.Tense IS NOT NULL AND NOT (X.Tense = $v)`; differential test `node-neq` |
| 2 | regex anchoring | **closed** | measured: Grew's `re"…"` is a *whole-string* match, identical to Cypher `=~`, so the pattern passes through unchanged. On SUD_Wolof-WTB `[lemma=re"a"]` == `[lemma="a"]` == 1116 and `[upos=re"OU"]` == 0. An earlier `.*`-wrapping version silently turned every regex into a substring search |
| 3 | Grew's virtual root node `__0__` | **closed** | materialised at import; see `neo4j-encoding.md` §2 dev. 4. Was worth exactly one node + one edge per sentence |
| 4 | injectivity across `with`/`without` | **closed** | Grew's injectivity spans the whole request; guards are emitted between subquery nodes and pattern nodes, not just within the pattern. Differential tests `with-new-node`, `without-new-node` |
| 5 | `global { is_projective }`, `is_tree` | **closed** | precomputed `Sentence.is_projective` / `is_tree` at import |
| 6 | `global { is_forest }`, `is_cyclic` | open | rejected at translation with a pointing error rather than silently mistranslated |
| 7 | `e1 >< e2`, `e1 << e2`, `X << e` (edge-span relations) | open | expressible as arithmetic on the four endpoint `idx` values; deferred to v1.5 |
| 8 | lexicons (`X.lemma = lexicon.f`) | open | out of scope; rejected at validation with a clear message |
| 9 | `X$` non-injective matching | **closed** | supported: `$`-suffixed ids are excluded from the `<>` guards. Differential test `non-injective` |
| 10 | multiword tokens in `<`/`<<` | **closed** | `idx` is over syntactic words; MWTs are separate `:Mwt` nodes, same as Grew |
| 11 | enhanced dependencies (DEPS) | open | not imported in v1; queries needing them are rejected |
| 12 | `meta.<key>` beyond `sent_id` / `text` | open | only those two are stored as properties; anything else is rejected rather than silently ignored |
| 13 | anonymous edge-variable collision between scopes | **closed** | `_e1` must be unique across the *whole* translation, not per block. Reusing it inside an `EXISTS` subquery makes Cypher bind the same relationship as the outer `MATCH`, so the subquery can never match and the count silently becomes 0. Caught by `with-new-node` / `without-new-node` |

### Deliberate supersets of Grew

Two constructs our grammar accepts that grewlib rejects. Both are pure sugar with an
unambiguous desugaring, and the differential tests run the desugared form through Grew so
the counts are still checked:

| ours | Grew equivalent |
|---|---|
| `X -[r]-> Y [upos=NOUN]` (inline feature structure on an endpoint) | `Y [upos=NOUN]; X -[r]-> Y` |
| `* -[subj]-> Y`, `Y -[subj]-> *` (unbound endpoint) | `Z -[subj]-> Y`, `Y -[subj]-> Z` |

Also: `pattern { X }` — a lone unconstrained node — is rejected by grewlib but accepted
here. It has no oracle, so it is covered by unit tests only.

## 8. Sentence retrieval

```cypher
MATCH (s:Sentence {treebank:$tb, sent_id:$sid})
RETURN s.conllu
```

Store the **raw CoNLL-U block** of each sentence as a property on the `Sentence` node at
import time. It costs ~1× the corpus size on top of the ~6× encoding overhead and removes
any need to reassemble a sentence from `Word` nodes for display. The tree viewer then
feeds that text straight to `reactive-dep-tree`.

## 9. Differential testing against Grew — non-negotiable

`grew` 1.21.0 and `grewpy_backend` 0.6.2 are installed on this machine under
`/opt/opam/grew` (see `setup.md`). They are **not** the production query engine, but they
are the oracle:

```
for each (treebank, request) in the test matrix:
    assert grewpy_count(tb, req) == neo4j_count(tb, req)
```

The test matrix must include, per construct in this document, at least one request, on at
least three typologically different treebanks (say `SUD_English-GUM`, `SUD_Japanese-GSD`,
`SUD_Wolof-WTB`). Any mismatch is a translator bug until proven a Grew bug.

This is the single most important piece of the project: without it, "we support Grew
queries" is an unverifiable claim, and every typological result computed downstream is
suspect. Build it before building the plotting UI.

## Addendum, 2026-09-02 (audit): two divergences section 7 missed

* **Regex dialect, not just anchoring.** Row 2 closes the whole-string-match question,
  but `re"…"` is POSIX ERE in Grew and Java regex in Cypher `=~`: a POSIX class like
  `[[:upper:]]` matches uppercase letters in Grew and a literal character class here.
  Plain patterns (`^a.*`, alternation, quantifiers) agree; POSIX classes and
  collation-dependent constructs silently do not.
* **`textform`/`wordform` are not imported.** Row 10 oversold the MWT story: Grew does
  not build MWT nodes — it exposes `textform`/`wordform` features on words, which our
  importer does not carry. A grew-match query using them returns silent zeros here
  (the LLM path's feature gate catches them; hand-typed queries see the zero preview).
* **The enhanced graph is not imported at all** (found by the UD differential leg,
  2026-09-02). grew's `ud` config loads the DEPS column as additional edges and empty
  nodes as real nodes; our importer reads the basic tree only. Measured on
  UD_English-GUM: `pattern { X -[1=aux]-> Y }` counts 16,859 in grew-match and 8,257
  here — the enhanced graph nearly doubles every relation it copies. A count compared
  against grew-match on an enhanced treebank WILL differ; the oracle suite loads a
  DEPS-stripped copy so it verifies the semantics we declare. See also
  docs/data-choices.md.

## Addendum, 2026-09-04: rejections, and two silent zeros closed

`check_bindings()` runs inside `translate()`, so every path (search, measure, preview,
`/validate`) gets it. It rejects what Grew itself rejects, verified against grewlib:

| construct | grewlib | us, before | us, now |
|---|---|---|---|
| `S.Number = v.Number` (undeclared `v`) | "Identifier 'v' not found" | joined a fresh unconstrained word — an inflated agreement rate that looked like a finding | rejected, naming what the request does declare |
| `X << Z` (undeclared `Z`) | rejected | same silent join | rejected |
| `X.lemma = lexicon.verbs` | rejected | same silent join | rejected, pointing at the alternation form (§7 row 8's promise, finally kept) |
| `e.length = 3` (edge var) | **accepted**, ≡ `length(X,Y)` | re-bound `e` as a Word: run-time type error or a wrong count | rejected, naming the equivalent `length(GOV, DEP)` form |
| `-[1=*]->` | **accepted**, ≡ "feature 1 present" | emitted `rel_1 = '*'` → **0 everywhere** | present-check; matches grew exactly (44,258 on Wolof-WTB) |

The last two are divergences we now fail loudly on rather than mis-answer. Implementing
`e.length`/`e.delta` as sugar for the endpoint form is the remaining small win.
