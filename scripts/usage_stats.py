#!/usr/bin/env python3
"""Daily usage counts for typometrics.elizia.net, from the nginx access log.

The site has its own log since 2026-11-23 (`/var/log/nginx/typometrics.access.log`);
logrotate keeps 14 days of it. This script folds those logs into `data/usage.sqlite`
-- one row per (day, section, metric) -- so the counts outlive the logs. It runs hourly
from cron (as root: the logs are root:adm 0640) and is idempotent: every day present in
the logs is recomputed and replaced.

**No IP address or user agent is stored.** A visitor is a distinct (IP, user agent) pair
*within one day*, counted in memory and discarded -- the same rule `querylog.py` follows
for queries. The cost is that a visitor is not recognised across days, so "visitors" means
daily visitors, and a week's figure is a sum of days, not a count of people.

Sections are path prefixes:

    home        /              today the legacy SPA; the welcome page after the reorg
    legacy      /legacy/       the old site once it moves there
    grugrutyp   /grugrutyp/
    menzerath   /menzerath/
    flux        /flux-oral-ecrit/

Metrics per section and day: `pageviews` (HTML entry pages, 200/304, humans),
`visitors`, `bot_requests`; plus `measures` and `searches` for grugrutyp (its API calls)
and `api_calls` for the legacy Django API (`/typometricsapp/`, one per plot drawn), which
is the best measure of legacy use because its SPA is a single page. Section `all` holds
site-wide visitors. Referrers of human page views are kept per external host.

    sudo .venv/bin/python scripts/usage_stats.py                 # hourly cron
    sudo .venv/bin/python scripts/usage_stats.py --backfill      # + the shared log (once)

`--backfill` also reads the 14 days of the server-wide `access.log` from before the site
had its own log. That log mixes every vhost and has no host field, so only the paths that
are unambiguously this site's are taken from it -- `/grugrutyp/` and `/typometricsapp/`.
Page views of `/` before 2026-11-23 22:15 UTC are therefore unknown, not zero.
"""

from __future__ import annotations

import argparse
import glob
import gzip
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("GRUGRUTYP_USAGE_DB", ROOT / "data" / "usage.sqlite"))
SITE_LOG = "/var/log/nginx/typometrics.access.log"
GLOBAL_LOG = "/var/log/nginx/access.log"
SITE_HOST = "typometrics.elizia.net"

LINE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<method>[A-Z]+) (?P<path>\S+)[^"]*" '
    r'(?P<status>\d{3}) \S+ "(?P<ref>[^"]*)" "(?P<ua>[^"]*)"'
)
BOT = re.compile(
    r"bot|crawl|spider|slurp|scrapy|curl|wget|python|httpx|aiohttp|go-http|java/|"
    r"libwww|headless|phantom|monitor|uptime|feedfetcher|facebookexternalhit|preview|"
    r"scan|fetch|^-?$",
    re.I,
)
PAGE_STATUS = {"200", "304"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS counts (
    day     TEXT NOT NULL,
    section TEXT NOT NULL,
    metric  TEXT NOT NULL,
    n       INTEGER NOT NULL,
    PRIMARY KEY (day, section, metric)
);
CREATE TABLE IF NOT EXISTS referrers (
    day  TEXT NOT NULL,
    host TEXT NOT NULL,
    n    INTEGER NOT NULL,
    PRIMARY KEY (day, host)
);
"""


def section_of(path: str) -> str | None:
    if path.startswith("/grugrutyp"):
        return "grugrutyp"
    if path.startswith("/typometricsapp/"):
        return "legacy_api"
    if path.startswith("/legacy"):
        return "legacy"
    if path.startswith("/menzerath"):
        return "menzerath"
    if path.startswith("/flux-oral-ecrit"):
        return "flux"
    return "home"


def is_pageview(section: str, method: str, path: str) -> bool:
    if method != "GET":
        return False
    if section == "grugrutyp":
        return path in ("/grugrutyp/", "/grugrutyp/index.html")
    if section in ("home", "legacy"):
        return path in ("/", "/index.html", "/legacy/", "/legacy/index.html")
    # static sub-sites: any HTML page or directory index
    return path.endswith("/") or path.endswith(".html")


def open_log(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", errors="replace")
    return open(path, errors="replace")


def log_files(base: str) -> list[str]:
    return [p for p in [base, f"{base}.1", *sorted(glob.glob(f"{base}.*.gz"))] if os.path.exists(p)]


def scan(paths: list[str], only_prefixes: tuple[str, ...] | None, acc: dict) -> None:
    for path in paths:
        with open_log(path) as fh:
            for raw in fh:
                m = LINE.match(raw)
                if not m:
                    continue
                full = m["path"]
                if only_prefixes and not full.startswith(only_prefixes):
                    continue
                day = datetime.strptime(m["ts"][:11], "%d/%b/%Y").date().isoformat()
                path_only = full.split("?", 1)[0]
                section = section_of(path_only)
                d = acc[day]
                ua = m["ua"]
                if BOT.search(ua):
                    d["counts"][(section if section != "legacy_api" else "legacy", "bot_requests")] += 1
                    continue
                who = (m["ip"], ua)
                if section == "legacy_api":
                    d["counts"][("legacy", "api_calls")] += 1
                    d["visitors"]["legacy"].add(who)
                    d["visitors"]["all"].add(who)
                    continue
                if section == "grugrutyp":
                    if m["method"] == "POST" and path_only == "/grugrutyp/api/measure":
                        d["counts"][("grugrutyp", "measures")] += 1
                    elif path_only.startswith("/grugrutyp/api/search"):
                        d["counts"][("grugrutyp", "searches")] += 1
                if m["status"] in PAGE_STATUS and is_pageview(section, m["method"], path_only):
                    d["counts"][(section, "pageviews")] += 1
                    d["visitors"][section].add(who)
                    d["visitors"]["all"].add(who)
                    ref = urlsplit(m["ref"]).hostname or ""
                    if ref and ref != SITE_HOST:
                        d["referrers"][ref] += 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backfill", action="store_true", help="also read the shared access.log")
    ap.add_argument("--db", type=Path, default=DB_PATH)
    args = ap.parse_args()

    acc: dict = defaultdict(lambda: {
        "counts": defaultdict(int),
        "visitors": defaultdict(set),
        "referrers": defaultdict(int),
    })
    site_files = log_files(SITE_LOG)
    scan(site_files, None, acc)
    if args.backfill:
        scan(log_files(GLOBAL_LOG), ("/grugrutyp", "/typometricsapp/"), acc)

    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)
    days = sorted(acc)
    stored = {r[0] for r in conn.execute("SELECT DISTINCT day FROM counts")}
    with conn:
        for i, day in enumerate(days):
            # The oldest day in a rotated log set is usually truncated at its start; never
            # let that partial view overwrite a day an earlier run saw whole.
            if i == 0 and day in stored and len(days) > 1:
                continue
            d = acc[day]
            conn.execute("DELETE FROM counts WHERE day = ?", (day,))
            conn.execute("DELETE FROM referrers WHERE day = ?", (day,))
            rows = [(day, s, metric, n) for (s, metric), n in d["counts"].items()]
            rows += [(day, s, "visitors", len(v)) for s, v in d["visitors"].items()]
            conn.executemany("INSERT INTO counts VALUES (?, ?, ?, ?)", rows)
            conn.executemany(
                "INSERT INTO referrers VALUES (?, ?, ?)",
                [(day, host, n) for host, n in d["referrers"].items()],
            )
    conn.close()
    # The API (user typometrics) reads this file; cron writes it as root.
    try:
        st = os.stat(ROOT / "data")
        os.chown(args.db, st.st_uid, st.st_gid)
    except PermissionError:
        pass
    print(f"{len(days)} days ({days[0] if days else '-'} .. {days[-1] if days else '-'}) -> {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
