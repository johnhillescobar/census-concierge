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
    ordered = sorted(set(years))
    if len(ordered) < 2:
        return False
    missing = [year for year in range(ordered[0], ordered[-1] + 1) if year not in set(ordered)]
    if not missing:
        return True
    acs1 = None if published is None else published.get("acs1")
    if acs1 is None:
        return False
    return all(year not in acs1 for year in missing)


def span_years(years: list[int]) -> list[int]:
    """First-requested order, then any holes in the inclusive span."""
    unique = list(dict.fromkeys(years))
    if not unique:
        return []
    present = set(unique)
    holes = [year for year in range(min(unique), max(unique) + 1) if year not in present]
    return unique + holes


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
        overlap = [year for year in kept if year not in set(destaggered)]
        plan = VintagePlan(
            dataset="acs5",
            attempted=destaggered,
            omitted=[*unpub, *overlap],
            reasons=[*unpub_reasons, *([REASON_OVERLAP] * len(overlap))],
            acs1_ineligible=acs1_ok is False,
        )
    else:
        use = "acs1" if series or dataset == "acs1" else dataset
        planned = span_years(years) if series else years
        attempted, omitted, reasons = _drop_unpublished(use, planned, published)
        plan = VintagePlan(dataset=use, attempted=attempted, omitted=omitted, reasons=reasons)
    if cap is None or len(plan.attempted) <= cap:
        return plan
    extra = plan.attempted[cap:]
    return VintagePlan(
        dataset=plan.dataset,
        attempted=plan.attempted[:cap],
        omitted=[*plan.omitted, *extra],
        reasons=[*plan.reasons, *([REASON_MAX] * len(extra))],
        acs1_ineligible=plan.acs1_ineligible,
    )
