#!/usr/bin/env python3
"""Which model should translate plain language into Grew query pairs?

Empirical, not aesthetic. The presets are ready-made ground truth: each carries a
natural-language description AND a reference query pair per scheme. A candidate model
gets the description; its output must

  1. **validate** -- parse, bind, compile, exactly like a hand-typed query;
  2. **count-match** -- return the same (n_scope, n_hit) as the reference on a real
     treebank (English-GUM by default). Same counts on 250k tokens is semantic identity
     for our purposes; "looks right" is how a plausible wrong number gets published.

For aggregates the comparison is (n_scope, total) with a small float tolerance.

Usage:
  .venv/bin/python scripts/nl2grew_bench.py --models gpt-5.4-nano,gpt-5.4-mini
  .venv/bin/python scripts/nl2grew_bench.py --no-counts        # syntax-only, no DB
  .venv/bin/python scripts/nl2grew_bench.py --failures out.json

Writes one summary line per model; --failures dumps every miss with what the model
produced, which is the file to read before blaming the model or the prompt.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from grugrutyp import nl2grew, presets  # noqa: E402
from grugrutyp.measure import MeasureSpec  # noqa: E402

SCHEMES = ("SUD", "UD")

# Several preset descriptions are deliberately parameterised UI captions ("…bearing THIS
# relation") -- fed verbatim, a model can only invent the parameter (one dutifully wrote
# `1=$REL`; another correctly refused and asked which). Real users name the thing, so the
# bench does too, phrased as a user would, matching the reference's concrete instance.
BENCH_TEXTS = {
    "head-initiality": "Of all subject relations, how often does the subject follow its governor?",
    "head-initiality-cfc": "Adjectives modifying a noun: how often does the adjective come after its noun?",
    "distribution": "What share of all word-to-word dependencies are subject relations?",
    "freq-cfc": "What share of all word-to-word dependencies are a noun governing an adjective as its modifier?",
    "pos-share": "What share of words are adpositions?",
    "mean-distance": "The average signed distance in words between governor and dependent, for subject relations.",
}


def cases(schemes: tuple[str, ...]) -> list[dict]:
    out = []
    for preset in presets.PRESETS:
        for scheme in schemes:
            if scheme not in preset.scope:
                continue
            out.append(
                {
                    "key": preset.key,
                    "scheme": scheme,
                    "text": BENCH_TEXTS.get(preset.key, preset.description),
                    "reference": MeasureSpec(
                        scope=preset.scope[scheme],
                        response=preset.response.get(scheme, ""),
                        kind=preset.kind,
                        expression=preset.expression,
                        aggregation=preset.aggregation,
                    ),
                }
            )
    return out


def counts_of(spec: MeasureSpec, treebank: str):
    from grugrutyp.engine.neo4j_engine import get_engine

    if spec.kind == "aggregate":
        total, n_scope = get_engine().aggregate(
            treebank, spec.scope, spec.expression, spec.aggregation
        )
        return ("agg", n_scope, None if total is None else round(float(total), 4))
    n_scope, n_hit = get_engine().count_pair(treebank, spec.scope, spec.response)
    return ("ratio", n_scope, n_hit)


def _value(counts) -> float | None:
    kind, n_scope, numerator = counts
    if not n_scope or numerator is None:
        return None
    return numerator / n_scope * (100.0 if kind == "ratio" else 1.0)


def _value_close(got, want, points: float = 0.5) -> bool:
    got_value, want_value = _value(got), _value(want)
    if got_value is None or want_value is None:
        return False
    if got[0] == "ratio":
        return abs(got_value - want_value) <= points  # percentage points on the axis
    return abs(got_value - want_value) <= 0.01 * max(1.0, abs(want_value))


def run_case(case: dict, model: str, treebank: str | None, reference_counts: dict) -> dict:
    result = nl2grew.translate(case["text"], case["scheme"], model)
    record = {
        "key": case["key"], "scheme": case["scheme"], "model": model,
        "ok": result.get("ok", False), "attempts": result.get("attempts"),
        "seconds": result.get("seconds"),
        "produced": {k: result.get(k, "") for k in ("kind", "scope", "response", "expression")},
        "error": result.get("error", "") or result.get("refusal", ""),
        "count_match": None,
        "value_match": None,
    }
    if not record["ok"] or treebank is None:
        return record
    spec = MeasureSpec(
        scope=result["scope"], response=result["response"], kind=result["kind"],
        expression=result["expression"], aggregation=result["aggregation"],
    )
    try:
        got = counts_of(spec, f"{case['scheme']}_{treebank}")
        want = reference_counts[(case["key"], case["scheme"])]
        if got[0] == "agg" and want[0] == "agg":
            same_total = (
                got[2] is not None and want[2] is not None
                and abs(got[2] - want[2]) <= 1e-3 * max(1.0, abs(want[2]))
            )
            record["count_match"] = got[1] == want[1] and same_total
        else:
            record["count_match"] = got == want
        # The softer, honest metric: the PLOTTED VALUE. Different-but-defensible scopes
        # (root edges in or out of a projectivity denominator) can carry identical
        # values; exact counts alone would call that a failure.
        record["value_match"] = record["count_match"] or _value_close(got, want)
        record["counts"] = {"got": got, "want": want}
    except Exception as exc:  # noqa: BLE001 -- a query that compiles but cannot run
        record["count_match"] = False
        record["error"] = f"count failed: {type(exc).__name__}: {exc}"
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default="gpt-5.4-nano,gpt-5.4-mini")
    parser.add_argument("--schemes", default="SUD,UD")
    parser.add_argument("--treebank", default="English-GUM")
    parser.add_argument("--no-counts", action="store_true")
    parser.add_argument("--failures", default="")
    parser.add_argument("--jobs", type=int, default=6)
    args = parser.parse_args()

    todo = cases(tuple(s.strip().upper() for s in args.schemes.split(",")))
    treebank = None if args.no_counts else args.treebank

    reference_counts: dict = {}
    if treebank:
        print(f"reference counts on {treebank} ({len(todo)} cases)…", flush=True)
        for case in todo:
            reference_counts[(case["key"], case["scheme"])] = counts_of(
                case["reference"], f"{case['scheme']}_{treebank}"
            )

    all_failures = []
    print(f"\n{'model':22s} {'valid':>9s} {'counts=':>9s} {'value≈':>9s} {'avg s':>6s}")
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            records = list(
                pool.map(lambda c: run_case(c, model, treebank, reference_counts), todo)
            )
        valid = sum(1 for r in records if r["ok"])
        matched = sum(1 for r in records if r["count_match"])
        close = sum(1 for r in records if r["value_match"])
        avg_s = sum(r["seconds"] or 0 for r in records) / max(1, len(records))
        n = len(records)
        print(
            f"{model:22s} {valid:>4d}/{n:<4d} {matched:>4d}/{n:<4d} {close:>4d}/{n:<4d} {avg_s:>6.1f}"
        )
        all_failures.extend(r for r in records if not r["ok"] or r["value_match"] is False)

    if args.failures:
        Path(args.failures).write_text(json.dumps(all_failures, indent=2, ensure_ascii=False))
        print(f"\n{len(all_failures)} misses -> {args.failures}")


if __name__ == "__main__":
    main()
