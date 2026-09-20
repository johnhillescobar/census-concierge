"""Defensible ACS vintages: ACS1 where published, else non-overlapping ACS5."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.contract import AskWarning

ACS5_SPAN = 5
REASON_GAP_2020 = "vintage_gap_2020"
REASON_OVERLAP = "overlapping_vintage"
REASON_MAX = "max_years"
REASON_NO_URL = "no_url"
REASON_UNPUBLISHED = "unpublished_vintage"
DEVICE_TABLE = "B28001"
RENT_TABLE = "B25064"
FAMILY_INCOME_TABLE = "B19113"
DISTRIBUTION_TABLE = "B19001"
POVERTY_TABLE = "B17001"
HEALTH_TABLE = "B27001"
_DEVICE = re.compile(r"\b(?:cell phones?|mobile phones?)\b", re.IGNORECASE)
_COMPUTER = re.compile(r"\bhouseholds with a computer\b", re.IGNORECASE)
_RENT = re.compile(r"\bmedian gross rent\b", re.IGNORECASE)
_FAMILY_INCOME = re.compile(r"\bmedian family income\b", re.IGNORECASE)
_DISTRIBUTION = re.compile(r"\bincome distribution\b", re.IGNORECASE)
_POVERTY = re.compile(r"\bpoverty\b", re.IGNORECASE)
_UNINSURED = re.compile(r"\bwithout health insurance\b", re.IGNORECASE)
_ACS1 = re.compile(r"\b(?:1-year|acs1)\b", re.IGNORECASE)
_SINCE_WORD = re.compile(r"\bsince\s+(?:19|20)\d{2}\b", re.IGNORECASE)
_SINCE = re.compile(r"\b(?:since|from|through)\s+((?:19|20)\d{2})\b", re.IGNORECASE)
_SPAN = re.compile(r"\b((?:19|20)\d{2})\s*[-–]\s*((?:19|20)\d{2})\b")
_YEAR_SPAN = re.compile(
    r"\b(?:from|between)\s+((?:19|20)\d{2})\s+(?:to|and|through)\s+((?:19|20)\d{2})\b|"
    r"\b((?:19|20)\d{2})\s+(?:to|through)\s+((?:19|20)\d{2})\b",
    re.IGNORECASE,
)
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


def year_span(question: str) -> list[int]:
    years: list[int] = []
    for first, second, third, fourth in _YEAR_SPAN.findall(question):
        start_text, end_text = (first, second) if first else (third, fourth)
        start, end = int(start_text), int(end_text)
        if end >= start:
            years.extend(range(start, end + 1))
    return years


def question_years(question: str) -> list[int]:
    years = [int(part) for pair in _SPAN.findall(question) for part in pair]
    years.extend(year_span(question))
    years.extend(int(match.group(1)) for match in _SINCE.finditer(question))
    return list(dict.fromkeys(years))


def requested_years(question: str, latest: int) -> list[int]:
    years = question_years(question)
    if _SINCE_WORD.search(question) and years:
        return list(range(min(years), latest + 1))
    return years


def wants_acs1(question: str) -> bool:
    return _ACS1.search(question) is not None


def device_table(question: str) -> str | None:
    text = str(question or "")
    if _DEVICE.search(text) or _COMPUTER.search(text):
        return DEVICE_TABLE
    return None


def pinned_table(question: str) -> str | None:
    if hit := device_table(question):
        return hit
    if _RENT.search(question):
        return RENT_TABLE
    if _FAMILY_INCOME.search(question):
        return FAMILY_INCOME_TABLE
    if _DISTRIBUTION.search(question):
        return DISTRIBUTION_TABLE
    if _POVERTY.search(question):
        return POVERTY_TABLE
    if _UNINSURED.search(question):
        return HEALTH_TABLE
    return None


def measure_unavailable(record: Any) -> AskWarning | None:
    if not _DEVICE.search(str(getattr(record, "question", "") or "")):
        return None
    return AskWarning(
        code="measure_unavailable",
        detail=(
            "ACS does not count devices; B28001 counts households in which "
            "someone has a smartphone (universe: Households)"
        ),
    )


def variable_not_in_vintage(record: Any) -> AskWarning | None:
    from src.retrieval.availability import REASON_VARIABLE

    artifact = getattr(record, "fetch", None)
    omitted = list(getattr(artifact, "omitted_years", None) or [])
    reasons = list(getattr(artifact, "omission_reasons", None) or [])
    missing = list(
        dict.fromkeys(
            int(year)
            for year, reason in zip(omitted, reasons, strict=False)
            if reason == REASON_VARIABLE
        )
    )
    if not missing:
        return None
    labeled = ", ".join(str(year) for year in missing)
    return AskWarning(
        code="variable_not_in_vintage",
        detail=f"variable absent or redefined in {labeled}; those years are not joined",
    )


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


def apply_variable_plan(
    plan: VintagePlan,
    template: Any,
    lookup: Any,
    requested: list[int],
    published: dict[str, set[int]] | None,
) -> VintagePlan:
    """Drop or reclassify years whose table, E/M, or definition does not match."""
    from src.retrieval.availability import (
        REASON_VARIABLE,
        drop_incompatible,
        introduction_omissions,
    )

    if lookup is None:
        return plan
    table_id, suffixes = ("", [])
    if plan.attempted or plan.omitted:
        table_id, suffixes = template.estimate_table()
    if not table_id:
        return plan
    kept, dropped, drop_reasons = drop_incompatible(
        lookup, plan.dataset, plan.attempted, table_id, suffixes
    )
    unpublished = [
        year
        for year, reason in zip(plan.omitted, plan.reasons, strict=True)
        if reason == REASON_UNPUBLISHED
    ]
    extra = set(
        introduction_omissions(lookup, plan.dataset, unpublished, table_id, requested, published)
    )
    if not dropped and not extra:
        return plan
    omitted = list(plan.omitted)
    reasons = [
        REASON_VARIABLE if year in extra else reason
        for year, reason in zip(omitted, plan.reasons, strict=True)
    ]
    omitted.extend(dropped)
    reasons.extend(drop_reasons)
    return VintagePlan(
        dataset=plan.dataset,
        attempted=kept,
        omitted=omitted,
        reasons=reasons,
        acs1_ineligible=plan.acs1_ineligible,
    )
