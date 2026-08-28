# Publishing to github.com/typometrics

Kim's instruction, 2026-08-28: *"once first version verified, push as public git repository
/ repositories on <https://github.com/typometrics>"*, and, when asked whether to split:
*"yes, you can split in several sub repos"*.

**Nothing has been pushed.** The only SSH key on this box is a *deploy key* for
`kimgerdes/kimsbrain`, which grants access to that one repository and cannot create or
push to anything under `typometrics/`. `gh` is not installed. This document is the
prepared plan so that publication is a short session rather than a design session.

## 1. The split

Two repositories, because exactly one piece of this is useful to someone who does not want
typometrics at all:

### `typometrics/grew2cypher`

The translator, standing alone. A Grew request in, a Cypher statement out, validated
against Grew itself.

```
grew2cypher/
  grew2cypher/            <- backend/grugrutyp/translate/, renamed
    grammar.lark  parser.py  ast.py  cypher.py
  tests/
    test_translate.py     <- 28 unit tests, no services
    test_differential.py  <- 132 tests against grewpy, needs Neo4j + the oracle
  docs/
    grew-to-cypher.md     <- the spec and every known divergence
    neo4j-encoding.md     <- the encoding it targets, and where it leaves the paper
  README.md  LICENSE  pyproject.toml
```

**Why this one is worth publishing on its own.** Anyone building on
Deworetzki & Ljunglöf's scheme will hit the same four things we did, and the paper does
not mention any of them because it benchmarks execution time rather than agreement: the
virtual root node, whole-string regex semantics, injectivity across `with`/`without`, and
anonymous edge-variable capture inside `EXISTS`. The differential suite is the artefact —
the code without it is just another translator you would have to trust.

It needs an encoding to target, so `docs/neo4j-encoding.md` and the schema go with it, and
the README has to be explicit that the translator assumes *our* encoding, not the paper's.

### `typometrics/grugrutyp`

Everything else: importer, measure layer, API, frontend, the analysis docs. Depends on
`grew2cypher`.

## 2. Splitting without losing history

`git subtree split` keeps the commits that touched those paths:

```bash
cd /home/typometrics/grugrutyp
git subtree split -P backend/grugrutyp/translate -b grew2cypher-history
# then, in a fresh clone of the new repo:
git pull /home/typometrics/grugrutyp grew2cypher-history
```

The translator's history is the interesting part — it is a log of things that turned out
not to be true — so it is worth the extra step rather than a fresh `git init`.

Note that the tests and docs live outside `backend/grugrutyp/translate/`, so their history
does not come across automatically. Either split them too and merge the branches, or
accept a single "move tests and docs" commit for those files. **Decide before splitting**;
after the fact it costs a rewrite.

## 3. Before the first push

- [ ] `gh auth login`, or an SSH key for the `typometrics` organisation
- [x] `.gitignore` excludes `.env`, `data/`, `logs/`, `.venv/`, `node_modules/`, `dist/`
- [x] no secret is tracked — `.env` is `600` and was never added
- [x] the two third-party PDFs are out of the repo *and* out of its history; they are
      cited with links in `docs/references.md`
- [x] `LICENSE`: AGPL-3.0, matching the existing typometrics code base, confirmed by Kim
- [ ] a `pyproject.toml` for `grew2cypher` (there is none yet; the backend is run from the
      source tree)
- [ ] decide what the public README says about the running instance: the URL is a live
      service on Kim's box, and publishing the code invites traffic to it
- [ ] `data/meta/*.tsv` **is** tracked and should be — it is the language configuration,
      it is small, and its history is the record of how the groupings were curated. It
      contains no third-party data beyond ISO 639 codes.

## 4. Not blocking, but worth doing first

The repository currently documents a system whose full corpus import has not finished.
A reader who clones it and follows the quick start gets the dev slice. Either finish the
import and say so, or make `--slice dev` the documented default and say that too. Right
now the README says both things in different places.
