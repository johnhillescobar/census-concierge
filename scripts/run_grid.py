#!/usr/bin/env python3
"""Score the multi-parent wildcard phrasing grid (CC-103) through POST /ask.

    python scripts/run_grid.py --repeat 3 [--limit N]

A cell passes when the fetched URLs cover one distinct parent per expected parent
at the cell's level. Aggregates only; needs OPENAI_API_KEY and
CENSUS_API_KEY. Appends each trial to evidence/grid-trials.jsonl (resumable) and
writes evidence/grid-latest.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
GRID = ROOT / "evals" / "cc103_phrasing_grid.toml"
OUT = ROOT / "evidence" / "grid-latest.json"
LOG = ROOT / "evidence" / "grid-trials.jsonl"
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "api"))

from src.geo_list import STATES  # noqa: E402


def cell_passes(cell: dict[str, Any], body: dict[str, Any]) -> bool:
    """One wildcard URL per expected parent: right level, a non-empty `in`, all distinct."""
    urls = [str(url) for url in body.get("urls") or []]
    parents: set[str] = set()
    for url in urls:
        query = parse_qs(urlparse(url).query)
        level, _, code = query.get("for", [""])[0].partition(":")
        if level != cell["level"] or code != "*" or not query.get("in", [""])[0]:
            return False
        parents.add(query["in"][0])
    if not (body.get("rows") and len(urls) == len(parents) == len(cell["expected_parents"])):
        return False
    if cell["level"] != "county":
        return True
    fips = {name.casefold(): code for name, _usps, code in STATES}
    return parents == {f"state:{fips.get(str(p).casefold())}" for p in cell["expected_parents"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--grid", type=Path, default=GRID, help="TOML file of cells")
    parser.add_argument("--tag", default="", help="suffix for the log and summary files")
    parser.add_argument("--level", choices=["county", "tract"], help="only cells of this level")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--batch", type=int, default=0, help="run at most N pending trials and resume across calls"
    )
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    log = LOG.with_stem(LOG.stem + args.tag)
    out = OUT.with_stem(OUT.stem + args.tag)
    if not args.batch:
        log.unlink(missing_ok=True)
    with args.grid.open("rb") as handle:
        cells = tomllib.load(handle)["cell"]
    if args.level:
        cells = [c for c in cells if c["level"] == args.level]
    if args.limit:
        cells = cells[: args.limit]

    from fastapi.testclient import TestClient
    from src.main import app

    def trial(job: tuple[int, dict[str, Any]]) -> dict[str, Any]:
        round_id, cell = job
        status, crashed, error = 0, "", ""
        try:
            with TestClient(app) as client:
                response = client.post("/ask", json={"question": cell["question"]})
            status = response.status_code
            body = response.json() if status == 200 else {}
            body = body if isinstance(body, dict) else {}
        except Exception as exc:  # noqa: BLE001 - one crashed ask is a miss, not an aborted run
            body, crashed, error = {}, type(exc).__name__, str(exc)[:200]
        ok = cell_passes(cell, body)
        mark = "ok" if ok else "MISS"
        print(f"{mark}  {cell['id']} r{round_id}  {cell['question']}", flush=True)
        got = [str(u).split("?")[-1][-40:] for u in body.get("urls") or []][:6]
        warnings = [str(w.get("code")) for w in body.get("warnings") or [] if isinstance(w, dict)]
        return {
            "id": cell["id"],
            "repeat": round_id,
            "passed": ok,
            "got": got,
            "status": status,
            "crashed": crashed,
            "error": error,
            "warnings": warnings,
        }

    done = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    seen = {(row["id"], row["repeat"]) for row in done}
    jobs = [
        (r, cell)
        for r in range(1, args.repeat + 1)
        for cell in cells
        if (cell["id"], r) not in seen
    ][: args.batch or None]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(trial, jobs):
            with log.open("a") as handle:
                handle.write(json.dumps(row) + chr(10))
    ids = {cell["id"] for cell in cells}
    rows = (json.loads(line) for line in log.read_text().splitlines())
    results = [r for r in rows if r["id"] in ids and r["repeat"] <= args.repeat]
    if not results:
        print("No trials recorded.", file=sys.stderr)
        return 1

    by: dict[str, list[bool]] = defaultdict(list)
    for key in ("verb", "connector", "parent_count", "level"):
        for cell in cells:
            for row in (r for r in results if r["id"] == cell["id"]):
                by[f"{key}={cell[key]}"].append(row["passed"])
    summary = {
        "cells": len(cells),
        "repeat": args.repeat,
        "trials": len(results),
        "expected_trials": len(cells) * args.repeat,
        "complete": len(results) == len(cells) * args.repeat,
        "pass_rate": round(sum(r["passed"] for r in results) / len(results), 3),
        "by_dimension": {k: round(sum(v) / len(v), 3) for k, v in sorted(by.items())},
        "misses": [r for r in results if not r["passed"]],
    }
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "misses"}, indent=2))
    if not summary["complete"]:
        done, total = summary["trials"], summary["expected_trials"]
        print(f"PARTIAL: {done} of {total} trials. Rerun the same command to continue.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
