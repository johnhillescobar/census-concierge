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
from src.contract import RequestLeg
from src.tools import ToolInput, ToolResult

MAX_IN_FLIGHT = 5
LastUrl = Callable[[], CensusURL | None]


class FetchDataInput(ToolInput):
    years: list[int] = Field(
        default_factory=list,
        description="Vintage end years to fetch, in order. Empty uses the URL already built.",
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


def unique_years(years: list[int]) -> list[int]:
    """De-duplicate, keeping first-requested order."""
    seen: set[int] = set()
    out: list[int] = []
    for year in years:
        if year not in seen:
            seen.add(year)
            out.append(year)
    return out


def clear_series(record: Any) -> None:
    record.url = None
    record.rows = []
    record.table_id = ""
    record.universe = ""
    record.fetch = None


def series_from_record(record: Any) -> dict[str, Any]:
    artifact = getattr(record, "fetch", None)
    if isinstance(artifact, FetchDataResult):
        return {
            "urls": list(artifact.urls),
            "requested_years": list(artifact.requested_years),
            "attempted_years": list(artifact.attempted_years),
            "succeeded_years": list(artifact.succeeded_years),
            "failed_years": list(artifact.failed_years),
            "omitted_years": list(artifact.omitted_years),
            "legs": list(artifact.legs),
        }
    built = getattr(record, "url", None)
    if built:
        return {
            "urls": [str(built)],
            "requested_years": [],
            "attempted_years": [],
            "succeeded_years": [],
            "failed_years": [],
            "omitted_years": [],
            "legs": [],
        }
    return {
        "urls": [],
        "requested_years": [],
        "attempted_years": [],
        "succeeded_years": [],
        "failed_years": [],
        "omitted_years": [],
        "legs": [],
    }


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
    return [
        {
            str(key): (None if value is None else str(value))
            for key, value in zip(header, row, strict=False)
        }
        for row in body
    ]


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
    detail: str,
) -> FetchDataResult:
    urls = [leg.url for leg in legs]
    attempted = [leg.year for leg in legs]
    succeeded = [leg.year for leg in legs if leg.ok]
    failed = [leg.year for leg in legs if not leg.ok]
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
    )


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
    census_key: Callable[[], str]
    http_get: Callable[[str], tuple[int, Any]] | None = None

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("fetch_data is async-only")

    def _fetch_one(
        self, template: CensusURL, year: int
    ) -> tuple[RequestLeg, list[dict[str, str | None]]]:
        census_url = template.with_year(year)
        redacted = str(census_url)
        live = census_url.with_key(self.census_key())
        try:
            if self.http_get is not None:
                status, payload = self.http_get(live)
            else:
                status, payload = _census_get(live)
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return (
                RequestLeg(
                    year=year, url=redacted, ok=False, status_code=0, detail=redact_text(str(exc))
                ),
                [],
            )
        if status != 200:
            raw = payload if isinstance(payload, str) else f"HTTP {status}"
            return (
                RequestLeg(
                    year=year,
                    url=redacted,
                    ok=False,
                    status_code=status,
                    detail=redact_text(str(raw)[:300]),
                ),
                [],
            )
        parsed = _rows_from_payload(payload)
        if parsed is None:
            raw = payload if isinstance(payload, str) else f"HTTP {status}"
            return (
                RequestLeg(
                    year=year,
                    url=redacted,
                    ok=False,
                    status_code=status,
                    detail=redact_text(str(raw)[:300]),
                ),
                [],
            )
        return (
            RequestLeg(year=year, url=redacted, ok=True, status_code=status, detail=""),
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
                detail="call build_url before fetch_data",
            )
            return result.detail, result
        if not requested:
            year = built.year
            requested = [year] if year is not None else []
        if not requested:
            result = _pack(
                ok=False,
                legs=[],
                rows=[],
                requested=[],
                omitted=[],
                detail="call build_url before fetch_data",
            )
            return result.detail, result
        sem = asyncio.Semaphore(MAX_IN_FLIGHT)

        async def one(year: int) -> tuple[RequestLeg, list[dict[str, str | None]]]:
            async with sem:
                return await asyncio.to_thread(self._fetch_one, built, year)

        gathered = await asyncio.gather(*(one(year) for year in requested))
        legs = [item[0] for item in gathered]
        rows: list[dict[str, str | None]] = []
        for leg, part in gathered:
            if leg.ok:
                rows.extend(part)
        ok = any(leg.ok for leg in legs)
        detail = next((leg.detail for leg in legs if not leg.ok), "")
        result = _pack(ok=ok, legs=legs, rows=rows, requested=requested, omitted=[], detail=detail)
        n_ok = len(result.succeeded_years)
        joined = ", ".join(result.urls)
        if ok:
            return f"{len(rows)} rows; {n_ok}/{len(legs)} years; URLs {joined}", result
        return f"fetch failed; URLs {joined}", result
