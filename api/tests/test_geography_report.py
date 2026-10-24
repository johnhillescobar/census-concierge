"""The model's geography report is validated, never trusted: fail open, first turn only.

Scripted model, so what is under test is the code that checks the report against geography.json
and the question's own words, and the timing around the beside-the-loop split call.
"""

from __future__ import annotations

import asyncio
import json
import zlib
from typing import Any

import pytest
from ask_fixtures import ENTRIES, _tools
from src.ask import ExecutionRecord, run_ask
from src.finish import plan_split
from src.retrieval.metadata import GeoLevel

# The real geography.json row; the shared fixture table stops at tract.
BLOCK_GROUP = GeoLevel(
    "block group", "150", ("state", "county", "tract"), ("county", "tract"), "tract"
)
STOPPED = "cannot be searched"


def _reply(
    level: str | None,
    named: list[str] | None = None,
    numbered: list[str] | None = None,
    **more: Any,
) -> dict[str, Any]:
    body = {
        "parents": [],
        "unit": level,
        "listing": False,
        "level": level,
        "named": named or [],
        "numbered": numbered or [],
        **more,
    }
    return {"content": json.dumps(body), "tool_calls": []}


async def _ask(
    question: str,
    split_reply: dict[str, Any],
    *,
    split_delay: float = 0.0,
    second_turn_delay: float = 0.0,
) -> tuple[Any, ExecutionRecord]:
    record = ExecutionRecord()
    tools = _tools(record)
    tools["resolve_geography"].geo_table = lambda dataset, year: [*ENTRIES, BLOCK_GROUP]
    turns = {"n": 0}

    async def complete(
        messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        del messages
        if not openai_tools:
            await asyncio.sleep(split_delay)
            return split_reply
        turns["n"] += 1
        if turns["n"] == 1:
            call = {"id": "1", "name": "search_tables", "args": {"question": question}}
            return {"content": "", "tool_calls": [call]}
        await asyncio.sleep(second_turn_delay)
        return {"content": "done", "tool_calls": []}

    return await run_ask(question, complete=complete, tools=tools, record=record), record


@pytest.mark.parametrize(
    ("question", "level", "named"),
    [
        ("Poverty rate by tract in NYC", "tract", ["New York City, New York"]),
        ("Block group income in Los Angelas County", "block group", ["Los Angeles County"]),
        ("Median rent by tract in Cook Co.", "tract", ["Cook County, Illinois"]),
        ("Poverty by tract in the Bay Area", "tract", ["San Francisco Bay Area"]),
    ],
)
async def test_a_place_the_user_abbreviated_or_misspelled_still_counts_as_named(
    question: str, level: str, named: list[str]
) -> None:
    response, record = await _ask(question, _reply(level, named))
    assert record.timings  # the loop ran; the question was not refused
    assert STOPPED not in response.answer


async def test_a_state_the_user_never_wrote_lets_the_loop_run_by_design() -> None:
    # The cost of not matching the report against the question's words: a model that invented a
    # state for a question of bare numbers would let a trap through. That was never seen in
    # about 170 live trap trials, and the loop is exactly where it was before. Refusing instead
    # turned 38 of 60 valid "Calif."-style questions into a refusal.
    response, record = await _ask("Poverty rate by tract", _reply("tract", ["Texas"]))
    assert record.timings
    assert STOPPED not in response.answer


async def test_a_state_the_user_wrote_as_a_code_in_the_question_counts() -> None:
    question = "Tract 1201 in county 201, state 48"
    response, record = await _ask(
        question, _reply("tract", ["state 48", "county 201"], ["tract 1201"])
    )
    assert record.timings
    assert STOPPED not in response.answer


async def test_a_verdict_that_arrives_after_tools_ran_never_replaces_the_loops_answer(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr("src.finish.FRAME_WAIT_SECONDS", 0.05)
    question = "Is the poverty rate in tract 71 higher than tract 305?"
    reply = _reply("tract", [], ["tract 71", "tract 305"])  # would be a stop if it came in time
    response, record = await _ask(question, reply, split_delay=0.2, second_turn_delay=0.4)
    assert any(item["tool"] == "search_tables" for item in record.timings)  # the loop's tools ran
    assert STOPPED not in response.answer  # and a late report did not overwrite its answer


async def test_a_slow_split_call_is_not_cancelled_by_the_first_turn_wait(monkeypatch: Any) -> None:
    monkeypatch.setattr("src.finish.FRAME_WAIT_SECONDS", 0.05)
    seen: list[Any] = []

    async def spy(dispatch: Any, tools: Any, record: Any, split: Any = None) -> None:
        seen.append(await split if split else None)

    monkeypatch.setattr("src.ask.finish_tools", spy)
    reply = _reply("county", ["Ohio", "Michigan"], listing=True, parents=["Ohio", "Michigan"])
    await _ask("All counties in Ohio and Michigan", reply, split_delay=0.3)
    assert [item["parents"] for item in seen] == [["Ohio", "Michigan"]]


@pytest.mark.parametrize("parents", [1, True, 2.5, "Texas", {"a": 1}])
async def test_a_malformed_parents_field_never_fails_the_request(parents: Any) -> None:
    reply = _reply("tract", [], ["tract 71"], parents=parents)
    response, _record = await _ask("Poverty in tract 71 versus tract 305", reply)
    assert response.answer


@pytest.mark.parametrize("parents", [1, True, 2.5, "Texas", {"a": 1}])
async def test_plan_split_reports_only_list_parents_as_named(parents: Any) -> None:
    async def complete(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict:
        del messages, tools
        return _reply("tract", [], ["tract 71"], parents=parents)

    found = await plan_split("anything", complete)
    assert found is not None and found["frame"]["named"] == []


@pytest.mark.parametrize(
    ("question", "state"),
    [
        ("Poverty by tract in Calif.", "California"),
        ("Block group income in Penn", "Pennsylvania"),
        ("Median rent by tract in Mass.", "Massachusetts"),
        ("Tract income in tx", "Texas"),
        ("Median age by tract in Califronia", "California"),
        ("Tract poverty in the Lone Star State", "Texas"),
        ("Tract poverty in IN", "Indiana"),
    ],
)
async def test_a_state_written_as_a_nickname_an_abbreviation_or_a_typo_counts(
    question: str, state: str
) -> None:
    # Measured live: refusing these turned 38 of 60 valid questions into a refusal.
    level = "block group" if "Block group" in question else "tract"
    response, record = await _ask(question, _reply(level, [state]))
    assert record.timings
    assert STOPPED not in response.answer


async def test_a_place_reported_with_its_own_county_chain_still_counts_as_named() -> None:
    question = "Poverty rate for Census Tract 9501, Dane County"
    reply = _reply("tract", ["Census Tract 9501, Dane County, Wisconsin"], ["Census Tract 9501"])
    response, record = await _ask(question, reply)
    assert record.timings
    assert STOPPED not in response.answer


async def test_the_numbered_place_alone_is_still_not_a_geography_when_it_has_no_chain() -> None:
    reply = _reply("tract", ["Census Tract 9501"], ["Census Tract 9501"])
    response, record = await _ask("Poverty rate for Census Tract 9501", reply)
    assert STOPPED in response.answer
    assert record.timings == []


async def test_the_report_is_read_once_however_many_turns_use_unknown_tools(
    monkeypatch: Any,
) -> None:
    import src.ask as ask_module

    checks: list[int] = []
    real = ask_module.incomplete

    async def spy(*args: Any, **kwargs: Any) -> Any:
        checks.append(1)
        return await real(*args, **kwargs)

    monkeypatch.setattr(ask_module, "incomplete", spy)
    record = ExecutionRecord()
    tools = _tools(record)
    turns = {"n": 0}

    async def complete(messages: Any, openai_tools: Any) -> dict[str, Any]:
        del messages
        if not openai_tools:
            return _reply("county", ["Harris County"])
        turns["n"] += 1
        if turns["n"] > 3:
            return {"content": "done", "tool_calls": []}
        call = {"id": str(turns["n"]), "name": "no_such_tool", "args": {}}
        return {"content": "", "tool_calls": [call]}

    await run_ask("population of Harris County", complete=complete, tools=tools, record=record)
    assert checks == [1]  # unknown tools do not count as tool calls, so the first turn is by index


@pytest.mark.parametrize("error", [EOFError("short"), zlib.error("bad"), AttributeError("x")])
async def test_unreadable_geography_metadata_of_any_kind_never_fails_the_request(
    error: Exception,
) -> None:
    record = ExecutionRecord()
    tools = _tools(record)

    def broken(dataset: str, year: int) -> list[GeoLevel]:
        raise error

    tools["resolve_geography"].geo_table = broken

    async def complete(messages: Any, openai_tools: Any) -> dict[str, Any]:
        del messages
        if not openai_tools:
            return _reply("tract", [], ["tract 71", "tract 305"])
        return {"content": "done", "tool_calls": []}

    response = await run_ask(
        "Poverty in tract 71 versus tract 305", complete=complete, tools=tools, record=record
    )
    assert response.answer == "done" or response.answer


async def test_a_flood_of_entries_cannot_stall_the_event_loop() -> None:
    import time

    flood = [f"place {i} " + "x" * 40 for i in range(5000)]
    started = time.perf_counter()
    response, _record = await _ask(
        "Poverty by tract " + " ".join(flood), _reply("tract", [], flood)
    )
    assert time.perf_counter() - started < 3.0
    assert response.answer
