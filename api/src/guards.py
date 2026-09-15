"""Slice-1 guards: pure functions over the execution record.

Evaluated once, at assemble time. None of them blocks — DESIGN.md §4.
"""

from __future__ import annotations

import math
import re
from typing import Protocol

from src.contract import Alternative, AskWarning

_ACS5_SPAN = 5
_RANGE = re.compile(r"\b((?:19|20)\d{2})\s*[-–]\s*((?:19|20)\d{2})\b")
_COMPARE = re.compile(
    r"\b(?:higher|lower|compare[d]?|versus|difference|ranked?|worst|best)\b|"
    r"\bvs\.?\b",
    re.IGNORECASE,
)
_UNIVERSES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("households", ("households", "household")),
    ("families", ("families", "family")),
    ("population", ("population",)),
    ("housing units", ("housing units", "housing unit")),
)
_MISSING = {
    None,
    "",
    "-999999999",
    "-888888888",
    "-666666666",
    "-555555555",
    "-333333333",
    "-222222222",
}
MOE_COMBINE_FORMULA = "sqrt(sum(MOE_i^2))"
_BRACKET_TABLE = "B19001"
_DEGRADED_AFTER = 5
_COMBINE = re.compile(
    r"\bcombined\b|\baggregat(?:e|ed|ion|ing)\b|"
    r"\bacross every\b|\bacross these\b|"
    r"\btotal\b.{0,80}\bacross\b|\bacross\b.{0,80}\btotal\b",
    re.IGNORECASE,
)


class GuardRecord(Protocol):
    question: str
    vintages: list[tuple[str, int]]
    geo_status: dict[str, str | bool] | None
    geographies: list[dict[str, str]]
    rows: list[dict[str, str | None]]
    table_id: str


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
    # Leftover last-fetch rows are not a vintage pair. Slice 3 keeps series.
    if overlapping_vintage(record) is not None:
        return None
    if not _COMPARE.search(record.question) or len(record.rows) < 2:
        return None
    keys = [key for key in record.rows[0] if key.endswith("E") and "_" in key]
    for estimate in keys:
        margin = f"{estimate[:-1]}M"
        for i, left in enumerate(record.rows):
            for right in record.rows[i + 1 :]:
                e1, e2 = _numeric(left, estimate), _numeric(right, estimate)
                m1, m2 = _numeric(left, margin), _numeric(right, margin)
                if e1 is None or e2 is None or m1 is None or m2 is None:
                    continue
                if abs(e1 - e2) <= math.sqrt(m1 * m1 + m2 * m2):
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
    listing = "; ".join(names)
    return AskWarning(
        code="ambiguous_place",
        detail=f"{len(names)} matching geographies: {listing}",
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


def _wants_combination(question: str) -> bool:
    return _COMBINE.search(question) is not None


def _median_measure(record: GuardRecord) -> bool:
    if re.search(r"\bmedian\b", record.question, re.IGNORECASE):
        return True
    table_id = getattr(record, "table_id", "") or ""
    for hit in getattr(record, "pool", []) or []:
        if not isinstance(hit, dict):
            continue
        if table_id and str(hit.get("table_id") or "") != table_id:
            continue
        if "median" in str(hit.get("title") or "").casefold():
            return True
    return False


def _format_number(value: float) -> str:
    rounded = round(value)
    if math.isclose(value, rounded, abs_tol=1e-9):
        return str(rounded)
    return f"{value:.10g}"


def combine_additive(rows: list[dict[str, str | None]]) -> tuple[int, dict[str, str | None] | None]:
    """Sum additive estimates; RSS the matching MOEs. Sentinels are dropped, not zero."""
    estimate_keys: list[str] = []
    for row in rows:
        for key in row:
            if key.endswith("E") and "_" in key and key not in estimate_keys:
                estimate_keys.append(key)
    combined: dict[str, str | None] = {}
    contributing: set[int] = set()
    for estimate in estimate_keys:
        margin = f"{estimate[:-1]}M"
        pairs: list[tuple[float, float, int]] = []
        for index, row in enumerate(rows):
            value, error = _numeric(row, estimate), _numeric(row, margin)
            if value is None or error is None:
                continue
            pairs.append((value, error, index))
        if len(pairs) < 2:
            continue
        for _value, _error, index in pairs:
            contributing.add(index)
        combined[estimate] = _format_number(sum(value for value, _error, _index in pairs))
        combined[margin] = _format_number(
            math.sqrt(sum(error * error for _value, error, _index in pairs))
        )
    count = len(contributing)
    if count < 2 or not combined:
        return count, None
    combined["NAME"] = f"combined ({count} areas)"
    combined["MOE_formula"] = MOE_COMBINE_FORMULA
    combined["component_count"] = str(count)
    return count, combined


def median_not_aggregatable(record: GuardRecord) -> AskWarning | None:
    if not _wants_combination(record.question) or not _median_measure(record):
        return None
    return AskWarning(
        code="median_not_aggregatable",
        detail="published medians cannot be averaged or population-weighted; "
        "B19001 household income brackets summed across areas approximate a combined median",
    )


def moe_aggregation_degraded(record: GuardRecord) -> AskWarning | None:
    if not _wants_combination(record.question) or _median_measure(record):
        return None
    count, combined = combine_additive(record.rows)
    if combined is None or count <= _DEGRADED_AFTER:
        return None
    return AskWarning(
        code="moe_aggregation_degraded",
        detail=(
            f"combined MOE uses {MOE_COMBINE_FORMULA} over {count} component areas; "
            "the approximation degrades past a handful of areas"
        ),
    )


def finish_aggregation(
    record: GuardRecord,
    rows: list[dict[str, str | None]],
    already: set[str],
) -> tuple[list[AskWarning], list[dict[str, str | None]], list[Alternative]]:
    warnings = evaluate(record)
    extra: list[Alternative] = []
    if any(item.code == "median_not_aggregatable" for item in warnings):
        if _BRACKET_TABLE not in already:
            extra.append(Alternative(table_id=_BRACKET_TABLE, reason="distribution versus median"))
        return warnings, rows, extra
    if not _wants_combination(record.question):
        return warnings, rows, extra
    _count, combined = combine_additive(rows)
    if combined is None:
        return warnings, rows, extra
    return warnings, [*rows, combined], extra


def evaluate(record: GuardRecord) -> list[AskWarning]:
    warnings: list[AskWarning] = []
    for guard in (
        overlapping_vintage,
        moe_not_significant,
        geography_unsupported,
        ambiguous_place,
        universe_mismatch,
        median_not_aggregatable,
        moe_aggregation_degraded,
    ):
        warning = guard(record)
        if warning is not None:
            warnings.append(warning)
    return warnings
