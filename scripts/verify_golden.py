#!/usr/bin/env python3
"""Check every `expect_table` and `expect_geo_level` against real ACS metadata.

    python scripts/verify_golden.py

A wrong fixture is worse than no fixture: it trains you to "fix" correct
behaviour. This is the ten-line version of an hour in a browser. It cannot tell
you a table is the *right* answer to the question — only that it exists, and
what its title and universe actually say. Read those.

Exits non-zero if any expected table or geography level does not exist.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from src.retrieval import metadata  # noqa: E402

QUESTIONS = ROOT / "evals" / "golden_questions.toml"


def main() -> int:
    universe: dict[str, metadata.Table] = {}
    levels: set[str] = set()
    for dataset in metadata.DATASETS:
        for year in metadata.cached_vintages(dataset):
            universe.update(metadata.tables(dataset, year))
            levels.update(metadata.geo_levels(dataset, year))
    if not universe:
        print("No cached metadata. Run scripts/fetch_metadata.py first.")
        return 1

    with QUESTIONS.open("rb") as handle:
        questions = tomllib.load(handle)["question"]

    bad = 0
    print(f"\nGOLDEN SET  ({len(universe)} tables, {len(levels)} geography levels)\n")
    for entry in questions:
        table_id = entry.get("expect_table")
        level = entry.get("expect_geo_level")
        problems = []
        if table_id and table_id not in universe:
            problems.append(f"table {table_id} does not exist")
        if level and level not in levels:
            problems.append(f"geography level {level!r} does not exist")

        if problems:
            bad += 1
            print(f"  FAIL  {entry['id']}  {'; '.join(problems)}")
            print(f"        {entry['text']}")
        elif table_id:
            table = universe[table_id]
            print(f"  ok    {entry['id']}  {table_id}  {table.title}")
            print(f"        universe: {table.universe or '(none published)'}")

    print(f"\n{bad} problem(s).\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
