"""Slice-1 guards: pure functions over the execution record.

Evaluated once, at assemble time. None of them blocks — DESIGN.md §4.
"""

from __future__ import annotations

import math
import re
from typing import Protocol

from src.contract import Alternative, AskWarning, GeoSpec

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
    r"\baggregat(?:e|ed|ion|ing)\b|"
    r"\bacross every\b|\bacross these\b|"
    r"\btotal\b.{0,80}\bacross\b|\bacross\b.{0,80}\btotal\b|"
    r"\bcombin(?:e|ed|ing)\b(?!\s+statistical\s+area)",
    re.IGNORECASE,
)
_DERIVED = re.compile(
    r"\b(?:mean|average|percent(?:age)?|rate|share|ratio|"
    r"index(?:es)?|densit(?:y|ies)|per[\s-]?capita)\b",
    re.IGNORECASE,
)
_ZIP = re.compile(r"\bzip codes?\b(?!\s+tabulation)|\bzip\b(?!\s+code)", re.IGNORECASE)
_ZCTA_CODE = re.compile(r"\b(\d{5})\b")


class GuardRecord(Protocol):
    question: str
    vintages: list[tuple[str, int]]
    geo_status: dict[str, str | bool] | None
    geographies: list[GeoSpec]
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


def acs1_geography_ineligible(record: GuardRecord) -> AskWarning | None:
    artifact = getattr(record, "fetch", None)
    if not getattr(artifact, "acs1_ineligible", False):
        return None
    return AskWarning(
        code="acs1_geography_ineligible",
        detail=(
            "ACS1 is not published for this geography (places of 65,000+); "
            "non-overlapping ACS5 end years are returned instead"
        ),
    )


def vintage_gap_2020(record: GuardRecord) -> AskWarning | None:
    artifact = getattr(record, "fetch", None)
    reasons = list(getattr(artifact, "omission_reasons", []) or [])
    years = list(getattr(artifact, "attempted_years", []) or [])
    dataset = str(getattr(artifact, "dataset", "") or "")
    if "vintage_gap_2020" not in reasons:
        if dataset != "acs1" or not years:
            return None
        if not (min(years) <= 2020 <= max(years) and 2020 not in years):
            return None
    return AskWarning(
        code="vintage_gap_2020",
        detail="the standard 2020 ACS1 release was never issued; 2020 is a gap, not interpolated",
    )


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
    if not status or status.get("legal") is not False or status.get("nested") is False:
        return None
    detail = str(status.get("detail") or "").strip()
    return AskWarning(
        code="geography_unsupported",
        detail=detail or "requested geography is not a legal combination for this dataset",
    )


def zcta_not_zip(record: GuardRecord) -> AskWarning | None:
    if not _ZIP.search(record.question):
        return None
    match = _ZCTA_CODE.search(record.question)
    code = match.group(1) if match else ""
    named = f"ZIP {code} / ZCTA {code}" if code else "ZIP / ZCTA"
    return AskWarning(
        code="zcta_not_zip",
        detail=(
            f"{named} is a USPS delivery route versus a block-built Census approximation "
            "(~10% of ZIPs have no ZCTA); ZCTAs nest in nothing, ACS1 does not publish them, "
            "and 2020 ZCTA definitions differ from 2010"
        ),
    )


def geography_not_nested(record: GuardRecord) -> AskWarning | None:
    status = record.geo_status
    if not status or status.get("nested") is not False:
        return None
    detail = str(status.get("detail") or "").strip()
    if not detail:
        detail = "requested containment is not expressible in Census for/in grammar"
    return AskWarning(
        code="geography_not_nested",
        detail=(
            f"{detail}; splitting it needs block-level areal allocation, which is out of scope"
        ),
    )


def ambiguous_place(record: GuardRecord) -> AskWarning | None:
    matches = record.geographies
    if len(matches) <= 1:
        return None
    names = [row.name or f"{row.for_spec} {row.in_spec}".strip() for row in matches]
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


def _selected_title(record: GuardRecord) -> str:
    table_id = getattr(record, "table_id", "") or ""
    member_title = ""
    for hit in getattr(record, "pool", []) or []:
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title") or "")
        if str(hit.get("table_id") or "") == table_id:
            return title
        if table_id in {str(member) for member in (hit.get("members") or [])}:
            member_title = title
    return member_title


def _median_measure(record: GuardRecord) -> bool:
    if re.search(r"\bmedian\b", record.question, re.IGNORECASE):
        return True
    return "median" in _selected_title(record).casefold()


def _additive_measure(record: GuardRecord) -> bool:
    if _median_measure(record):
        return False
    if _DERIVED.search(record.question):
        return False
    return _DERIVED.search(_selected_title(record)) is None


def _format_number(value: float) -> str:
    rounded = round(value)
    if math.isclose(value, rounded, abs_tol=1e-9):
        return str(rounded)
    return f"{value:.10g}"


def _year_key(row: dict[str, str | None]) -> str:
    return str(row.get("year") or "")


def _area_id(row: dict[str, str | None], index: int) -> str:
    return str(row.get("GEO_ID") or "") or f"#{index}"


def _combine_group(
    rows: list[dict[str, str | None]],
) -> tuple[int, dict[str, str | None] | None]:
    estimate_keys: list[str] = []
    for row in rows:
        for key in row:
            if key.endswith("E") and "_" in key and key not in estimate_keys:
                estimate_keys.append(key)
    combined: dict[str, str | None] = {}
    contributing: set[str] = set()
    pair_counts: list[int] = []
    for estimate in estimate_keys:
        margin = f"{estimate[:-1]}M"
        pairs: list[tuple[float, float, str]] = []
        for index, row in enumerate(rows):
            value, error = _numeric(row, estimate), _numeric(row, margin)
            if value is None or error is None:
                continue
            pairs.append((value, error, _area_id(row, index)))
        if len(pairs) < 2:
            continue
        pair_counts.append(len(pairs))
        for _value, _error, area in pairs:
            contributing.add(area)
        combined[estimate] = _format_number(sum(value for value, _error, _area in pairs))
        combined[margin] = _format_number(
            math.sqrt(sum(error * error for _value, error, _area in pairs))
        )
    count = len(contributing)
    if count < 2 or not combined or any(n != count for n in pair_counts):
        return count, None
    combined["GEO_ID"] = ""
    combined["NAME"] = f"combined ({count} areas)"
    combined["MOE_formula"] = MOE_COMBINE_FORMULA
    combined["component_count"] = str(count)
    return count, combined


def combine_additive(
    rows: list[dict[str, str | None]],
) -> tuple[int, list[dict[str, str | None]]]:
    """Sum additive estimates within a vintage; RSS the matching MOEs.

    Year-tagged series rows are separate vintages, not extra areas. Sentinels
    are dropped, not treated as zero.
    """
    groups: dict[str, list[dict[str, str | None]]] = {}
    order: list[str] = []
    for row in rows:
        key = _year_key(row)
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(row)
    combined_rows: list[dict[str, str | None]] = []
    max_count = 0
    for key in order:
        count, combined = _combine_group(groups[key])
        max_count = max(max_count, count)
        if combined is None:
            continue
        if key:
            combined["year"] = key
        combined_rows.append(combined)
    return max_count, combined_rows


def _household_income_median(record: GuardRecord) -> bool:
    return (getattr(record, "table_id", "") or "") == "B19013"


def median_not_aggregatable(record: GuardRecord) -> AskWarning | None:
    if not _wants_combination(record.question) or not _median_measure(record):
        return None
    detail = "published medians cannot be averaged or population-weighted"
    if _household_income_median(record):
        detail += (
            "; B19001 household income brackets summed across areas approximate a combined median"
        )
    return AskWarning(code="median_not_aggregatable", detail=detail)


def moe_aggregation_degraded(record: GuardRecord) -> AskWarning | None:
    if not _wants_combination(record.question) or not _additive_measure(record):
        return None
    count, combined_rows = combine_additive(record.rows)
    if not combined_rows or count <= _DEGRADED_AFTER:
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
        if _household_income_median(record) and _BRACKET_TABLE not in already:
            extra.append(Alternative(table_id=_BRACKET_TABLE, reason="distribution versus median"))
        return warnings, rows, extra
    if not _wants_combination(record.question) or not _additive_measure(record):
        return warnings, rows, extra
    _count, combined_rows = combine_additive(rows)
    if not combined_rows:
        return warnings, rows, extra
    return warnings, [*rows, *combined_rows], extra


def evaluate(record: GuardRecord) -> list[AskWarning]:
    warnings: list[AskWarning] = []
    for guard in (
        overlapping_vintage,
        acs1_geography_ineligible,
        vintage_gap_2020,
        moe_not_significant,
        geography_unsupported,
        ambiguous_place,
        universe_mismatch,
        median_not_aggregatable,
        moe_aggregation_degraded,
        zcta_not_zip,
        geography_not_nested,
    ):
        warning = guard(record)
        if warning is not None:
            warnings.append(warning)
    return warnings
