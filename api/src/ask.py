"""The ask loop.

POST /ask calls `run_ask`. The four tools (`search_tables`, `resolve_geography`,
`build_url`, `fetch_data`) land in CC-23; this module is the seam they hang on.
"""

from __future__ import annotations

from src.contract import AskResponse


async def run_ask(question: str) -> AskResponse:
    """Return the declared contract. Empty fields until the loop can fill them."""
    _ = question
    return AskResponse(
        answer="",
        url="",
        rows=[],
        moe=[],
        geoid="",
        universe="",
        table_id="",
        alternatives=[],
        warnings=[],
    )
