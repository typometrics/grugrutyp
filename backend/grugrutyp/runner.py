"""Evaluate a measure across many treebanks and stream the points back.

Four levers make a ~705-treebank fan-out interactive, in the order they matter
(`docs/sampling.md` section 6): the cache, sampling, parallelism, and streaming. The first
three reduce the work; the fourth only reduces the *perceived* wait, but that is what the
user experiences, so the runner is a generator and the API is an SSE endpoint.
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
    """Which treebanks this run covers, **smallest first**.

    This was largest-first, on the standard argument that a worker pool's makespan is set
    by its biggest item. That argument optimises the wrong thing here. With eight workers
    the first eight tasks are then Czech-PDTC, German-HDT, Russian-Taiga and friends -- so
    nothing at all reaches the plot until the largest treebanks in the corpus are done.
    Measured: **0 of 352 treebanks after 102 seconds**, an apparently hung page.

    The endpoint streams precisely so the plot fills in as results land, and smallest-first
    puts a hundred languages on screen in the first few seconds. What it costs is total
    makespan, and only on a cold run -- the cache makes every later run instant, and
    `docs/sampling.md` §6 already ranks the cache above every other lever.
    """
    available = get_engine().treebanks()
    if options.treebanks:
        wanted = set(options.treebanks)
        chosen = [tb for tb in available if tb.name in wanted]
    else:
        chosen = [tb for tb in available if tb.scheme == options.scheme.upper()]
    return sorted(chosen, key=lambda tb: tb.n_tokens)


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


def evaluate(
    specs: list[MeasureSpec],
    treebank: TreebankInfo,
    options: RunOptions,
    cache: MeasureCache | None = None,
) -> list[Point]:
    """Every axis of one treebank, on **one** sub-corpus.

    Sharing the sample across axes is not an optimisation, it is a correctness
    requirement: if x came from a 10% sample and y from the full treebank, the point on
    the scatter describes two different corpora. So the percentage is decided once from
    the token budget, and if *any* axis comes back too imprecise to plot, *every* axis is
    recomputed at 100%.
    """
    pct = sample_pct(treebank.n_tokens, options.policy.token_budget)
    points = [Point(treebank=treebank.name, language=treebank.language) for _ in specs]
    started = time.perf_counter()

    def gather(at_pct: int) -> list[tuple[int, float, bool]]:
        """Every axis at one percentage, retrying a transient failure."""
        last: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return [_counts_at(spec, treebank, at_pct, options, cache) for spec in specs]
            except Exception as exc:  # noqa: BLE001 -- classified below
                last = exc
                if not _is_transient(exc) or attempt == MAX_ATTEMPTS:
                    raise
                time.sleep(RETRY_BACKOFF * attempt)
        raise last  # type: ignore[misc]

    try:
        raw = gather(pct)

        # Sampling trades precision for speed, and for a rare phenomenon there is no
        # precision to trade. Escalation is per treebank, so one rare-in-Czech phenomenon
        # does not slow down the other 704.
        def wants_full(spec: MeasureSpec, n_scope: int, numerator: float) -> bool:
            if spec.kind == "aggregate":
                # An aggregate has no binomial interval -- the query returns a sum, not the
                # variance -- so only the scope size can be judged. The other two triggers
                # are about the precision of a proportion and do not apply.
                return n_scope < options.policy.min_scope
            return options.policy.escalate(n_scope, int(numerator))

        escalated = pct < 100 and any(
            wants_full(spec, n_scope, numerator)
            for spec, (n_scope, numerator, _) in zip(specs, raw)
        )
        if escalated:
            pct = 100
            raw = gather(pct)

        for point, spec, (n_scope, numerator, cached) in zip(points, specs, raw):
            point.n_scope = n_scope
            point.kind, point.aggregation = spec.kind, spec.aggregation
            if spec.kind == "aggregate":
                point.total = numerator
            else:
                point.n_hit = int(numerator)
            point.sample_pct, point.escalated, point.cached = pct, escalated, cached
    except Exception as exc:  # a broken treebank must not kill the other 704
        # Say what actually went wrong. "1 treebank(s) failed" with no cause is a dead end,
        # and a timeout means something quite different from a bad query.
        kind = "timed out" if _is_transient(exc) else "failed"
        for point in points:
            point.error = f"{kind} after {MAX_ATTEMPTS} attempts: {type(exc).__name__}: {exc}"

    for point in points:
        point.seconds = time.perf_counter() - started
    return points


def run(specs: list[MeasureSpec], options: RunOptions) -> Iterator[list[Point]]:
    """Yield one list of points (one per axis) per treebank, as soon as each is ready.

    `validate()` runs first and deliberately raises: discovering on treebank 300 of 705
    that the response pattern names an unbound node means five wasted minutes and, far
    worse, 299 numbers that look like results.
    """
    for spec in specs:
        spec.validate()
    chosen = select(options)
    cache = get_cache() if options.use_cache else None

    with ThreadPoolExecutor(max_workers=max(1, options.workers)) as pool:
        futures = [pool.submit(evaluate, specs, tb, options, cache) for tb in chosen]
        for future in as_completed(futures):
            yield future.result()
