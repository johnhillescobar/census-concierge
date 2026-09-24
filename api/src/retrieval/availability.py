"""Which tables and variables exist in which vintage, and under what universe."""

from __future__ import annotations

import gzip
import json
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha1
from pathlib import Path
from typing import Any

from . import metadata
from .text import strip_vintage

REASON_VARIABLE = "variable_not_in_vintage"
_HOUSEHOLD = frozenset({"", "hshld", "household", "households"})
TableFacts = Callable[[str, int, str], dict[str, Any] | None]

ARTIFACT = metadata.ROOT / "index_store" / "availability.json.gz"


def build() -> dict[str, Any]:
    """Join cached metadata into one `(dataset, vintage, table) -> facts` map."""
    datasets: dict[str, dict[str, dict[str, Any]]] = {}
    for dataset in metadata.DATASETS:
        for year in metadata.cached_vintages(dataset):
            tables = metadata.tables(dataset, year)
            by_table: dict[str, list[str]] = defaultdict(list)
            labels: dict[str, list[tuple[str, str]]] = defaultdict(list)
            for variable in metadata.variables(dataset, year).values():
                prefix = f"{variable.table_id}_"
                suffix = variable.variable_id.removeprefix(prefix)
                by_table[variable.table_id].append(suffix)
                labels[variable.table_id].append((suffix, variable.label))

            datasets.setdefault(dataset, {})[str(year)] = {
                table_id: {
                    "title": table.title,
                    "universe": table.universe,
                    "variables": sorted(by_table.get(table_id, [])),
                    "label_sig": _label_sig(labels.get(table_id, [])),
                }
                for table_id, table in sorted(tables.items())
            }
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "datasets": datasets,
    }


def union_tables(matrix: dict[str, Any]) -> dict[str, metadata.Table]:
    """Every table that ever existed, described by its most recent vintage."""
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


def _universe(raw: str) -> str:
    folded = raw.strip().casefold()
    return "households" if folded in _HOUSEHOLD else folded


def _label_sig(pairs: list[tuple[str, str]]) -> str:
    blob = "\n".join(
        f"{suffix}\t{strip_vintage(label).casefold()}" for suffix, label in sorted(pairs)
    )
    return sha1(blob.encode()).hexdigest()[:16]


def same_definition(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """True when title/universe/label differences are encoding, not a redefinition."""
    left_sig, right_sig = str(left.get("label_sig") or ""), str(right.get("label_sig") or "")
    if left_sig and right_sig and left_sig != right_sig:
        return False
    return (
        _universe(str(left.get("universe") or "")) == _universe(str(right.get("universe") or ""))
        and strip_vintage(str(left.get("title") or "")).casefold()
        == strip_vintage(str(right.get("title") or "")).casefold()
    )


def _estimate_suffixes(suffixes: list[str]) -> set[str]:
    return {item[:-1] + "E" if item.endswith("M") else item for item in suffixes}


def _required_suffixes(suffixes: list[str], reference_vars: set[str]) -> set[str]:
    """E always; matching M only when the reference vintage lists margins."""
    needed = _estimate_suffixes(suffixes)
    if not suffixes or not any(item.endswith("M") for item in reference_vars):
        return needed
    return needed | {item[:-1] + "M" for item in needed if item.endswith("E")}


def drop_incompatible(
    lookup: TableFacts,
    dataset: str,
    years: list[int],
    table_id: str,
    suffixes: list[str],
) -> tuple[list[int], list[int], list[str]]:
    """Keep years whose table, E/M suffixes, and definition match the latest usable year."""
    facts_by_year = {year: lookup(dataset, year, table_id) for year in years}
    estimates = _estimate_suffixes(suffixes)
    usable = [
        year
        for year in years
        if (facts := facts_by_year[year]) is not None
        and (not estimates or estimates <= set(facts.get("variables") or []))
    ]
    reference = facts_by_year[max(usable)] if usable else None
    required = _required_suffixes(suffixes, set((reference or {}).get("variables") or []))
    kept: list[int] = []
    omitted: list[int] = []
    reasons: list[str] = []
    published: set[str]
    for year in years:
        facts = facts_by_year[year]
        published = set((facts or {}).get("variables") or [])
        if (
            facts is None
            or (required and not required <= published)
            or (reference is not None and not same_definition(facts, reference))
        ):
            omitted.append(year)
            reasons.append(REASON_VARIABLE)
            continue
        kept.append(year)
    return kept, omitted, reasons


def introduction_omissions(
    lookup: TableFacts,
    dataset: str,
    unpublished: list[int],
    table_id: str,
    requested: list[int],
    published: dict[str, set[int]] | None,
) -> list[int]:
    """Unpublished years before a mid-range table introduction are not a silent join."""
    if not unpublished or not published or not requested or not table_id:
        return []
    lo, hi = min(requested), max(requested)
    if not _published_hole(lookup, table_id, published, lo, hi):
        return []
    present = [
        year
        for year in published.get(dataset, ())
        if lo <= year <= hi and lookup(dataset, year, table_id) is not None
    ]
    first = min(present) if present else None
    if first is None:
        return list(unpublished)
    return [year for year in unpublished if year < first]


def _published_hole(
    lookup: TableFacts,
    table_id: str,
    published: dict[str, set[int]],
    lo: int,
    hi: int,
) -> bool:
    for dataset, years in published.items():
        span = [year for year in years if lo <= year <= hi]
        if not span:
            continue
        flags = [lookup(dataset, year, table_id) is not None for year in span]
        if any(flags) and not all(flags):
            return True
    return False
