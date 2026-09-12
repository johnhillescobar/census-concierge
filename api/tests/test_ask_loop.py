"""Hand-rolled ask loop: scripted model, injected tools, no live keys."""

from __future__ import annotations

from typing import Any

import pytest
from src.ask import ExecutionRecord, dispatch, run_ask
from src.census_url import CensusURL
from src.contract import AskResponse
from src.geo import ResolveGeographyTool
from src.tools import BuildUrlTool, FetchDataTool, SearchTablesTool
from test_ask_tools import ENTRIES, _describe, _list_geographies, _search


def _tools(record: ExecutionRecord) -> dict[str, Any]:
    facts = {"acs5": {2024: {"B01003": {"universe": "Total population", "variables": ["001E"]}}}}
    return {
        "search_tables": SearchTablesTool(search=_search, describe=_describe),
        "resolve_geography": ResolveGeographyTool(
            list_geographies=_list_geographies, entries=ENTRIES
        ),
        "build_url": BuildUrlTool(
            allowed_tables=lambda: (
                {hit["table_id"] for hit in record.pool}
                | {member for hit in record.pool for member in hit.get("members") or []}
            ),
            latest_vintage=lambda dataset: 2024,
            table_facts=lambda dataset, year, table_id: (
                facts.get(dataset, {}).get(year, {}).get(table_id)
            ),
            last_geography=lambda: record.geography,
            allowed_geographies=lambda: (
                {
                    (str(geo.get("for") or ""), str(geo.get("in") or ""))
                    for geo in record.geographies
                }
                if len(record.geographies) == 1
                else set()
            ),
        ),
        "fetch_data": FetchDataTool(
            last_url=lambda: record.url,
            census_key=lambda: "secret",
            http_get=lambda url: (
                200,
                [
                    ["NAME", "B01003_001E", "B01003_001M", "GEO_ID", "state", "county"],
                    ["Harris County, Texas", "4838303", "123", "0500000US48201", "48", "201"],
                ],
            ),
        ),
    }


async def test_scripted_loop_fills_url_rows_geoid_and_universe() -> None:
    record = ExecutionRecord()
    tools = _tools(record)
    queue: list[dict[str, Any]] = [
        {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "name": "search_tables",
                    "args": {"question": "population of Harris County, Texas"},
                }
            ],
        },
        {
            "content": "",
            "tool_calls": [
                {"id": "2", "name": "resolve_geography", "args": {"query": "Harris County, Texas"}}
            ],
        },
        {
            "content": "",
            "tool_calls": [{"id": "3", "name": "build_url", "args": {"table_id": "B01003"}}],
        },
        {"content": "", "tool_calls": [{"id": "4", "name": "fetch_data", "args": {}}]},
        {"content": "Harris County has data.", "tool_calls": []},
    ]

    async def complete(
        messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        names = {tool["function"]["name"] for tool in openai_tools}
        assert names == {"search_tables", "resolve_geography", "build_url", "fetch_data"}
        _ = messages
        return queue.pop(0)

    response = await run_ask(
        "population of Harris County, Texas", complete=complete, tools=tools, record=record
    )
    assert isinstance(response, AskResponse)
    assert response.table_id == "B01003"
    assert response.universe == "Total population"
    assert response.geoid == "0500000US48201"
    assert "key=" not in response.url
    assert "B01003_001E" in response.url
    assert "B01003_001M" in response.url
    assert response.rows[0]["B01003_001E"] == "4838303"
    assert response.moe[0]["B01003_001M"] == "123"
    assert queue == []
    assert [tick["tool"] for tick in record.timings] == [
        "search_tables",
        "resolve_geography",
        "build_url",
        "fetch_data",
    ]


async def test_two_consecutive_failures_of_the_same_tool_abort() -> None:
    record = ExecutionRecord()
    tool = FetchDataTool(last_url=lambda: None, census_key=lambda: "")
    with pytest.raises(RuntimeError, match="fetch_data failed twice"):
        await dispatch(tool, {"id": "a", "args": {}}, record)
        await dispatch(tool, {"id": "b", "args": {}}, record)


async def test_failed_fetch_still_returns_the_built_url() -> None:
    record = ExecutionRecord()
    record.pool = [{"table_id": "B01003", "universe": "Total population", "members": []}]
    record.geography = {"for": "county:201", "in": "state:48", "geoid": "0500000US48201"}
    record.geographies = [dict(record.geography)]
    facts = {"acs5": {2024: {"B01003": {"universe": "Total population", "variables": ["001E"]}}}}
    tools = {
        "search_tables": SearchTablesTool(search=_search, describe=_describe),
        "resolve_geography": ResolveGeographyTool(
            list_geographies=_list_geographies, entries=ENTRIES
        ),
        "build_url": BuildUrlTool(
            allowed_tables=lambda: {"B01003"},
            latest_vintage=lambda dataset: 2024,
            table_facts=lambda dataset, year, table_id: facts["acs5"][year][table_id],
            last_geography=lambda: record.geography,
            allowed_geographies=lambda: (
                {
                    (str(geo.get("for") or ""), str(geo.get("in") or ""))
                    for geo in record.geographies
                }
                if len(record.geographies) == 1
                else set()
            ),
        ),
        "fetch_data": FetchDataTool(
            last_url=lambda: record.url,
            census_key=lambda: "secret",
            http_get=lambda url: (400, "error: unknown/unsupported geography hierarchy"),
        ),
    }
    queue = [
        {
            "content": "",
            "tool_calls": [{"id": "1", "name": "build_url", "args": {"table_id": "B01003"}}],
        },
        {"content": "", "tool_calls": [{"id": "2", "name": "fetch_data", "args": {}}]},
        {"content": "The fetch failed.", "tool_calls": []},
    ]

    async def complete(
        messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        _ = messages, openai_tools
        return queue.pop(0)

    response = await run_ask("population", complete=complete, tools=tools, record=record)
    assert response.url
    assert "key=" not in response.url
    assert response.rows == []
    assert str(record.url) == response.url
    assert response.geoid == "0500000US48201"


async def test_search_does_not_select_the_table() -> None:
    record = ExecutionRecord()
    tools = _tools(record)
    queue: list[dict[str, Any]] = [
        {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "name": "search_tables",
                    "args": {"question": "population of Harris County, Texas"},
                }
            ],
        },
        {"content": "candidates listed", "tool_calls": []},
    ]

    async def complete(
        messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        _ = messages, openai_tools
        return queue.pop(0)

    response = await run_ask(
        "population of Harris County, Texas", complete=complete, tools=tools, record=record
    )
    assert record.pool[0]["table_id"] == "B01003"
    assert response.table_id == ""
    assert response.universe == ""


async def test_failed_rebuild_clears_the_previous_url_and_rows() -> None:
    record = ExecutionRecord()
    tools = _tools(record)
    record.pool = [{"table_id": "B01003", "universe": "Total population", "members": []}]
    record.geography = {"for": "county:201", "in": "state:48", "geoid": "0500000US48201"}
    record.geographies = [dict(record.geography)]
    record.url = CensusURL(
        "https://api.census.gov/data/2024/acs/acs5?get=NAME&for=county:201&in=state:48"
    )
    record.table_id = "B01003"
    record.universe = "Total population"
    record.rows = [{"GEO_ID": "0500000US48201", "B01003_001E": "1"}]
    await dispatch(tools["build_url"], {"id": "x", "args": {"table_id": "B99999"}}, record)
    assert record.url is None
    assert record.rows == []
    assert record.table_id == ""
    assert record.universe == ""


async def test_successful_rebuild_drops_previous_rows() -> None:
    record = ExecutionRecord()
    tools = _tools(record)
    record.pool = [{"table_id": "B01003", "universe": "Total population", "members": []}]
    record.geography = {"for": "county:201", "in": "state:48", "geoid": "0500000US48201"}
    record.geographies = [dict(record.geography)]
    record.rows = [{"GEO_ID": "0500000US48201", "B01003_001E": "1"}]
    await dispatch(tools["build_url"], {"id": "x", "args": {"table_id": "B01003"}}, record)
    assert record.rows == []
    assert record.url is not None
    assert record.table_id == "B01003"


async def test_ambiguous_geography_cannot_be_built_as_one_url() -> None:
    record = ExecutionRecord()
    tools = _tools(record)
    await dispatch(tools["search_tables"], {"id": "1", "args": {"question": "population"}}, record)
    await dispatch(
        tools["resolve_geography"], {"id": "2", "args": {"query": "Cook County"}}, record
    )
    assert len(record.geographies) == 3
    assert record.geography is None
    await dispatch(
        tools["build_url"],
        {
            "id": "3",
            "args": {"table_id": "B01003", "for_spec": "county:031", "in_spec": "state:17"},
        },
        record,
    )
    assert record.url is None
    assert record.table_id == ""
