#!/usr/bin/env python3
"""Re-score an existing grid trial log with the county-identity check; no API calls (CC-103).

    python scripts/rescore_grid.py --grid <cells.toml> --log <grid-trials*.jsonl>

A trial keeps its pass only if it also fetched the counties the cell names (see
`tract_identity_ok`). Trials store the end of each URL, which holds the `in` clause. Prints
counts only, never question text or URLs, so it is safe on the sealed grid and its log.
"""

from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path

from run_grid import tract_identity_ok


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    with args.grid.open("rb") as handle:
        cells = {c["id"]: c for c in tomllib.load(handle)["cell"]}
    rows = [json.loads(line) for line in args.log.read_text().splitlines()]
    old = sum(r["passed"] for r in rows)
    flipped = 0
    for row in rows:
        cell = cells[row["id"]]
        if row["passed"] and cell["level"] == "tract":
            ins = [fragment.partition("in=")[2] for fragment in row["got"]]
            flipped += not tract_identity_ok(cell, ins)
    new = old - flipped
    print(f"trials={len(rows)} passed_before={old} passed_after={new} flipped_to_miss={flipped}")


if __name__ == "__main__":
    main()
