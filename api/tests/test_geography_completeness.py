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
from src.geo import detect_level
from src.geo_list import find_state
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


TRACTS = ["tract 71", "tract 305"]
Q_TRACTS = "Is the poverty rate in tract 71 higher than tract 305"
Q_BLOCKS = "Is block group 4 larger than block group 9"
Q_COUNTIES = "Which is bigger, county 15 or county 33"
BGS, COUNTIES = ["block group 4", "block group 9"], ["county 15", "county 33"]

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
        ["tract 5871", "county 201"],
        False,
        (),
    ),
    # every tract or block group in a county given by number: the number carries the county, and
    # the unit listed is never asked for its own number
    ("Poverty by tract in county 5 of Ohio", "tract", ["Ohio"], ["county 5"], False, ()),
    ("Rent by block group in county 5 of Ohio", "block group", ["Ohio"], ["county 5"], False, ()),
    ("Rent by block group in county 5", "block group", [], ["county 5"], False, ("state",)),
    # every block group inside a tract given by number: the tract number needs its county and state
    (
        "Income by block group in tract 1201 of Ohio",
        "block group",
        ["Ohio"],
        ["tract 1201"],
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
        [*BGS, "tract 1201"],
        True,
        (),
    ),
    # levels that list with no parent at all, and a question that asks about no level
    ("Population by county", "county", [], [], False, ()),
    ("Total population", None, [], [], False, ()),
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
    assert find_state(response.answer) is None  # code wrote it; no state or county invented


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
            _frame("block group", [], ["county 5"]),
            "every block group in a county identified by its number needs state, and it names "
            "no geography. Name the state and ask again.",
        ),
        (
            "Rent by block group in tract 1201 of Ohio",
            _frame("block group", ["Ohio"], ["tract 1201"]),
            "every block group in a tract identified by its number needs state and county, and "
            "it names only the state. Name the county and ask again.",
        ),
        (
            "What is the median age in my county?",
            _frame("county", [], pointing=["my county"]),
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
    reply = _frame("tract", TRACTS, TRACTS)
    response, record, _fetched = await _ask(f"{Q_TRACTS}?", reply)
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert "names no geography" in response.answer  # the numbers did not pass for a state
    assert record.timings == []


async def test_a_number_the_user_never_wrote_is_not_a_place_when_filed_under_named() -> None:
    ref = f"tract {_novel_codes(15, 1)[0]}"  # in no question: the model made it up
    response, record, _fetched = await _ask("Population by tract", _frame("tract", [ref], [ref]))
    assert STOPPED in response.answer
    assert record.timings == []


async def test_a_number_that_is_only_the_start_of_one_the_user_wrote_is_not_theirs() -> None:
    # "county 1" and "county 3" are the first characters of "county 15" and "county 33".
    reply = _frame("county", [], ["county 1", "county 3"])
    _response, record, _fetched = await _ask("Which is bigger, county 15 or county 33?", reply)
    assert record.timings


async def test_a_number_the_user_never_wrote_cannot_make_a_question_incomplete() -> None:
    invented = f"county {_novel_codes(6, 1)[0]}"  # the model reports it; "by county" never says it
    _response, record, _fetched = await _ask(
        "Population by county", _frame("county", [], [invented])
    )
    assert record.timings


async def test_a_number_written_in_words_is_not_one_the_user_wrote_verbatim() -> None:
    # "county fifteen" reported as "county 15": it cannot refuse a county question, which lists
    # under state:* anyway.
    question = "Which is bigger, county fifteen or county thirty-three?"
    _response, record, _fetched = await _ask(question, _frame("county", [], COUNTIES))
    assert record.timings


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


@pytest.mark.parametrize("report", [None, {}, {"frame": None}])
async def test_without_a_usable_report_nothing_is_stopped(report: Any) -> None:
    record = ExecutionRecord(question="Population by tract")
    done: asyncio.Future[dict[str, Any] | None] = asyncio.get_running_loop().create_future()
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


async def _split(**fields: Any) -> dict[str, Any] | None:
    async def complete(
        messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        del messages, openai_tools
        return {"content": json.dumps(fields), "tool_calls": []}

    return await finish.plan_split("any question", complete)


def _shape(**over: Any) -> dict[str, Any]:
    return {
        "frame": {
            "level": None,
            "named": [],
            "numbered": [],
            "asks_for": None,
            "county_named": False,
            "pointing": [],
            **over,
        }
    }


async def test_the_split_report_always_carries_the_level_and_the_places_it_found() -> None:
    found = await _split(
        parents=[],
        unit="tract",  # the kind of row wanted is not the level asked about
        listing=False,
        level="county",
        named=["Dane County, Wisconsin"],
        numbered=["county 7301"],
        county_named=True,
        asks_for="data",
    )
    assert found == _shape(
        level="county",
        named=["Dane County, Wisconsin"],
        numbered=["county 7301"],
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
    assert found is not None and found["frame"]["county_named"] is reported


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
    assert finish._NEEDS.get((detect_level(row) or "", single), ()) == derived


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
            _frame("block group", ["1400000US5502"], ["block group 1"]),
            "county",
        ),
        # a state GEOID encodes the state and no county
        (
            f"Poverty in tract 71 of {GEOID_STATE}",
            _frame("tract", [GEOID_STATE], ["tract 71"]),
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
        ("What is the median age in my county?", _frame("county", [], pointing=["my county"])),
        ("Population of where I live", _frame(None, [], pointing=["where I live"])),
        (
            "Compare my county with Harris County, Texas",
            _frame(
                "county",
                ["Harris County, Texas"],
                county_named=True,
                pointing=["my county"],
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
    assert find_state(response.answer) is None  # code wrote it; no place was guessed


@pytest.mark.parametrize(
    ("question", "pointing"),
    [
        ("Population of Harris County, Texas", ["my county"]),  # the user never wrote it
        ("Population of Smyth County, Virginia", ["my"]),  # a piece of another word
        ("Population of Harris County, Texas", ["", " ", "-"]),  # nothing to look for
        ("Population of Harris County, Texas", [7, None, {"a": "my county"}]),  # not text
    ],
)
async def test_a_pointing_phrase_the_user_did_not_write_cannot_refuse_a_question(
    question: str, pointing: list[Any]
) -> None:
    frame = _frame("county", ["Harris County, Texas"], county_named=True, pointing=pointing)
    response, record, _fetched = await _ask(question, frame)
    assert record.timings
    assert STOPPED not in response.answer


async def test_a_pointing_phrase_on_an_empty_question_is_judged_on_the_report_alone() -> None:
    record = ExecutionRecord(question="")
    done: asyncio.Future[dict[str, Any] | None] = asyncio.get_running_loop().create_future()
    done.set_result({"frame": {"level": "county", "pointing": [""]}})
    assert await finish.incomplete(record, done) is None


async def test_pointing_phrases_past_the_cap_are_not_read() -> None:
    padding = [f"phrase {n}" for n in range(finish.MAX_REPORTED)]
    frame = _frame("county", [], pointing=[*padding, "my county"])
    _response, record, _fetched = await _ask("What is the median age in my county?", frame)
    assert record.timings  # the phrase is past the cap, so the report is not read that far


async def test_a_question_that_asks_which_table_holds_something_may_point_at_a_place() -> None:
    frame = _frame("county", [], asks_for="tables", pointing=["my county"])
    response, record, _fetched = await _ask("Which table has median age for my county?", frame)
    assert record.timings and STOPPED not in response.answer
    assert record.tables_only is True


async def test_the_split_report_carries_pointing_phrases_as_a_list() -> None:
    found = await _split(level="county", pointing=["my county"])
    assert found == _shape(level="county", pointing=["my county"])
    for sent in ("my county", 7, None, {"a": "my county"}):
        found = await _split(level="county", pointing=sent)
        assert found is not None and found["frame"]["pointing"] == []
