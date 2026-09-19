"""MOE_diff pairing for geography and year comparisons.

Guards warn; AskResponse.comparisons carries the numbers. None of this blocks.
"""

from __future__ import annotations

import math
import re
from typing import Any

from src.contract import AskWarning, Comparison, GeoSpec

_COMPARE = re.compile(
    r"\b(?:higher|lower|compare[d]?|versus|difference|ranked?|worst|best)\b|"
    r"\bvs\.?\b",
    re.IGNORECASE,
)
_TRACT_VS = re.compile(
    r"tracts?\s+(\d{3,4}).{0,80}(?:higher than|lower than|versus|compared to|vs\.?)"
    r"\s+(?:tract\s+)?(\d{3,4})",
    re.I,
)
_COUNTY = re.compile(
    r"\b([A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*)*)\s+count(?:y|ies)\b",
    re.IGNORECASE,
)
_RANK = {
    "block group": 0,
    "tract": 1,
    "place": 2,
    "county": 3,
    "state": 4,
    "us": 5,
}


def moe_diff(left: float, right: float) -> float:
    return math.sqrt(left * left + right * right)


def parentless_tracts(query: str, *, dataset: str, year: int) -> tuple[str, list[GeoSpec]] | None:
    from src.geo_list import find_state

    match = _TRACT_VS.search(query)
    if not match or find_state(query) is not None or _COUNTY.search(query):
        return None
    specs = [
        GeoSpec(
            level="tract",
            name=f"Census Tract {raw}",
            for_spec=f"tract:{int(raw):04d}00",
            dataset=dataset,
            vintage=year,
        )
        for raw in match.groups()
    ]
    detail = f"tract {match.group(1)} vs tract {match.group(2)} needs state and county"
    return detail, specs


def _numeric(row: dict[str, str | None], key: str) -> float | None:
    from src.vintages import CENSUS_MISSING

    raw = row.get(key)
    if not isinstance(raw, str) or raw in CENSUS_MISSING:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _label(value: float) -> str:
    rounded = round(value)
    if math.isclose(value, rounded, abs_tol=1e-9):
        return str(rounded)
    return f"{value:.10g}"


def nested_pair(left: GeoSpec, right: GeoSpec) -> bool:
    if left.level == right.level:
        return False
    child, parent = (left, right)
    if _RANK.get(left.level, 9) > _RANK.get(right.level, 9):
        child, parent = right, left
    code = parent.codes.get(parent.level)
    return bool(code) and child.codes.get(parent.level) == code


def shares_sample(record: Any) -> bool:
    geos = list(getattr(record, "geographies", []) or [])[:2]
    status = getattr(record, "geo_status", None) or {}
    if not status.get("compare") or len(geos) < 2:
        return False
    return nested_pair(geos[0], geos[1])


def _pair_ok(
    left: dict[str, str | None],
    right: dict[str, str | None],
    *,
    cross_geo_series: bool,
) -> bool:
    same_geo = (left.get("GEO_ID") or "") == (right.get("GEO_ID") or "")
    same_year = (left.get("year") or "") == (right.get("year") or "")
    if cross_geo_series:
        return bool(not same_geo and same_year)
    return not (same_geo and same_year)


def comparison_rows(record: Any, rows: list[dict[str, str | None]]) -> list[Comparison]:
    if not _COMPARE.search(str(getattr(record, "question", "") or "")):
        return []
    usable = [row for row in rows if str(row.get("GEO_ID") or "")]
    if len(usable) < 2:
        return []
    keys = [key for key in usable[0] if key.endswith("E") and "_" in key]
    years = {str(row.get("year") or "") for row in usable} - {""}
    geos = {str(row.get("GEO_ID") or "") for row in usable} - {""}
    cross = len(years) > 1 and len(geos) > 1
    shared = shares_sample(record)
    out: list[Comparison] = []
    for estimate in keys:
        margin = f"{estimate[:-1]}M"
        for i, left in enumerate(usable):
            for right in usable[i + 1 :]:
                if not _pair_ok(left, right, cross_geo_series=cross):
                    continue
                e1, e2 = _numeric(left, estimate), _numeric(right, estimate)
                m1, m2 = _numeric(left, margin), _numeric(right, margin)
                if e1 is None or e2 is None or m1 is None or m2 is None:
                    continue
                threshold = moe_diff(m1, m2)
                left_year = str(left.get("year") or "")
                right_year = str(right.get("year") or "")
                out.append(
                    Comparison(
                        variable=estimate,
                        geoid_a=str(left.get("GEO_ID") or ""),
                        geoid_b=str(right.get("GEO_ID") or ""),
                        year=left_year if left_year and left_year == right_year else "",
                        estimate_a=_label(e1),
                        estimate_b=_label(e2),
                        moe_a=_label(m1),
                        moe_b=_label(m2),
                        threshold=_label(threshold),
                        distinguishable=abs(e1 - e2) > threshold,
                        shared_sample=shared,
                    )
                )
    return out


def significance_warning(record: Any) -> AskWarning | None:
    if any(
        not item.distinguishable
        for item in comparison_rows(record, list(getattr(record, "rows", []) or []))
    ):
        return AskWarning(
            code="moe_not_significant",
            detail="difference is within the 90% margin of error and is not distinguishable",
        )
    return None


def shared_sample(record: Any) -> AskWarning | None:
    if not shares_sample(record):
        return None
    return AskWarning(
        code="shared_sample",
        detail=(
            "compared geographies share ACS sample; independent MOE_diff "
            "overstates the variance of the difference"
        ),
    )
