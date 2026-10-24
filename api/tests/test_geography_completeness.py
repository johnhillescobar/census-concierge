"""A question must name the geography its level needs, or it is answered at once and not searched.

The model reports the level and what the question names (the split call). Scripted here, so the
code that validates that report against geography.json is what is under test.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from ask_fixtures import ENTRIES, _tools
from src.ask import ExecutionRecord, run_ask
from src.geo_list import find_state
from src.retrieval.metadata import GeoLevel

# The real geography.json row; the shared fixture table stops at tract.
BLOCK_GROUP = GeoLevel(
    "block group", "150", ("state", "county", "tract"), ("county", "tract"), "tract"
)


def _frame(level: str | None, named: list[str], *, listing: bool = False) -> dict[str, Any]:
    reply = {"parents": [], "unit": level, "listing": listing, "level": level, "named": named}
    return {"content": json.dumps(reply), "tool_calls": []}


async def _ask(
    question: str, split_reply: dict[str, Any]
) -> tuple[Any, ExecutionRecord, list[str]]:
    record = ExecutionRecord()
    tools = _tools(record)
    tools["resolve_geography"].geo_table = lambda dataset, year: [*ENTRIES, BLOCK_GROUP]
    fetched: list[str] = []
    inner = tools["fetch_data"].http_get
    tools["fetch_data"].http_get = lambda url: (fetched.append(url), inner(url))[1]
    turns = {"n": 0}

    async def complete(
        messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        del messages
        if not openai_tools:
            return split_reply
        turns["n"] += 1
        if turns["n"] > 1:
            return {"content": "done", "tool_calls": []}
        call = {"id": "1", "name": "search_tables", "args": {"question": question}}
        return {"content": "", "tool_calls": [call]}

    response = await run_ask(question, complete=complete, tools=tools, record=record)
    return response, record, fetched


@pytest.mark.parametrize(
    ("question", "level", "needs"),
    [
        ("Is the poverty rate in tract 71 higher than tract 305?", "tract", ("state", "county")),
        ("Is block group 4 larger than block group 9 or block group 2?", "block group", ("tract",)),
        ("Which is bigger, county 15 or county 33 or county 8?", "county", ("state",)),
        ("give me the 12 tract", "tract", ("state", "county")),
    ],
)
async def test_no_geography_named_is_answered_at_once_and_never_searched(
    question: str, level: str, needs: tuple[str, ...]
) -> None:
    response, record, fetched = await _ask(question, _frame(level, []))
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert response.urls == [] and response.rows == [] and response.alternatives == []
    assert record.timings == [] and fetched == []  # no tool ran, nothing was fetched
    assert level in response.answer and all(part in response.answer for part in needs)
    assert find_state(response.answer) is None  # code wrote it; no state, county or place invented


async def test_a_place_the_model_remembers_but_the_user_never_wrote_is_not_a_geography() -> None:
    question = "Is the poverty rate in tract 71 higher than tract 305?"
    response, record, _fetched = await _ask(question, _frame("tract", ["Texas", "Harris County"]))
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert record.timings == []


async def test_a_state_the_user_wrote_is_a_geography_even_if_the_model_omits_it() -> None:
    question = "Is the poverty rate in tract 71 higher than tract 305 in Texas?"
    response, record, _fetched = await _ask(question, _frame("tract", []))
    assert record.timings  # the loop ran
    assert "cannot be searched" not in response.answer


async def test_a_named_geography_lets_the_loop_run() -> None:
    question = "What is the population of Harris County, Texas?"
    _response, record, _fetched = await _ask(question, _frame("county", ["Harris County"]))
    assert record.timings


async def test_every_county_lists_under_a_wildcard_state_so_it_is_not_incomplete() -> None:
    _response, record, _fetched = await _ask(
        "Population by county", _frame("county", [], listing=True)
    )
    assert record.timings


async def test_every_tract_needs_a_county_so_a_nationwide_listing_is_incomplete() -> None:
    response, record, _fetched = await _ask(
        "Population by tract", _frame("tract", [], listing=True)
    )
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert record.timings == []


@pytest.mark.parametrize("level", ["state", "zcta", None])
async def test_levels_that_need_no_parent_are_never_incomplete(level: str | None) -> None:
    _response, record, _fetched = await _ask("Total population", _frame(level, []))
    assert record.timings


async def test_no_verdict_from_the_model_means_the_loop_runs_as_usual() -> None:
    garbled = {"content": "not json at all", "tool_calls": []}
    _response, record, _fetched = await _ask("Poverty in tract 71 versus tract 305", garbled)
    assert record.timings
