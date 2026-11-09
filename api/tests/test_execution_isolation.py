"""Once the model has stated its intent, execution is a function of that intent and not of the
question's wording. The model is scripted: the same tool calls and the same frame come back
whatever the user typed, so any difference between two wordings was made by our own code.

The harness proves itself with mutants: code that reads the question with a keyword, a substring
or a regex is injected, and the comparison must catch it. Differences that exist today are marked
`xfail(strict=True)` with the story that owns the fix (PLAN, Slice 6), so fixing one forces its
marker out. They are findings of this instrument, not fixes: nothing in api/src changed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import pytest
from ask_fixtures import _describe, _tools
from src import ask
from src.ask import ExecutionRecord, dispatch, run_ask
from src.tools import SearchTablesTool

SEARCH = {"id": "1", "name": "search_tables", "args": {"question": "population"}}
BUILD = {"id": "3", "name": "build_url", "args": {"table_id": "B01003"}}
FETCH = {"id": "4", "name": "fetch_data", "args": {}}


def resolve(**args: Any) -> dict[str, Any]:
    return {"id": "2", "name": "resolve_geography", "args": args}


COUNTY = [SEARCH, resolve(query="Harris County, Texas", level="county"), BUILD, FETCH]
STATE = [SEARCH, resolve(query="Harris County, Texas", level="state"), BUILD, FETCH]
# The model's report beside the loop. `named` stays empty: it is copied from the wording as the
# user wrote it, so it is the one report that legitimately differs between two wordings.
FRAME = {
    "parents": [],
    "unit": "",
    "listing": False,
    "level": "county",
    "named": [],
    "numbered": [],
    "asks_for": "data",
    "pointing": [],
}

NEUTRAL = [
    "population of Harris County, Texas",
    "How many people live in Harris County, TX?",
    "Harris County Texas headcount",
]

# Where today's code reads the wording, with the PLAN story that removes it. "unplaced" means
# no story in PLAN's table owns it yet.
CC104 = "geography execution still re-reads the question (finish.py, compare.py); CC-104"
CC129 = "time and product are still read from the question's words (vintages.py); CC-129"
UNPLACED = "guards.py reads a ZIP from the question; no PLAN story owns it (geography: CC-104/106)"


def model(calls: list[dict[str, Any]]) -> Callable[..., Any]:
    """The same turns every time: one tool call per turn, then a closing sentence."""
    turns = [{"content": "", "tool_calls": [call]} for call in calls]
    turns.append({"content": "Harris County has data.", "tool_calls": []})

    async def complete(
        messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        _ = messages
        if not tools:  # the beside-the-loop frame call
            return {"content": json.dumps(FRAME), "tool_calls": []}
        return turns.pop(0)

    return complete


async def execute(question: str, calls: list[dict[str, Any]]) -> dict[str, Any]:
    record = ExecutionRecord()
    tools = _tools(record)
    # Retrieval maps the question to a table and is the model-owned half; the table is part of the
    # fixed intent here, so it is the same whatever the wording.
    tools["search_tables"] = SearchTablesTool(
        search=lambda q, k=10: ["B01003"][:k], describe=_describe
    )
    response = await run_ask(question, complete=model(calls), tools=tools, record=record)
    return response.model_dump(mode="json")


async def differing(calls: list[dict[str, Any]], wordings: list[str]) -> list[str]:
    """Wordings whose execution is not the first wording's, down to the last field."""
    first = await execute(wordings[0], calls)
    return [w for w in wordings[1:] if await execute(w, calls) != first]


def finding(reason: str) -> Any:
    return pytest.mark.xfail(strict=True, reason=reason)


async def test_a_fixed_intent_executes_identically_under_neutral_rewordings() -> None:
    assert await differing(COUNTY, NEUTRAL) == []
    assert (await execute(NEUTRAL[0], COUNTY))["rows"]  # the run really fetched something


SCANNED = [
    pytest.param("average population of Harris County, Texas", id="a statistic"),
    pytest.param("population of Harris County, Texas if you can, thanks", id="filler"),
    pytest.param(
        "population of every tract in Harris County, Texas",
        marks=finding(CC104),
        id="a level word",
    ),
    pytest.param(
        "Harris County, Texas population compared to Dane County",
        marks=finding(CC104),
        id="a comparison",
    ),
    pytest.param(
        "population of Harris County, Texas zip code 77002", marks=finding(UNPLACED), id="a zip"
    ),
    pytest.param(
        "population of Harris County, Texas in 1-year ACS", marks=finding(CC129), id="a dataset"
    ),
    pytest.param("population of Harris County, Texas in 2022", marks=finding(CC129), id="a year"),
    pytest.param(
        "population of Harris County, Texas since 2018", marks=finding(CC129), id="an open range"
    ),
    pytest.param(
        "population of Harris County, Texas every year from 2018",
        marks=finding(CC129),
        id="a year span",
    ),
]


@pytest.mark.parametrize("wording", SCANNED)
async def test_words_that_look_like_other_intents_do_not_change_a_stated_one(wording: str) -> None:
    assert await differing(COUNTY, [NEUTRAL[0], wording]) == []


async def test_a_different_stated_intent_changes_execution_under_the_same_wording() -> None:
    county = await execute(NEUTRAL[0], COUNTY)
    state = await execute(NEUTRAL[0], STATE)
    assert county["urls"] != state["urls"]
    assert "for=county" in county["urls"][0] and "for=state" in state["urls"][0]


async def test_invalid_intent_is_sent_back_for_repair_and_never_parsed_from_the_wording() -> None:
    for wording in [NEUTRAL[0], "population of every tract in Harris County, Texas"]:
        record = ExecutionRecord(question=wording)
        tools = _tools(record)
        call = resolve(query="Harris County, Texas")  # `level` is required and missing
        out = await dispatch(tools["resolve_geography"], call, record)
        assert "failed" in out
        assert record.geography is None  # no level was invented from `tract` or `county`


@pytest.mark.parametrize(
    "wording",
    [
        NEUTRAL[1],
        pytest.param("every tract, Harris County", marks=finding(CC104), id="a level word"),
    ],
)
async def test_a_repaired_intent_executes_identically_under_any_wording(wording: str) -> None:
    repaired = [SEARCH, resolve(query="Harris County, Texas"), *COUNTY[1:]]  # first call invalid
    assert await differing(repaired, [NEUTRAL[0], wording]) == []


# --- the harness against code that reads the question ---------------------------------------------


def reads_question_in_pin(monkeypatch: pytest.MonkeyPatch, test: Callable[[str], bool]) -> None:
    original = ask.pin_tool_args

    def pinned(name: str, args: dict[str, Any], override: Any, question: str) -> dict[str, Any]:
        out = original(name, args, override, question)
        if name == "resolve_geography" and test(question):
            out = {**out, "level": "state"}
        return out

    monkeypatch.setattr(ask, "pin_tool_args", pinned)


def reads_question_in_answer(monkeypatch: pytest.MonkeyPatch, test: Callable[[str], bool]) -> None:
    original = ask.assemble

    def assembled(answer: str, record: ExecutionRecord) -> Any:
        return original(answer + (" (changed)" if test(record.question) else ""), record)

    monkeypatch.setattr(ask, "assemble", assembled)


MUTANTS = [
    pytest.param(reads_question_in_pin, lambda q: "plugh" in q.casefold(), "plugh", id="substring"),
    pytest.param(
        reads_question_in_pin, lambda q: bool(re.search(r"\bxyzzy\b", q)), "xyzzy", id="regex"
    ),
    pytest.param(
        reads_question_in_pin, lambda q: "quux" in q.casefold().split(), "quux", id="keyword"
    ),
    pytest.param(
        reads_question_in_answer, lambda q: "frob" in q.casefold(), "frob", id="late-in-the-answer"
    ),
]


@pytest.mark.parametrize(("inject", "trigger", "word"), MUTANTS)
async def test_the_harness_catches_code_that_reads_the_question(
    monkeypatch: pytest.MonkeyPatch,
    inject: Callable[..., None],
    trigger: Callable[[str], bool],
    word: str,
) -> None:
    wordings = [NEUTRAL[0], f"population of Harris County, Texas, {word}"]
    assert await differing(COUNTY, wordings) == []  # the control: unmutated code is isolated
    inject(monkeypatch, trigger)
    assert await differing(COUNTY, wordings) == [wordings[1]]
