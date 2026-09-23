"""HTTP models for POST /ask.

One boundary, one pair of models. Rows stay untyped dicts — a census row that
becomes five models through five layers is how the predecessor grew. Alternatives
and warnings are typed because the TypeScript client (slice 2) generates from
this schema; `urls[]` is one redacted Census URL per attempted request, or the
built URL when every vintage is omitted.
"""

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
    reason: str = Field(
        description="How this table differs: universe, distribution versus median, "
        "collapsed table, race iteration, or related table."
    )


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


_UNSAFE_TITLE = re.compile(r"<\s*(?:svg|script|iframe)\b|javascript:|on\w+\s*=", re.I)


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


class AskResponse(BaseModel):
    answer: str = Field(description="Natural-language answer.")
    urls: list[str] = Field(
        description=(
            "Key-redacted Census API URLs, one per attempted request, in requested order. "
            "When every requested vintage is omitted, this is the built URL so the request "
            "is still editable."
        )
    )
    requested_years: list[int] = Field(
        description="Years asked of fetch_data, de-duplicated in first-requested order."
    )
    attempted_years: list[int] = Field(
        description="Unique vintages for which a Census request was issued."
    )
    succeeded_years: list[int] = Field(
        description="Unique attempted vintages with at least one successful HTTP call."
    )
    failed_years: list[int] = Field(
        description="Unique attempted vintages with at least one failed or timed-out call."
    )
    omitted_years: list[int] = Field(description="Requested years that were not attempted.")
    omission_reasons: list[str] = Field(
        description="Reason code per omitted year, same order as omitted_years."
    )
    legs: list[RequestLeg] = Field(
        description="Per-request outcome in requested order, including failed legs."
    )
    rows: list[dict[str, str | None]] = Field(
        description="Census rows as returned. Each row carries GEO_ID (AFFGEOID); "
        "empty when the row is a combined total rather than a published area."
    )
    moe: list[dict[str, str | None]] = Field(
        description="Per-row 90% margins, keyed to each estimate's matching M variable."
    )
    geoid: str = Field(
        description="AFFGEOID of the selected geography; empty when many areas are returned."
    )
    universe: str = Field(description="Published universe of the selected table.")
    table_id: str = Field(description="Selected ACS table ID.")
    alternatives: list[Alternative] = Field(
        description="Related tables with the reason they differ from the selection."
    )
    comparisons: list[Comparison] = Field(
        description="Paired estimates with MOE_diff, 90% conclusion, and shared-sample flag."
    )
    warnings: list[AskWarning] = Field(
        description="Non-blocking guards: overlapping_vintage, moe_not_significant, "
        "geography_unsupported, ambiguous_place, universe_mismatch, "
        "median_not_aggregatable, moe_aggregation_degraded, zcta_not_zip, "
        "geography_not_nested, acs1_geography_ineligible, vintage_gap_2020, "
        "boundary_change_2020, measure_unavailable, variable_not_in_vintage, "
        "shared_sample."
    )
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
    if not saw:
        return none
    try:
        spec = ChartSpec.model_validate(payload)
    except ValidationError:
        return {**none, "chart_unavailable": True}
    years = {str(row.get("year") or row.get("vintage") or "") for row in rows} - {""}
    geos = {str(row.get("GEO_ID") or "") for row in rows} - {""}
    estimates = {key for row in rows for key in row if key.endswith("E") and "_" in key}
    fits = (spec.x != "year" or len(years) > 1) and (spec.x != "geography" or len(geos) > 1)
    fits = fits and (spec.series_by != "geography" or len(geos) > 1)
    fits = fits and (spec.series_by != "variable" or len(estimates) > 1)
    codes = {getattr(item, "code", "") for item in warnings or []}
    if spec.x == "year" and "overlapping_vintage" in codes:
        fits = False
    return none if not fits else {"answer": cleaned, "chart": spec, "chart_unavailable": False}
