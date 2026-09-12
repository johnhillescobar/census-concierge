"""HTTP models for POST /ask.

One boundary, one pair of models. Rows stay untyped dicts — a census row that
becomes five models through five layers is how the predecessor grew. Alternatives
and warnings are typed because the TypeScript client (slice 2) generates from
this schema; `url` is singular so slice 3 can grow `urls[]` without redesigning
rows.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


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


class Alternative(BaseModel):
    table_id: str = Field(description="ACS table ID.")
    reason: str = Field(
        description="How this table differs: universe, distribution versus median, "
        "collapsed table, race iteration, or related table."
    )


class AskWarning(BaseModel):
    code: str = Field(description="Machine-readable warning code.")
    detail: str = Field(description="What was raised, in one sentence.")


class AskResponse(BaseModel):
    answer: str = Field(description="Natural-language answer.")
    url: str = Field(description="Census API URL for this answer. Singular; slice 3 grows urls[].")
    rows: list[dict[str, str | None]] = Field(
        description="Census rows as returned. Each row carries GEO_ID (AFFGEOID)."
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
        description="Typed warnings. Empty until slice-1 guards land."
    )
