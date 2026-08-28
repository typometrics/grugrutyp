# Query pairs: turning two Grew requests into one typological measure

Background: Herrera, Corro & Kahane, *Sparse Logistic Regression with High-order Features
for Automatic Grammar Rule Extraction from Treebanks* (LREC-COLING 2024, PDF in this
folder). Project page <https://autogramm.github.io/grex-lrec-coling-2024/>,
code <https://github.com/FilippoC/grex-lrec-coling-2024>.

## 1. What the grex paper does

The paper formalises a **syntactic grammar rule** as

> **S ⟹ (P --α%--> Q)**
>
> "Within all dependencies that match the pattern **S** (the *scope*), the predictor **P**
> triggers the linguistic phenomenon **Q** in **α %** of cases."

Three separate patterns:

| symbol | name | who writes it | example |
|---|---|---|---|
| **S** | scope | the linguist | all `subj` relations |
| **Q** | phenomenon / response | the linguist | the subject follows its governor |
| **P** | predictor | **the machine** | the governor has an expletive codependent |

S and Q are hand-written because they encode the linguistic question. P is *learned*: the
search space is every attribute of the governor, dependent, grandparent, siblings and
grandchildren (their Figure 2), plus relative-position attributes, and a sparse L1
logistic regression is trained to predict Q inside S. Features are ranked by the
**regularisation path** — the order in which each feature's weight becomes non-zero as λ
decreases. Earlier entry = more salient.

Statistics attached to each candidate rule:

```
μ = #(S ∧ Q) / #(S)                     base rate of Q in the scope
α = #(S ∧ P ∧ Q) / #(S ∧ P)             rate of Q once P holds
G = 2n (α ln(α/μ) + (1-α) ln((1-α)/(1-μ)))     G-test, significant if p < 0.01
coverage  = #(S ∧ P ∧ Q) / #(S ∧ Q)
precision = #(S ∧ P ∧ Q) / #(S ∧ P)     ( = α )
```

Other practical decisions worth copying: `form` is never used as a feature; `lemma` only
for closed-class POS (AUX, ADP); features must occur ≥ 5 times in the scope; when studying
number agreement the `Number` attribute is removed to prevent information leaks.

### The names, exactly as the paper uses them

Worth fixing the vocabulary, because grugrutyp's UI should use the same words as the
paper it implements:

| symbol | the paper's term | quoted from §3.2 / Def. 1 |
|---|---|---|
| **S** | the **scope** | "The scope S of the rule is a given pattern and we consider all dependencies satisfying S." |
| **Q** | the **response pattern** (the *linguistic phenomenon of interest*) | "we seek to identify what triggers satisfaction of response pattern Q amongst all relations that satisfy S." |
| **P** | the **predictor** (the *trigger*) | "the pattern P that acts as a trigger of Q in the scope S." |
| **α** | the rule's **frequency** | `S ⟹ (P --α%--> Q)` |
| **μ** | the **base rate** of Q in the scope | `μ = #(S∧Q)/#(S)` |

The whole object `S ⟹ (P --α%--> Q)` is a **syntactic grammar rule** (Definition 1). The
notation is borrowed from Mel'čuk's correspondence rules in Meaning-Text Theory, where it
would be written `S ⟹ Q | P`, read "S can correspond to Q in the context P".

The division of labour is the paper's own, and it is exactly grugrutyp's:

> "In practice, patterns **S and Q are manually defined**, as they define the linguistic
> phenomena of interest in a given scope. […] However, potential patterns **P are the ones
> that the machine learning model must fill**."

So **grugrutyp v1 is the hand-written half**: the linguist writes S and Q, and we plot μ
across treebanks. Learning P is Phase 5. In the UI the two editors are therefore labelled
**Scope (S)** and **Response (Q)** — not "query" and "subquery", which say nothing.

## 2. What grugrutyp takes from it

grugrutyp's core object is the **(S, Q) pair without P**:

```
value(treebank) = 100 × #(S ∧ Q) / #(S)          -- this is μ, per treebank
```

That is, the paper's *base rate* μ becomes grugrutyp's *typological variable*. The paper
computes μ for one language in order to test whether a learned P shifts it; grugrutyp
computes μ across ~250 treebanks and plots it.

This is the right generalisation of what typometrics already does. Every current
"direction" measure is a hard-coded (S, Q) pair:

```
head-initiality of subj  ≡  S: pattern { GOV -[1=subj]-> DEP }
                            Q: with    { GOV << DEP }
```

Two such pairs give the x and y of a scatter plot — the 2-D case in `ideas.md`.

## 3. Precise semantics

Let `count(R)` be the number of **matchings** of request `R` over a treebank
(Grew semantics: per sentence, per variable assignment — see `grew-query-language.md` §8).

```
n_scope = count(S)
n_hit   = count(S ⊕ Q)
value   = 100 * n_hit / n_scope        (undefined if n_scope == 0)
```

`S ⊕ Q` means: the clauses of Q are appended to S, **as `with { … }` blocks**, so that

* Q's constraints are evaluated against the variables S bound;
* Q cannot multiply the matching count, so `0 ≤ n_hit ≤ n_scope` is guaranteed.

### Well-formedness rules the UI must enforce

1. Every node/edge identifier free in Q must be bound in S. Otherwise Q silently
   introduces a new node and the ratio loses meaning. → validate before running.
2. Q may not contain a bare `pattern` block. The UI offers `with` and `without`.
   (`without` is legitimate: "subjects that do *not* have an expletive codependent".)
3. `n_scope` below a threshold (default 30, user-adjustable) ⇒ the treebank is dropped
   from the plot, the same role `axminocc` plays today.

### Confidence

Unlike the current precomputed tables, we know `n_scope` exactly, so we can show a
binomial confidence interval per point (Wilson score, α = 0.05) for free. A point from
40 subjects and a point from 400 000 subjects should not look identical. Today's site
cannot do this.

## 4. Worked pairs, reproducing existing typometrics measures

```grew
%%% head-initiality of a relation r  (≡ positive-direction.tsv / head_initiality_comb.tsv)
S: pattern { GOV -[1=subj]-> DEP }
Q: with    { GOV << DEP }

%%% head-initiality by governor-POS × relation × dependent-POS  (≡ posdircfc.tsv)
S: pattern { GOV [upos=NOUN]; GOV -[1=mod]-> DEP [upos=ADJ] }
Q: with    { GOV << DEP }

%%% relative frequency of relation r among all relations  (≡ f.tsv / distribution)
S: pattern { GOV -> DEP }
Q: with    { GOV -[1=subj]-> DEP }

%%% share of a POS among all words  (≡ cat.tsv)
S: pattern { X }
Q: with    { X [upos=ADP] }

%%% projectivity rate — needs a sentence-level scope, see §6
```

## 5. Beyond μ: keeping the P machinery in view

`ideas.md` asks, long term, for "lists of phenomena that are strange about a specific
language". That is exactly grex's P, run per treebank:

* fix (S, Q) — e.g. subject position;
* fit the sparse logistic regression per treebank over the grandparent/siblings/
  grandchildren feature space;
* the ranked P list is the language's description of *when* the phenomenon happens;
* a phenomenon is "strange" for language L when L's α-profile is far from its
  neighbours'.

This is phase 4 in `plan.md`, not v1. But it constrains the design now: the backend must
be able to return, for a given (S, Q) and treebank, **the raw matchings with their
feature context**, not only the two counts. So the query API needs a `search` mode
returning matchings, not just a `count` mode. That is the same endpoint the tree viewer
needs, which is why the intermediate step in `ideas.md` is a good first target.

## 6. Known semantic gap: matching-level vs sentence-level measures

`#(S∧Q)/#(S)` is a ratio of *matchings*. Some typometrics measures are not of that shape:

| measure | shape | handled how |
|---|---|---|
| head-initiality, direction, POS share, relation share | ratio of matchings | native (S, Q) |
| mean dependency distance (`f-dist.tsv`) | **mean of a numeric value** over matchings | needs an *aggregate* mode: `avg(delta(GOV,DEP))` |
| tree height (`height.tsv`) | mean over **sentences** of a per-sentence value | needs a sentence-level scope + aggregate |
| Menzerath–Altmann | regression over sentence lengths | not a query pair at all |
| flexibility | entropy over a distribution | derived from a set of (S,Q) values |

So the backend needs **three** measure kinds, not one:

1. `ratio` — `#(S∧Q)/#(S)` (the query pair; v1)
2. `aggregate` — `avg|median|stddev` of a numeric expression over the matchings of S
   (`delta(GOV,DEP)`, `abs(delta(...))`, `length(...)`); this covers all the distance
   measures and is a small extension of the same machinery (v1.5)
3. `derived` — computed in Python from a family of (1)/(2) results (flexibility, entropy,
   Menzerath); v2+

See `measures-mapping.md` for which existing measure falls where.
