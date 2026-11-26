"""A question must carry what its geography level needs, or it is answered at once and not searched.

The model reports the level, the places the question names, the places it identifies only by a
number inside another place, and whether a county is named (the split call). Scripted here, so the
code that compares that report with what the Census API accepts for the kind of question is what is
under test. Every row of the needs table was measured against the live API (ACS 5-year 2023).
"""

from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
from typing import Any

import pytest
from ask_fixtures import DANE, ENTRIES, _tools, only_dane
from src import finish
from src.ask import ExecutionRecord, run_ask
from src.contract import ResultPlan
from src.geo_level import GeoIntent, level_name
from src.geo_list import state_of
from src.retrieval.metadata import GeoLevel

GOLDEN = (Path(__file__).resolve().parents[2] / "evals" / "golden_questions.toml").read_text(
    encoding="utf-8"
)
STOPPED = "cannot be searched"

# The real geography.json row; the shared fixture table stops at tract.
BLOCK_GROUP = GeoLevel(
    "block group", "150", ("state", "county", "tract"), ("county", "tract"), "tract"
)


def _frame(
    level: str | None,
    named: list[str],
    numbered: list[str] | None = None,
    *,
    county_named: bool = False,
    **more: Any,
) -> dict[str, Any]:
    reply = {
        "parents": [],
        "unit": level,
        "listing": False,  # never trusted: the verdict follows the report's level and places
        "level": level,
        "named": named,
        "numbered": numbered or [],
        "county_named": county_named,
        **more,
    }
    return {"content": json.dumps(reply), "tool_calls": []}


async def _run(
    question: str,
    split_reply: dict[str, Any],
    *,
    steps: list[tuple[str, dict[str, Any]]] | None = None,
    http_get: Any = None,
    listing: Any = None,
    split_delay: float = 0.0,
    later_turn_delay: float = 0.0,
    split_error: Exception | None = None,
    record: ExecutionRecord | None = None,
    override: ResultPlan | None = None,
) -> tuple[Any, ExecutionRecord, list[str], list[int]]:
    """Scripted model: the split call gets `split_reply`; the loop calls `steps` in order."""
    record = record or ExecutionRecord()
    tools = _tools(record)
    tools["resolve_geography"].geo_table = lambda dataset, year: [*ENTRIES, BLOCK_GROUP]
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
            if split_error is not None:
                raise split_error
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


def _novel_codes(seed: int, count: int) -> list[str]:
    """Numbers that appear in no golden question and not in the split prompt."""
    rng = random.Random(seed)
    codes: list[str] = []
    while len(codes) < count:
        code = str(rng.randint(400, 9999))
        if code not in GOLDEN and code not in finish._SPLIT_PARENTS and code not in codes:
            codes.append(code)
    return codes


TRACTS = ["tract", "tract"]
Q_TRACTS = "Is the poverty rate in tract 71 higher than tract 305"
Q_BLOCKS = "Is block group 4 larger than block group 9"
Q_COUNTIES = "Which is bigger, county 15 or county 33"
BGS, COUNTIES = ["block group", "block group"], ["county", "county"]

# (question, level, named, numbered, county_named, what the question lacks; () = answerable)
# A listing wants every unit in the parents; "by number" is one unit its number alone cannot find.
CASES = [
    # every tract / block group: the state is all the wildcards cannot supply
    ("Population by tract", "tract", [], [], False, ("state",)),
    ("Population by tract in Texas", "tract", ["Texas"], [], False, ()),
    ("Poverty by tract in Franklin County", "tract", ["Franklin County, Ohio"], [], True, ()),
    ("Income by block group", "block group", [], [], False, ("state",)),
    ("Income by block group in Wyoming", "block group", ["Wyoming"], [], False, ()),
    # one county by number: the state
    (f"{Q_COUNTIES}?", "county", [], COUNTIES, False, ("state",)),
    (f"{Q_COUNTIES} in Ohio?", "county", ["Ohio"], COUNTIES, False, ()),
    # one tract by number: state and county ("ambiguous geography" without both)
    (f"{Q_TRACTS}?", "tract", [], TRACTS, False, ("state", "county")),
    (f"{Q_TRACTS} in Kentucky?", "tract", ["Kentucky"], TRACTS, False, ("county",)),
    (
        f"{Q_TRACTS} in Franklin County, KY?",
        "tract",
        ["Franklin County, Kentucky"],
        TRACTS,
        True,
        (),
    ),
    (
        "Tract 5871 in county 201, state 21",
        "tract",
        ["state 21"],
        ["tract", "county"],
        False,
        (),
    ),
    # every tract or block group in a county given by number: the number carries the county, and
    # the unit listed is never asked for its own number
    ("Poverty by tract in county 5 of Ohio", "tract", ["Ohio"], ["county"], False, ()),
    ("Rent by block group in county 5 of Ohio", "block group", ["Ohio"], ["county"], False, ()),
    ("Rent by block group in county 5", "block group", [], ["county"], False, ("state",)),
    # every block group inside a tract given by number: the tract number needs its county and state
    (
        "Income by block group in tract 1201 of Ohio",
        "block group",
        ["Ohio"],
        ["tract"],
        False,
        ("county",),
    ),
    # one block group by number: state, county and tract
    (f"{Q_BLOCKS}?", "block group", [], BGS, False, ("state", "county", "tract")),
    (
        f"{Q_BLOCKS} in Franklin County, KY?",
        "block group",
        ["Franklin County, Kentucky"],
        BGS,
        True,
        ("tract",),
    ),
    (
        f"{Q_BLOCKS} of tract 1201 in Franklin County, KY?",
        "block group",
        ["Franklin County, Kentucky"],
        [*BGS, "tract"],
        True,
        (),
    ),
    # levels that list with no parent at all, and a question that asks about no level
    ("Population by county", "county", [], [], False, ()),
    # a number is its own level when the model reports none
    (f"{Q_TRACTS}?", None, [], TRACTS, False, ("state", "county")),
]


@pytest.mark.parametrize(("question", "level", "named", "numbered", "county", "lacks"), CASES)
async def test_a_question_is_answerable_exactly_when_it_carries_what_its_level_needs(
    question: str,
    level: str | None,
    named: list[str],
    numbered: list[str],
    county: bool,
    lacks: tuple[str, ...],
) -> None:
    reply = _frame(level, named, numbered, county_named=county)
    response, record, fetched = await _ask(question, reply)
    if not lacks:
        assert record.timings  # the loop ran
        assert STOPPED not in response.answer
        return
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert response.urls == [] and response.rows == [] and response.alternatives == []
    assert record.timings == [] and fetched == []  # no tool ran, nothing was fetched
    expected = level or "tract"
    assert expected in response.answer and expected in response.warnings[0].detail
    assert all(part in response.answer for part in lacks)
    assert state_of(response.answer) is None  # code wrote it; no state or county invented


async def test_a_question_with_no_place_and_no_level_is_refused_before_any_tool_runs() -> None:
    response, record, fetched = await _ask("Total population", _frame(None, []))
    assert STOPPED in response.answer
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert response.urls == [] and response.rows == []
    assert record.timings == [] and fetched == []


async def test_a_question_over_several_years_that_names_none_is_refused_before_any_tool_runs() -> (
    None
):
    reply = _frame("county", ["Dane County, Wisconsin"], trend=True, years=[])
    response, record, fetched = await _ask("How has population changed in Dane County?", reply)
    assert STOPPED in response.answer and "years" in response.answer
    assert response.urls == [] and response.rows == []
    assert record.timings == [] and fetched == []


async def test_a_question_over_several_years_that_names_them_runs() -> None:
    reply = _frame("county", ["Dane County, Wisconsin"], trend=True, years=[2018, 2022])
    response, record, _ = await _ask("Population of Dane County, 2018 to 2022", reply)
    assert STOPPED not in response.answer
    assert record.timings


async def test_a_question_that_names_no_years_runs_unless_the_report_says_it_spans_years() -> None:
    reply = _frame("county", ["Dane County, Wisconsin"], years=[])  # no trend flag at all
    response, record, _ = await _ask("Population of Dane County", reply)
    assert STOPPED not in response.answer
    assert record.timings


async def test_a_report_with_no_parents_list_has_not_answered_the_place_question() -> None:
    assert (await _split(level="county")).answered_places is False
    assert (await _split(parents="Ohio")).answered_places is False  # not a list
    assert (await _split(parents=[])).answered_places is True


def test_the_report_gives_the_intent_its_trend_its_places_answer_and_the_states_it_wrote() -> None:
    intent = GeoIntent()
    intent.adopt(_shape(answered_places=True, trend=True, states_named=["OH", "Texas"]))
    assert intent.answered_places is True and intent.trend is True
    assert intent.states_named == ["OH", "Texas"]
    assert GeoIntent().states_named is None  # unknown until a report says otherwise


async def test_only_a_true_flag_is_a_trend_and_only_a_list_of_strings_names_states() -> None:
    sent = await _split(parents=["Ohio"], trend="yes", states_named=["OH", 5, "Ohio"])
    assert sent.trend is False and sent.states_named == ["OH", "Ohio"]
    bad = await _split(parents=["Ohio"], trend=True, states_named="OH")
    assert bad.trend is True and bad.states_named is None
    assert (await _split(parents=["Ohio"])).states_named is None  # unknown, never "none named"


NO_PLACE_STEPS = [
    ("search_tables", {"question": "median gross rent"}),
    ("resolve_geography", {"level": None, "places": []}),
    ("build_url", {"table_id": "B25064"}),
    ("fetch_data", {}),
]
EMPTY_REPORT = {"content": "{}", "tool_calls": []}  # a report that says nothing: the loop runs


@pytest.mark.parametrize("report", [EMPTY_REPORT, {"content": "not json", "tool_calls": []}])
async def test_a_comparison_that_names_no_place_ends_with_a_message_and_no_national_fetch(
    report: dict[str, Any],
) -> None:
    response, record, fetched, _ = await _run(
        "Is median gross rent higher in one city than another?", report, steps=NO_PLACE_STEPS
    )
    assert response.urls == [] and response.rows == []
    assert fetched == [] and record.geographies == [] and record.url is None
    assert response.answer.startswith("Nothing was fetched because no place was resolved")
    assert "geography_level_mismatch" not in [w.code for w in response.warnings]


@pytest.mark.parametrize("attempt", NO_PLACE_STEPS[2:], ids=["build", "fetch"])
async def test_either_attempt_with_no_place_is_told_no_place_was_resolved(
    attempt: tuple[str, dict[str, Any]],
) -> None:
    steps = [*NO_PLACE_STEPS[:2], attempt]
    response, record, fetched, _ = await _run(
        "Median gross rent somewhere", EMPTY_REPORT, steps=steps
    )
    assert fetched == [] and response.urls == [] and record.url is None
    assert response.answer.startswith("Nothing was fetched because no place was resolved")


async def test_the_nation_is_fetched_only_when_the_model_states_it() -> None:
    steps = [*NO_PLACE_STEPS[:1], ("resolve_geography", {"level": "us", "places": []})]
    response, record, fetched, _ = await _run(
        "Median gross rent of the nation", EMPTY_REPORT, steps=[*steps, *NO_PLACE_STEPS[2:]]
    )
    assert len(fetched) == 1 and "for=us" in fetched[0]
    assert response.urls and not response.answer.startswith("Nothing was fetched")


async def test_a_question_about_which_table_holds_something_is_never_told_nothing_was_fetched() -> (
    None
):
    reply = _frame(None, [], asks_for="tables")
    response, record, fetched = await _ask("Which table holds median gross rent?", reply)
    assert fetched == [] and record.url is None and record.timings
    assert not response.answer.startswith("Nothing was fetched")


async def test_an_ambiguous_name_is_resolved_once_and_the_repair_does_not_guess_again() -> None:
    steps = [
        ("search_tables", {"question": "population"}),
        (
            "resolve_geography",
            {"places": ["Springfield", "Texas"], "level": None, "levels": ["place", "state"]},
        ),
    ]
    reply = _frame("place", [], parents=["Springfield", "Texas"])
    response, record, fetched, _ = await _run("Springfield versus Texas", reply, steps=steps)
    assert record.geo_status["ambiguous"] is True and fetched == []
    asked = [tick["tool"] for tick in record.timings]
    assert asked.count("resolve_geography") == 1  # the repair never re-resolves an ambiguous name


async def test_a_place_name_matching_several_places_is_refused_with_its_candidates() -> None:
    steps = [
        ("search_tables", {"question": "population"}),
        ("resolve_geography", {"places": ["Springfield"], "level": "place"}),
        ("build_url", {"table_id": "B01003"}),
        ("fetch_data", {}),
    ]
    response, record, fetched, _ = await _run(
        "Population of Springfield", _frame("place", ["Springfield"]), steps=steps
    )
    assert response.urls == [] and response.rows == [] and fetched == []
    assert record.geography is None and record.geo_status["ambiguous"] is True
    assert response.answer.startswith(
        "Nothing was fetched: the question needs more geographic detail"
    )
    assert not any(ch.isdigit() for ch in response.answer)
    warning = next(w for w in response.warnings if w.code == "ambiguous_place")
    assert len(warning.candidates) == 3


async def test_a_candidate_of_an_ambiguous_name_cannot_be_built_by_passing_its_for_spec() -> None:
    steps = [
        ("search_tables", {"question": "population"}),
        ("resolve_geography", {"places": ["Springfield"], "level": "place"}),
        (
            "build_url",
            {"table_id": "B01003", "for_spec": "place:72000", "in_spec": "state:17"},
        ),
        ("fetch_data", {}),
    ]
    response, record, fetched, _ = await _run(
        "Population of Springfield", _frame("place", ["Springfield"]), steps=steps
    )
    assert record.geo_status["ambiguous"] is True and record.url is None
    assert response.urls == [] and response.rows == [] and fetched == []


async def test_a_comparison_missing_one_place_is_refused_not_answered_with_the_other() -> None:
    steps = [
        ("search_tables", {"question": "population"}),
        ("resolve_geography", {"places": ["Chicago, IL", "Zzyzx, TX"], "level": "place"}),
        ("build_url", {"table_id": "B01003"}),
        ("fetch_data", {}),
    ]
    reply = _frame("place", ["Chicago, IL", "Zzyzx, TX"])
    response, record, fetched, _ = await _run("Compare Chicago and Zzyzx", reply, steps=steps)
    assert response.urls == [] and response.rows == [] and fetched == []
    warning = next(w for w in response.warnings if w.code == "geography_unsupported")
    assert "Zzyzx, TX" in warning.detail and "Chicago" not in warning.detail


async def test_a_name_matching_exactly_one_place_resolves_without_its_state() -> None:
    steps = [
        ("search_tables", {"question": "population"}),
        ("resolve_geography", {"places": ["Chicago"], "level": "place"}),
        ("build_url", {"table_id": "B01003"}),
        ("fetch_data", {}),
    ]
    response, record, fetched, _ = await _run(
        "Population of Chicago", _frame("place", ["Chicago"]), steps=steps
    )
    assert len(fetched) == 1 and response.urls and response.rows
    assert not response.answer.startswith("Nothing was fetched")


async def test_a_which_table_answer_with_no_report_keeps_the_models_own_text() -> None:
    steps = [("search_tables", {"question": "which table has median rent"})]
    response, record, fetched, _ = await _run(
        "Which table has median rent?", EMPTY_REPORT, steps=steps
    )
    assert response.answer == "done"  # nothing was built or fetched, and nothing was attempted
    assert fetched == [] and response.urls == []


async def test_a_nation_the_model_states_is_not_a_missing_place() -> None:
    response, record, fetched = await _ask("Total population of the nation", _frame("us", []))
    assert STOPPED not in response.answer
    assert record.timings  # the loop ran


async def test_a_report_that_names_a_level_but_no_place_is_a_listing_not_a_refusal() -> None:
    response, record, fetched = await _ask("Population by state", _frame("state", []))
    assert STOPPED not in response.answer
    assert record.timings


@pytest.mark.parametrize(
    ("question", "reply", "said"),
    [
        (
            "Population by tract",
            _frame("tract", []),
            "every tract needs state, and it names no geography. Name the state and ask again.",
        ),
        (
            f"{Q_TRACTS} in Kentucky?",
            _frame("tract", ["Kentucky"], TRACTS),
            "a tract identified by its number needs state and county, and it names only the "
            "state. Name the county and ask again.",
        ),
        (
            f"{Q_BLOCKS}?",
            _frame("block group", [], BGS),
            "a block group identified by its number needs state, county and tract, and it names "
            "no geography. Name the state, county and tract and ask again.",
        ),
        (
            f"{Q_BLOCKS} in Franklin County, KY?",
            _frame("block group", ["Franklin County, Kentucky"], BGS, county_named=True),
            "a block group identified by its number needs state, county and tract, and it names "
            "only the state and county. Name the tract and ask again.",
        ),
        (
            "Rent by block group in county 5",
            _frame("block group", [], ["county"]),
            "every block group in a county identified by its number needs state, and it names "
            "no geography. Name the state and ask again.",
        ),
        (
            "Rent by block group in tract 1201 of Ohio",
            _frame("block group", ["Ohio"], ["tract"]),
            "every block group in a tract identified by its number needs state and county, and "
            "it names only the state. Name the county and ask again.",
        ),
        (
            "What is the median age in my county?",
            _frame("county", [], pointing=True),
            "it is about a place it does not name. Name the place, with its state, and ask again.",
        ),
    ],
)
async def test_the_answer_says_what_the_question_needs_what_it_names_and_what_it_lacks(
    question: str, reply: dict[str, Any], said: str
) -> None:
    response, _record, _fetched = await _ask(question, reply)
    assert response.answer == f"This question is incomplete and cannot be searched: {said}"


async def test_a_number_the_model_files_under_named_is_still_not_a_name() -> None:
    reply = _frame("tract", ["tract 71", "tract 305"], TRACTS)
    response, record, _fetched = await _ask(f"{Q_TRACTS}?", reply)
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert "names no geography" in response.answer  # the numbers did not pass for a state
    assert record.timings == []


async def test_a_number_the_user_never_wrote_is_not_a_place_when_filed_under_named() -> None:
    ref = f"tract {_novel_codes(15, 1)[0]}"  # the model made it up, and filed it under named
    response, record, _fetched = await _ask(
        "Population by tract", _frame("tract", [ref], ["tract"])
    )
    assert STOPPED in response.answer
    assert "names no geography" in response.answer  # the made-up number gave no state
    assert record.timings == []


async def test_no_verdict_from_the_model_means_the_loop_runs_as_usual() -> None:
    garbled = {"content": "not json at all", "tool_calls": []}
    _response, record, _fetched = await _ask("Poverty in tract 71 versus tract 305", garbled)
    assert record.timings


# --- fail open: nothing the model does wrong refuses an answer ---------------------------------


@pytest.mark.parametrize("failure", [RuntimeError("boom"), KeyError("missing"), TypeError("bad")])
async def test_a_split_call_that_raises_anything_never_fails_the_request(
    failure: Exception,
) -> None:
    response, record, _fetched, calls = await _run(
        "Population by tract in Texas", _frame("tract", ["Texas"]), split_error=failure
    )
    assert calls == [1] and record.timings  # the call was made, failed, and the loop ran on
    assert STOPPED not in response.answer


@pytest.mark.parametrize("failure", [OSError("down"), ValueError("bad"), RuntimeError("boom")])
async def test_a_split_task_that_raised_means_the_loop_runs_as_usual(failure: Exception) -> None:
    async def broken() -> dict[str, Any] | None:
        raise failure

    record = ExecutionRecord(question="Population by tract")
    assert await finish.incomplete(record, asyncio.ensure_future(broken())) is None
    assert record.geo_status is None


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
    assert STOPPED not in response.answer


@pytest.mark.parametrize("report", [None, GeoIntent(), GeoIntent(reported=True)])
async def test_without_a_usable_report_nothing_is_stopped(report: Any) -> None:
    record = ExecutionRecord(question="Population by tract")
    done: asyncio.Future[GeoIntent | None] = asyncio.get_running_loop().create_future()
    done.set_result(report)
    assert await finish.incomplete(record, done) is None
    assert await finish.incomplete(record, None) is None
    assert record.geo_status is None


async def test_a_pinned_plan_that_names_the_places_is_never_checked_or_split() -> None:
    plan = ResultPlan(table_id="B17001", geographies=[DANE])
    refs = [f"tract {code}" for code in _novel_codes(11, 2)]
    response, record, _fetched, split_calls = await _run(
        "Is " + " bigger than ".join(refs) + "?",
        _frame("tract", [], refs),
        override=plan,
    )
    assert split_calls == [] and record.timings
    assert STOPPED not in response.answer


async def test_a_pinned_plan_with_no_places_does_not_excuse_the_question() -> None:
    # A plan that only picks a table names no geography, so the question still has to.
    plan = ResultPlan(table_id="B17001")
    response, record, _fetched, split_calls = await _run(
        "Population by tract", _frame("tract", []), override=plan
    )
    assert split_calls == [1]
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert record.timings == []


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
    assert STOPPED not in response.answer


# --- what the model's report is allowed to look like -------------------------------------------


async def _split(**fields: Any) -> GeoIntent | None:
    async def complete(
        messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        del messages, openai_tools
        return {"content": json.dumps(fields), "tool_calls": []}

    return await finish.plan_split("any question", complete)


def _shape(**over: Any) -> GeoIntent:
    return GeoIntent(reported=True, **over)


async def test_the_split_report_always_carries_the_level_and_the_places_it_found() -> None:
    found = await _split(
        parents=[],
        unit="tract",  # the kind of row wanted is not the level asked about
        listing=False,
        level="county",
        named=["Dane County, Wisconsin"],
        numbered=["county"],
        county_named=True,
        asks_for="data",
    )
    assert found == _shape(
        answered_places=True,
        level="county",
        named=["Dane County, Wisconsin"],
        numbered=["county"],
        county_named=True,
        asks_for="data",
    )


@pytest.mark.parametrize(
    ("sent", "reported"),
    [(True, True), (False, False), ("true", False), (1, False), (None, False), ([True], False)],
)
async def test_a_county_is_named_only_when_the_model_says_true_and_nothing_else(
    sent: Any, reported: bool
) -> None:
    found = await _split(level="tract", county_named=sent)
    assert found is not None and found.county_named is reported


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
    assert (found.parents, found.unit) == (
        ["Dane County, Wisconsin", "Sauk County, Wisconsin"],
        "tract",
    )
    assert found.named == ["Dane County, Wisconsin", "Sauk County, Wisconsin"]


@pytest.mark.parametrize("sent", ["false", "true", "yes", 1, 0, None, [True]])
async def test_only_a_true_listing_flag_makes_the_places_a_listing(sent: Any) -> None:
    found = await _split(parents=["Ohio", "Michigan"], unit="county", listing=sent, level="county")
    assert found is not None
    assert (found.parents, found.unit) == ([], None)  # a string is not the model saying yes
    assert found.places == ["Ohio", "Michigan"]


async def test_the_report_carries_the_dataset_and_years_the_model_stated() -> None:
    found = await _split(level="county", dataset="acs1", years=[2018, 2019, 2020])
    assert found is not None
    assert (found.dataset, found.years) == ("acs1", [2018, 2019, 2020])


@pytest.mark.parametrize("dataset", ["ACS1", "1-year", "acs3", 1, True, None, ["acs1"]])
async def test_a_dataset_that_is_not_a_published_product_name_is_not_reported(dataset: Any) -> None:
    found = await _split(level="county", dataset=dataset)
    assert found is not None and found.dataset is None


@pytest.mark.parametrize(
    ("sent", "kept"),
    [
        ([True, 2022, "2021", 2020.0, None, [2019], 2018], [2022, 2018]),
        (
            [10**30, -(10**7), 1999, 2101, 2000, 2100],
            [2000, 2100],
        ),  # a year the loop could never walk
        ("2022", []),
        (2022, []),
        ({"2022": 1}, []),
        (None, []),
    ],
)
async def test_only_whole_numbers_count_as_the_years_the_model_stated(
    sent: Any, kept: list[int]
) -> None:
    found = await _split(level="county", years=sent)
    assert found is not None and found.years == kept


async def test_one_parent_is_a_listing_and_still_a_frame() -> None:
    found = await _split(
        parents=["Dane County, Wisconsin"], unit="tract", listing=True, level="tract"
    )
    assert found is not None and found.parents == ["Dane County, Wisconsin"]
    assert found.named == ["Dane County, Wisconsin"]


async def test_places_of_the_wrong_type_are_ignored_not_iterated() -> None:
    found = await _split(
        unit="county", listing=False, level="county", named="Wisconsin", numbered=7
    )
    assert found == _shape(level="county")


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
        ("resolve_geography", {"level": None, "places": places}),
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
        (
            "resolve_geography",
            {"level": "tract", "parents": ["Dane County, WI"], "parent_level": "county"},
        ),
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


@pytest.mark.parametrize("single", [False, True])
@pytest.mark.parametrize("row", sorted({entry.name for entry in [*ENTRIES, BLOCK_GROUP]}))
def test_the_needs_table_is_what_the_censuss_own_metadata_says(row: str, single: bool) -> None:
    # geography.json lists, per level, the parents it takes and which of them may be a wildcard.
    # Every unit listed can leave its wildcard parents to the URL; one unit by number cannot, the
    # API refuses a wildcard for it. Measured live (ACS5 2023) to agree with every level here.
    rows = [entry for entry in [*ENTRIES, BLOCK_GROUP] if entry.name == row]
    derived = min(
        (tuple(p for p in entry.requires if single or p not in entry.wildcard) for entry in rows),
        key=len,
    )
    assert finish._NEEDS.get((level_name(row) or "", single), ()) == derived


# --- a GEOID the user wrote carries the hierarchy it encodes -----------------------------------

GEOID_TRACT = "1400000US55025000100"  # tract 000100 in Dane County (025), Wisconsin (55)
GEOID_COUNTY = "0500000US55025"
GEOID_STATE = "0400000US55"


@pytest.mark.parametrize(
    ("question", "frame"),
    [
        (
            f"Population of block group 1 in tract {GEOID_TRACT}, Dane County, Wisconsin",
            _frame("block group", [GEOID_TRACT, "Dane County, Wisconsin"], ["block group 1"]),
        ),
        (
            f"Population of block group 1 in tract {GEOID_TRACT}",
            _frame("block group", [GEOID_TRACT], ["block group 1"]),
        ),
        (
            f"Poverty in tract 71 of county {GEOID_COUNTY}",
            _frame("tract", [GEOID_COUNTY], ["tract 71"]),
        ),
    ],
)
async def test_a_geoid_the_user_wrote_supplies_the_parents_it_encodes(
    question: str, frame: dict[str, Any]
) -> None:
    response, record, _fetched = await _ask(question, frame)
    assert record.timings
    assert STOPPED not in response.answer


@pytest.mark.parametrize(
    ("question", "frame", "lacks"),
    [
        # too short to be a tract GEOID, so it encodes nothing
        (
            "Population of block group 1 in tract 1400000US5502",
            _frame("block group", ["1400000US5502"], ["block group"]),
            "county",
        ),
        # a state GEOID encodes the state and no county
        (
            f"Poverty in tract 71 of {GEOID_STATE}",
            _frame("tract", [GEOID_STATE], ["tract"]),
            "county",
        ),
    ],
)
async def test_a_geoid_supplies_only_what_it_encodes(
    question: str, frame: dict[str, Any], lacks: str
) -> None:
    response, record, fetched = await _ask(question, frame)
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert lacks in response.answer
    assert record.timings == [] and fetched == []


# --- a phrase that points at a place without naming it -----------------------------------------


@pytest.mark.parametrize(
    ("question", "frame"),
    [
        ("What is the median age in my county?", _frame("county", [], pointing=True)),
        ("Population of where I live", _frame(None, [], pointing=True)),
        (
            "Compare my county with Harris County, Texas",
            _frame(
                "county",
                ["Harris County, Texas"],
                county_named=True,
                pointing=True,
            ),
        ),
    ],
)
async def test_a_phrase_that_points_at_a_place_without_naming_it_is_refused_at_once(
    question: str, frame: dict[str, Any]
) -> None:
    response, record, fetched = await _ask(question, frame)
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert response.urls == [] and response.rows == [] and response.alternatives == []
    assert record.timings == [] and fetched == []
    assert state_of(response.answer) is None  # code wrote it; no place was guessed


async def test_a_question_that_asks_which_table_holds_something_may_point_at_a_place() -> None:
    frame = _frame("county", [], asks_for="tables", pointing=True)
    response, record, _fetched = await _ask("Which table has median age for my county?", frame)
    assert record.timings and STOPPED not in response.answer
    assert record.intent.tables_only is True


async def test_the_split_report_carries_pointing_as_a_flag_and_nothing_else() -> None:
    assert await _split(level="county", pointing=True) == _shape(level="county", pointing=True)
    for sent in ("my county", 7, None, ["my county"]):
        found = await _split(level="county", pointing=sent)
        assert found is not None and found.pointing is False


# --- the intent the split report fills: what each field carries, and when ----------------------


async def test_places_are_reported_for_a_comparison_and_parents_only_for_a_listing() -> None:
    sent = {"parents": ["Ohio", "Michigan"], "unit": "county", "parent_level": "state"}
    compared = await _split(listing=False, **sent)
    assert compared is not None
    assert (compared.places, compared.parents, compared.unit, compared.parent_level) == (
        ["Ohio", "Michigan"],
        [],
        None,
        None,
    )
    listed = await _split(listing=True, **sent)
    assert listed is not None
    assert (listed.places, listed.parents, listed.unit, listed.parent_level) == (
        [],
        ["Ohio", "Michigan"],
        "county",
        "state",
    )


@pytest.mark.parametrize(
    "sent",
    [
        {"parents": ["Ohio"], "unit": "galaxy", "parent_level": "state"},  # no unit it can split
        {"parents": [], "unit": "county", "parent_level": "state"},  # nothing to list under
    ],
)
async def test_a_listing_needs_parents_and_a_unit_it_can_split(sent: dict[str, Any]) -> None:
    found = await _split(listing=True, **sent)
    assert found is not None
    assert (found.places, found.parents, found.unit, found.parent_level) == ([], [], None, None)


@pytest.mark.parametrize("level", [7, ["state"], {"a": 1}, None])
async def test_a_parent_level_that_is_not_text_is_not_reported(level: Any) -> None:
    found = await _split(parents=["Ohio"], unit="county", listing=True, parent_level=level)
    assert found is not None and found.parents == ["Ohio"] and found.parent_level is None


async def test_the_report_incomplete_reads_stays_on_the_record_for_the_guards() -> None:
    record = ExecutionRecord(question="Which table has median age?")
    done: asyncio.Future[GeoIntent | None] = asyncio.get_running_loop().create_future()
    done.set_result(GeoIntent(reported=True, asks_for="tables", level="county"))
    assert await finish.incomplete(record, done) is None
    assert record.intent.reported is True and record.intent.tables_only is True
    assert record.intent.level == "county"
