# References

The two papers grugrutyp is built on are **not redistributed here** — they are
third-party publications with their own licences. Links and citations only.

---

## Graph databases for treebank search

> Niklas Deworetzki and Peter Ljunglöf. 2025.
> **Graph Databases for Fast Queries in UD Treebanks.**
> In *Proceedings of the 23rd International Workshop on Treebanks and Linguistic Theories
> (TLT, SyntaxFest 2025)*, pages 32–43. Association for Computational Linguistics.

* Reference implementation: <https://github.com/Niklas-Deworetzki/neo4j-ud-importer>
  (Kotlin; `neo4corpus.jar`; benchmark queries under `experiments/queries/`)

What we take from it, and where we depart: [`neo4j-encoding.md`](neo4j-encoding.md).

Headline results, for the record: Neo4j needs ~1 % of Grew-match's query time (28 s vs
0.28 s per million tokens); the property-based encoding costs ~6× the CoNLL-U size, the
node-based one ~10×; execution time is linear in corpus size for both.

**Important caveat, established by our own testing** (`neo4j-encoding.md` §1): the paper's
translation scheme is not *count-equivalent* to Grew. It drops Grew's virtual root node,
emits no injectivity guards, and omits the same-sentence join. None of that matters for a
benchmark measuring execution time — all four of their queries are fully connected
patterns — but it does matter for a tool whose output is a statistic.

---

## Grammar rule extraction (the query-pair idea)

> Santiago Herrera, Caio Corro and Sylvain Kahane. 2024.
> **Sparse Logistic Regression with High-order Features for Automatic Grammar Rule
> Extraction from Treebanks.**
> In *Proceedings of the Joint International Conference on Computational Linguistics,
> Language Resources and Evaluation (LREC-COLING 2024)*.
> arXiv:2403.17534

* Project page: <https://autogramm.github.io/grex-lrec-coling-2024/>
* Code: <https://github.com/FilippoC/grex-lrec-coling-2024>
* arXiv: <https://arxiv.org/abs/2403.17534>

How the (S, Q) measure is derived from it: [`query-pairs.md`](query-pairs.md).

The formalisation grugrutyp adopts: a rule is `S ⟹ (P --α%--> Q)` — within all
dependencies matching the *scope* S, the predictor P triggers phenomenon Q in α % of
cases. grugrutyp's typological variable is the paper's base rate
`μ = #(S∧Q)/#(S)`, computed per treebank instead of per language. Learning P is Phase 5.

---

## Tools and data

* **Grew / Grew-match** — Bruno Guillaume. 2021. *Graph matching and graph rewriting:
  GREW tools for corpus exploration, maintenance and conversion.* EACL 2021 System
  Demonstrations, pages 168–175. <https://grew.fr>
  * request syntax: <https://grew.fr/doc/request/>
  * graph model: <https://grew.fr/doc/graph/>
  * Python binding: <https://grew.fr/usage/python/>
* **SUD** — Kim Gerdes, Bruno Guillaume, Sylvain Kahane, Guy Perrier. 2018.
  *SUD or Surface-Syntactic Universal Dependencies.* <https://surfacesyntacticud.org>
* **Universal Dependencies 2.18** — <https://universaldependencies.org/download.html>
  (LINDAT handle `11234/1-6149`)
* **reactive-dep-tree** / **DependencyTreeJS** — Kirian Guiller.
  <https://github.com/kirianguiller/reactive-dep-tree>
* **Neo4j** — <https://neo4j.com>; Cypher: Francis et al. 2018, SIGMOD.

## Prior work this replaces

* **typometrics** — <https://typometrics.elizia.net>, and the measures described in its
  `Presentation.vue`. See [`current-typometrics.md`](current-typometrics.md) and
  [`measures-mapping.md`](measures-mapping.md).
