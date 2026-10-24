"""A question must name the geography its level needs, or it is answered at once and not searched.

The model reports the level, the places the question names, and the places it identifies only by a
number inside another place (the split call). Scripted here, so the code that validates that report
against geography.json is what is under test.
"""

from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
from typing import Any

import pytest
from ask_fixtures import DANE, ENTRIES, _tools, only_dane
from src import ask as ask_module
from src import finish
from src.ask import ExecutionRecord, run_ask
from src.contract import ResultPlan
from src.geo_list import find_state
from src.retrieval.metadata import GeoLevel

GOLDEN = (Path(__file__).resolve().parents[2] / "evals" / "golden_questions.toml").read_text(
    encoding="utf-8"
)

# The real geography.json row; the shared fixture table stops at tract.
BLOCK_GROUP = GeoLevel(
    "block group", "150", ("state", "county", "tract"), ("county", "tract"), "tract"
)


def _frame(
    level: str | None, named: list[str], numbered: list[str] | None = None
) -> dict[str, Any]:
    reply = {
        "parents": [],
        "unit": level,
        "listing": False,  # never trusted: the verdict follows the metadata
        "level": level,
        "named": named,
        "numbered": numbered or [],
    }
    return {"content": json.dumps(reply), "tool_calls": []}


async def _run(
    question: str,
    split_reply: dict[str, Any],
    *,
    steps: list[tuple[str, dict[str, Any]]] | None = None,
    http_get: Any = None,
    geo_table: Any = None,
    listing: Any = None,
    split_delay: float = 0.0,
    later_turn_delay: float = 0.0,
    record: ExecutionRecord | None = None,
    override: ResultPlan | None = None,
) -> tuple[Any, ExecutionRecord, list[str], list[int]]:
    """Scripted model: the split call gets `split_reply`; the loop calls `steps` in order."""
    record = record or ExecutionRecord()
    tools = _tools(record)
    tools["resolve_geography"].geo_table = geo_table or (
        lambda dataset, year: [*ENTRIES, BLOCK_GROUP]
    )
    if listing is not None:
        tools["resolve_geography"].list_geographies = listing
    fetched: list[str] = []
    inner = http_get or tools["fetch_data"].http_get
    tools["fetch_data"].http_get = lambda url: (fetched.append(url), inner(url))[1]
    script = steps or [("search_tables", {"question": question})]
    turns: list[int] = []
    split_calls: list[int] = []

    async def complete(
        messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        del messages
        if not openai_tools:
            split_calls.append(1)
            await asyncio.sleep(split_delay)
            return split_reply
        turn = len(turns)
        turns.append(1)
        if turn and later_turn_delay:
            await asyncio.sleep(later_turn_delay)
        if turn >= len(script):
            return {"content": "done", "tool_calls": []}
        name, args = script[turn]
        return {"content": "", "tool_calls": [{"id": str(turn), "name": name, "args": args}]}

    response = await run_ask(
        question, complete=complete, tools=tools, record=record, override=override
    )
    return response, record, fetched, split_calls


async def _ask(
    question: str, split_reply: dict[str, Any]
) -> tuple[Any, ExecutionRecord, list[str]]:
    response, record, fetched, _split_calls = await _run(question, split_reply)
    return response, record, fetched


@pytest.mark.parametrize(
    ("question", "level", "numbered", "needs"),
    [
        (
            "Is the poverty rate in tract 71 higher than tract 305?",
            "tract",
            ["tract 71", "tract 305"],
            ("state", "county"),
        ),
        (
            "Is block group 4 larger than block group 9 or block group 2?",
            "block group",
            ["block group 4", "block group 9", "block group 2"],
            ("tract",),
        ),
        (
            "Which is bigger, county 15 or county 33 or county 8?",
            "county",
            ["county 15", "county 33", "county 8"],
            ("state",),
        ),
        ("give me the 12 tract", "tract", ["12 tract"], ("state", "county")),
    ],
)
async def test_no_geography_named_is_answered_at_once_and_never_searched(
    question: str, level: str, numbered: list[str], needs: tuple[str, ...]
) -> None:
    response, record, fetched = await _ask(question, _frame(level, [], numbered))
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert response.urls == [] and response.rows == [] and response.alternatives == []
    assert record.timings == [] and fetched == []  # no tool ran, nothing was fetched
    assert level in response.answer and all(part in response.answer for part in needs)
    assert find_state(response.answer) is None  # code wrote it; no state, county or place invented


async def test_places_identified_only_by_number_stop_a_level_that_would_otherwise_list() -> None:
    # "county" lists under state:*, so only the numbered places make this question incomplete.
    question = "Which is bigger, county 15 or county 33?"
    response, record, _fetched = await _ask(
        question, _frame("county", [], ["county 15", "county 33"])
    )
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert record.timings == []


async def test_a_number_the_model_files_under_named_is_still_not_a_name() -> None:
    question = "Is the poverty rate in tract 71 higher than tract 305?"
    reply = _frame("tract", ["tract 71", "tract 305"], ["tract 71", "tract 305"])
    response, record, _fetched = await _ask(question, reply)
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert record.timings == []


async def test_a_state_the_model_remembers_but_the_user_never_wrote_is_not_a_geography() -> None:
    question = "Is the poverty rate in tract 71 higher than tract 305?"
    reply = _frame("tract", ["Texas"], ["tract 71", "tract 305"])
    response, record, _fetched = await _ask(question, reply)
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert record.timings == []


async def test_a_state_the_user_wrote_is_a_geography_even_if_the_model_omits_it() -> None:
    question = "Is the poverty rate in tract 71 higher than tract 305 in Texas?"
    response, record, _fetched = await _ask(
        question, _frame("tract", [], ["tract 71", "tract 305"])
    )
    assert record.timings  # the loop ran
    assert "cannot be searched" not in response.answer


async def test_a_state_the_user_abbreviated_and_the_model_spelled_out_still_counts() -> None:
    question = "Is the poverty rate in tract 71 higher than tract 305 in TX?"
    reply = _frame("tract", ["Texas"], ["tract 71", "tract 305"])
    response, record, _fetched = await _ask(question, reply)
    assert record.timings
    assert "cannot be searched" not in response.answer


async def test_a_named_geography_lets_the_loop_run() -> None:
    question = "What is the population of Harris County, Texas?"
    _response, record, _fetched = await _ask(question, _frame("county", ["Harris County"]))
    assert record.timings


async def test_every_county_lists_under_a_wildcard_state_so_it_is_not_incomplete() -> None:
    _response, record, _fetched = await _ask("Population by county", _frame("county", []))
    assert record.timings


async def test_every_tract_needs_a_county_so_a_nationwide_listing_is_incomplete() -> None:
    response, record, _fetched = await _ask("Population by tract", _frame("tract", []))
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


# --- numbers and levels the code has never seen, taken from the metadata -----------------------

METADATA = [*ENTRIES, BLOCK_GROUP]
LEVELS = sorted({entry.name for entry in METADATA})


def _smallest_requirement(level: str) -> tuple[str, ...]:
    return min((entry.requires for entry in METADATA if entry.name == level), key=len)


def _novel_codes(seed: int, count: int) -> list[str]:
    """Numbers that appear in no golden question and not in the split prompt."""
    rng = random.Random(seed)
    codes: list[str] = []
    while len(codes) < count:
        code = str(rng.randint(400, 9999))
        if code not in GOLDEN and code not in finish._SPLIT_PARENTS and code not in codes:
            codes.append(code)
    return codes


@pytest.mark.parametrize("filed_under_named_too", [False, True])
@pytest.mark.parametrize("count", [2, 3, 4])
@pytest.mark.parametrize("level", LEVELS)
async def test_bare_numbers_at_any_metadata_level_are_stopped_exactly_when_it_needs_parents(
    level: str, count: int, filed_under_named_too: bool
) -> None:
    needs = _smallest_requirement(level)
    refs = [f"{level} {code}" for code in _novel_codes(len(level) * 7 + count, count)]
    question = "Is " + " bigger than ".join(refs) + "?"
    response, record, fetched = await _ask(
        question, _frame(level, refs if filed_under_named_too else [], refs)
    )
    if not needs:  # state and ZCTA stand on their own; there is nothing to demand
        assert record.timings and "cannot be searched" not in response.answer
        return
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert response.urls == [] and response.rows == [] and response.alternatives == []
    assert record.timings == [] and fetched == []
    assert all(part in response.answer for part in needs)
    assert level in response.warnings[0].detail
    assert find_state(response.answer) is None


async def test_the_answer_names_the_smallest_set_of_parents_the_level_can_stand_on() -> None:
    # county has two metadata rows: state alone, and a metropolitan-area form that needs three
    refs = [f"county {code}" for code in _novel_codes(5, 2)]
    question = "Is " + " or ".join(refs) + " bigger?"
    response, _record, _fetched = await _ask(question, _frame("county", [], refs))
    assert "state" in response.answer and "metropolitan" not in response.answer


async def test_a_number_the_user_never_wrote_cannot_make_a_question_incomplete() -> None:
    invented = f"county {_novel_codes(6, 1)[0]}"  # the model reports it; "by county" never says it
    _response, record, _fetched = await _ask(
        "Population by county", _frame("county", [], [invented])
    )
    assert record.timings


async def test_numbered_tracts_inside_a_named_county_are_a_complete_question() -> None:
    # No state is written, so only the named county can make this complete.
    a, b = _novel_codes(7, 2)
    question = f"Is poverty in tract {a} higher than tract {b} in Dane County?"
    reply = _frame("tract", ["Dane County, Wisconsin"], [f"tract {a}", f"tract {b}"])
    response, record, _fetched = await _ask(question, reply)
    assert record.timings
    assert "cannot be searched" not in response.answer


async def test_parents_the_model_lists_count_as_named_places() -> None:
    question = "Which tracts in Dane County and Sauk County are poorest?"
    reply = {
        "content": json.dumps(
            {
                "parents": ["Dane County, Wisconsin", "Sauk County, Wisconsin"],
                "unit": "tract",
                "listing": True,
                "level": "tract",
                "named": [],
                "numbered": [],
            }
        ),
        "tool_calls": [],
    }
    response, record, _fetched = await _ask(question, reply)
    assert record.timings
    assert "cannot be searched" not in response.answer


# --- fail open: nothing the model or the metadata does wrong refuses an answer -----------------


@pytest.mark.parametrize("failure", [OSError, ValueError, TypeError, KeyError])
async def test_unreadable_geography_metadata_means_the_loop_runs_as_usual(
    failure: type[Exception],
) -> None:
    def unreadable(dataset: str, year: int) -> list[GeoLevel]:
        raise failure("no geography metadata")

    refs = [f"tract {code}" for code in _novel_codes(8, 2)]
    response, record, _fetched, _calls = await _run(
        "Is " + " bigger than ".join(refs) + "?",
        _frame("tract", [], refs),
        geo_table=unreadable,
    )
    assert record.timings
    assert "cannot be searched" not in response.answer


async def test_a_report_that_is_late_means_the_loop_runs_as_usual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(finish, "FRAME_WAIT_SECONDS", 0.05)
    monkeypatch.setattr(finish, "SPLIT_WAIT_SECONDS", 0.05)
    refs = [f"tract {code}" for code in _novel_codes(9, 2)]
    response, record, _fetched, _calls = await asyncio.wait_for(
        _run(
            "Is " + " bigger than ".join(refs) + "?",
            _frame("tract", [], refs),
            split_delay=30.0,  # never arrives in time; the request must not wait for it
        ),
        10.0,
    )
    assert record.timings
    assert "cannot be searched" not in response.answer


async def test_a_report_that_lands_after_the_wait_does_not_overturn_a_loop_already_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(finish, "FRAME_WAIT_SECONDS", 0.05)
    refs = [f"tract {code}" for code in _novel_codes(10, 2)]
    response, record, _fetched, _calls = await _run(
        "Is " + " bigger than ".join(refs) + "?",
        _frame("tract", [], refs),
        split_delay=0.15,  # after the wait, before the second model turn finishes
        later_turn_delay=0.4,
    )
    assert record.timings  # a tool already ran under the documented fail-open
    assert "cannot be searched" not in response.answer


async def test_only_the_first_model_turn_checks_the_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checks: list[int] = []
    real = finish.incomplete

    async def spy(*args: Any, **kwargs: Any) -> str | None:
        checks.append(1)
        return await real(*args, **kwargs)

    monkeypatch.setattr(ask_module, "incomplete", spy)
    a, b = _novel_codes(14, 2)
    question = f"Is poverty in tract {a} higher than tract {b} in Dane County?"
    search = ("search_tables", {"question": question})
    reply = _frame("tract", ["Dane County, Wisconsin"], [f"tract {a}", f"tract {b}"])
    await _run(question, reply, steps=[search, search, search])
    assert checks == [1]  # four model turns ran, and only the first looked at the report


@pytest.mark.parametrize("missing", ["tool", "report"])
async def test_without_the_geography_tool_or_a_report_nothing_is_stopped(missing: str) -> None:
    record = ExecutionRecord(question="Is tract 5871 bigger than tract 6203?")
    tools = {} if missing == "tool" else _tools(record)
    report: asyncio.Future[dict[str, Any] | None] = asyncio.get_running_loop().create_future()
    report.set_result({"frame": {"level": "tract", "named": [], "numbered": ["tract 5871"]}})
    split = report if missing == "tool" else None
    assert await finish.incomplete(record, tools, split) is None
    assert record.geo_status is None


async def test_a_pinned_plan_is_never_checked_for_a_geography_in_the_question() -> None:
    plan = ResultPlan(table_id="B17001", geographies=[DANE])
    refs = [f"tract {code}" for code in _novel_codes(11, 2)]
    response, record, _fetched, split_calls = await _run(
        "Is " + " bigger than ".join(refs) + "?",
        _frame("tract", [], refs),
        override=plan,
    )
    assert split_calls == [] and record.timings
    assert "cannot be searched" not in response.answer


# --- what the model's report is allowed to look like -------------------------------------------


async def _split(**fields: Any) -> dict[str, Any] | None:
    async def complete(
        messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        del messages, openai_tools
        return {"content": json.dumps(fields), "tool_calls": []}

    return await finish.plan_split("any question", complete)


async def test_the_split_report_always_carries_the_level_and_the_places_it_found() -> None:
    found = await _split(
        parents=[],
        unit="county",
        listing=False,
        level="county",
        named=["Dane County, Wisconsin"],
        numbered=["county 7301"],
    )
    assert found == {
        "frame": {
            "level": "county",
            "named": ["Dane County, Wisconsin"],
            "numbered": ["county 7301"],
        }
    }


async def test_a_multi_parent_listing_report_carries_parents_unit_and_frame() -> None:
    found = await _split(
        parents=["Dane County, Wisconsin", "Sauk County, Wisconsin"],
        unit="tract",
        listing=True,
        level="tract",
        named=[],
        numbered=[],
    )
    assert found is not None
    assert (found["parents"], found["unit"]) == (
        ["Dane County, Wisconsin", "Sauk County, Wisconsin"],
        "tract",
    )
    assert found["frame"]["named"] == ["Dane County, Wisconsin", "Sauk County, Wisconsin"]


async def test_one_parent_is_not_a_split_but_is_still_a_frame() -> None:
    found = await _split(
        parents=["Dane County, Wisconsin"], unit="tract", listing=True, level="tract"
    )
    assert found is not None and "parents" not in found
    assert found["frame"]["named"] == ["Dane County, Wisconsin"]


async def test_places_of_the_wrong_type_are_ignored_not_iterated() -> None:
    found = await _split(
        unit="county", listing=False, level="county", named="Wisconsin", numbered=7
    )
    assert found == {"frame": {"level": "county", "named": [], "numbered": []}}


@pytest.mark.parametrize("parents", ["Wisconsin", 5, True])
async def test_a_parents_field_of_the_wrong_type_cannot_fail_the_request(parents: Any) -> None:
    a, b = _novel_codes(13, 2)
    question = f"Is poverty higher in tract {a} than in tract {b}?"
    reply = {
        "content": json.dumps(
            {"parents": parents, "unit": "tract", "listing": True, "level": "tract"}
        ),
        "tool_calls": [],
    }
    response, _record, _fetched = await _ask(question, reply)  # raises TypeError today
    assert response.warnings is not None
    found = await _split(parents=parents, unit="tract", listing=True, level="tract")
    assert found == {"frame": {"level": "tract", "named": [], "numbered": []}}


# --- grounding: a place counts only if the user wrote it ---------------------------------------


async def test_a_remembered_state_is_not_grounded_by_a_word_that_spells_its_abbreviation() -> None:
    a, b = _novel_codes(12, 2)
    question = f"Is poverty in tract {a} higher than tract {b}?"  # "in" is not Indiana
    reply = _frame("tract", ["Indiana"], [f"tract {a}", f"tract {b}"])
    response, record, _fetched = await _ask(question, reply)
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert record.timings == []


# --- a valid question is not refused: it still fetches, and its comparison carries the margins ---


def _answer_with_margins(rows: list[list[str]], header: list[str]) -> Any:
    return lambda url: (200, [header, *rows])


async def test_two_named_places_still_fetch_and_compare_with_margins() -> None:
    question = (
        "Is median gross rent higher in Chicago city, Illinois "
        "than in Los Angeles city, California?"
    )
    header = ["NAME", "B25064_001E", "B25064_001M", "GEO_ID", "state", "place"]
    chicago = ["Chicago city, Illinois", "1729", "14", "1600000US1714000", "17", "14000"]
    angeles = ["Los Angeles city, California", "1403", "9", "1600000US0644000", "06", "44000"]

    def http_get(url: str) -> tuple[int, Any]:
        return 200, [header, chicago if "place:1714000" in url else angeles]

    places = ["Chicago city, Illinois", "Los Angeles city, California"]
    steps = [
        ("search_tables", {"question": question}),
        ("resolve_geography", {"places": places}),
        ("build_url", {"table_id": "B25064"}),
        ("fetch_data", {}),
    ]
    response, _record, fetched, _calls = await _run(
        question, _frame("place", places), steps=steps, http_get=http_get
    )
    assert len(fetched) == 2 and len(response.urls) == 2  # one URL per place, both shown
    assert "geography_unsupported" not in {item.code for item in response.warnings}
    assert {row["GEO_ID"] for row in response.rows} == {chicago[3], angeles[3]}
    assert len(response.moe) == 2
    (pair,) = response.comparisons  # one column, one pair
    assert {pair.geoid_a, pair.geoid_b} == {chicago[3], angeles[3]}
    assert {pair.moe_a, pair.moe_b} == {"14", "9"} and pair.threshold
    assert pair.distinguishable is True
    assert "comparison_too_large" not in {item.code for item in response.warnings}


async def test_tracts_inside_a_named_county_still_fetch_and_compare_with_margins() -> None:
    question = "Is poverty higher in some tracts of Dane County, Wisconsin than in others?"
    header = ["NAME", "B17001_001E", "B17001_001M", "GEO_ID", "state", "county", "tract"]
    tracts = [
        [f"Tract {n}", str(1000 + 40 * n), str(30 + n), f"1400000US55025{n:06d}", "55", "025"]
        + [f"{n:06d}"]
        for n in (3, 5, 8)
    ]
    steps = [
        ("search_tables", {"question": question}),
        ("resolve_geography", {"query": "every tract in Dane County, Wisconsin"}),
        ("build_url", {"table_id": "B17001"}),
        ("fetch_data", {}),
    ]
    response, _record, fetched, _calls = await _run(
        question,
        _frame("tract", ["Dane County, Wisconsin"]),
        steps=steps,
        http_get=_answer_with_margins(tracts, header),
        listing=only_dane,
    )
    assert len(fetched) == 1 and "tract:*" in fetched[0] and "county:025" in fetched[0]
    assert response.urls and "B17001_001M" in response.urls[0]
    assert len(response.rows) == 3 and len(response.moe) == 3
    assert len(response.comparisons) == 3  # three tracts make three pairs of one column
    assert all(pair.moe_a and pair.moe_b and pair.threshold for pair in response.comparisons)
    assert "comparison_too_large" not in {item.code for item in response.warnings}
