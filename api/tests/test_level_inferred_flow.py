"""A level the code had to infer reaches the response as a warning, through the real tool call."""

from __future__ import annotations

from ask_fixtures import _tools
from src.ask import ExecutionRecord, dispatch
from src.guards import evaluate


async def _resolved(level: str | None) -> list[str]:
    record = ExecutionRecord(question="Cook County")
    geo = _tools(record)["resolve_geography"]
    await dispatch(
        geo, {"id": "1", "args": {"level": level, "places": ["Cook County, Illinois"]}}, record
    )
    return [warning.code for warning in evaluate(record)]


async def test_a_null_level_the_code_had_to_infer_is_warned_as_unverified() -> None:
    assert "geography_level_unverified" in await _resolved(None)


async def test_a_stated_level_run_as_stated_is_not_warned_as_unverified() -> None:
    assert "geography_level_unverified" not in await _resolved("county")
