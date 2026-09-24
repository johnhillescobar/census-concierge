"""fetch_data: one tool, optional years, bounded concurrent Census GETs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any, Literal

import httpx
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.census_url import CensusURL, redact_text
from src.contract import GeoSpec, RequestLeg
from src.tools import ToolInput, ToolResult
from src.vintages import (
    REASON_NO_URL,
    VintagePlan,
    apply_variable_plan,
    is_series,
    plan_years,
    span_years,
)

MAX_IN_FLIGHT = 5
MAX_YEARS = 12
LastUrl = Callable[[], CensusURL | None]
LastGeographies = Callable[[], list[GeoSpec]]
QuestionYears = Callable[[], list[int]]


class FetchDataInput(ToolInput):
    years: list[int] = Field(
        default_factory=list,
        description=(
            "Vintage end years to fetch, in order. Empty uses the URL already built. "
            f"At most {MAX_YEARS}; extras are omitted."
        ),
    )


class FetchDataResult(ToolResult):
    ok: bool
    url: str
    urls: list[str]
    rows: list[dict[str, str | None]]
    status_code: int
    detail: str
    legs: list[RequestLeg]
    requested_years: list[int]
    attempted_years: list[int]
    succeeded_years: list[int]
    failed_years: list[int]
    omitted_years: list[int]
    omission_reasons: list[str]
    dataset: str = ""
    acs1_ineligible: bool = False


def unique_years(years: list[int]) -> list[int]:
    """De-duplicate, keeping first-requested order."""
    seen: set[int] = set()
    out: list[int] = []
    for year in years:
        if year not in seen:
            seen.add(year)
            out.append(year)
    return out


def _kept_urls(record: Any) -> list[str]:
    kept = [url for url in list(getattr(record, "retained_urls", None) or []) if url]
    extra = list(getattr(getattr(record, "fetch", None), "urls", None) or [])
    built = getattr(record, "url", None)
    if built:
        extra.append(str(built))
    for url in extra:
        redacted = str(CensusURL(url)) if url else ""
        if redacted and redacted not in kept:
            kept.append(redacted)
    record.retained_urls = kept
    return kept


def clear_series(record: Any) -> None:
    _kept_urls(record)
    record.url = None
    record.rows = []
    record.table_id = ""
    record.universe = ""
    record.fetch = None


def series_from_record(record: Any) -> dict[str, Any]:
    kept = _kept_urls(record)
    artifact = getattr(record, "fetch", None)
    built = getattr(record, "url", None)
    urls = [str(built)] if built else kept
    years: dict[str, Any] = {
        "requested_years": [],
        "attempted_years": [],
        "succeeded_years": [],
        "failed_years": [],
        "omitted_years": [],
        "omission_reasons": [],
        "legs": [],
    }
    if isinstance(artifact, FetchDataResult):
        urls = list(artifact.urls) or urls
        years = {
            "requested_years": list(artifact.requested_years),
            "attempted_years": list(artifact.attempted_years),
            "succeeded_years": list(artifact.succeeded_years),
            "failed_years": list(artifact.failed_years),
            "omitted_years": list(artifact.omitted_years),
            "omission_reasons": list(artifact.omission_reasons),
            "legs": list(artifact.legs),
        }
    return {"urls": [str(CensusURL(url)) for url in urls if url], **years}


def _census_get(url: str) -> tuple[int, Any]:
    response = httpx.get(url, timeout=60.0)
    try:
        payload: Any = response.json()
    except json.JSONDecodeError:
        payload = response.text
    return response.status_code, payload


def _rows_from_payload(payload: Any) -> list[dict[str, str | None]] | None:
    if not isinstance(payload, list) or not payload:
        return None
    header, *body = payload
    if not isinstance(header, list):
        return None
    rows: list[dict[str, str | None]] = []
    for row in body:
        if not isinstance(row, list):
            return None
        rows.append(
            {
                str(key): (None if value is None else str(value))
                for key, value in zip(header, row, strict=False)
            }
        )
    return rows


def _tag_year(rows: list[dict[str, str | None]], year: int) -> list[dict[str, str | None]]:
    tagged: list[dict[str, str | None]] = []
    for row in rows:
        item = dict(row)
        item["year"] = str(year)
        tagged.append(item)
    return tagged


def _pack(
    *,
    ok: bool,
    legs: list[RequestLeg],
    rows: list[dict[str, str | None]],
    requested: list[int],
    omitted: list[int],
    reasons: list[str],
    detail: str,
    dataset: str = "",
    acs1_ineligible: bool = False,
) -> FetchDataResult:
    urls = [leg.url for leg in legs]
    attempted = unique_years([leg.year for leg in legs])
    succeeded = unique_years([leg.year for leg in legs if leg.ok])
    failed = unique_years([leg.year for leg in legs if not leg.ok])
    status = 0
    if failed:
        status = next(leg.status_code for leg in legs if not leg.ok)
    elif succeeded:
        status = next(leg.status_code for leg in legs if leg.ok)
    return FetchDataResult(
        ok=ok,
        url=urls[0] if urls else "",
        urls=urls,
        rows=rows,
        status_code=status,
        detail=detail,
        legs=legs,
        requested_years=requested,
        attempted_years=attempted,
        succeeded_years=succeeded,
        failed_years=failed,
        omitted_years=omitted,
        omission_reasons=reasons,
        dataset=dataset,
        acs1_ineligible=acs1_ineligible,
    )


def _tool_content(result: FetchDataResult) -> str:
    joined = ", ".join(result.urls)
    n_ok = sum(1 for leg in result.legs if leg.ok)
    n_legs = len(result.legs)
    bits: list[str] = []
    if result.ok:
        bits.append(f"{len(result.rows)} rows; {n_ok}/{n_legs} legs")
    else:
        bits.append("fetch failed")
    if result.failed_years:
        years = ",".join(str(year) for year in result.failed_years)
        bits.append(f"failed {years} HTTP {result.status_code}")
        if result.detail and not result.ok:
            bits.append(result.detail)
    if result.omitted_years:
        pairs = ",".join(
            f"{year}:{reason}"
            for year, reason in zip(result.omitted_years, result.omission_reasons, strict=True)
        )
        bits.append(f"omitted {pairs}")
    if joined:
        bits.append(f"URLs {joined}")
    return "; ".join(bits)


class FetchDataTool(BaseTool):
    name: str = "fetch_data"
    description: str = (
        "Fetch the built URL. Pass years to fan out across vintages; "
        "omit years for the one already built."
    )
    args_schema: type[BaseModel] = FetchDataInput
    response_format: Literal["content_and_artifact"] = "content_and_artifact"
    model_config = ConfigDict(arbitrary_types_allowed=True)

    last_url: LastUrl
    last_geographies: LastGeographies | None = None
    census_key: Callable[[], str]
    http_get: Callable[[str], tuple[int, Any]] | None = None
    published: Callable[[str], set[int]] | None = None
    table_facts: Callable[[str, int, str], dict[str, Any] | None] | None = None
    question_years: QuestionYears | None = None
    allow_overlapping_acs5: bool = False

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("fetch_data is async-only")

    def _get(self, live: str) -> tuple[int, Any]:
        if self.http_get is not None:
            return self.http_get(live)
        return _census_get(live)

    def _published(self) -> dict[str, set[int]] | None:
        if self.published is None:
            return None
        return {"acs5": self.published("acs5"), "acs1": self.published("acs1")}

    def _acs1_ok(self, template: CensusURL, published: dict[str, set[int]] | None) -> bool | None:
        if template.for_is_wildcard():
            return False
        years = (published or {}).get("acs1") or set()
        if not years:
            return None
        probe = template.with_dataset("acs1").with_year(max(years))
        try:
            status, payload = self._get(probe.with_key(self.census_key()))
            parsed = _rows_from_payload(payload)
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
            return None
        if status == 200:
            return None if parsed is None else bool(parsed)
        if status in {204, 404}:
            return False
        return None

    def _fetch_one(
        self, template: CensusURL, year: int, for_spec: str = ""
    ) -> tuple[RequestLeg, list[dict[str, str | None]]]:
        census_url = template.with_year(year)
        redacted = str(census_url)
        try:
            status, payload = self._get(census_url.with_key(self.census_key()))
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return (
                RequestLeg(
                    year=year,
                    url=redacted,
                    ok=False,
                    status_code=0,
                    detail=redact_text(str(exc)),
                    for_spec=for_spec,
                ),
                [],
            )
        parsed = _rows_from_payload(payload) if status == 200 else None
        if parsed is None:
            raw = payload if isinstance(payload, str) else f"HTTP {status}"
            return (
                RequestLeg(
                    year=year,
                    url=redacted,
                    ok=False,
                    status_code=status,
                    detail=redact_text(str(raw)[:300]),
                    for_spec=for_spec,
                ),
                [],
            )
        return (
            RequestLeg(
                year=year, url=redacted, ok=True, status_code=status, detail="", for_spec=for_spec
            ),
            _tag_year(parsed, year),
        )

    async def _arun(self, years: list[int] | None = None) -> tuple[str, FetchDataResult]:
        requested = unique_years(list(years or []))
        built = self.last_url()
        if built is None:
            result = _pack(
                ok=False,
                legs=[],
                rows=[],
                requested=requested,
                omitted=requested,
                reasons=[REASON_NO_URL] * len(requested),
                detail="call build_url before fetch_data",
            )
            return result.detail, result
        asked = unique_years(self.question_years() if self.question_years is not None else [])
        if not requested:
            year = built.year
            requested = asked or ([year] if year is not None else [])
        elif asked:
            requested = unique_years([*requested, *asked])
        if not requested:
            result = _pack(
                ok=False,
                legs=[],
                rows=[],
                requested=[],
                omitted=[],
                reasons=[],
                detail="call build_url before fetch_data",
            )
            return result.detail, result
        published = self._published()
        series = is_series(requested, published) and not self.allow_overlapping_acs5
        if series:
            requested = span_years(requested)
        acs1_ok: bool | None = None
        if series and built.dataset != "acs1":
            acs1_ok = await asyncio.to_thread(self._acs1_ok, built, published)
        plan = apply_variable_plan(
            plan_years(
                dataset=built.dataset or "acs5",
                years=requested,
                published=published,
                acs1_ok=acs1_ok,
                allow_overlapping_acs5=self.allow_overlapping_acs5,
                cap=MAX_YEARS,
            ),
            built,
            self.table_facts,
            requested,
            published,
        )
        sem = asyncio.Semaphore(MAX_IN_FLIGHT)
        specs = list(self.last_geographies() or []) if self.last_geographies else []
        geos: list[GeoSpec | None] = list(specs) if specs else [None]

        async def fanout(
            planned: VintagePlan,
        ) -> list[tuple[RequestLeg, list[dict[str, str | None]]]]:
            template = built.with_dataset(planned.dataset)

            async def one(
                year: int, spec: GeoSpec | None
            ) -> tuple[RequestLeg, list[dict[str, str | None]]]:
                async with sem:
                    url = (
                        template
                        if spec is None
                        else template.with_geography(spec.for_spec, spec.in_spec)
                    )
                    clause = spec.for_spec if spec is not None else ""
                    return await asyncio.to_thread(self._fetch_one, url, year, clause)

            if not planned.attempted:
                return []
            return list(
                await asyncio.gather(
                    *(one(year, spec) for spec in geos for year in planned.attempted)
                )
            )

        gathered = await fanout(plan)
        unpublished = {204, 404}
        if plan.dataset == "acs1" and any(
            (not leg.ok) and leg.status_code in unpublished for leg, _rows in gathered
        ):
            plan = apply_variable_plan(
                plan_years(
                    dataset="acs5",
                    years=requested,
                    published=published,
                    acs1_ok=False,
                    allow_overlapping_acs5=self.allow_overlapping_acs5,
                    cap=MAX_YEARS,
                ),
                built,
                self.table_facts,
                requested,
                published,
            )
            gathered = await fanout(plan)
        legs = [item[0] for item in gathered]
        rows: list[dict[str, str | None]] = []
        for leg, part in gathered:
            if leg.ok:
                rows.extend(part)
        ok = any(leg.ok for leg in legs)
        detail = next((leg.detail for leg in legs if not leg.ok), "")
        result = _pack(
            ok=ok,
            legs=legs,
            rows=rows,
            requested=requested,
            omitted=plan.omitted,
            reasons=plan.reasons,
            detail=detail,
            dataset=plan.dataset,
            acs1_ineligible=plan.acs1_ineligible,
        )
        return _tool_content(result), result
