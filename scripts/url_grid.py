#!/usr/bin/env python3
"""URL breadth grid (CC-120): variables x geography level x parent depth x time, scored on the URL.

    python scripts/url_grid.py generate [--seed N] [--out PATH]   # needs CENSUS_API_KEY
    python scripts/url_grid.py run --repeat 3 [--grid PATH]       # needs OPENAI + CENSUS keys

`generate` walks the cached geography.json rows and the availability matrix, resolves real
parents and row counts from the Census API once, and writes a cell file
(`evals/url_breadth_grid.toml` is seed 0). The owner seals a held-out grid by generating with a
seed only they hold and keeping the file outside the repo; `run --grid PATH --aggregate-only`
prints counts, never questions.

`run` asks each cell through POST /ask and scores the URLs and rows it gets back, separately from
the demo's answered rate. Checks are reported as distinct numbers: cap, level, http, cardinality,
variables, em_pairing, geo_id, years, fail_closed. A cell passes when every applicable check does.
The summary lands in evidence/url-grid-latest.json only when every trial ran; a partial run writes
evidence/url-grid-partial.json, and trials recorded against another grid are ignored.

Live usage per run: one /ask per cell per repeat (about 20 s, one model loop and one to three
Census calls each); `generate` makes one Census call per cell.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import time
import tomllib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
GRID = ROOT / "evals" / "url_breadth_grid.toml"
LATEST = ROOT / "evidence" / "url-grid-latest.json"
PARTIAL = ROOT / "evidence" / "url-grid-partial.json"
LOG = ROOT / "evidence" / "url-grid-trials.jsonl"
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "api"))

from src.census_url import CENSUS_API, CensusURL, redact_text  # noqa: E402
from src.retrieval import availability, metadata  # noqa: E402

CAP = 50  # the Census `get` limit, NAME and GEO_ID included
COUNTS = ("1", "24", "25", "whole")
CHECKS = (
    *("cap", "level", "dataset", "geography", "table", "http", "cardinality"),
    *("variables", "em_pairing", "geo_id", "years"),
)


# --- scoring -----------------------------------------------------------------------------------


def get_size(url: str) -> int:
    """Variables a URL's `get` asks for; `group(B01001)` is one."""
    get = parse_qs(urlparse(url).query).get("get", [""])[0]
    return len([item for item in get.split(",") if item])


def is_estimate(key: str) -> bool:
    table, _, tail = key.partition("_")
    return bool(table) and tail.endswith("E") and tail[:-1].isdigit()


def score(cell: dict[str, Any], body: dict[str, Any]) -> dict[str, bool | None]:
    """One entry per check: True, False, or None when the cell does not exercise it."""
    urls = [str(u) for u in body.get("urls") or []]
    rows = [r for r in body.get("rows") or [] if isinstance(r, dict)]
    legs = body.get("legs") or []
    columns = {key for row in rows for key in row}
    out: dict[str, bool | None] = dict.fromkeys(CHECKS)
    out["cap"] = bool(urls) and all(get_size(u) <= CAP for u in urls)
    levels = {parse_qs(urlparse(u).query).get("for", [""])[0].partition(":")[0] for u in urls}
    out["level"] = bool(urls) and levels == {cell["level"]}
    paths = [urlparse(u).path for u in urls]
    out["dataset"] = bool(urls) and all(p.endswith("/" + cell["dataset"]) for p in paths)
    if cell["scope"] == "listing":
        wanted = sorted(cell["in_spec"].split())
        ins = [sorted(parse_qs(urlparse(u).query).get("in", [""])[0].split()) for u in urls]
        out["geography"] = bool(urls) and all(parents == wanted for parents in ins)
    if cell["fail_closed"]:
        out["http"] = None
        out["cardinality"] = not rows  # an unpublished level yields no rows, never substitutes
        return out
    out["http"] = bool(legs) and all(
        leg.get("ok") and leg.get("status_code") == 200 for leg in legs
    )
    by_year: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        by_year[str(row.get("year") or "")].add(str(row.get("GEO_ID") or ""))
    expected = cell["expected_rows"]
    out["cardinality"] = bool(by_year) and all(len(g - {""}) == expected for g in by_year.values())
    estimates = {key for key in columns if is_estimate(key)}
    tables = {k.partition("_")[0] for k in estimates}
    out["table"] = bool(estimates) and tables == {cell["table_id"]}
    if cell["scope"] == "named":
        out["geography"] = {str(r.get("GEO_ID")) for r in rows} == {cell["expected_geoid"]}
    out["variables"] = len(estimates) >= cell["estimates"]
    out["em_pairing"] = bool(estimates) and all(key[:-1] + "M" in columns for key in estimates)
    out["geo_id"] = bool(rows) and all(row.get("GEO_ID") for row in rows)
    if cell["years"]:
        attempted, omitted = set(body.get("attempted_years") or []), body.get("omitted_years") or []
        reasons = body.get("omission_reasons") or []
        named = len(reasons) == len(omitted) and all(str(r).strip() for r in reasons)
        published = set(cell["years"]) - set(cell["unpublished"])
        out["years"] = published <= attempted and set(cell["unpublished"]) <= set(omitted) and named
    return out


def passed(checks: dict[str, bool | None]) -> bool:
    return all(v for v in checks.values() if v is not None)


# --- generation --------------------------------------------------------------------------------


def estimate_count(suffixes: list[str]) -> int:
    return len([s for s in suffixes if s.endswith("E") and s[:-1].isdigit()])


def reference(
    client: httpx.Client, key: str, year: int, level: str, in_spec: str = ""
) -> list[list[str]]:
    """The Census answer for `for=level:*`, fetched by the harness: the expected cardinality."""
    params = {"get": "NAME,GEO_ID", "for": f"{level}:*"}
    if in_spec:
        params["in"] = in_spec
    url = CensusURL(f"{CENSUS_API}/{year}/acs/acs5?{urlencode(params)}").with_key(key)
    try:
        response = client.get(url)
        payload = response.json() if response.status_code == 200 else []
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError(f"reference for {level}: {redact_text(str(exc))[:120]}") from None
    if response.status_code not in {200, 204}:  # a transient failure must not read as "no rows"
        raise RuntimeError(f"reference for {level}: HTTP {response.status_code}")
    return payload[1:] if isinstance(payload, list) and len(payload) > 1 else []


def parents_for(
    client: httpx.Client, key: str, year: int, requires: tuple[str, ...], rng: random.Random
) -> tuple[str, str] | None:
    """Walk the required parents, picking one at random each step. -> (`in` spec, last name)."""
    in_spec, name = "", ""
    for parent in requires:
        rows = reference(client, key, year, parent, in_spec)
        if not rows:
            return None
        pick = rng.choice(rows)
        code = pick[-1]
        name = pick[0]
        in_spec = f"{in_spec} {parent}:{code}".strip()
    return in_spec, name


def phrase_geo(level: str, scope: str, parent: str, place: str) -> str:
    if scope == "named":
        return f"for {place}"
    return f"for every {level} in {parent or 'the United States'}"


def unpublished(matrix: dict[str, Any], dataset: str, table: str, years: list[int]) -> list[int]:
    """Requested years in which this table does not exist for the dataset."""
    return [y for y in years if table not in matrix[dataset].get(str(y), {})]


def count_phrase(count: str, table: str) -> str:
    if count == "1":
        return f"{table}_001E from table {table}"
    if count == "whole":
        return f"Every variable in table {table}"
    return f"The first {count} estimates of table {table}"


def generate(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    matrix = availability.load()["datasets"]
    acs5, acs1 = sorted(int(y) for y in matrix["acs5"]), sorted(int(y) for y in matrix["acs1"])
    year = acs5[-1]
    tables = matrix["acs5"][str(year)]
    sized = {
        t: estimate_count(f["variables"])
        for t, f in tables.items()
        if metadata.is_subject_table(t) and metadata.family_id(t) == t and len(t) == 6
    }
    pool = {
        "1": [t for t, n in sized.items() if n >= 1],
        "24": [t for t, n in sized.items() if n >= 24],
        "25": [t for t, n in sized.items() if n >= 25],
        "whole": [t for t, n in sized.items() if 26 <= n <= 45],
    }
    for key in pool:
        pool[key].sort()
    cells: list[dict[str, Any]] = []
    skipped: list[str] = []
    levels = metadata.geo_entries("acs5", year)
    acs1_names = {g.name for g in metadata.geo_entries("acs1", acs1[-1])}
    key = os.environ["CENSUS_API_KEY"]

    def add(
        level: Any,
        scope: str,
        count: str,
        dataset: str = "acs5",
        time: str = "latest",
        years: list[int] | None = None,
        fail_closed: bool = False,
    ) -> None:
        table = rng.choice(pool[count])
        with httpx.Client(timeout=60.0) as client:
            chain = parents_for(client, key, year, level.requires, rng)
            if chain is None:
                skipped.append(f"{level.name} requires {','.join(level.requires)}")
                return
            in_spec, parent = chain
            listing = reference(client, key, year, level.name, in_spec)
        if not listing:
            skipped.append(f"{level.name} listing is empty for {in_spec or 'the nation'}")
            return
        pick = rng.choice(listing) if scope == "named" else ["", ""]
        when = {"acs5": "with the ACS 5-year", "acs1": "with the ACS 1-year"}[dataset]
        geo = phrase_geo(level.name, scope, parent, pick[0])
        question = f"{count_phrase(count, table)} {geo}, {when}"
        years = years or []
        if years:
            question += ", for the years " + ", ".join(str(y) for y in years)
        cells.append(
            {
                "id": f"u{len(cells):03d}",
                "level": level.name,
                "depth": len(level.requires),
                "scope": scope,
                "var_count": count,
                "time": time,
                "dataset": dataset,
                "table_id": table,
                "in_spec": in_spec if scope == "listing" else "",
                "expected_geoid": pick[1],
                "estimates": sized[table] if count == "whole" else int(count),
                "expected_rows": 0 if fail_closed else 1 if scope == "named" else len(listing),
                "fail_closed": fail_closed,
                "years": years,
                "unpublished": unpublished(matrix, dataset, table, years),
                "question": question,
            }
        )

    for index, level in enumerate(levels):
        for scope in ("listing", "named"):
            if scope == "listing" and not level.requires and level.name in {"us"}:
                continue
            add(level, scope, COUNTS[(index + (scope == "named")) % len(COUNTS)])
    state = next(g for g in levels if g.name == "state")
    for count in COUNTS:
        add(state, "named", count)
    gap = next((y for y in range(acs1[0], acs1[-1]) if y not in acs1), 0)
    series = {
        "single": ("acs5", [acs5[-2]]),
        "acs5_series": ("acs5", [acs5[-1] - 5, acs5[-1]]),
        "acs1_series": ("acs1", acs1[-3:]),
        "gap": ("acs1", [gap - 1, gap, gap + 1] if gap else acs1[-3:]),
    }
    for name, (dataset, years) in series.items():
        add(state, "named", "1", dataset, time=name, years=years)
    for level in [g for g in levels if g.name not in acs1_names and g.requires][:3]:
        add(level, "listing", "1", "acs1", fail_closed=True)
    return {
        "generated": {
            "date": date.today().isoformat(),
            "vintage_acs5": year,
            "vintage_acs1": acs1[-1],
            "seed": seed,
        },
        "skipped": skipped,
        "cell": cells,
    }


def dump_toml(grid: dict[str, Any]) -> str:
    lines = ["# Generated by scripts/url_grid.py; do not edit by hand."]
    for name, value in grid["generated"].items():
        lines.append(f"# {name} = {value}")
    for item in grid["skipped"]:
        lines.append(f"# skipped: {item}")
    for cell in grid["cell"]:
        lines += ["", "[[cell]]"]
        lines += [f"{k} = {json.dumps(v)}" for k, v in cell.items()]
    return "\n".join(lines) + "\n"


# --- running -----------------------------------------------------------------------------------


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT
        )
        return out.stdout.strip()
    except OSError:
        return ""


def summarize(
    cells: list[dict[str, Any]],
    results: list[dict[str, Any]],
    repeat: int,
    grid_sha: str,
    subset: bool = False,
) -> dict[str, Any]:
    complete = not subset and len(results) == len(cells) * repeat
    rates: dict[str, list[bool]] = defaultdict(list)
    for row in results:
        for check, ok in row["checks"].items():
            if ok is not None:
                rates[check].append(ok)
    by: dict[str, list[bool]] = defaultdict(list)
    ids = {c["id"]: c for c in cells}
    for row in results:
        for dim in ("var_count", "depth", "scope", "time", "dataset", "level"):
            by[f"{dim}={ids[row['id']][dim]}"].append(row["passed"])
    seconds = sorted(r["seconds"] for r in results)
    return {
        "status": "FINAL" if complete else ("SUBSET" if subset else "PARTIAL"),
        "complete": complete,
        "grid_sha": grid_sha,
        "git_sha": git_sha(),
        "finished": datetime.now(UTC).isoformat(timespec="seconds"),
        "cells": len(cells),
        "repeat": repeat,
        "trials": len(results),
        "expected_trials": len(cells) * repeat,
        "pass_rate": round(sum(r["passed"] for r in results) / max(len(results), 1), 3),
        "checks": {
            k: {"rate": round(sum(v) / len(v), 3), "n": len(v)} for k, v in sorted(rates.items())
        },
        "by_dimension": {k: round(sum(v) / len(v), 3) for k, v in sorted(by.items())},
        "max_seconds": seconds[-1] if seconds else 0,
        "p95_seconds": seconds[math.ceil(0.95 * len(seconds)) - 1] if seconds else 0,
        "crashed": sum(bool(r.get("crashed")) for r in results),
        "git_shas": sorted({str(r.get("git_sha", "")) for r in results}),
        "misses": [
            {
                "id": r["id"],
                "repeat": r["repeat"],
                "failed": [k for k, v in r["checks"].items() if v is False],
            }
            for r in results
            if not r["passed"]
        ],
    }


def read_log(path: Path) -> list[dict[str, Any]]:
    """Recorded trials; a line cut short by an interrupted run is skipped, not fatal."""
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines() if path.exists() else []:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def run(args: argparse.Namespace) -> int:
    missing = [k for k in ("OPENAI_API_KEY", "CENSUS_API_KEY") if not os.environ.get(k)]
    if missing:
        raise SystemExit(
            f"{', '.join(missing)} must be set; a keyless run scores outages as misses"
        )
    if args.aggregate_only and not args.tag:
        raise SystemExit(
            "--aggregate-only needs --tag: a sealed run must not overwrite the baseline"
        )
    tag = "-".join(t for t in (args.tag, "subset" if args.limit else "") if t)
    log, latest, partial = (
        path.with_stem(path.stem + (f"-{tag}" if tag else "")) for path in (LOG, LATEST, PARTIAL)
    )
    raw = args.grid.read_bytes()
    grid_sha = hashlib.sha256(raw).hexdigest()[:12]
    cells = tomllib.loads(raw.decode())["cell"][: args.limit or None]
    if not (args.resume or args.batch):
        log.unlink(missing_ok=True)
    for stale in (latest, partial):  # a stale scoreboard can never sit beside a run in progress
        stale.unlink(missing_ok=True)
    from fastapi.testclient import TestClient
    from src.main import app

    commit = git_sha()

    def trial(job: tuple[int, dict[str, Any]]) -> dict[str, Any]:
        repeat, cell = job
        started = time.monotonic()
        body: Any = {}
        crashed = ""
        try:
            with TestClient(app) as client:
                response = client.post("/ask", json={"question": cell["question"]})
            body = response.json() if response.status_code == 200 else {}
        except Exception as exc:  # noqa: BLE001 - one crashed ask is a miss, not an aborted run
            crashed = type(exc).__name__
        checks = score(cell, body if isinstance(body, dict) else {})
        ok = passed(checks)
        label = f"{cell['id']} r{repeat}" if not args.aggregate_only else "trial"
        note = f" CRASH {crashed}" if crashed else ""
        print(f"{'ok  ' if ok else 'MISS'} {label}{note}", flush=True)
        return {
            "id": cell["id"],
            "repeat": repeat,
            "grid_sha": grid_sha,
            "git_sha": commit,
            "checks": checks,
            "passed": ok,
            "crashed": crashed,
            "seconds": round(time.monotonic() - started, 1),
        }

    seen = {(r["id"], r["repeat"]) for r in read_log(log) if r["grid_sha"] == grid_sha}
    jobs = [(r, c) for r in range(1, args.repeat + 1) for c in cells if (c["id"], r) not in seen][
        : args.batch or None
    ]
    if log.exists() and not log.read_bytes().endswith(bytes([10])):
        with log.open("a") as handle:  # a cut-short last line must not swallow the next record
            handle.write(chr(10))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(trial, job) for job in jobs]):
            with log.open("a") as handle:  # on disk as each trial finishes, so Ctrl-C loses little
                handle.write(json.dumps(future.result()) + chr(10))
    ids = {c["id"] for c in cells}
    results = [
        r
        for r in read_log(log)
        if r["grid_sha"] == grid_sha and r["id"] in ids and r["repeat"] <= args.repeat
    ]
    summary = summarize(cells, results, args.repeat, grid_sha, subset=bool(args.limit))
    if args.aggregate_only:
        summary["misses"] = len(summary["misses"])
    (latest if summary["complete"] else partial).write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "misses"}, indent=2))
    if not summary["complete"]:
        print(f"{summary['status']}: no final scoreboard; --resume continues a partial run.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--seed", type=int, default=0)
    gen.add_argument("--out", type=Path, default=GRID)
    go = sub.add_parser("run")
    go.add_argument("--repeat", type=int, default=3)
    go.add_argument("--grid", type=Path, default=GRID)
    go.add_argument("--limit", type=int, default=0)
    go.add_argument("--batch", type=int, default=0, help="run at most N pending trials")
    go.add_argument("--workers", type=int, default=6)
    go.add_argument("--tag", default="", help="suffix for the log and scoreboards (sealed grids)")
    go.add_argument("--resume", action="store_true", help="continue the trials log of this grid")
    go.add_argument(
        "--aggregate-only", action="store_true", help="no per-cell misses (sealed grid)"
    )
    args = parser.parse_args()
    if args.command == "generate":
        args.out.write_text(dump_toml(generate(args.seed)), encoding="utf-8")
        print(f"wrote {args.out}")
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
