"""Regression against the current site's precomputed 2.12 tables.

Needs Neo4j with the corpus imported; skipped otherwise. `scripts/regression_2_12.py`
prints the full comparison -- this file asserts only the part that can be asserted.

**What is and is not being claimed.** The old tables are UD/SUD 2.12 and the database is
2.18, so a per-language difference is meaningless: six releases changed annotations, added
treebanks to existing languages and re-tokenised some. Asserting a per-language tolerance
would be asserting that UD stopped changing, and the test would fail on the next release
for a reason that has nothing to do with this code.

What *is* assertable is the **systematic** part. If our head-initiality had an inverted
direction convention, an off-by-one in `idx`, or the root node inside a scope that should
exclude it, every language would move together and the median would move with them. So the
test asserts a near-zero median and a majority landing close, and leaves the tail alone.

Head-initiality is the measure used, and deliberately the only one: it is a per-relation
ratio, so it is immune to the root-node convention that `docs/measures-mapping.md` §2
point 1 is about -- a `subj` edge never originates at Grew's virtual root. A disagreement
on `distribution` or `cat` would be ambiguous between a real bug and a mis-replayed
convention, which is not what a regression test should be for.
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from grugrutyp import langconfig
from grugrutyp.measure import MeasureSpec, SamplingPolicy, merge_by_language
from grugrutyp.runner import RunOptions, run

regression_2_12 = pytest.importorskip("regression_2_12")

MIN_SCOPE = 100
MIN_LANGUAGES = 20


def _deltas(scheme: str, relation: str) -> list[tuple[str, float]]:
    table_path = regression_2_12.TABLES[scheme]
    if not table_path.exists():
        pytest.skip(f"{table_path} not available")
    table = regression_2_12.load_table(table_path)

    spec = MeasureSpec(
        scope=regression_2_12.grew_scope(relation, scheme), response="with { GOV << DEP }"
    )
    options = RunOptions(
        scheme=scheme, policy=SamplingPolicy(token_budget=None, min_scope=MIN_SCOPE)
    )
    points = [group[0] for group in run([spec], options)]

    out = []
    for merged in merge_by_language(points):
        if merged.n_scope < MIN_SCOPE:
            continue
        old = table.get(langconfig._fold(merged.language), {}).get(relation)
        if old is not None:
            out.append((merged.language, merged.value - old))
    return out


@pytest.mark.slow
@pytest.mark.parametrize(
    ("scheme", "relation"),
    [("SUD", "subj"), ("SUD", "comp:obj"), ("UD", "nsubj"), ("UD", "obj")],
)
def test_head_initiality_has_no_systematic_offset_against_2_12(scheme, relation):
    deltas = _deltas(scheme, relation)
    if len(deltas) < MIN_LANGUAGES:
        pytest.skip(f"only {len(deltas)} languages in common -- import more of the corpus")

    values = [delta for _, delta in deltas]
    median = statistics.median(values)
    close = sum(abs(delta) <= 5 for delta in values)

    # A convention error moves every language the same way. Annotation drift does not.
    assert abs(median) < 2.0, (
        f"{scheme} {relation}: median delta {median:+.2f} against the 2.12 table. "
        "Per-language drift is expected between releases; a systematic offset is not, "
        "and points at a direction convention, an idx off-by-one, or the root node "
        "sitting inside a scope that should exclude it."
    )
    assert close / len(values) >= 0.75, (
        f"{scheme} {relation}: only {close}/{len(values)} languages within 5 points. "
        "Six releases of annotation should not move three quarters of them that far."
    )


@pytest.mark.slow
def test_the_2_12_tables_and_our_language_names_still_line_up():
    """The comparison is worthless if the join silently matches nothing.

    The 2.12 tables are keyed on the configuration's curated language names, which UD has
    since renamed in 25 cases (`docs/language-config.md` §4). Accent- and underscore-
    folding is what keeps the join working; if that regresses, every other assertion here
    starts passing vacuously on an empty set.
    """
    table = regression_2_12.load_table(regression_2_12.TABLES["SUD"])
    ours = {langconfig._fold(name) for name in langconfig.disk_lcodes()}
    overlap = ours & set(table)
    assert len(overlap) >= 80, (
        f"only {len(overlap)} of {len(table)} 2.12 languages match a 2.18 language name"
    )
