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
    table_id: str
    reason: str


class AskWarning(BaseModel):
    code: str
    detail: str


class AskResponse(BaseModel):
    answer: str
    url: str
    rows: list[dict[str, str | None]]
    moe: list[dict[str, str | None]]
    geoid: str
    universe: str
    table_id: str
    alternatives: list[Alternative]
    warnings: list[AskWarning]
