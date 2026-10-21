"""The figures an answer states: rendered by code from the rows; the model's text is checked.

The model writes framing only. Every number it still writes must be one the response itself
carries; a text with any other number is dropped and the rendered figures stand alone.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from src.retrieval import metadata
from src.vintages import CENSUS_MISSING

MAX_FIGURES = 20
NO_FIGURES = "No figures were fetched for this request; see the warnings and the URL."
_YEARS = ("requested_years", "attempted_years", "succeeded_years", "failed_years", "omitted_years")
_BREAKS = str.maketrans("-–—/|", "     ")
_EDGE = ".,;:!?()[]{}\"'*_`~<>=+$%"


def _cells(
    rows: list[dict[str, str | None]],
) -> tuple[list[tuple[dict[str, str | None], str, str]], int]:
    """The first MAX_FIGURES estimate cells as (row, variable, year), and how many there are."""
    found = [
        (row, key, str(row.get("year") or ""))
        for row in rows
        for key in row
        if key.endswith("E") and "_" in key
    ]
    return found[:MAX_FIGURES], len(found)


def _labels(dataset: str, year: int, wanted: set[str]) -> dict[str, str]:
    try:
        found = metadata.variables(dataset, year)
    except Exception:  # noqa: BLE001 - a label lookup must never fail a fetch that succeeded
        return {}
    return {
        key: found[key].label.removeprefix("Estimate!!").replace("!!", " - ")
        for key in wanted & found.keys()
    }


async def labels_for(rows: list[dict[str, str | None]], dataset: str) -> dict[str, dict[str, str]]:
    """Variable labels for the figures that will be shown: one lookup per vintage, off the loop."""
    wanted: dict[str, set[str]] = {}
    for _row, key, year in _cells(rows)[0]:
        if year.isdigit():
            wanted.setdefault(year, set()).add(key)
    found = await asyncio.gather(
        *(asyncio.to_thread(_labels, dataset, int(year), keys) for year, keys in wanted.items())
    )
    return dict(zip(wanted, found, strict=True))


def _numbers(text: str) -> list[float]:
    """Every token that holds a digit and that float() reads: commas, $ and % stripped."""
    found = []
    for token in text.translate(_BREAKS).split():
        token = token.strip(_EDGE).replace(",", "")
        if any(char.isdigit() for char in token):
            with contextlib.suppress(ValueError):
                found.append(abs(float(token)))
    return found


def _shown(raw: str) -> str:
    whole, dot, fraction = raw.partition(".")
    try:
        return f"{int(whole):,}{dot}{fraction}"
    except ValueError:
        return raw


def _render(rows: list[dict[str, str | None]], record: Any) -> tuple[list[str], list[str]]:
    """The figure sentences, and the texts (labels, titles, universe) they rest on."""
    shown, total = _cells(rows)
    labels = getattr(getattr(record, "fetch", None), "labels", None) or {}
    lines: list[str] = []
    texts: list[str] = []
    for row, key, year in shown:
        est, moe = (
            None if row.get(k) in CENSUS_MISSING else row.get(k) for k in (key, key[:-1] + "M")
        )
        value = (
            f"{_shown(est)} (margin of error {_shown(moe) if moe else 'not published'})"
            if est
            else "not available"
        )
        label = labels.get(year, {}).get(key, key)
        texts.append(label)
        geoid = row.get("GEO_ID")
        place = " ".join(part for part in (row.get("NAME"), f"({geoid})" if geoid else "") if part)
        vintage = " ".join(part for part in (row.get("dataset"), year) if part)
        lines.append(f"{label}: {value}" + "".join(f", {p}" for p in (place, vintage) if p) + ".")
    if total > MAX_FIGURES:
        lines.append(f"{MAX_FIGURES} of {total} figures shown; the table has the rest.")
    table_facts = getattr(record, "table_facts", None)
    table = shown[0][1].split("_")[0] if shown else ""
    about: dict[str, list[str]] = {}
    for dataset, year in dict.fromkeys(
        (str(row.get("dataset") or ""), year) for row, _key, year in shown
    ):
        facts = (
            table_facts(dataset, int(year), table) if table_facts and year.isdigit() else None
        ) or {}
        title, universe = (
            facts.get("title"),
            facts.get("universe") or getattr(record, "universe", ""),
        )
        text = " ".join(
            [
                f"Table {table}: {title}." if title else "",
                f"Universe: {universe}" if universe else "",
            ]
        ).strip()
        if text:
            about.setdefault(text, []).append(year)
    texts += list(about)
    lines += [
        text if len(about) == 1 else f"{', '.join(years)}: {text}" for text, years in about.items()
    ]
    return lines, texts


def _allowed(rows: list[dict[str, str | None]], record: Any, texts: list[str]) -> set[float]:
    """Numbers the response carries: row cells, years asked, the dataset's digits, system texts."""
    allowed: set[float] = set()
    for row in rows:
        for key, cell in row.items():
            if cell in CENSUS_MISSING:
                continue
            text = str(cell).split("US")[-1] if key == "GEO_ID" else str(cell)
            if key == "dataset":
                text = "".join(char if char.isdigit() else " " for char in text)
            allowed.update(_numbers(text))
    fetch = getattr(record, "fetch", None)
    allowed.update(float(year) for name in _YEARS for year in getattr(fetch, name, None) or [])
    allowed.update(number for text in texts for number in _numbers(text))
    return allowed


def checked(prose: str, rows: list[dict[str, str | None]], record: Any) -> tuple[str, str]:
    """The answer to show, and why the model's text was dropped ("" when it was kept).

    The answer is the model's framing followed by the rendered figures. A framing that states
    a number the response does not carry is replaced by the rendered figures alone.
    """
    lines, texts = _render(rows, record)
    if not lines and not _numbers(prose):
        return prose, ""
    allowed = _allowed(rows, record, [*texts, *lines])
    stray = sorted({number for number in _numbers(prose) if number not in allowed})
    problem = ""
    if stray:
        listed = ", ".join(f"{number:,.10g}" for number in stray[:5])
        problem = (
            f"The model's text stated {listed}, not in the fetched data; figures below replace it."
        )
        prose = ""
    return "\n\n".join(
        part for part in (prose.strip(), "\n".join(lines)) if part
    ) or NO_FIGURES, problem
