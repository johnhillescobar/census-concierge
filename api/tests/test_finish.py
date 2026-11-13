"""Direct unit tests for finish_tools: the recovery path run at the end of
every ask loop, regardless of whether the model's own turns hit an error.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from ask_fixtures import _harris
from src.ask import ExecutionRecord, dispatch
from src.census_url import CensusURL
from src.contract import GeoSpec
from src.fetch import FetchDataTool
from src.finish import finish_tools, plan_split


def _fetch_tool(
    record: ExecutionRecord, status_code: int, estimate: str = "4838303"
) -> FetchDataTool:
    rows = [
        ["NAME", "GEO_ID", "B01003_001E", "B01003_001M", "state", "county"],
        ["Harris County, Texas", "0500000US48201", estimate, "123", "48", "201"],
    ]
    return FetchDataTool(
        last_url=lambda: record.url,
        census_key=lambda: "secret",
        question_years=lambda: [2024],
        published=lambda dataset: {2024},
        http_get=lambda url: (status_code, rows if status_code == 200 else "server error"),
    )


async def test_finish_tools_retries_fetch_after_a_failed_but_non_none_attempt() -> None:
    record = ExecutionRecord(question="population of Harris County, Texas")
    record.geographies = [_harris()]
    record.geography = record.geographies[0]
    record.url = CensusURL(
        "https://api.census.gov/data/2024/acs/acs5"
        "?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=county:201&in=state:48"
    )
    record.table_id = "B01003"
    record.pool = [{"table_id": "B01003", "title": "Total Population", "members": []}]

    failing = _fetch_tool(record, status_code=500)
    await dispatch(failing, {"id": "1", "args": {}}, record)
    assert record.fetch is not None
    assert record.fetch.ok is False

    tools = {"fetch_data": _fetch_tool(record, status_code=200)}
    await finish_tools(dispatch, tools, record)

    assert record.fetch is not None
    assert record.fetch.ok is True
    assert record.rows


async def test_finish_tools_does_not_refetch_an_already_successful_attempt() -> None:
    """A retry gate that fires unconditionally would refetch every request,
    doubling API calls for the common (already-succeeded) case."""
    record = ExecutionRecord(question="population of Harris County, Texas")
    record.geographies = [_harris()]
    record.geography = record.geographies[0]
    record.url = CensusURL(
        "https://api.census.gov/data/2024/acs/acs5"
        "?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=county:201&in=state:48"
    )
    record.table_id = "B01003"
    record.pool = [{"table_id": "B01003", "title": "Total Population", "members": []}]

    succeeding = _fetch_tool(record, status_code=200, estimate="4838303")
    await dispatch(succeeding, {"id": "1", "args": {}}, record)
    assert record.fetch is not None
    assert record.fetch.ok is True
    first_rows = record.rows

    # A different estimate: if the retry gate wrongly refires, this value would
    # show up in record.rows instead of the original successful fetch's.
    tools = {"fetch_data": _fetch_tool(record, status_code=200, estimate="9999999")}
    await finish_tools(dispatch, tools, record)

    assert record.rows == first_rows


def _wildcard(name: str, state: str) -> GeoSpec:
    return GeoSpec(level="county", name=name, for_spec="county:*", in_spec=f"state:{state}")


def _splitter(
    parents: object, level: object = "county", parent_level: object = None, dataset: object = None
) -> Any:
    async def complete(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict:
        complete.calls += 1  # type: ignore[attr-defined]
        reply = {
            "level": None,
            "parents": parents,
            "unit": level or "county",
            "listing": level is not None,
            "parent_level": parent_level,
            "dataset": dataset,
        }
        return {"content": json.dumps(reply), "tool_calls": []}

    complete.calls = 0  # type: ignore[attr-defined]
    return complete


async def _run_split(
    question: str,
    geos: list[GeoSpec],
    complete: Any,
    resolved: int = 2,
    status: dict[str, Any] | None = None,
    url: str | None = None,
    stated: list[str | None] | None = None,
    unmet: set[str] | None = None,
) -> tuple[list[dict[str, Any]], ExecutionRecord]:
    record = ExecutionRecord(question=question)
    record.intent.levels = list(stated or [])  # what the model's own geography call asked for
    record.intent.unmet = set(unmet or ())
    record.url = CensusURL(url) if url else None
    record.geographies = geos
    record.geo_status = status
    seen: list[dict[str, Any]] = []

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        seen.append(call["args"])
        rec.geographies = [_wildcard("a", "01"), _wildcard("b", "02")][:resolved]
        return ""

    await finish_tools(
        fake_dispatch,
        {"resolve_geography": object()},
        record,
        plan_split(record.question, complete),
    )
    return seen, record


async def test_listing_that_kept_one_parent_is_resolved_with_every_parent() -> None:
    complete = _splitter(["Ohio", "Michigan"])
    seen, _ = await _run_split(
        "List every county in Ohio and Michigan.", [_wildcard("m", "26")], complete
    )
    assert seen == [{"parents": ["Ohio", "Michigan"], "parent_level": None, "level": "county"}]


async def test_listing_resolved_at_the_wrong_level_is_resolved_again() -> None:
    states = [
        GeoSpec(level="state", name="a", for_spec="state:39"),
        GeoSpec(level="state", for_spec="state:26"),
    ]
    seen, _ = await _run_split(
        "Show each county in Ohio plus Michigan.", states, _splitter(["Ohio", "Michigan"])
    )
    assert seen == [{"parents": ["Ohio", "Michigan"], "parent_level": None, "level": "county"}]


async def test_a_listing_at_the_wrong_level_in_the_right_parent_is_resolved_again() -> None:
    """Every row is a wildcard, in Ohio, for the right dataset: only the level is wrong."""
    tracts = [GeoSpec(level="tract", name="t", for_spec="tract:*", in_spec="state:39")]
    seen, _ = await _run_split("counties of Ohio", tracts, _splitter(["Ohio"]), resolved=1)
    assert seen == [{"parents": ["Ohio"], "parent_level": None, "level": "county"}]
    counties = [_wildcard("a", "39")]
    kept, _ = await _run_split("counties of Ohio", counties, _splitter(["Ohio"]), resolved=1)
    assert kept == []  # the same listing at the right level is left alone


async def test_listing_already_one_wildcard_per_parent_is_left_alone() -> None:
    done = [_wildcard("a", "39"), _wildcard("b", "26")]
    seen, _ = await _run_split(
        "All counties in Ohio and Michigan.", done, _splitter(["Ohio", "Michigan"])
    )
    assert seen == []


async def test_listing_that_dropped_a_parent_of_three_is_resolved_again() -> None:
    two = [_wildcard("a", "39"), _wildcard("b", "26")]
    seen, _ = await _run_split(
        "All counties in Ohio, Michigan and Indiana.",
        two,
        _splitter(["Ohio", "Michigan", "Indiana"]),
    )
    assert len(seen) == 1 and len(seen[0]["parents"]) == 3


async def test_comparison_resolution_is_left_alone_when_the_model_says_it_is_not_a_listing() -> (
    None
):
    record = ExecutionRecord(question="Compare Harris County and Travis County")
    record.geographies = [_harris(), _harris()]
    record.geo_status = {"legal": True, "compare": True, "compare_count": 2}
    seen: list[dict[str, Any]] = []

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        seen.append(call["args"])
        return ""

    complete = _splitter(["Harris County, Texas", "Travis County, Texas"], None)
    await finish_tools(
        fake_dispatch,
        {"resolve_geography": object()},
        record,
        plan_split(record.question, complete),
    )
    assert complete.calls == 1 and seen == []


async def test_comparison_resolution_the_model_calls_a_listing_is_repaired() -> None:
    record = ExecutionRecord(question="All tracts in Cook and DuPage County.")
    record.geographies = [_harris(), _harris()]
    record.geo_status = {"legal": True, "compare": True, "compare_count": 2}
    seen: list[dict[str, Any]] = []

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        seen.append(call["args"])
        rec.geo_status = {"legal": True, "nested": True}
        rec.geographies = [
            GeoSpec(level="tract", name="a", for_spec="tract:*", in_spec="state:17 county:031"),
            GeoSpec(level="tract", name="b", for_spec="tract:*", in_spec="state:17 county:043"),
        ]
        return ""

    complete = _splitter(["Cook County, Illinois", "DuPage County, Illinois"], "tract")
    await finish_tools(
        fake_dispatch,
        {"resolve_geography": object()},
        record,
        plan_split(record.question, complete),
    )
    assert seen[0]["parents"] == ["Cook County, Illinois", "DuPage County, Illinois"]


async def test_without_a_model_there_is_no_split() -> None:
    assert await plan_split("All counties in Ohio and Michigan.", None) is None


async def test_finish_without_a_split_leaves_the_resolution_alone() -> None:
    record = ExecutionRecord(question="All counties in Ohio and Michigan.")
    record.geographies = [_wildcard("m", "26")]
    seen: list[dict[str, Any]] = []

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        seen.append(call["args"])
        return ""

    await finish_tools(fake_dispatch, {"resolve_geography": object()}, record)
    assert seen == []


async def test_model_naming_no_listing_level_leaves_the_resolution_alone() -> None:
    two = [_harris(), _harris()]
    done = {"legal": True, "compare": True, "compare_count": 2}
    seen, _ = await _run_split(
        "population of Harris County and Travis County",
        two,
        _splitter(["Harris", "Travis"], None),
        status=done,
    )
    assert seen == []


async def test_comparison_resolved_apart_is_resolved_together_with_the_models_places() -> None:
    two = [_harris(), _harris()]
    seen, _ = await _run_split(
        "population of Harris County and Travis County",
        two,
        _splitter(["Harris County, TX", "Travis County, TX"], None),
        status={"legal": True, "compare": False},
    )
    assert seen == [
        {"places": ["Harris County, TX", "Travis County, TX"], "level": None, "levels": []}
    ]


async def test_listing_of_one_parent_at_the_wrong_level_is_resolved_again() -> None:
    seen, _ = await _run_split(
        "counties of Ohio",
        [GeoSpec(level="state", name="Ohio", for_spec="state:39")],
        _splitter(["Ohio"]),
        resolved=1,
    )
    assert seen == [{"parents": ["Ohio"], "parent_level": None, "level": "county"}]


async def test_a_level_the_loop_stated_and_got_stands_over_a_one_parent_report() -> None:
    """The split call is a second model reading the question and is often wrong about a listing;
    for one parent it must not turn the state the loop asked for and fetched into a county list."""
    ohio = [GeoSpec(level="state", name="Ohio", for_spec="state:39")]
    seen, record = await _run_split(
        "People without insurance in Ohio", ohio, _splitter(["Ohio"]), resolved=1, stated=["state"]
    )
    assert seen == [] and record.geographies == ohio


async def test_a_one_parent_report_still_repairs_what_the_loop_never_stated_or_never_got() -> None:
    ohio = [GeoSpec(level="state", name="Ohio", for_spec="state:39")]
    want = [{"parents": ["Ohio"], "parent_level": None, "level": "county"}]
    for stated, unmet in [(None, None), (["state"], {"county"}), ([None], None)]:
        seen, _ = await _run_split(
            "counties of Ohio", ohio, _splitter(["Ohio"]), resolved=1, stated=stated, unmet=unmet
        )
        assert seen == want, (stated, unmet)


async def test_a_county_parent_or_another_state_is_not_covered_by_the_loops_stated_state() -> None:
    wisconsin = [GeoSpec(level="state", name="Wisconsin", for_spec="state:55")]
    seen, _ = await _run_split(
        "tracts in Dane County",
        wisconsin,
        _splitter(["Dane County, WI"], "tract", "county"),
        resolved=1,
        stated=["state"],
    )
    assert seen == [{"parents": ["Dane County, WI"], "parent_level": "county", "level": "tract"}]
    seen, _ = await _run_split(
        "counties of Ohio", wisconsin, _splitter(["Ohio"]), resolved=1, stated=["state"]
    )
    assert seen == [{"parents": ["Ohio"], "parent_level": None, "level": "county"}]


async def test_a_two_parent_report_still_overrides_the_loops_stated_level() -> None:
    states = [
        GeoSpec(level="state", name="Ohio", for_spec="state:39"),
        GeoSpec(level="state", name="Michigan", for_spec="state:26"),
    ]
    seen, _ = await _run_split(
        "List every county in Ohio and Michigan.",
        states,
        _splitter(["Ohio", "Michigan"]),
        stated=["state", "state"],
    )
    assert seen == [{"parents": ["Ohio", "Michigan"], "parent_level": None, "level": "county"}]


async def test_a_county_parent_is_re_resolved_with_the_level_the_model_gave() -> None:
    seen, _ = await _run_split(
        "tracts in Dane County",
        [GeoSpec(level="state", name="Wisconsin", for_spec="state:55")],
        _splitter(["Dane County, WI"], "tract", "county"),
        resolved=1,
    )
    assert seen == [{"parents": ["Dane County, WI"], "parent_level": "county", "level": "tract"}]


async def test_an_unsupported_repair_is_kept_when_the_loop_resolved_nothing() -> None:
    """Fewer geographies than parents, but the loop had none: the candidate and why it cannot
    be run are the only answer there is."""
    record = ExecutionRecord(question="Counties of Ohio and Michigan")
    candidate = _wildcard("every county", "")

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        rec.geographies = [candidate]
        rec.geo_status = {"legal": False, "detail": "not published", "nested": True}
        return ""

    await finish_tools(
        fake_dispatch,
        {"resolve_geography": object()},
        record,
        plan_split(record.question, _splitter(["Ohio", "Michigan"])),
    )
    assert record.geographies == [candidate]
    assert record.geo_status is not None and record.geo_status["detail"] == "not published"


async def test_a_repair_that_cannot_be_nested_keeps_the_loops_listing_and_says_why() -> None:
    record = ExecutionRecord(question="Counties in Ohio, Michigan")
    first = [_wildcard("m", "26")]
    record.geographies = first
    why = "zip code tabulation area does not nest in state"

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        rec.geographies = [_wildcard("a", "01")]
        rec.geo_status = {"legal": False, "detail": why, "nested": False}
        return ""

    split = plan_split(record.question, _splitter(["Ohio", "Michigan"]))
    await finish_tools(fake_dispatch, {"resolve_geography": object()}, record, split)
    assert record.geographies == first  # the unsupported repair does not replace what ran
    assert record.geo_status is not None and record.geo_status["nested"] is False
    assert record.geo_status["detail"] == why  # and the reason it cannot be nested is kept


async def test_single_named_place_is_left_alone_when_the_model_says_it_is_not_a_listing() -> None:
    complete = _splitter(["Harris County, Texas"], None)
    seen, record = await _run_split("population of Harris County, Texas", [_harris()], complete)
    assert complete.calls == 1 and seen == []


async def test_single_named_county_for_a_tract_listing_is_re_resolved_with_every_parent() -> None:
    complete = _splitter(["King County, Washington", "Pierce County, Washington"], "tract")
    seen, _ = await _run_split(
        "Every tract in King plus Pierce County.", [_harris(for_spec="county:053")], complete
    )
    assert seen == [
        {
            "parents": ["King County, Washington", "Pierce County, Washington"],
            "parent_level": None,
            "level": "tract",
        }
    ]


async def test_single_parent_reply_leaves_the_resolution_alone() -> None:
    seen, _ = await _run_split(
        "All counties in Lewis and Clark County.", [_wildcard("m", "26")], _splitter(["Lewis"])
    )
    assert seen == []


async def test_unparseable_split_reply_changes_nothing() -> None:
    async def complete(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict:
        return {"content": "no idea", "tool_calls": []}

    seen, _ = await _run_split(
        "All counties in Ohio and Michigan.", [_wildcard("m", "26")], complete
    )
    assert seen == []


async def test_failed_re_resolution_restores_the_earlier_geography() -> None:
    first = [_wildcard("m", "26")]
    _, record = await _run_split(
        "All counties in Ohio and Michigan.", first, _splitter(["Ohio", "Michigan"]), resolved=1
    )
    assert record.geographies == first


async def _split_with(
    reply: Any, geos: list[GeoSpec], dispatch_result: Any = "wild"
) -> tuple[list[dict[str, Any]], ExecutionRecord]:
    record = ExecutionRecord(question="All counties in Ohio and Michigan.")
    record.geographies = geos
    record.intent.legs = ["earlier"]
    seen: list[dict[str, Any]] = []

    async def complete(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict:
        if isinstance(reply, Exception):
            raise reply
        return {"content": json.dumps(reply), "tool_calls": []}

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        seen.append(call["args"])
        if isinstance(dispatch_result, Exception):
            rec.consecutive_failures["resolve_geography"] = 1
            raise dispatch_result
        rec.intent.legs = []
        rec.geographies = (
            [_wildcard("a", "01"), _wildcard("b", "02")]
            if dispatch_result == "wild"
            else [_harris(), _harris()]
        )
        return ""

    await finish_tools(
        fake_dispatch,
        {"resolve_geography": object()},
        record,
        plan_split(record.question, complete),
    )
    return seen, record


_GOOD = {"level": None, "parents": ["Ohio", "Michigan"], "unit": "county", "listing": True}


async def test_model_call_that_raises_never_fails_the_answer() -> None:
    seen, record = await _split_with(OSError("rate limited"), [_wildcard("m", "26")])
    assert seen == [] and len(record.geographies) == 1


async def test_parents_that_are_not_a_list_are_ignored() -> None:
    reply = {**_GOOD, "parents": "Ohio and Michigan"}
    seen, _ = await _split_with(reply, [_wildcard("m", "26")])
    assert seen == []


async def test_unit_outside_the_listing_levels_is_ignored() -> None:
    seen, _ = await _split_with({**_GOOD, "unit": "state; drop"}, [_wildcard("m", "26")])
    assert seen == []


async def test_failed_dispatch_keeps_the_loops_own_two_geographies() -> None:
    two = [_wildcard("a", "39"), _harris()]
    _, record = await _split_with(_GOOD, two, dispatch_result=RuntimeError("boom"))
    assert record.geographies == two
    assert "resolve_geography" not in record.consecutive_failures


async def test_re_resolution_to_non_wildcards_is_rejected_and_state_restored() -> None:
    first = [_wildcard("m", "26")]
    _, record = await _split_with(_GOOD, first, dispatch_result="parents")
    assert record.geographies == first and record.intent.legs == ["earlier"]


async def test_failed_repair_restores_the_fetched_answer() -> None:
    record = ExecutionRecord(question="All counties in Ohio and Michigan.")
    record.geographies = [_wildcard("m", "26")]
    record.rows = [{"GEO_ID": "x"}]
    record.table_id = "B01003"

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        rec.rows, rec.table_id, rec.geographies = [], "", []
        return ""

    await finish_tools(
        fake_dispatch,
        {"resolve_geography": object()},
        record,
        plan_split(record.question, _splitter(["Ohio", "Michigan"])),
    )
    assert record.rows == [{"GEO_ID": "x"}] and record.table_id == "B01003"


async def test_repair_resolution_that_is_not_nested_is_rejected() -> None:
    first = [_wildcard("m", "26")]
    record = ExecutionRecord(question="All counties in Ohio and Michigan.")
    record.geographies = first

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        rec.geographies = [_wildcard("a", "01"), _wildcard("b", "02")]
        rec.geo_status = {"legal": True, "nested": False}
        return ""

    await finish_tools(
        fake_dispatch,
        {"resolve_geography": object()},
        record,
        plan_split(record.question, _splitter(["Ohio", "Michigan"])),
    )
    assert record.geographies == first


async def test_an_acs1_report_resolves_the_repair_against_acs1() -> None:
    seen, _ = await _run_split(
        "ACS 1-year all counties in Ohio and Michigan.",
        [_wildcard("m", "26")],
        _splitter(["Ohio", "Michigan"], dataset="acs1"),
    )
    assert seen[0]["dataset"] == "acs1"


async def test_model_decides_for_a_phrasing_with_no_unit_word_or_joiner() -> None:
    seen, _ = await _run_split(
        "Everything inside Ohio along with Michigan.",
        [_wildcard("m", "26")],
        _splitter(["Ohio", "Michigan"], "place"),
    )
    assert seen == [{"parents": ["Ohio", "Michigan"], "parent_level": None, "level": "place"}]


async def test_one_parent_written_as_place_and_state_is_not_re_resolved() -> None:
    seen, _ = await _run_split(
        "All tracts in Harris County, Texas.",
        [GeoSpec(level="tract", name="h", for_spec="tract:*", in_spec="state:48 county:201")],
        _splitter(["Harris County, Texas"], "tract"),
    )
    assert seen == []


async def test_repeated_parent_is_one_parent() -> None:
    seen, _ = await _run_split(
        "All counties in Ohio and Ohio.",
        [_wildcard("o", "39")],
        _splitter(["Ohio", "ohio", "Ohio"]),
    )
    assert seen == []


async def _redo_args(record: ExecutionRecord) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        seen.append(call["args"])
        return ""

    await finish_tools(fake_dispatch, {"resolve_geography": object()}, record)
    return seen


async def test_resolved_comparison_with_two_queries_is_not_resolved_again() -> None:
    record = ExecutionRecord(question="Harris County and Travis County")
    record.geographies = [_harris()]
    record.intent.legs = ["Harris County, TX", "Travis County, TX"]
    record.geo_status = {"legal": True, "compare": True, "compare_count": 2}
    assert await _redo_args(record) == []


async def test_unresolved_pair_of_single_place_queries_is_resolved_together() -> None:
    record = ExecutionRecord(question="Harris County and Travis County")
    record.geographies = [_harris()]
    record.intent.legs = ["Harris County, TX", "Travis County, TX"]
    record.geo_status = {"legal": True, "compare": False}
    assert await _redo_args(record) == [
        {"places": ["Harris County, TX", "Travis County, TX"], "level": None, "levels": []}
    ]


async def test_finish_never_resolves_the_question_itself() -> None:
    """The model reported nothing, so nothing is resolved: no place is read from the words."""
    record = ExecutionRecord(question="every tract in Cook County, Illinois")
    record.geographies = [_harris()]
    record.intent.legs = ["Cook County, IL", "Harris County, TX"]
    record.geo_status = {"legal": True, "compare": True, "compare_count": 2}
    assert await _redo_args(record) == []
    empty = ExecutionRecord(question="every tract in Cook County, Illinois")
    assert await _redo_args(empty) == []


async def test_an_accepted_repair_never_leaves_the_old_parents_url_and_rows() -> None:
    record = ExecutionRecord(question="Counties in Ohio, Michigan")
    record.geographies = [_wildcard("m", "26")]
    record.url = CensusURL(
        "https://api.census.gov/data/2024/acs/acs5?get=NAME&for=county:*&in=state:26"
    )
    record.rows = [{"GEO_ID": "old"}]

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        if call["id"] == "resolve_geography":
            rec.geographies = [_wildcard("a", "01"), _wildcard("b", "02")]
        return ""  # build_url fails to produce a new URL

    tools = {"resolve_geography": object(), "build_url": object()}
    split = plan_split(record.question, _splitter(["Ohio", "Michigan"]))
    await finish_tools(fake_dispatch, tools, record, split)
    assert record.url is None and record.rows == []


async def test_extra_ambiguity_candidates_after_the_chosen_parents_do_not_block_the_repair() -> (
    None
):
    record = ExecutionRecord(question="Counties in Ohio, Michigan")
    record.geographies = [_wildcard("m", "26")]

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        rec.geographies = [
            _wildcard("a", "01"),
            _wildcard("b", "02"),
            GeoSpec(level="county", name="other", for_spec="county:001", in_spec="state:13"),
        ]
        return ""

    split = plan_split(record.question, _splitter(["Ohio", "Michigan"]))
    await finish_tools(fake_dispatch, {"resolve_geography": object()}, record, split)
    assert len(record.geographies) == 3 and record.geographies[0].name == "a"


async def test_cancelling_the_request_while_waiting_for_the_split_is_not_swallowed() -> None:
    record = ExecutionRecord(question="Counties in Ohio, Michigan")
    record.geographies = [_wildcard("m", "26")]

    async def never() -> dict[str, Any] | None:
        await asyncio.sleep(30)

    async def run() -> None:
        async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
            return ""

        await finish_tools(fake_dispatch, {"resolve_geography": object()}, record, never())

    task = asyncio.create_task(run())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_a_rejected_repair_restores_the_retained_urls() -> None:
    record = ExecutionRecord(question="Counties in Ohio, Michigan")
    record.geographies = [_wildcard("m", "26")]
    record.retained_urls = ["https://api.census.gov/old"]

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        rec.retained_urls = ["https://api.census.gov/old", "https://api.census.gov/new"]
        rec.geographies = [_harris(), _harris()]  # not wildcards: rejected
        return ""

    split = plan_split(record.question, _splitter(["Ohio", "Michigan"]))
    await finish_tools(fake_dispatch, {"resolve_geography": object()}, record, split)
    assert record.retained_urls == ["https://api.census.gov/old"]


async def test_a_listing_already_resolved_for_acs5_is_resolved_again_for_an_acs1_report() -> None:
    done = [_wildcard("a", "39"), _wildcard("b", "26")]
    built = (
        "https://api.census.gov/data/2024/acs/acs1?get=NAME,B01003_001E&for=county:*&in=state:39"
    )
    seen, _ = await _run_split(
        "ACS 1-year all counties in Ohio and Michigan.",
        done,
        _splitter(["Ohio", "Michigan"], dataset="acs1"),
        url=built,
    )
    assert [call.get("dataset") for call in seen] == ["acs1"]


def _tracts_in(state: str, county: str) -> GeoSpec:
    return GeoSpec(
        level="tract", name="t", for_spec="tract:*", in_spec=f"state:{state} county:{county}"
    )


async def test_a_listing_at_the_right_level_in_the_wrong_parent_is_resolved_again() -> None:
    reply = _splitter(["Lancaster County, Nebraska"], "tract", "county")
    wrong, _ = await _run_split("tracts in Lancaster County", [_tracts_in("42", "071")], reply, 1)
    assert [call["parents"] for call in wrong] == [["Lancaster County, Nebraska"]]
    right, _ = await _run_split("tracts in Lancaster County", [_tracts_in("31", "109")], reply, 1)
    assert right == []


async def test_a_question_the_model_reports_as_the_nation_is_resolved_as_the_nation() -> None:
    async def complete(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict:
        reply = {"level": "us", "parents": [], "unit": "county", "listing": False}
        return {"content": json.dumps(reply), "tool_calls": []}

    record = ExecutionRecord(question="population of the country")
    seen: list[dict[str, Any]] = []

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        seen.append(call["args"])
        return ""

    await finish_tools(
        fake_dispatch,
        {"resolve_geography": object()},
        record,
        plan_split(record.question, complete),
    )
    assert seen == [{"places": [], "level": "us"}]


async def test_a_comparison_of_places_at_different_levels_is_not_forced_to_one_level() -> None:
    async def complete(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict:
        reply = {"level": "county", "parents": ["Cook County, IL", "Texas"], "listing": False}
        return {"content": json.dumps(reply), "tool_calls": []}

    record = ExecutionRecord(question="Cook County versus Texas")
    seen: list[dict[str, Any]] = []

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        seen.append(call["args"])
        return ""

    await finish_tools(
        fake_dispatch,
        {"resolve_geography": object()},
        record,
        plan_split(record.question, complete),
    )
    assert seen == [{"places": ["Cook County, IL", "Texas"], "level": None, "levels": []}]


@pytest.mark.parametrize(
    ("question", "stated", "repaired"),
    [
        ("ACS 1-year all counties in Ohio and Michigan.", None, None),
        ("ACS 1-year all counties in Ohio and Michigan.", "acs5", None),
        ("all counties in Ohio and Michigan.", "acs1", "acs1"),
    ],
)
async def test_the_repair_resolves_against_the_dataset_the_report_states_not_the_wording(
    question: str, stated: str | None, repaired: str | None
) -> None:
    seen, _ = await _run_split(
        question, [_wildcard("m", "26")], _splitter(["Ohio", "Michigan"], dataset=stated)
    )
    assert [call.get("dataset") for call in seen] == [repaired]
