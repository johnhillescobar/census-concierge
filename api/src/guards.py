"""Slice-1 guards: pure functions over the execution record.

Evaluated once, at assemble time. None of them blocks — DESIGN.md §4.
"""

from __future__ import annotations

import math
import re
from typing import Protocol

from src.contract import AskWarning

_ACS5_SPAN = 5
_RANGE = re.compile(r"\b((?:19|20)\d{2})\s*[-–]\s*((?:19|20)\d{2})\b")
_COMPARE = re.compile(
    r"\b(?:higher|lower|compare[d]?|versus|difference|ranked?|worst|best)\b|"
    r"\bvs\.?\b|\bmore than\b|\bless than\b",
    re.IGNORECASE,
)
_UNIVERSES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("households", ("households", "household")),
    ("families", ("families", "family")),
    ("population", ("population",)),
    ("housing units", ("housing units", "housing unit")),
)
_MISSING = {None, "", "-999999999", "-888888888", "-666666666", "-222222222"}


class GuardRecord(Protocol):
    question: str
    vintages: list[tuple[str, int]]
    geo_status: dict[str, str | bool] | None
    geographies: list[dict[str, str]]
    rows: list[dict[str, str | None]]


def _acs5_end_years(question: str) -> list[int]:
    years: list[int] = []
    for start_text, end_text in _RANGE.findall(question):
        start, end = int(start_text), int(end_text)
        if end - start == _ACS5_SPAN - 1:
            years.append(end)
    return years


def _overlaps(years: list[int]) -> bool:
    ordered = sorted(set(years))
    return any(b - a < _ACS5_SPAN for a, b in zip(ordered, ordered[1:], strict=False))


def overlapping_vintage(record: GuardRecord) -> AskWarning | None:
    years = _acs5_end_years(record.question)
    years.extend(year for dataset, year in record.vintages if dataset == "acs5")
    if not _overlaps(years):
        return None
    labeled = ", ".join(str(year) for year in sorted(set(years)))
    return AskWarning(
        code="overlapping_vintage",
        detail=f"ACS5 vintages {labeled} share sample years and are not comparable",
    )


def _numeric(row: dict[str, str | None], key: str) -> float | None:
    raw = row.get(key)
    if not isinstance(raw, str) or raw in _MISSING:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def moe_not_significant(record: GuardRecord) -> AskWarning | None:
    if not _COMPARE.search(record.question) or len(record.rows) < 2:
        return None
    keys = [key for key in record.rows[0] if key.endswith("E") and "_" in key]
    if not keys:
        return None
    estimate = keys[0]
    margin = f"{estimate[:-1]}M"
    for i, left in enumerate(record.rows):
        for right in record.rows[i + 1 :]:
            e1, e2 = _numeric(left, estimate), _numeric(right, estimate)
            m1, m2 = _numeric(left, margin), _numeric(right, margin)
            if e1 is None or e2 is None or m1 is None or m2 is None:
                continue
            diff = abs(e1 - e2)
            se = math.sqrt(m1 * m1 + m2 * m2)
            if diff <= se:
                return AskWarning(
                    code="moe_not_significant",
                    detail="difference is within the 90% margin of error "
                    "and is not distinguishable",
                )
    return None


def geography_unsupported(record: GuardRecord) -> AskWarning | None:
    status = record.geo_status
    if not status or status.get("legal") is not False:
        return None
    detail = str(status.get("detail") or "").strip()
    return AskWarning(
        code="geography_unsupported",
        detail=detail or "requested geography is not a legal combination for this dataset",
    )


def ambiguous_place(record: GuardRecord) -> AskWarning | None:
    matches = record.geographies
    if len(matches) <= 1:
        return None
    names = [
        str(row.get("name") or f"{row.get('for', '')} {row.get('in', '')}".strip())
        for row in matches
    ]
    listing = "; ".join(names[:12])
    extra = f" (+{len(names) - 12} more)" if len(names) > 12 else ""
    return AskWarning(
        code="ambiguous_place",
        detail=f"{len(names)} matching geographies: {listing}{extra}",
    )


def _named_universes(text: str) -> list[str]:
    folded = text.casefold()
    found: list[str] = []
    for label, needles in _UNIVERSES:
        if any(re.search(rf"\b{re.escape(needle)}\b", folded) for needle in needles):
            found.append(label)
    return found


def universe_mismatch(record: GuardRecord) -> AskWarning | None:
    named = _named_universes(record.question)
    if len(named) < 2:
        return None
    return AskWarning(
        code="universe_mismatch",
        detail=f"question crosses universes: {' × '.join(named)}",
    )


def evaluate(record: GuardRecord) -> list[AskWarning]:
    warnings: list[AskWarning] = []
    for guard in (
        overlapping_vintage,
        moe_not_significant,
        geography_unsupported,
        ambiguous_place,
        universe_mismatch,
    ):
        warning = guard(record)
        if warning is not None:
            warnings.append(warning)
    return warnings
