"""Evaluate a measure across many treebanks and stream the points back.

Four levers make a ~705-treebank fan-out interactive, in the order they matter
(`docs/sampling.md` section 6): the cache, sampling, parallelism, and streaming. The first
three reduce the work; the fourth only reduces the *perceived* wait, but that is what the
user experiences, so the runner is a generator and the API is an SSE endpoint.

The unit of evaluation is the **language**, not the treebank (Kim, 2026-08-29: "I don't
want to keep the treebanks separate anymore"). One sampling percentage is computed from
the language's total tokens and applied to every one of its treebanks; since the sample
filter is a deterministic per-sentence bucket, that is a uniform random sample over the
whole language, drawing from each treebank in proportion to its size. Escalation is also
decided on the language's summed counts. The per-treebank machinery below it — cache
rows, retries, the points on the wire — is unchanged; treebanks are still *stored* and
*cached* separately, they are just no longer *sampled* or *judged* separately.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Iterator

from .cache import MeasureCache, get_cache
from .engine.neo4j_engine import TreebankInfo, get_engine
from .measure import MeasureSpec, Point, SamplingPolicy, sample_pct
from .meta import CORPUS_VERSION

# Neo4j is the bottleneck and it is a single container. Eight workers on eight cores
# saturates it without queueing inside the driver; more only moves the queue.
DEFAULT_WORKERS = 8

# A treebank whose query times out is retried, because the cause is almost always
# transient: eight workers hitting one database, or a page cache too small for the corpus,
# so the same query succeeds when the load drops. Without this a single slow treebank
# disappears from the plot with nothing but a line in the error list -- which is what
# happened to SUD_Arabic-PADT.
MAX_ATTEMPTS = 3
RETRY_BACKOFF = 5.0  # seconds, multiplied by the attempt number


def _is_transient(exc: Exception) -> bool:
    """Timeouts and service-availability errors are worth another go; a bad query is not.

    Matching on the message rather than the exception class: the driver raises
    `ClientError` for a transaction timeout and for a syntax error alike, and retrying a
    syntax error three times only delays the report.
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    if any(word in text for word in ("syntax", "unsupported", "invalidexpression", "not bound")):
        return False
    return any(
        word in text
        for word in ("timeout", "timed out", "transient", "unavailable", "deadlock", "defunct")
    )


@dataclass
class RunOptions:
    scheme: str = "SUD"
    treebanks: list[str] | None = None  # None => every treebank of the scheme
    policy: SamplingPolicy = field(default_factory=SamplingPolicy)
    workers: int = DEFAULT_WORKERS
    use_cache: bool = True
    version: str = CORPUS_VERSION


def select(options: RunOptions) -> list[TreebankInfo]:
    """Which treebanks this run covers."""
    available = get_engine().treebanks()
    if options.treebanks:
        wanted = set(options.treebanks)
        chosen = [tb for tb in available if tb.name in wanted]
    else:
        chosen = [tb for tb in available if tb.scheme == options.scheme.upper()]
    return sorted(chosen, key=lambda tb: tb.n_tokens)


def group_by_language(chosen: list[TreebankInfo]) -> list[list[TreebankInfo]]:
    """One task per language, **smallest language first**.

    Scheduling was smallest-*treebank*-first for the same reason: with eight workers and
    largest-first, nothing at all reached the plot until Czech and German were done --
    measured at 0 of 352 treebanks after 102 seconds, an apparently hung page.
    Smallest-first puts a hundred languages on screen in the first few seconds; what it
    costs is total makespan, and only on a cold run, because the cache makes every later
    run instant.
    """
    by_language: dict[str, list[TreebankInfo]] = {}
    for tb in chosen:  # `chosen` is size-sorted, so each group is too
        by_language.setdefault(tb.language, []).append(tb)
    return sorted(by_language.values(), key=lambda tbs: sum(tb.n_tokens for tb in tbs))


def _counts_at(
    spec: MeasureSpec,
    treebank: TreebankInfo,
    pct: int,
    options: RunOptions,
    cache: MeasureCache | None,
) -> tuple[int, float, bool]:
    """`(n_scope, accumulator, from_cache)` at a fixed sample percentage. No escalation.

    The second element is `n_hit` for a ratio and the aggregate accumulator (a sum, for
    `avg`) for an aggregate. Both are "the numerator", both merge across a language's
    treebanks by summing, and both share the cache row -- which is why the cache column is
    a REAL rather than an INTEGER.

    `treebank.imported_at` goes into the cache key, so a re-imported treebank starts from
    scratch rather than serving counts taken against its previous contents.
    """
    query_hash = spec.query_hash()
    revision = treebank.imported_at
    if cache and options.use_cache:
        hit = cache.get(treebank.name, query_hash, pct, options.version, revision)
        if hit:
            return hit[0], hit[1], True

    started = time.perf_counter()
    sample = pct if pct < 100 else None
    if spec.kind == "aggregate":
        total, n_scope = get_engine().aggregate(
            treebank.name, spec.scope, spec.expression, spec.aggregation, sample=sample
        )
        numerator = 0.0 if total is None else float(total)
    else:
        n_scope, numerator = get_engine().count_pair(
            treebank.name, spec.scope, spec.response, sample=sample
        )
    if cache:
        cache.put(
            treebank.name, query_hash, pct, n_scope, numerator,
            time.perf_counter() - started, options.version, revision,
        )
    return n_scope, numerator, False


def evaluate_language(
    specs: list[MeasureSpec],
    treebanks: list[TreebankInfo],
    options: RunOptions,
    cache: MeasureCache | None = None,
) -> list[list[Point]]:
    """Every axis of every treebank of one language, on **one** sub-corpus.

    Sharing the sample is not an optimisation, it is a correctness requirement, twice
    over. Across axes: if x came from a 10% sample and y from the full treebank, the
    point on the scatter describes two different corpora. Across treebanks: the language
    value merges by summing raw counts, and summing a 3% slice of German-HDT with 100% of
    German-GSD would weight GSD thirtyfold. So the percentage is decided **once, from the
    language's total tokens**, every treebank is queried at that rate, and escalation is
    judged on the language's summed counts -- a phenomenon rare in one small treebank but
    well-attested across the language is no reason to rescan anything.
    """
    n_tokens = sum(tb.n_tokens for tb in treebanks)
    pct = sample_pct(n_tokens, options.policy.token_budget)
    points = [[Point(treebank=tb.name, language=tb.language) for _ in specs] for tb in treebanks]
    raw: dict[str, list[tuple[int, float, bool]]] = {}

    def gather(treebank: TreebankInfo, at_pct: int) -> None:
        """Every axis of one treebank at one percentage, retrying a transient failure."""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                raw[treebank.name] = [
                    _counts_at(spec, treebank, at_pct, options, cache) for spec in specs
                ]
                return
            except Exception as exc:  # noqa: BLE001 -- classified below
                if not _is_transient(exc) or attempt == MAX_ATTEMPTS:
                    raise
                time.sleep(RETRY_BACKOFF * attempt)

    def gather_all(at_pct: int) -> None:
        """A broken treebank must not kill its language, let alone the other 192."""
        for tb, tb_points in zip(treebanks, points):
            if tb_points[0].error:
                continue  # already failed terminally at the lower percentage
            started = time.perf_counter()
            try:
                gather(tb, at_pct)
            except Exception as exc:  # noqa: BLE001
                # Say what actually went wrong. "1 treebank(s) failed" with no cause is a
                # dead end, and a timeout means something else than a bad query.
                kind = "timed out" if _is_transient(exc) else "failed"
                for point in tb_points:
                    point.error = f"{kind} after {MAX_ATTEMPTS} attempts: {type(exc).__name__}: {exc}"
            for point in tb_points:
                point.seconds += time.perf_counter() - started

    gather_all(pct)

    # Sampling trades precision for speed, and for a rare phenomenon there is no precision
    # to trade. Judged on the language's summed counts: that is the number that gets
    # plotted, and it is the reason a small treebank inside a large language no longer
    # triggers a rescan on its own sliver of the sample.
    def wants_full(axis: int) -> bool:
        spec = specs[axis]
        n_scope = sum(counts[axis][0] for counts in raw.values())
        numerator = sum(counts[axis][1] for counts in raw.values())
        if spec.kind == "aggregate":
            # An aggregate has no binomial interval -- the query returns a sum, not the
            # variance -- so only the scope size can be judged. The other two triggers
            # are about the precision of a proportion and do not apply.
            return n_scope < options.policy.min_scope
        return options.policy.escalate(n_scope, int(numerator))

    escalated = pct < 100 and raw and any(wants_full(axis) for axis in range(len(specs)))
    if escalated:
        # Bounded, not straight to 100% -- see SamplingPolicy.escalated_pct. A language
        # already at or above the escalation ceiling has nothing to gain, so skip the
        # second pass entirely rather than re-running the same percentage.
        target = options.policy.escalated_pct(n_tokens)
        if target > pct:
            pct = target
            gather_all(pct)
        else:
            escalated = False

    for tb, tb_points in zip(treebanks, points):
        counts = raw.get(tb.name)
        if counts is None:
            continue  # failed terminally; its error is already on the points
        for point, spec, (n_scope, numerator, cached) in zip(tb_points, specs, counts):
            point.n_scope = n_scope
            point.kind, point.aggregation = spec.kind, spec.aggregation
            if spec.kind == "aggregate":
                point.total = numerator
            else:
                point.n_hit = int(numerator)
            point.sample_pct, point.escalated, point.cached = pct, escalated, cached
    return points


def run(specs: list[MeasureSpec], options: RunOptions) -> Iterator[list[Point]]:
    """Yield one list of points (one per axis) per treebank, as soon as each is ready.

    Treebanks of one language are evaluated together (see `evaluate_language`) and
    therefore arrive together: a language's point lands on the plot once, complete,
    instead of drifting as its treebanks trickle in.

    `validate()` runs first and deliberately raises: discovering on treebank 300 of 705
    that the response pattern names an unbound node means five wasted minutes and, far
    worse, 299 numbers that look like results.
    """
    for spec in specs:
        spec.validate()
    languages = group_by_language(select(options))
    cache = get_cache() if options.use_cache else None

    with ThreadPoolExecutor(max_workers=max(1, options.workers)) as pool:
        futures = [
            pool.submit(evaluate_language, specs, treebanks, options, cache)
            for treebanks in languages
        ]
        for future in as_completed(futures):
            yield from future.result()
