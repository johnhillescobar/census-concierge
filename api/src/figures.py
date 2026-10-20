"""What the model is shown of a fetch: its first figures, each read in its own vintage."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.retrieval import metadata
from src.vintages import CENSUS_MISSING

MAX_FIGURES = 20


def _labels(dataset: str, year: int, wanted: set[str]) -> dict[str, str]:
    try:
        found = metadata.variables(dataset, year)
    except Exception:  # noqa: BLE001 - a label lookup must never fail a fetch that succeeded
        return {}
    return {
        key: found[key].label.removeprefix("Estimate!!").replace("!!", " - ")
        for key in wanted & found.keys()
    }


def figure_lines(
    rows: list[dict[str, str | None]], dataset: str, table_facts: Callable[..., Any] | None
) -> str:
    """The first MAX_FIGURES estimates as labelled lines: the only values the model is shown.

    A label, a table title and a universe belong to one vintage ("in 2019 dollars"), so each
    figure takes its own year's.
    """
    keys = [
        (row, key, int(row.get("year") or 0))
        for row in rows
        for key in row
        if key.endswith("E") and "_" in key
    ]
    shown = keys[:MAX_FIGURES]
    table = shown[0][1].split("_")[0] if shown else ""
    years = list(dict.fromkeys(year for _, _, year in shown))
    labels = {year: _labels(dataset, year, {key for _, key, _ in shown}) for year in years}
    lines = []
    for row, key, year in shown:
        est, moe = (None if row.get(k) in CENSUS_MISSING else row[k] for k in (key, f"{key[:-1]}M"))
        value = f"{est} (margin of error {moe or 'not published'})" if est else "not available"
        place = f"{row.get('NAME')} ({row.get('GEO_ID')}) | {dataset} {row.get('year')}"
        lines.append(f"{labels[year].get(key, key)} | {value} | {place}")
    if len(keys) > MAX_FIGURES:
        rest = len(keys) - MAX_FIGURES
        lines.append(f"{MAX_FIGURES} of {len(keys)} figures shown; the other {rest} were fetched.")
    about: dict[str, list[str]] = {}
    for year in years:
        facts = (table_facts(dataset, year, table) if table_facts else None) or {}
        title, universe = facts.get("title"), facts.get("universe")
        text = " ".join(
            [
                f"Table {table}: {title}." if title else "",
                f"Universe: {universe}" if universe else "",
            ]
        ).strip()
        if text:
            about.setdefault(text, []).append(str(year))
    lines += [text if len(about) == 1 else f"{', '.join(ys)}: {text}" for text, ys in about.items()]
    return "\n".join(lines)
