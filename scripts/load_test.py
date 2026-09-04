#!/usr/bin/env python3
"""Load test for the public endpoints (Phase 4).

The question is not "how many requests per second" -- this is a research site whose
bottleneck is a spinning disk, and nobody is benchmarking throughput. The question is
the one the audit raised and the rate limits answered blind: **what happens to an
ordinary visitor while someone else is running the expensive thing.** So the test
measures the interactive endpoints' latency alone, then again under a background load
of concurrent measure streams, and reports the degradation.

    .venv/bin/python scripts/load_test.py                 # against the live site
    .venv/bin/python scripts/load_test.py --base http://127.0.0.1:8020 --direct

`--direct` talks to uvicorn and bypasses nginx, which is how you tell an app-level
limit from a transport-level one: through nginx a flood should be *shed* (429/503),
directly it should merely queue.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request

# Warm, cheap, and representative of what a page load does.
PROBES = [
    ("treebanks", "GET", "/treebanks", None),
    ("languages", "GET", "/languages?view=family", None),
    ("presets", "GET", "/presets?scheme=SUD", None),
    (
        "search",
        "POST",
        "/search",
        {"treebank": "SUD_English-GUM", "request": "pattern { X [upos=ADV] }", "limit": 5},
    ),
    (
        "preview",
        "POST",
        "/measure/preview",
        {
            "treebank": "SUD_English-GUM",
            "scope": "pattern { GOV -[1=subj]-> DEP }",
            "response": "with { GOV << DEP }",
        },
    ),
]

MEASURE = {
    "scheme": "SUD",
    "token_budget": 100000,
    "x": {
        "scope": "pattern { GOV -[1=subj]-> DEP }",
        "response": "with { GOV << DEP }",
    },
}


def call(base: str, method: str, path: str, payload: dict | None, timeout: float = 120):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{base}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            return time.perf_counter() - started, response.status
    except urllib.error.HTTPError as exc:
        exc.read()
        return time.perf_counter() - started, exc.code
    except Exception:  # noqa: BLE001 -- a timeout is a result, not a crash
        return time.perf_counter() - started, 0


def probe_round(base: str, repeats: int) -> dict[str, list[float]]:
    timings: dict[str, list[float]] = {name: [] for name, *_ in PROBES}
    codes: dict[str, set] = {name: set() for name, *_ in PROBES}
    for _ in range(repeats):
        for name, method, path, payload in PROBES:
            seconds, status = call(base, method, path, payload)
            timings[name].append(seconds)
            codes[name].add(status)
    for name in codes:
        bad = {c for c in codes[name] if c != 200}
        if bad:
            print(f"    ! {name}: non-200 responses {sorted(bad)}")
    return timings


def summarise(label: str, timings: dict[str, list[float]]) -> None:
    print(f"  {label}")
    for name, values in timings.items():
        values = sorted(values)
        median = statistics.median(values)
        worst = values[-1]
        print(f"    {name:12} median {median*1000:7.0f} ms   worst {worst*1000:7.0f} ms")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://typometrics.elizia.net/grugrutyp/api")
    parser.add_argument("--direct", action="store_true", help="label only: bypassing nginx")
    parser.add_argument("--streams", type=int, default=4, help="concurrent /measure runs")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    print(f"target: {args.base}{'  (direct, no nginx)' if args.direct else ''}\n")

    print("[1] baseline -- interactive endpoints, nothing else running")
    summarise("baseline", probe_round(args.base, args.repeats))

    print(f"\n[2] under load -- {args.streams} concurrent /measure streams")
    stop = threading.Event()
    outcomes: list[tuple[float, int]] = []

    def hammer():
        while not stop.is_set():
            outcomes.append(call(args.base, "POST", "/measure", MEASURE, timeout=600))

    threads = [threading.Thread(target=hammer, daemon=True) for _ in range(args.streams)]
    for thread in threads:
        thread.start()
    time.sleep(5)  # let the streams get going before probing
    under_load = probe_round(args.base, args.repeats)
    stop.set()
    for thread in threads:
        thread.join(timeout=30)

    summarise("under load", under_load)
    shed = sum(1 for _, status in outcomes if status in (429, 503))
    failed = sum(1 for _, status in outcomes if status == 0)
    print(
        f"\n  measure streams: {len(outcomes)} completed, {shed} shed (429/503), "
        f"{failed} timed out or errored"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
