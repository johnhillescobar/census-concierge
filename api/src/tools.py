"""Ask-loop tools: schemas plus search_tables, build_url, and fetch_data.

resolve_geography lives in `geo.py` so legality stays next to geography.json.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any, Literal

import httpx
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.census_url import CENSUS_API, CensusURL

# --- markers. Direct BaseModel subclasses named these are excluded from the
# domain-model budget; every tool I/O class subclasses one of them instead. ---


class ToolInput(BaseModel):
    """Args schema for one tool. Field descriptions are what the model sees."""


class ToolResult(BaseModel):
    """Typed artifact. The model sees only the content string, not this object."""


class SearchTablesInput(ToolInput):
    question: str = Field(description="The user's question, verbatim.")
    k: int = Field(default=10, ge=1, le=20, description="Candidate pool size.")


class SearchTablesResult(ToolResult):
    hits: list[dict[str, Any]]


class ResolveGeographyInput(ToolInput):
    query: str = Field(description="Place, county, or a wildcard like 'all counties in Oregon'.")
    level: str | None = Field(
        default=None, description="geography.json name if already known, else omit."
    )


class BuildUrlInput(ToolInput):
    table_id: str = Field(description="ACS table ID from search_tables or a family member.")
    variables: list[str] = Field(
        default_factory=list,
        description="Estimate variable IDs (E). Empty means every E in the table.",
    )
    dataset: str = Field(default="acs5", description="acs5 or acs1.")
    vintage: int | None = Field(default=None, description="End year. Empty means latest ACS5.")
    for_spec: str | None = Field(default=None, description="Census for=, e.g. county:201")
    in_spec: str | None = Field(default=None, description="Census in=, e.g. state:48")


class BuildUrlResult(ToolResult):
    ok: bool
    url: str
    table_id: str
    variables: list[str]
    dataset: str
    vintage: int
    detail: str
    universe: str = ""


class FetchDataInput(ToolInput):
    """No arguments. Fetches the URL already produced by build_url."""


class FetchDataResult(ToolResult):
    ok: bool
    url: str
    rows: list[dict[str, str | None]]
    status_code: int
    detail: str


DescribeTable = Callable[[str], dict[str, Any] | None]
SearchFn = Callable[[str, int], list[str]]
AllowedTables = Callable[[], set[str]]
AllowedGeographies = Callable[[], set[tuple[str, str]]]
LatestVintage = Callable[[str], int]
TableFacts = Callable[[str, int, str], dict[str, Any] | None]
LastUrl = Callable[[], CensusURL | None]
LastGeography = Callable[[], dict[str, str] | None]


def _census_get(url: str) -> tuple[int, Any]:
    response = httpx.get(url, timeout=60.0)
    try:
        payload: Any = response.json()
    except json.JSONDecodeError:
        payload = response.text
    return response.status_code, payload


def pair_margins(variable_ids: list[str]) -> list[str]:
    """Every E is followed by its M. Idempotent if M is already present."""
    out: list[str] = []
    seen: set[str] = set()
    for variable_id in variable_ids:
        if variable_id not in seen:
            out.append(variable_id)
            seen.add(variable_id)
        if variable_id.endswith("E"):
            margin = f"{variable_id[:-1]}M"
            if margin not in seen:
                out.append(margin)
                seen.add(margin)
    return out


class SearchTablesTool(BaseTool):
    name: str = "search_tables"
    description: str = "Find candidate ACS tables for a question."
    args_schema: type[BaseModel] = SearchTablesInput
    response_format: Literal["content_and_artifact"] = "content_and_artifact"
    model_config = ConfigDict(arbitrary_types_allowed=True)

    search: SearchFn
    describe: DescribeTable

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("search_tables is async-only")

    async def _arun(self, question: str, k: int = 10) -> tuple[str, SearchTablesResult]:
        table_ids = await asyncio.to_thread(self.search, question, k)
        hits: list[dict[str, Any]] = []
        for table_id in table_ids:
            meta = self.describe(table_id) or {}
            hits.append(
                {
                    "table_id": table_id,
                    "title": meta.get("title", ""),
                    "universe": meta.get("universe", ""),
                    "members": list(meta.get("members") or []),
                }
            )
        artifact = SearchTablesResult(hits=hits)
        listing = ", ".join(
            f"{hit['table_id']} ({hit['universe'] or 'universe unpublished'})" for hit in hits
        )
        summary = f"{len(hits)} candidates" + (f": {listing}" if listing else "")
        return summary, artifact


class BuildUrlTool(BaseTool):
    name: str = "build_url"
    description: str = "Build the complete Census API URL for a table, geography, and vintage."
    args_schema: type[BaseModel] = BuildUrlInput
    response_format: Literal["content_and_artifact"] = "content_and_artifact"
    model_config = ConfigDict(arbitrary_types_allowed=True)

    allowed_tables: AllowedTables
    allowed_geographies: AllowedGeographies
    latest_vintage: LatestVintage
    table_facts: TableFacts
    last_geography: LastGeography

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("build_url is async-only")

    async def _arun(
        self,
        table_id: str,
        variables: list[str] | None = None,
        dataset: str = "acs5",
        vintage: int | None = None,
        for_spec: str | None = None,
        in_spec: str | None = None,
    ) -> tuple[str, BuildUrlResult]:
        variables = list(variables or [])
        year = vintage if vintage is not None else self.latest_vintage(dataset)
        allowed = self.allowed_tables()
        if not allowed:
            result = BuildUrlResult(
                ok=False,
                url="",
                table_id=table_id,
                variables=[],
                dataset=dataset,
                vintage=year,
                detail="call search_tables before build_url",
            )
            return result.detail, result
        if table_id not in allowed:
            result = BuildUrlResult(
                ok=False,
                url="",
                table_id=table_id,
                variables=[],
                dataset=dataset,
                vintage=year,
                detail=f"{table_id} is not in the search pool or its family members",
            )
            return result.detail, result
        facts = self.table_facts(dataset, year, table_id)
        if facts is None:
            result = BuildUrlResult(
                ok=False,
                url="",
                table_id=table_id,
                variables=[],
                dataset=dataset,
                vintage=year,
                detail=f"{table_id} is not in {dataset} {year}",
            )
            return result.detail, result
        suffixes: list[str] = list(facts.get("variables") or [])
        if not variables:
            variables = [f"{table_id}_{suffix}" for suffix in suffixes]
        normalized: list[str] = []
        missing: list[str] = []
        for variable_id in variables:
            full = (
                variable_id
                if variable_id.startswith(f"{table_id}_")
                else f"{table_id}_{variable_id}"
            )
            suffix = full.removeprefix(f"{table_id}_")
            if suffix not in suffixes and not suffix.endswith("M"):
                missing.append(full)
            normalized.append(full)
        variables = normalized
        if missing:
            result = BuildUrlResult(
                ok=False,
                url="",
                table_id=table_id,
                variables=variables,
                dataset=dataset,
                vintage=year,
                detail=f"variables not in {dataset} {year}: {missing}",
            )
            return result.detail, result
        paired = pair_margins(variables)
        geography = self.last_geography() or {}
        for_clause = (for_spec or "").strip() or geography.get("for") or ""
        in_clause = (in_spec or "").strip() or geography.get("in") or ""
        allowed_geo = self.allowed_geographies()
        if not for_clause or (for_clause, in_clause) not in allowed_geo:
            result = BuildUrlResult(
                ok=False,
                url="",
                table_id=table_id,
                variables=paired,
                dataset=dataset,
                vintage=year,
                detail="resolve_geography before build_url, or pass a for_spec from its matches",
                universe=str(facts.get("universe") or ""),
            )
            return result.detail, result
        get_cols = ["NAME", "GEO_ID", *paired]
        query = f"get={','.join(get_cols)}&for={for_clause}"
        if in_clause:
            query += f"&in={in_clause}"
        url = CensusURL(f"{CENSUS_API}/{year}/acs/{dataset}?{query}")
        result = BuildUrlResult(
            ok=True,
            url=str(url),
            table_id=table_id,
            variables=paired,
            dataset=dataset,
            vintage=year,
            detail="",
            universe=str(facts.get("universe") or ""),
        )
        return str(url), result


class FetchDataTool(BaseTool):
    name: str = "fetch_data"
    description: str = "Fetch rows for the URL already built. Does not take a URL."
    args_schema: type[BaseModel] = FetchDataInput
    response_format: Literal["content_and_artifact"] = "content_and_artifact"
    model_config = ConfigDict(arbitrary_types_allowed=True)

    last_url: LastUrl
    census_key: Callable[[], str]
    http_get: Callable[[str], tuple[int, Any]] | None = None

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("fetch_data is async-only")

    async def _arun(self) -> tuple[str, FetchDataResult]:
        built = self.last_url()
        if built is None:
            result = FetchDataResult(
                ok=False, url="", rows=[], status_code=0, detail="call build_url before fetch_data"
            )
            return result.detail, result
        redacted = str(built)
        live = built.with_key(self.census_key())
        try:
            if self.http_get is not None:
                status, payload = await asyncio.to_thread(self.http_get, live)
            else:
                status, payload = await asyncio.to_thread(_census_get, live)
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError) as exc:
            result = FetchDataResult(
                ok=False, url=redacted, rows=[], status_code=0, detail=str(exc)
            )
            return f"fetch failed; URL {redacted}", result
        if status != 200 or not isinstance(payload, list) or not payload:
            detail = payload if isinstance(payload, str) else f"HTTP {status}"
            result = FetchDataResult(
                ok=False, url=redacted, rows=[], status_code=status, detail=str(detail)[:300]
            )
            return f"fetch failed ({status}); URL {redacted}", result
        header, *body = payload
        rows = [
            {
                str(key): (None if value is None else str(value))
                for key, value in zip(header, row, strict=False)
            }
            for row in body
        ]
        result = FetchDataResult(ok=True, url=redacted, rows=rows, status_code=status, detail="")
        return f"{len(rows)} rows; URL {redacted}", result
