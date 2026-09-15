"""HTTP models for POST /ask.

One boundary, one pair of models. Rows stay untyped dicts — a census row that
becomes five models through five layers is how the predecessor grew. Alternatives
and warnings are typed because the TypeScript client (slice 2) generates from
this schema; `urls[]` is one redacted Census URL per attempted vintage.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator, model_validator

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


class RequestLeg(BaseModel):
    year: int = Field(description="Vintage end year for this Census request.")
    url: str = Field(description="Key-redacted Census API URL for this year.")
    ok: bool = Field(description="Whether this HTTP call returned parseable rows.")
    status_code: int = Field(description="Census HTTP status; 0 on timeout or transport failure.")
    detail: str = Field(description="Redacted reason when ok is false; empty on success.")


class AskResponse(BaseModel):
    answer: str = Field(description="Natural-language answer.")
    urls: list[str] = Field(
        description="Key-redacted Census API URLs, one per attempted year, in requested order."
    )
    requested_years: list[int] = Field(
        description="Years asked of fetch_data, de-duplicated in first-requested order."
    )
    attempted_years: list[int] = Field(description="Years for which a Census request was issued.")
    succeeded_years: list[int] = Field(description="Attempted years whose HTTP call succeeded.")
    failed_years: list[int] = Field(description="Attempted years that failed or timed out.")
    omitted_years: list[int] = Field(description="Requested years that were not attempted.")
    legs: list[RequestLeg] = Field(
        description="Per-year outcome in requested order, including failed legs."
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
    warnings: list[AskWarning] = Field(
        description="Non-blocking guards: overlapping_vintage, moe_not_significant, "
        "geography_unsupported, ambiguous_place, universe_mismatch, "
        "median_not_aggregatable, moe_aggregation_degraded, zcta_not_zip, "
        "geography_not_nested."
    )
