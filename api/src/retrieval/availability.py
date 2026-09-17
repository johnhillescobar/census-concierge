"""Which tables and variables exist in which vintage, and under what universe.

A lookup, not a search. The semantic index is deliberately vintage-agnostic —
a discontinued table must stay findable — so this is where the "does it exist
in 2019?" question is answered. Slice 3's guards join on it rather than asking
the model to remember: `vintage_gap_2020` and the universe half of
`universe_mismatch` are reads from this file.

Variable IDs are stored as suffixes under their table (`B01003` + `001E`),
which drops the table prefix from roughly half a million strings.
"""

from __future__ import annotations

import gzip
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import metadata

ARTIFACT = metadata.ROOT / "index_store" / "availability.json.gz"


def build() -> dict[str, Any]:
    """Join cached metadata into one `(dataset, vintage, table) -> facts` map."""
    datasets: dict[str, dict[str, dict[str, Any]]] = {}
    for dataset in metadata.DATASETS:
        for year in metadata.cached_vintages(dataset):
            tables = metadata.tables(dataset, year)
            by_table: dict[str, list[str]] = defaultdict(list)
            for variable in metadata.variables(dataset, year).values():
                prefix = f"{variable.table_id}_"
                by_table[variable.table_id].append(variable.variable_id.removeprefix(prefix))

            datasets.setdefault(dataset, {})[str(year)] = {
                table_id: {
                    "title": table.title,
                    "universe": table.universe,
                    "variables": sorted(by_table.get(table_id, [])),
                }
                for table_id, table in sorted(tables.items())
            }
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "datasets": datasets,
    }


def union_tables(matrix: dict[str, Any]) -> dict[str, metadata.Table]:
    """Every table that ever existed, described by its most recent vintage.

    The union is the point: a table dropped after 2019 is still the right answer
    to a question about 2018, so it has to be in the semantic index. Taking the
    newest description keeps titles current for everything still published.
    """
    latest: dict[str, tuple[int, metadata.Table]] = {}
    for vintages in matrix["datasets"].values():
        for year_text, tables in vintages.items():
            year = int(year_text)
            for table_id, facts in tables.items():
                if table_id in latest and latest[table_id][0] >= year:
                    continue
                latest[table_id] = (
                    year,
                    metadata.Table(
                        table_id=table_id,
                        title=facts["title"],
                        universe=facts["universe"],
                    ),
                )
    return {table_id: table for table_id, (_, table) in sorted(latest.items())}


def write(matrix: dict[str, Any], path: Path = ARTIFACT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(matrix, handle)
    return path


def load(path: Path = ARTIFACT) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        matrix: dict[str, Any] = json.load(handle)
    return matrix
