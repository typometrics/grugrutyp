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


@dataclass
class RunOptions:
    scheme: str = "SUD"
    treebanks: list[str] | None = None  # None => every treebank of the scheme
    policy: SamplingPolicy = field(default_factory=SamplingPolicy)
    workers: int = DEFAULT_WORKERS
    use_cache: bool = True
    version: str = CORPUS_VERSION


def select(options: RunOptions) -> list[TreebankInfo]:
    """Which treebanks this run covers.

    Largest first. With a worker pool the makespan is set by the biggest item, so starting
    Czech-PDTC last would leave seven workers idle waiting for it.
    """
    available = get_engine().treebanks()
    if options.treebanks:
        wanted = set(options.treebanks)
        chosen = [tb for tb in available if tb.name in wanted]
    else:
        chosen = [tb for tb in available if tb.scheme == options.scheme.upper()]
    return sorted(chosen, key=lambda tb: -tb.n_tokens)


def _counts_at(
    spec: MeasureSpec,
    treebank: TreebankInfo,
    pct: int,
    options: RunOptions,
    cache: MeasureCache | None,
) -> tuple[int, int, bool]:
    """`(n_scope, n_hit, from_cache)` at a fixed sample percentage. No escalation.

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
    n_scope, n_hit = get_engine().count_pair(
        treebank.name, spec.scope, spec.response, sample=pct if pct < 100 else None
    )
    if cache:
        cache.put(
            treebank.name, query_hash, pct, n_scope, n_hit,
            time.perf_counter() - started, options.version, revision,
        )
    return n_scope, n_hit, False


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

    try:
        raw = [_counts_at(spec, treebank, pct, options, cache) for spec in specs]

        # Sampling trades precision for speed, and for a rare phenomenon there is no
        # precision to trade. Escalation is per treebank, so one rare-in-Czech phenomenon
        # does not slow down the other 704.
        escalated = pct < 100 and any(
            options.policy.escalate(n_scope, n_hit) for n_scope, n_hit, _ in raw
        )
        if escalated:
            pct = 100
            raw = [_counts_at(spec, treebank, pct, options, cache) for spec in specs]

        for point, (n_scope, n_hit, cached) in zip(points, raw):
            point.n_scope, point.n_hit = n_scope, n_hit
            point.sample_pct, point.escalated, point.cached = pct, escalated, cached
    except Exception as exc:  # a broken treebank must not kill the other 704
        for point in points:
            point.error = f"{type(exc).__name__}: {exc}"

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
