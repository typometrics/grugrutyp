# The Grew query language — reference for grugrutyp

Transcribed from <https://grew.fr/doc/graph/> and <https://grew.fr/doc/request/>
(fetched 2026-08-28), restricted to what grugrutyp needs to support.

## 1. The graph model

A Grew graph is a set of **nodes** and **labelled directed edges**.

* A node has an identifier and a **feature structure**: a finite list of
  `(feature_name, feature_value)` pairs. For a CoNLL-U word these are `form`, `lemma`,
  `upos`, `xpos`, plus every FEATS pair (`Number=Sing`, `Gender=Masc`, …) and MISC.
* Nodes are **totally ordered** when they come from a sentence (words), which is what
  makes `<`, `<<`, `delta` and `length` meaningful. Grew also allows unordered nodes
  (constituents, AMR concepts); grugrutyp only needs ordered ones.
* An **edge label is itself a flat feature structure**, not an atom. The mapping from
  surface syntax to features depends on the configuration:

  | config | example label | internal features |
  |---|---|---|
  | `ud` | `aux:pass` | `1=aux, 2=pass` |
  | `sud` | `comp:obl@agent` | `1=comp, 2=obl, deep=agent` |
  | `basic` | `obj` | `rel=obj` |

  **This matters a lot for grugrutyp, and it matters in both schemes.** A subrelation
  label is not an opaque string: `X -[1=comp]-> Y` matches `comp`, `comp:obj`,
  `comp:obl@agent`… in SUD, and `X -[1=aux]-> Y` matches `aux`, `aux:pass`, `aux:caus`…
  in UD. The same holds for every UD subrelation — `nsubj:pass`, `obl:arg`, `acl:relcl`,
  `flat:name`, `det:poss`. Only the `@deep` third feature is SUD-specific.

  That subsumption is precisely the "simple function" vs "syntactic function" distinction
  that `datapreparation/statConll.py` implements by hand with `relationsplit` and an
  `@`-split — and it is why the importer decomposes every label into
  `deprel` / `rel_1` / `rel_2` / `rel_deep` for UD as well as SUD.

* Reserved pseudo-features on an edge variable `e`:
  * `e.label` — the whole label feature structure
  * `e.length` — number of nodes spanned between the two ordered endpoints (min 1)
  * `e.delta` — signed relative position of the endpoints

## 2. Request structure

A request is a sequence of clauses of four kinds:

```
pattern { ... }     # what must be found — binds node/edge variables
with    { ... }     # positive filter: at least one extension must satisfy it
without { ... }     # negative filter: no extension may satisfy it
global  { ... }     # whole-graph / metadata conditions
```

`pattern` may occur several times (they are conjoined). `with` and `without` may each
occur several times. Variables introduced inside `with`/`without` are local to that clause
and are not part of the result.

**Matching is injective by default**: two distinct identifiers match two distinct nodes.
Suffix an identifier with `$` to allow it to coincide with an already-matched node
(`X -[ARG1]-> B$`).

## 3. Node clauses

```
X                                   # any node
X [upos=VERB]                       # feature equality
X [Mood=Ind|Imp]                    # disjunction of values
X [Tense <> Fut]                    # inequality
X [Number]        /  X [Number=*]   # feature is defined, any value
X [!Person]                         # feature is NOT defined
X [form="être"]                     # quotes needed for non-ASCII / reserved chars
X [lemma = re"s.*"]                 # POSIX regex
X [Gloss = /.*POSS.*/i]             # PCRE regex, i = case-insensitive
X [upos=VERB, VerbForm=Part] | [upos=ADJ]   # disjunction of whole feature structures
```

Constraints inside `[...]` are conjoined.

## 4. Edge clauses

```
X -> Y                     # some edge, any label
X -[nsubj]-> Y             # exact label
X -[nsubj|obj]-> Y         # label disjunction
X -[^nsubj|obj]-> Y        # negated label set
X -[re".*subj"]-> Y        # regex over the label
e: X -[nsubj]-> Y          # bind the edge to a variable e
X -[1=comp, 2=obl|aux]-> Y # constrain individual label features
X -[1=comp, !deep]-> Y     # label feature undefined
X ->> Y                    # path of length ≥ 1 from X to Y (dominance)
* -[nsubj]-> Y             # Y has an incoming nsubj from anywhere
Y -[nsubj]-> *             # Y has an outgoing nsubj to anywhere
```

## 5. Order and distance

```
X < Y                  # X immediately precedes Y
X << Y                 # X precedes Y at any distance
length(X,Y) = 4        # 3 nodes strictly between X and Y
delta(X,Y) = 4         # signed: Y is 4 positions after X
delta(X,Y) = -4        # Y is 4 positions before X
delta(X,Y) > 0         # =, <, <=, >, >= all allowed
```

`delta(X,Y) > 0` ⇔ `X << Y`, and is exactly the predicate typometrics calls
**positive direction / head-initiality** when X is the governor.

## 6. Comparisons

```
X.lemma = Y.lemma           # same feature value on two nodes
X.Number <> Y.Number        # different
X.lemma = "avoir"
X.lemma = re".*ing"
!X.VerbForm                 # absent

e1.label = e2.label         # two edges carry the same label
e1 >< e2                    # the two edge spans cross
e1 << e2                    # e1's span is inside e2's
X << e                      # node X lies strictly inside edge e's span
```

## 7. Global clauses

```
global { is_tree }          # acyclic, single root
global { is_forest }
global { is_cyclic }
global { is_projective }
global { is_not_projective }        # any of the above can be prefixed by is_not_
pattern { meta.sent_id = "fr-1" }
pattern { meta.text = re"And.*" }
pattern { meta.speaker_id = * }
pattern { !meta.speaker_id }
```

## 8. Semantics of counting — the point that matters most

Grew-match considers **each sentence a separate graph**. A request returns a *set of
matchings*: one matching = one assignment of every `pattern` variable to a graph node.
`corpus.count(request)` counts **matchings, not sentences**; a sentence with three
subjects contributes 3.

This is exactly the denominator semantics grugrutyp needs. For a scope query S and a
subquery Q:

```
value(treebank) = 100 × count(S ∧ Q) / count(S)
```

where `S ∧ Q` means "the request S with Q's clauses appended", so that Q's constraints
are evaluated **against the variables S already bound**. Q must not re-bind a variable
name used in S with a different meaning.

Two clean ways to express Q:

* as extra clauses in a `pattern` block (adds constraints, can also add nodes — beware,
  adding a node changes the number of matchings, see §9);
* as a `with { ... }` block, which filters matchings without multiplying them.

**For grugrutyp the subquery must be applied as `with { ... }`** unless the user
explicitly wants multiplicities. Otherwise a scope of 100 subjects where 10 governors
each have 2 adverbial dependents gives 110/100 = 110 %.

## 9. Multiplicity pitfall, worked

```
S:  pattern { GOV -[subj]-> DEP }                        →  N matchings
Q as pattern: pattern { GOV -[subj]-> DEP; GOV -> ADV [upos=ADV] }
                                                          →  one matching per (subj, adverb) pair
Q as with:    pattern { GOV -[subj]-> DEP }
              with    { GOV -> ADV [upos=ADV] }           →  one matching per subj that has ≥1 adverb
```

Only the third form gives a percentage in [0, 100].

## 10. Worked examples for grugrutyp measures

```grew
% head-initiality of the subject relation (SUD)
% scope
pattern { GOV -[1=subj]-> DEP }
% subquery
with { GOV << DEP }

% is the object a pronoun, among all objects
pattern { GOV -[1=comp, 2=obj]-> DEP }
with    { DEP [upos=PRON] }

% adjective before its noun, among noun→adj modifiers
pattern { N [upos=NOUN]; N -[1=mod]-> A [upos=ADJ] }
with    { A << N }

% subject inversion in the presence of an expletive codependent (grex paper, fig. 1)
pattern { V -[1=subj]-> S }
with    { V -[deep=expl]-> E; V << S }
```

## 11. Things Grew has that a Cypher translation will not get for free

Listed here because they bound the scope of `grew-to-cypher.md`:

* `->>` transitive dominance (Cypher: variable-length `-[:DEPREL*1..]->`, fine)
* `e1 >< e2`, `e1 << e2`, `X << e` — edge-span relations, need arithmetic on the
  endpoints' positions (expressible, verbose)
* lexicons (`X.lemma = lexicon.field`) — out of scope for v1
* `global { is_projective }` — a whole-graph property; would have to be precomputed as a
  property on the Sentence node at import time
* PCRE regexes with flags — Cypher has `=~` with inline `(?i)`, mostly fine
* graph rewriting (`GRS`, `commands`) — entirely out of scope, grugrutyp only queries
