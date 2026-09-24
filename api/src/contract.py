"""HTTP models for POST /ask. One boundary; rows stay untyped dicts."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

_CLAUSE = re.compile(r"(.+?):(\S+)")


def clause_codes(*clauses: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for clause in clauses:
        for match in _CLAUSE.finditer(clause):
            parsed[match.group(1).strip()] = match.group(2)
    return parsed


class AskRequest(BaseModel):
    question: str = Field(
        min_length=1,
        description="The user's question. Leading and trailing whitespace is stripped.",
    )

    @field_validator("question")
    @classmethod
    def question_is_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be blank")
        return stripped


class GeoSpec(BaseModel):
    """Executable geography. `for`/`in` come from metadata, not from prose."""

    level: str = ""
    name: str = ""
    geoid: str = ""
    for_spec: str = ""
    in_spec: str = ""
    dataset: str = "acs5"
    vintage: int = 0
    codes: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fill_codes(self) -> GeoSpec:
        self.codes = clause_codes(self.in_spec, self.for_spec)
        return self


class Alternative(BaseModel):
    table_id: str = Field(description="ACS table ID.")
    title: str = Field(description="Published table title.")
    universe: str = Field(description="Published universe of this table.")
    reason: str = Field(description="How this table differs from the selection.")


class AskWarning(BaseModel):
    code: str = Field(description="Machine-readable warning code.")
    detail: str = Field(description="What was raised, in one sentence.")
    candidates: list[GeoSpec] = Field(
        default_factory=list,
        description="Ranked executable geographies when code is ambiguous_place; else empty.",
    )


class Comparison(BaseModel):
    variable: str = Field(description="Estimate variable compared.")
    geoid_a: str = Field(description="AFFGEOID of the first leg.")
    geoid_b: str = Field(description="AFFGEOID of the second leg.")
    year: str = Field(description="Vintage end year when both legs share one; else empty.")
    estimate_a: str = Field(description="Published estimate for geoid_a.")
    estimate_b: str = Field(description="Published estimate for geoid_b.")
    moe_a: str = Field(description="90% margin for estimate_a.")
    moe_b: str = Field(description="90% margin for estimate_b.")
    threshold: str = Field(description="MOE_diff = sqrt(moe_a^2 + moe_b^2).")
    distinguishable: bool = Field(
        description="True when abs(estimate_a - estimate_b) exceeds threshold."
    )
    shared_sample: bool = Field(
        description="True when the compared geographies nest and share ACS sample."
    )


class RequestLeg(BaseModel):
    year: int = Field(description="Vintage end year for this Census request.")
    url: str = Field(description="Key-redacted Census API URL for this year.")
    ok: bool = Field(description="Whether this HTTP call returned parseable rows.")
    status_code: int = Field(description="Census HTTP status; 0 on timeout or transport failure.")
    detail: str = Field(description="Redacted reason when ok is false; empty on success.")
    for_spec: str = Field(
        default="",
        description="Census for= clause for this geography leg; empty when the built URL is used.",
    )


_UNSAFE_TITLE = re.compile(r"<[^>]+>|javascript:", re.I)


class ChartSpec(BaseModel):
    """Roles over rows/moe. No duplicated data, Vega, or markup."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["line", "bar"] = Field(description="line for years; bar for geographies.")
    x: Literal["year", "geography"] = Field(description="Axis from row year or GEO_ID.")
    y: Literal["estimate"] = Field(description="Estimate columns; never copied values.")
    series_by: Literal["geography", "variable"] | None = Field(
        default=None, description="Split by GEO_ID or estimate variable."
    )
    title: str = Field(description="Plain-text title.")
    show_moe: Literal[True] = Field(default=True, description="MOE display cannot be opted out.")

    @field_validator("title")
    @classmethod
    def title_is_plain_text(cls, value: str) -> str:
        if _UNSAFE_TITLE.search(value):
            raise ValueError("title must not contain markup or code")
        return value

    @model_validator(mode="after")
    def line_is_year_and_bar_is_geography(self) -> ChartSpec:
        if (self.type == "line") != (self.x == "year"):
            raise ValueError("line uses x=year; bar uses x=geography")
        return self


class ResultPlan(BaseModel):
    """Executed table, variables, years, and geographies. Not extracted from prose."""

    table_id: str = Field("", description="Selected ACS table ID.")
    variables: list[str] = Field(default_factory=list, description="Estimate IDs (E) from the URL.")
    dataset: str = Field("acs5", description="acs5 or acs1 actually requested.")
    years: list[int] = Field(default_factory=list, description="Vintages a request was issued for.")
    requested_years: list[int] = Field(default_factory=list, description="Fetch request years.")
    geographies: list[GeoSpec] = Field(default_factory=list, description="Ordered resolved geos.")
    allow_overlapping_acs5: bool = Field(False, description="Consecutive ACS5 explicitly allowed.")

    @model_validator(mode="after")
    def consistent(self) -> ResultPlan:
        from src.geo import legal_predicate

        zcta = "zip code tabulation area"
        geo = next((g for g in self.geographies if zcta in (g.level, g.for_spec)), None)
        wild = bool(geo and geo.for_spec.endswith(":*"))
        if (
            self.dataset == "acs1"
            and geo
            and legal_predicate(geo.level or zcta, frozenset(), wildcard=wild, entries=[]) is None
        ):
            raise ValueError("ACS1 is not published for ZCTA")
        prefix = f"{self.table_id}_"
        if any(
            not item.endswith("E") or (self.table_id and not item.startswith(prefix))
            for item in self.variables
        ):
            raise ValueError("variable outside selected table")
        if self.requested_years and set(self.years) - set(self.requested_years):
            raise ValueError("effective years were not requested")
        return self


def plan_from_record(record: Any) -> ResultPlan:
    fetch, url = getattr(record, "fetch", None), getattr(record, "url", None)
    table, suffixes = url.estimate_table() if url is not None else ("", [])
    if fetch is not None:
        years = list(fetch.attempted_years)
        requested = list(fetch.requested_years)
    else:
        years = [url.year] if url is not None else []
        requested = years
    geos = list(getattr(record, "geographies", None) or [])
    if (getattr(record, "geo_status", None) or {}).get("compare"):
        geos = geos[:2]
    dataset = str(getattr(fetch, "dataset", "") or "") or (url.dataset if url else "")
    vintages = getattr(record, "vintages", None) or []
    return ResultPlan(
        table_id=str(getattr(record, "table_id", "") or table),
        variables=[f"{table}_{item}" for item in suffixes] if table else [],
        dataset=dataset or (vintages[0][0] if vintages else "acs5"),
        years=years,
        requested_years=requested,
        geographies=geos,
        allow_overlapping_acs5=bool(getattr(record, "allow_overlapping_acs5", False)),
    )


class AskResponse(BaseModel):
    answer: str = Field(description="Natural-language answer.")
    urls: list[str] = Field(description="Key-redacted Census API URLs, one per attempted request.")
    requested_years: list[int] = Field(description="Years asked of fetch_data.")
    attempted_years: list[int] = Field(description="Vintages a Census request was issued for.")
    succeeded_years: list[int] = Field(description="Attempted vintages that returned rows.")
    failed_years: list[int] = Field(description="Attempted vintages that failed or timed out.")
    omitted_years: list[int] = Field(description="Requested years that were not attempted.")
    omission_reasons: list[str] = Field(description="Reason code per omitted year.")
    legs: list[RequestLeg] = Field(description="Per-request outcome in requested order.")
    rows: list[dict[str, str | None]] = Field(description="Census rows; each carries GEO_ID.")
    moe: list[dict[str, str | None]] = Field(description="Per-row 90% margins keyed to each M.")
    geoid: str = Field(description="AFFGEOID of the selected geography; empty if many.")
    universe: str = Field(description="Published universe of the selected table.")
    table_id: str = Field(description="Selected ACS table ID.")
    alternatives: list[Alternative] = Field(description="Related tables, with why they differ.")
    comparisons: list[Comparison] = Field(description="Paired estimates with MOE_diff.")
    warnings: list[AskWarning] = Field(description="Non-blocking guards (docs/requirements.md).")
    plan: ResultPlan = Field(description="Executed table, years, and geographies for this answer.")
    chart: ChartSpec | None = Field(default=None, description="Validated chart roles, or null.")
    chart_unavailable: bool = Field(default=False, description="Model chart failed validation.")


def take_chart(
    answer: str,
    rows: list[dict[str, str | None]],
    warnings: list[Any] | None = None,
) -> dict[str, Any]:
    text = answer.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if "```" in text:
            text = text[: text.rfind("```")].strip()
    cleaned, payload, saw = answer, None, False
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        body = None
    if isinstance(body, dict) and "answer" in body:
        cleaned = str(body.get("answer") or "")
        raw = body.get("chart")
        saw = raw is not None
        payload = raw if isinstance(raw, dict) else {}
    none: dict[str, Any] = {"answer": cleaned, "chart": None, "chart_unavailable": False}
    spec: ChartSpec | None = None
    unavailable = False
    if saw:
        try:
            spec = ChartSpec.model_validate(payload)
        except ValidationError:
            unavailable = True
    years = {str(row.get("year") or row.get("vintage") or "") for row in rows} - {""}
    geos = {str(row.get("GEO_ID") or "") for row in rows} - {""}
    estimates = {key for row in rows for key in row if key.endswith("E") and "_" in key}
    if spec is None and not unavailable:
        title = str((rows[0].get("table_id") if rows else "") or "")
        if len(years) > 1:
            series: Literal["geography"] | None = "geography" if len(geos) > 1 else None
            spec = ChartSpec(type="line", x="year", y="estimate", title=title, series_by=series)
        elif len(geos) > 1:
            spec = ChartSpec(type="bar", x="geography", y="estimate", title=title)
    if spec is None:
        return {**none, "chart_unavailable": unavailable}
    fits = (spec.x != "year" or len(years) > 1) and (spec.x != "geography" or len(geos) > 1)
    fits = fits and (spec.series_by != "geography" or len(geos) > 1)
    fits = fits and (spec.series_by != "variable" or len(estimates) > 1)
    codes = {getattr(item, "code", "") for item in warnings or []}
    if spec.x == "year" and "overlapping_vintage" in codes:
        fits = False
    return none if not fits else {"answer": cleaned, "chart": spec, "chart_unavailable": False}
