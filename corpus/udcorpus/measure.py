"""A reference measure in plain Python: head-initiality of a relation, per language.

This is the classic typometrics axis -- of all dependencies bearing relation R, the share
where the governor comes first -- computed straight from the CoNLL-U files, with no
database. It exists so that a grugrutyp number can be reproduced independently: the
grugrutyp preset "Head-initiality of a relation" asks Grew

    scope     pattern { GOV -[1=subj]-> DEP }      (SUD; UD: -[1=nsubj]->)
    response  with { GOV << DEP }

and plots 100 * #(scope and response) / #(scope), with every treebank of a language
summed (`treebanks.measure_selection`). This module counts the same thing.

    python -m udcorpus.measure head-initial --rel subj --scheme SUD
    python -m udcorpus.measure head-initial --rel comp:obj --scheme SUD --language French Wolof
    python -m udcorpus.measure head-initial --rel any --scheme UD --budget 100000

What "the same thing" means, precisely:

* `--rel subj` matches every label whose first component is `subj` (`subj`, `subj:pass`,
  `subj@expl`), as Grew's `-[1=subj]->` does; `--rel comp:obj` requires both components
  (`-[1=comp,2=obj]->`), `--rel comp:obl@agent` all three. `--rel any` is every
  word-to-word dependency, i.e. every edge except the root attachment (grugrutyp:
  `pattern { GOV -> DEP } without { GOV [form="__0__"] }`).
* "head-initial" is `GOV << DEP`: the governor's position is smaller than the
  dependent's. With a specific relation the virtual root never matters (no `subj` edge
  comes from it); `--rel root` counts root attachments, which are head-initial by
  definition (the virtual root sits at position 0).
* a HEAD that points at no word of the sentence (malformed data) is no edge, as in the
  grugrutyp import.
* `--budget N` reproduces grugrutyp's sampling: a language with more than N tokens is
  read on the k% of its sentences whose `sample_bucket(sent_id) < k`, k =
  `stats.sample_pct`. grugrutyp's plots use N = 100000 by default; without `--budget`
  every sentence is read (grugrutyp's "full corpus" / escalated points).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from . import config
from .conllu import decompose_deprel, read_conllu, sample_bucket
from .stats import sample_pct, wilson
from .treebanks import Treebank, measure_selection

BUCKETS = 100


def relation_matcher(rel: str):
    """`subj` -> a predicate over deprel strings, with Grew's feature-subset semantics."""
    if rel == "any":
        return None
    wanted = decompose_deprel(rel)
    wanted.pop("deprel", None)  # the full string is not a constraint, its parts are

    def matches(deprel: str) -> bool:
        have = decompose_deprel(deprel)
        return all(have.get(key) == value for key, value in wanted.items())

    return matches


@dataclass
class LanguageCounts:
    """Per-bucket counts, so any sample rate can be read off one pass over the files."""

    language: str
    treebanks: list[Treebank]
    n_tokens: list[int] = field(default_factory=lambda: [0] * BUCKETS)
    n_scope: list[int] = field(default_factory=lambda: [0] * BUCKETS)
    n_hit: list[int] = field(default_factory=lambda: [0] * BUCKETS)

    def at(self, budget: int | None) -> dict:
        pct = sample_pct(sum(self.n_tokens), budget)
        scope = sum(self.n_scope[:pct])
        hit = sum(self.n_hit[:pct])
        low, high = wilson(hit, scope)
        return {
            "language": self.language,
            "family": self.treebanks[0].family,
            "treebanks": len(self.treebanks),
            "n_tokens": sum(self.n_tokens),
            "sample_pct": pct,
            "n_scope": scope,
            "n_hit": hit,
            "value": round(100 * hit / scope, 4) if scope else None,
            "ci_low": round(low, 4),
            "ci_high": round(high, 4),
        }


def count_head_initial(language: str, treebanks: list[Treebank], rel: str) -> LanguageCounts:
    matches = relation_matcher(rel)
    out = LanguageCounts(language, treebanks)
    for tb in treebanks:
        for path in tb.conllu_files():
            for sentence in read_conllu(path):
                bucket = sample_bucket(sentence.sent_id)
                out.n_tokens[bucket] += sentence.n_tokens
                present = {w.idx for w in sentence.words}
                for word in sentence.words:
                    if matches is None:
                        if word.head == 0:
                            continue  # the root attachment, excluded by `any`
                    elif not matches(word.deprel):
                        continue
                    if word.head != 0 and word.head not in present:
                        continue  # no such governor: no edge
                    out.n_scope[bucket] += 1
                    if word.head < word.idx:
                        out.n_hit[bucket] += 1
    return out


def head_initial(
    rel: str,
    scheme: str = "SUD",
    version: str | None = None,
    languages: list[str] | None = None,
    budget: int | None = None,
) -> list[dict]:
    """One row per language: counts, percentage, Wilson 95% interval."""
    selection = measure_selection(scheme, version)
    if languages:
        wanted = set(languages)
        selection = {k: v for k, v in selection.items() if k in wanted}
        unknown = wanted - set(selection)
        if unknown:
            raise KeyError(f"no {scheme} treebanks for: {', '.join(sorted(unknown))}")
    return [count_head_initial(lang, tbs, rel).at(budget) for lang, tbs in selection.items()]


COLUMNS = ["language", "family", "treebanks", "n_tokens", "sample_pct", "n_scope", "n_hit",
           "value", "ci_low", "ci_high"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="measure", required=True)
    hi = sub.add_parser("head-initial", help="share of head-initial dependencies of a relation")
    hi.add_argument("--rel", required=True, help="subj, comp:obj, mod, any, ... (UD: nsubj, obj, ...)")
    hi.add_argument("--scheme", choices=["SUD", "UD"], default="SUD")
    hi.add_argument("--version", help="release, e.g. 2.19 (default: highest on disk)")
    hi.add_argument("--language", nargs="+", help="directory names, e.g. French Old_French")
    hi.add_argument("--budget", type=int, default=0,
                    help="token budget for sampling, as grugrutyp (its default: 100000); 0 = all")
    args = ap.parse_args(argv)

    version = args.version or config.default_version()
    rows = head_initial(args.rel, args.scheme, version, args.language, args.budget or None)
    print(f"# head-initial {args.rel} {args.scheme} v{version} budget={args.budget or 'none'}",
          file=sys.stderr)
    print("\t".join(COLUMNS))
    for row in rows:
        print("\t".join("" if row[c] is None else str(row[c]) for c in COLUMNS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
