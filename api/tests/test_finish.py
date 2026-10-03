"""Direct unit tests for finish_tools: the recovery path run at the end of
every ask loop, regardless of whether the model's own turns hit an error.
"""

from __future__ import annotations

import json
from typing import Any

from ask_fixtures import _harris
from src.ask import ExecutionRecord, dispatch
from src.census_url import CensusURL
from src.contract import GeoSpec, ResultPlan
from src.fetch import FetchDataTool
from src.finish import _wrong_comparison, finish_tools


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


def _splitter(parents: object, level: object = "county") -> Any:
    async def complete(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict:
        complete.calls += 1  # type: ignore[attr-defined]
        reply = {"parents": parents, "unit": level or "county", "listing": level is not None}
        return {"content": json.dumps(reply), "tool_calls": []}

    complete.calls = 0  # type: ignore[attr-defined]
    return complete


async def _run_split(
    question: str, geos: list[GeoSpec], complete: Any, resolved: int = 2
) -> tuple[list[dict[str, Any]], ExecutionRecord]:
    record = ExecutionRecord(question=question)
    record.geographies = geos
    seen: list[dict[str, Any]] = []

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        seen.append(call["args"])
        rec.geographies = [_wildcard("a", "01"), _wildcard("b", "02")][:resolved]
        return ""

    await finish_tools(fake_dispatch, {"resolve_geography": object()}, record, complete)
    return seen, record


async def test_listing_that_kept_one_parent_is_resolved_with_every_parent() -> None:
    complete = _splitter(["Ohio", "Michigan"])
    seen, _ = await _run_split(
        "List every county in Ohio and Michigan.", [_wildcard("m", "26")], complete
    )
    assert seen == [{"query": "every county in Ohio, Michigan", "parents": ["Ohio", "Michigan"]}]


async def test_listing_resolved_at_the_wrong_level_is_resolved_again() -> None:
    states = [
        GeoSpec(level="state", name="a", for_spec="state:39"),
        GeoSpec(level="state", for_spec="state:26"),
    ]
    seen, _ = await _run_split(
        "Show each county in Ohio plus Michigan.", states, _splitter(["Ohio", "Michigan"])
    )
    assert seen == [{"query": "every county in Ohio, Michigan", "parents": ["Ohio", "Michigan"]}]


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
    await finish_tools(fake_dispatch, {"resolve_geography": object()}, record, complete)
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
    await finish_tools(fake_dispatch, {"resolve_geography": object()}, record, complete)
    assert seen[0]["parents"] == ["Cook County, Illinois", "DuPage County, Illinois"]


async def test_override_plan_never_calls_the_model() -> None:
    record = ExecutionRecord(question="All counties in Ohio and Michigan.")
    record.geographies = [_wildcard("m", "26")]
    record.override = ResultPlan(geographies=[_wildcard("m", "26")])
    complete = _splitter(["Ohio", "Michigan"])

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        return ""

    await finish_tools(fake_dispatch, {"resolve_geography": object()}, record, complete)
    assert complete.calls == 0


async def test_model_naming_no_listing_level_leaves_the_resolution_alone() -> None:
    two = [_harris(), _harris()]
    seen, _ = await _run_split(
        "population of Harris County and Travis County", two, _splitter(["Harris", "Travis"], None)
    )
    assert seen == []


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
            "query": "every tract in King County, Washington, Pierce County, Washington",
            "parents": ["King County, Washington", "Pierce County, Washington"],
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
    record.geo_queries = ["earlier"]
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
        rec.geo_queries = []
        rec.geographies = (
            [_wildcard("a", "01"), _wildcard("b", "02")]
            if dispatch_result == "wild"
            else [_harris(), _harris()]
        )
        return ""

    await finish_tools(fake_dispatch, {"resolve_geography": object()}, record, complete)
    return seen, record


_GOOD = {"parents": ["Ohio", "Michigan"], "unit": "county", "listing": True}


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
    assert record.geographies == first and record.geo_queries == ["earlier"]


async def test_failed_repair_restores_the_fetched_answer() -> None:
    record = ExecutionRecord(question="All counties in Ohio and Michigan.")
    record.geographies = [_wildcard("m", "26")]
    record.rows = [{"GEO_ID": "x"}]
    record.table_id = "B01003"

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        rec.rows, rec.table_id, rec.geographies = [], "", []
        return ""

    await finish_tools(
        fake_dispatch, {"resolve_geography": object()}, record, _splitter(["Ohio", "Michigan"])
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
        fake_dispatch, {"resolve_geography": object()}, record, _splitter(["Ohio", "Michigan"])
    )
    assert record.geographies == first


async def test_acs1_question_resolves_the_repair_against_acs1() -> None:
    seen, _ = await _run_split(
        "ACS 1-year all counties in Ohio and Michigan.",
        [_wildcard("m", "26")],
        _splitter(["Ohio", "Michigan"]),
    )
    assert seen[0]["dataset"] == "acs1"


async def test_model_decides_for_a_phrasing_with_no_unit_word_or_joiner() -> None:
    seen, _ = await _run_split(
        "Everything inside Ohio along with Michigan.",
        [_wildcard("m", "26")],
        _splitter(["Ohio", "Michigan"], "place"),
    )
    assert seen == [{"query": "every place in Ohio, Michigan", "parents": ["Ohio", "Michigan"]}]


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


async def test_resolved_comparison_with_two_queries_is_not_flagged_for_redo() -> None:
    record = ExecutionRecord(question="Harris County and Travis County")
    record.geo_queries = ["Harris County, TX", "Travis County, TX"]
    record.geo_status = {"legal": True, "compare": True, "compare_count": 2}
    assert _wrong_comparison(record, record.question) is False


async def test_unresolved_pair_of_single_place_queries_is_flagged_for_redo() -> None:
    record = ExecutionRecord(question="Harris County and Travis County")
    record.geo_queries = ["Harris County, TX", "Travis County, TX"]
    record.geo_status = {"legal": True, "compare": False}
    assert _wrong_comparison(record, record.question) is True


async def test_redo_after_a_resolved_comparison_resolves_the_question_not_the_places() -> None:
    record = ExecutionRecord(question="every tract in Cook County, Illinois")
    record.geographies = [_harris()]
    record.geo_queries = ["Cook County, IL", "Harris County, TX"]
    record.geo_status = {"legal": True, "compare": True, "compare_count": 2}
    seen: list[dict[str, Any]] = []

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        seen.append(call["args"])
        return ""

    await finish_tools(fake_dispatch, {"resolve_geography": object()}, record)
    assert seen == [{"query": "every tract in Cook County, Illinois"}]
