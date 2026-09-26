"""Ask-loop tools: schemas plus search_tables and build_url."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from src.census_url import CENSUS_API, CensusURL
from src.contract import GeoSpec
from src.vintages import pinned_table

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
    query: str = Field(
        default="", description="Place, county, or a wildcard like 'all counties in Oregon'."
    )
    places: list[str] | None = Field(
        default=None,
        description=(
            "For a 2+ way comparison: every compared place, each already canonicalized as "
            "'Place, ST' (infer the state yourself even if the question named none, e.g. "
            "'Chicago' -> 'Chicago, IL'). One call resolves all of them; omit query."
        ),
    )
    level: str | None = Field(
        default=None, description="geography.json name if already known, else omit."
    )
    dataset: Literal["acs5", "acs1"] = Field(default="acs5", description="acs5 or acs1.")
    vintage: int | None = Field(
        default=None, description="End year. Empty means latest for the dataset."
    )


class BuildUrlInput(ToolInput):
    table_id: str = Field(description="ACS table ID from search_tables or a family member.")
    variables: list[str] = Field(
        default_factory=list,
        description="Estimate variable IDs (E). Empty means the table total (001E).",
    )
    dataset: Literal["acs5", "acs1"] = Field(default="acs5", description="acs5 or acs1.")
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


DescribeTable = Callable[[str], dict[str, Any] | None]
SearchFn = Callable[[str, int], list[str]]
SelectFn = Callable[[str, list[dict[str, Any]]], str]
AllowedTables = Callable[[], set[str]]
AllowedGeographies = Callable[[], set[tuple[str, str, str]]]
LatestVintage = Callable[[str], int]
TableFacts = Callable[[str, int, str], dict[str, Any] | None]
LastGeography = Callable[[], GeoSpec | None]


def _promote(hits: list[dict[str, Any]], picked: str) -> list[dict[str, Any]]:
    """Move the selector's table to front. An unknown ID leaves ranking as-is."""
    if not any(hit["table_id"] == picked for hit in hits):
        return hits
    return [hit for hit in hits if hit["table_id"] == picked] + [
        hit for hit in hits if hit["table_id"] != picked
    ]


def _with_device_table(
    question: str, hits: list[dict[str, Any]], describe: DescribeTable
) -> list[dict[str, Any]]:
    table_id = pinned_table(question)
    if not table_id:
        return hits
    if any(hit["table_id"] == table_id for hit in hits):
        return _promote(hits, table_id)
    meta = describe(table_id) or {}
    if not meta:
        return hits
    injected = {
        "table_id": table_id,
        "title": meta.get("title", ""),
        "universe": meta.get("universe", ""),
        "members": list(meta.get("members") or []),
    }
    return [injected, *[hit for hit in hits if hit["table_id"] != table_id]]


def _pick_table(question: str, hits: list[dict[str, Any]], select: SelectFn | None) -> str:
    if select is not None:
        return select(question, hits)
    from src.retrieval.rerank import Candidate, choose

    return choose(
        question,
        [
            Candidate(str(hit["table_id"]), str(hit["title"]), str(hit.get("universe") or ""))
            for hit in hits
        ],
    )


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


def _build_fail(
    table_id: str,
    dataset: str,
    year: int,
    detail: str,
    variables: list[str] | None = None,
    universe: str = "",
) -> tuple[str, BuildUrlResult]:
    fail = BuildUrlResult(
        ok=False,
        url="",
        table_id=table_id,
        variables=list(variables or []),
        dataset=dataset,
        vintage=year,
        detail=detail,
        universe=universe,
    )
    return fail.detail, fail


class SearchTablesTool(BaseTool):
    name: str = "search_tables"
    description: str = "Find candidate ACS tables for a question."
    args_schema: type[BaseModel] = SearchTablesInput
    response_format: Literal["content_and_artifact"] = "content_and_artifact"
    model_config = ConfigDict(arbitrary_types_allowed=True)

    search: SearchFn
    describe: DescribeTable
    select: SelectFn | None = None
    _picks: dict[str, str] = PrivateAttr(default_factory=dict)

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
        if len(hits) > 1:
            picked = self._picks.get(question)
            if picked is None:
                picked = await asyncio.to_thread(_pick_table, question, hits, self.select)
                self._picks[question] = picked
            hits = _promote(hits, picked)
        hits = _with_device_table(question, hits, self.describe)
        artifact = SearchTablesResult(hits=hits)
        if not hits:
            return "0 candidates", artifact
        lead = hits[0]
        summary = (
            f"selected {lead['table_id']} {lead['title']} "
            f"({lead['universe'] or 'universe unpublished'})"
        )
        members = [str(member) for member in lead.get("members") or []]
        if members:
            summary += f"; members {', '.join(members)}"
        if len(hits) > 1:
            summary += f"; {len(hits) - 1} related tables"
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
        if not allowed or table_id not in allowed:
            detail = (
                "call search_tables before build_url"
                if not allowed
                else f"{table_id} is not in the search pool or its family members"
            )
            return _build_fail(table_id, dataset, year, detail)
        facts = self.table_facts(dataset, year, table_id)
        if facts is None:
            return _build_fail(table_id, dataset, year, f"{table_id} is not in {dataset} {year}")
        suffixes: list[str] = list(facts.get("variables") or [])
        if not variables:
            variables = [f"{table_id}_001E"]
        normalized: list[str] = []
        missing: list[str] = []
        for variable_id in variables:
            full = (
                variable_id
                if variable_id.startswith(f"{table_id}_")
                else f"{table_id}_{variable_id}"
            )
            suffix = full.removeprefix(f"{table_id}_")
            if suffix.endswith("M"):
                estimate = f"{suffix[:-1]}E"
                if estimate not in suffixes:
                    missing.append(full)
                else:
                    estimate_id = f"{table_id}_{estimate}"
                    if estimate_id not in normalized:
                        normalized.append(estimate_id)
            elif suffix not in suffixes:
                missing.append(full)
            if full not in normalized:
                normalized.append(full)
        variables = normalized
        if missing:
            return _build_fail(
                table_id, dataset, year, f"variables not in {dataset} {year}: {missing}", variables
            )
        paired = pair_margins(variables)
        geography = self.last_geography()
        for_clause = (for_spec or "").strip() or (geography.for_spec if geography else "")
        in_clause = (in_spec or "").strip() or (geography.in_spec if geography else "")
        allowed_geo = self.allowed_geographies()
        if not for_clause or (for_clause, in_clause, dataset) not in allowed_geo:
            return _build_fail(
                table_id,
                dataset,
                year,
                "resolve_geography before build_url, or pass a for_spec from its matches",
                paired,
                str(facts.get("universe") or ""),
            )
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
