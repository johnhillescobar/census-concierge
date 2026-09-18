"""Defensible ACS vintages: ACS1 where published, else non-overlapping ACS5."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ACS5_SPAN = 5
REASON_GAP_2020 = "vintage_gap_2020"
REASON_OVERLAP = "overlapping_vintage"
REASON_MAX = "max_years"
REASON_NO_URL = "no_url"
REASON_UNPUBLISHED = "unpublished_vintage"
CENSUS_MISSING = {
    None,
    "",
    "-999999999",
    "-888888888",
    "-666666666",
    "-555555555",
    "-333333333",
    "-222222222",
}


@dataclass(frozen=True)
class VintagePlan:
    dataset: str
    attempted: list[int]
    omitted: list[int]
    reasons: list[str]
    acs1_ineligible: bool = False


def consecutive(years: list[int]) -> bool:
    ordered = sorted(set(years))
    return len(ordered) >= 2 and ordered[-1] - ordered[0] + 1 == len(ordered)


def is_series(years: list[int], published: dict[str, set[int]] | None = None) -> bool:
    """A year list is a series if it is dense, or the only holes are unpublished ACS1 years."""
    if consecutive(years):
        return True
    ordered = sorted(set(years))
    if len(ordered) < 2:
        return False
    missing = [year for year in range(ordered[0], ordered[-1] + 1) if year not in set(ordered)]
    acs1 = None if published is None else published.get("acs1")
    if acs1 is None:
        return False
    return all(year not in acs1 for year in missing)


def span_years(years: list[int]) -> list[int]:
    """Inclusive end-year span covering the requested years."""
    unique = list(dict.fromkeys(years))
    if not unique:
        return []
    return list(range(min(unique), max(unique) + 1))


def period_for(dataset: str, year: int) -> str:
    """ACS release window for an end year: ACS1 is that year; ACS5 is year-4–year."""
    if dataset == "acs1":
        return str(year)
    return f"{year - ACS5_SPAN + 1}-{year}"


def stamp_provenance(
    rows: list[dict[str, str | None]],
    *,
    dataset: str,
    table_id: str = "",
    fallback_year: int | None = None,
) -> list[dict[str, str | None]]:
    """Attach dataset, vintage, period, and table_id to each series point."""
    tagged: list[dict[str, str | None]] = []
    for row in rows:
        item = dict(row)
        raw = str(item.get("year") or item.get("vintage") or "")
        year = int(raw) if raw.isdigit() else fallback_year
        ds = str(item.get("dataset") or dataset or "acs5")
        item["dataset"] = ds
        table = table_id or next(
            (key.split("_", 1)[0] for key in item if "_" in key and key.endswith("E")),
            str(item.get("table_id") or ""),
        )
        if table:
            item["table_id"] = str(item.get("table_id") or table)
        if year is not None:
            item["year"] = str(year)
            item["vintage"] = str(year)
            item["period"] = str(item.get("period") or period_for(ds, year))
        tagged.append(item)
    return tagged


def moe_rows(rows: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    """Per-row 90% MOE. Sentinels are None; a published 0 stays 0."""
    out: list[dict[str, str | None]] = []
    for row in rows:
        moe: dict[str, str | None] = {key: row[key] for key in ("GEO_ID", "NAME") if key in row}
        for key in row:
            if key.endswith("E") and "_" in key:
                raw = row.get(f"{key[:-1]}M")
                moe[f"{key[:-1]}M"] = None if raw in CENSUS_MISSING else raw
        out.append(moe)
    return out


def nonoverlapping_acs5(years: list[int]) -> list[int]:
    """Keep first-requested order; drop any year within four of a kept year."""
    kept: list[int] = []
    for year in years:
        if all(abs(year - other) >= ACS5_SPAN for other in kept):
            kept.append(year)
    return kept


def latest_vintages(matrix: dict[str, Any] | None = None) -> tuple[int, int | None]:
    if matrix is None:
        from src.retrieval import availability

        try:
            matrix = availability.load()
        except (OSError, ValueError, KeyError):
            return 2024, None
    acs5 = max(int(year) for year in matrix["datasets"]["acs5"])
    acs1_years = [int(year) for year in matrix["datasets"].get("acs1", {})]
    return acs5, max(acs1_years) if acs1_years else None


def _drop_unpublished(
    dataset: str, years: list[int], published: dict[str, set[int]] | None
) -> tuple[list[int], list[int], list[str]]:
    known = None if published is None else published.get(dataset)
    if known is None:
        return list(years), [], []
    attempted: list[int] = []
    omitted: list[int] = []
    reasons: list[str] = []
    for year in years:
        if year in known:
            attempted.append(year)
            continue
        omitted.append(year)
        gap = dataset == "acs1" and year == 2020
        reasons.append(REASON_GAP_2020 if gap else REASON_UNPUBLISHED)
    return attempted, omitted, reasons


def plan_years(
    *,
    dataset: str,
    years: list[int],
    published: dict[str, set[int]] | None = None,
    acs1_ok: bool | None = False,
    allow_overlapping_acs5: bool = False,
    cap: int | None = None,
) -> VintagePlan:
    """Choose dataset and attempted years. Does not invent values for gaps."""
    if not years:
        return VintagePlan(dataset=dataset, attempted=[], omitted=[], reasons=[])
    series = is_series(years, published) and not allow_overlapping_acs5
    if series and dataset != "acs1" and acs1_ok is not True:
        kept, unpub, unpub_reasons = _drop_unpublished("acs5", years, published)
        destaggered = nonoverlapping_acs5(kept)
        unpub_map = dict(zip(unpub, unpub_reasons, strict=True))
        kept_set = set(destaggered)
        omitted: list[int] = []
        reasons: list[str] = []
        for year in list(dict.fromkeys(years)):
            if year in kept_set:
                continue
            omitted.append(year)
            reasons.append(unpub_map.get(year, REASON_OVERLAP))
        plan = VintagePlan(
            dataset="acs5",
            attempted=destaggered,
            omitted=omitted,
            reasons=reasons,
            acs1_ineligible=acs1_ok is False,
        )
    else:
        use = "acs1" if series or dataset == "acs1" else dataset
        planned = span_years(years) if series else years
        attempted, omitted, reasons = _drop_unpublished(use, planned, published)
        plan = VintagePlan(dataset=use, attempted=attempted, omitted=omitted, reasons=reasons)
    if cap is None or len(plan.attempted) <= cap:
        return plan
    kept = plan.attempted[:cap]
    kept_set = set(kept)
    reason_map = dict(zip(plan.omitted, plan.reasons, strict=True))
    extra_set = set(plan.attempted[cap:])
    capped: list[int] = []
    capped_reasons: list[str] = []
    for year in list(dict.fromkeys([*years, *plan.omitted, *plan.attempted])):
        if year in kept_set:
            continue
        if year not in extra_set and year not in reason_map:
            continue
        capped.append(year)
        capped_reasons.append(reason_map.get(year, REASON_MAX))
    return VintagePlan(
        dataset=plan.dataset,
        attempted=kept,
        omitted=capped,
        reasons=capped_reasons,
        acs1_ineligible=plan.acs1_ineligible,
    )
