"""The figures an answer states: rendered by code from the rows; the model's text is checked.

The model writes framing only. Every number it still writes must be one the response itself
carries; a text with any other number is dropped and the rendered figures stand alone.
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.retrieval import metadata
from src.vintages import CENSUS_MISSING

MAX_FIGURES = 20
NO_FIGURES = "No figures were fetched for this request; see the warnings and the URL."
_YEARS = ("requested_years", "attempted_years", "succeeded_years", "failed_years", "omitted_years")
_BREAKS = str.maketrans("-–—/|", "     ")
_EDGE = ".,;:!?()[]{}\"'*_`~<>=+$%"
_LEAD = _EDGE.replace(".", "")  # a leading "." stays: ".5" is not 5


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
    found.sort(key=lambda cell: "component_count" not in cell[0])  # combined rows first
    return found[:MAX_FIGURES], len(found)


def _labels(dataset: str, year: int, wanted: set[str]) -> dict[str, str]:
    try:
        found = metadata.variables(dataset, year)
    except Exception:  # noqa: BLE001 - a label lookup must never fail a fetch that succeeded
        return {}
    return {
        key: found[key].label.removeprefix("Estimate!!").replace("!!", " - ").rstrip(":")
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


def _numbers(text: str) -> list[float | str]:
    """Every token that holds a digit: its value if float() reads it, else the token itself."""
    found: list[float | str] = []
    for token in text.translate(_BREAKS).split():
        token = token.strip(_LEAD).rstrip(_EDGE)
        if any(char.isnumeric() for char in token):
            try:
                found.append(abs(float(token.replace(",", ""))))
            except ValueError:
                found.append(token.casefold())
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


def _allowed(rows: list[dict[str, str | None]], record: Any, texts: list[str]) -> set[float | str]:
    """What the response carries: cells, keys, years, status codes, dataset digits, system texts."""
    fetch = getattr(record, "fetch", None)
    vintages = getattr(record, "vintages", None) or []
    datasets = {str(row.get("dataset") or "") for row in rows} | {str(name) for name, _ in vintages}
    texts = [*texts, *("".join(c if c.isdigit() else " " for c in name) for name in datasets)]
    pool = getattr(record, "pool", None) or []
    texts += [str(getattr(record, "table_id", "") or ""), *datasets]
    texts += [str(reason) for reason in getattr(fetch, "omission_reasons", None) or []]
    texts += [str(x) for hit in pool for x in [hit.get("table_id"), *(hit.get("members") or [])]]
    for row in rows:
        for key, cell in row.items():
            if cell not in CENSUS_MISSING:
                texts += [str(cell), key, key.split("_")[0]]
                texts += [str(cell).split("US")[-1]] if key == "GEO_ID" else []
    allowed = {number for text in texts for number in _numbers(text)}
    codes = [
        getattr(fetch, "status_code", 0),
        *(x.status_code for x in getattr(fetch, "legs", None) or []),
    ]
    years = [year for name in _YEARS for year in getattr(fetch, name, None) or []]
    built = getattr(getattr(record, "url", None), "year", None)
    allowed.update(float(n) for n in [*codes, *years, *(year for _, year in vintages), built] if n)
    return allowed


def stray(text: str, rows: list[dict[str, str | None]], record: Any) -> list[float | str]:
    """The numbers in the text that the response does not carry."""
    lines, texts = _render(rows, record)
    allowed = _allowed(rows, record, [*texts, *lines])
    return sorted({number for number in _numbers(text) if number not in allowed}, key=str)


def checked(prose: str, rows: list[dict[str, str | None]], record: Any) -> tuple[str, str]:
    """The answer to show, and why the model's text was dropped ("" when it was kept).

    The answer is the model's framing followed by the rendered figures. A framing that states
    a number the response does not carry is replaced by the rendered figures alone.
    """
    lines, _texts = _render(rows, record)
    if not lines and not _numbers(prose):
        return prose, ""
    bad = stray(prose, rows, record)
    problem = ""
    if bad:
        listed = ", ".join(f"{n:,.10g}" if isinstance(n, float) else n for n in bad[:5])
        problem = f"The model's text stated {listed}, not in the fetched data; " + (
            "figures below replace it." if lines else "it was removed."
        )
        prose = ""
    block = "\n".join(lines)
    return "\n\n".join(part for part in (prose.strip(), block) if part) or NO_FIGURES, problem
