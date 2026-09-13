"""Hand-rolled ask loop: scripted model, injected tools, no live keys."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from src.ask import ExecutionRecord, assemble, dispatch, run_ask
from src.census_url import CensusURL
from src.contract import AskResponse
from src.geo import ResolveGeographyTool
from src.tools import BuildUrlTool, FetchDataTool, SearchTablesTool
from test_ask_route import CONTRACT_FIELDS
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
            allowed_geographies=lambda: {
                (str(geo.get("for") or ""), str(geo.get("in") or "")) for geo in record.geographies
            },
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
    assert list(response.model_dump()) == list(CONTRACT_FIELDS)
    assert response.table_id == "B01003"
    assert response.universe == "Total population"
    assert response.geoid == "0500000US48201"
    assert "key=" not in response.url
    parts = urlsplit(response.url)
    assert parts.path == "/data/2024/acs/acs5"
    query = parse_qs(parts.query)
    assert "B01003_001E" in query["get"][0]
    assert "B01003_001M" in query["get"][0]
    assert "GEO_ID" in query["get"][0]
    assert query["for"] == ["county:201"]
    assert query["in"] == ["state:48"]
    assert "key" not in query
    assert response.rows[0]["B01003_001E"] == "4838303"
    assert response.rows[0]["GEO_ID"] == "0500000US48201"
    assert "url" not in response.rows[0]
    assert response.moe[0]["B01003_001M"] == "123"
    assert "B01003_001E" not in response.moe[0]
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
            allowed_geographies=lambda: {
                (str(geo.get("for") or ""), str(geo.get("in") or "")) for geo in record.geographies
            },
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


async def test_ambiguous_geography_builds_the_selected_url() -> None:
    record = ExecutionRecord(question="Population of Cook County")
    tools = _tools(record)
    await dispatch(tools["search_tables"], {"id": "1", "args": {"question": "population"}}, record)
    await dispatch(
        tools["resolve_geography"], {"id": "2", "args": {"query": "Cook County"}}, record
    )
    assert len(record.geographies) == 3
    assert record.geography is not None
    assert record.geography["in"] == "state:17"
    await dispatch(tools["build_url"], {"id": "3", "args": {"table_id": "B01003"}}, record)
    await dispatch(tools["fetch_data"], {"id": "4", "args": {}}, record)
    response = assemble("Cook County, Illinois", record)
    assert record.url is not None
    assert "county:031" in str(record.url)
    assert "state:17" in str(record.url)
    assert response.table_id == "B01003"
    assert response.rows
    assert response.universe == "Total population"
    assert [item.code for item in response.warnings] == ["ambiguous_place"]
    assert "Cook County, Georgia" in response.warnings[0].detail
    assert "Cook County, Minnesota" in response.warnings[0].detail


def test_assemble_emits_every_declared_field() -> None:
    response = assemble("", ExecutionRecord())
    assert list(response.model_dump()) == list(CONTRACT_FIELDS)
    assert response.warnings == []
    assert response.alternatives == []


def test_each_estimate_is_returned_with_its_matching_margin() -> None:
    record = ExecutionRecord()
    record.geography = {"geoid": "0500000US48201"}
    record.rows = [
        {
            "NAME": "Harris County, Texas",
            "GEO_ID": "0500000US48201",
            "B01003_001E": "4838303",
            "B01003_001M": "123",
            "state": "48",
            "county": "201",
        }
    ]
    response = assemble("x", record)
    assert response.moe == [
        {
            "NAME": "Harris County, Texas",
            "GEO_ID": "0500000US48201",
            "B01003_001M": "123",
        }
    ]
    assert "url" not in response.rows[0]


def test_missing_margin_stays_visible_as_none() -> None:
    record = ExecutionRecord()
    record.rows = [{"GEO_ID": "0500000US48201", "B01003_001E": "1"}]
    response = assemble("x", record)
    assert response.moe[0]["B01003_001M"] is None


def test_every_row_carries_an_affgeoid() -> None:
    record = ExecutionRecord()
    record.geography = {"geoid": "0500000US48201", "for": "county:201", "in": "state:48"}
    record.rows = [{"NAME": "Harris County, Texas", "B01003_001E": "1", "B01003_001M": "2"}]
    response = assemble("x", record)
    assert response.rows[0]["GEO_ID"] == "0500000US48201"
    assert response.geoid == "0500000US48201"


def test_many_rows_do_not_name_one_geoid() -> None:
    record = ExecutionRecord()
    record.geography = {"for": "county:*", "in": "state:41", "geoid": ""}
    record.rows = [
        {"GEO_ID": "0500000US41001", "B01003_001E": "1", "B01003_001M": "2"},
        {"GEO_ID": "0500000US41003", "B01003_001E": "3", "B01003_001M": "4"},
    ]
    response = assemble("x", record)
    assert response.geoid == ""
    assert [row["GEO_ID"] for row in response.rows] == ["0500000US41001", "0500000US41003"]


def test_empty_matrix_universe_falls_back_to_the_search_hit() -> None:
    record = ExecutionRecord()
    record.table_id = "B19013"
    record.universe = ""
    record.pool = [
        {
            "table_id": "B19013",
            "title": "Median Household Income",
            "universe": "Households",
            "members": [],
        }
    ]
    assert assemble("x", record).universe == "Households"


def test_alternatives_say_how_they_differ() -> None:
    record = ExecutionRecord()
    record.table_id = "B19013"
    record.universe = "Households"
    record.pool = [
        {
            "table_id": "B19013",
            "title": "Median Household Income",
            "universe": "Households",
            "members": ["B19013A"],
        },
        {
            "table_id": "B19113",
            "title": "Median Family Income",
            "universe": "Families",
            "members": [],
        },
        {
            "table_id": "B19001",
            "title": "Household Income",
            "universe": "Households",
            "members": [],
        },
        {
            "table_id": "B15003",
            "title": "Educational Attainment",
            "universe": "Population 25 years and over",
            "members": ["C15003"],
        },
        {
            "table_id": "B25044",
            "title": "Tenure by Vehicles Available",
            "universe": "Occupied housing units",
            "members": ["C25045"],
        },
        {
            "table_id": "B11001",
            "title": "Household Type",
            "universe": "Households",
            "members": [],
        },
    ]
    by_id = {item.table_id: item.reason for item in assemble("x", record).alternatives}
    assert by_id["B19013A"] == "race iteration"
    assert by_id["B19113"] == "universe"
    assert by_id["B19001"] == "distribution versus median"
    assert by_id["C15003"] == "related table"
    assert by_id["C25045"] == "related table"
    assert by_id["B11001"] == "related table"
    assert "B19013" not in by_id


def test_collapsed_reason_is_relative_to_the_selection() -> None:
    record = ExecutionRecord()
    record.table_id = "B15003"
    record.universe = "Population 25 years and over"
    record.pool = [
        {
            "table_id": "B15003",
            "title": "Educational Attainment",
            "universe": "Population 25 years and over",
            "members": ["C15003"],
        },
        {
            "table_id": "B19013",
            "title": "Median Household Income",
            "universe": "Households",
            "members": ["B19013A"],
        },
    ]
    by_id = {item.table_id: item.reason for item in assemble("x", record).alternatives}
    assert by_id["C15003"] == "collapsed table"
    assert by_id["B19013"] == "universe"
    assert by_id["B19013A"] == "related table"


def test_a_collapsed_member_is_not_a_race_iteration_of_the_pick() -> None:
    record = ExecutionRecord()
    record.table_id = "B15003A"
    record.universe = "Population 25 years and over"
    record.pool = [
        {
            "table_id": "B15003",
            "title": "Educational Attainment",
            "universe": "Population 25 years and over",
            "members": ["C15003", "B15003A"],
        }
    ]
    by_id = {item.table_id: item.reason for item in assemble("x", record).alternatives}
    assert by_id["C15003"] == "collapsed table"
    assert by_id["B15003"] == "race iteration"


def test_selected_member_uses_the_parent_title() -> None:
    record = ExecutionRecord()
    record.table_id = "B19013A"
    record.universe = "Households"
    record.pool = [
        {
            "table_id": "B19013",
            "title": "Median Household Income",
            "universe": "Households",
            "members": ["B19013A"],
        },
        {
            "table_id": "B19001",
            "title": "Household Income",
            "universe": "Households",
            "members": [],
        },
    ]
    by_id = {item.table_id: item.reason for item in assemble("x", record).alternatives}
    assert by_id["B19001"] == "distribution versus median"
    assert by_id["B19013"] == "race iteration"


def test_no_selection_does_not_label_pool_members_as_collapsed() -> None:
    record = ExecutionRecord()
    record.pool = [
        {
            "table_id": "B15003",
            "title": "Educational Attainment",
            "universe": "Population 25 years and over",
            "members": ["C15003", "B15003A"],
        }
    ]
    by_id = {item.table_id: item.reason for item in assemble("x", record).alternatives}
    assert by_id["C15003"] == "related table"
    assert by_id["B15003A"] == "related table"
    assert by_id["B15003"] == "related table"


def test_selecting_a_collapsed_member_labels_the_parent() -> None:
    record = ExecutionRecord()
    record.table_id = "C15003"
    record.universe = "Population 25 years and over"
    record.pool = [
        {
            "table_id": "B15003",
            "title": "Educational Attainment",
            "universe": "Population 25 years and over",
            "members": ["C15003"],
        }
    ]
    by_id = {item.table_id: item.reason for item in assemble("x", record).alternatives}
    assert by_id["B15003"] == "collapsed table"
    assert "C15003" not in by_id


async def test_universe_comes_from_the_requested_vintage() -> None:
    record = ExecutionRecord()
    record.pool = [
        {
            "table_id": "B01003",
            "title": "Total Population",
            "universe": "Total population",
            "members": [],
        }
    ]
    record.geography = {"for": "county:201", "in": "state:48", "geoid": "0500000US48201"}
    record.geographies = [dict(record.geography)]
    facts = {
        "acs5": {
            2024: {"B01003": {"universe": "Total population", "variables": ["001E"]}},
            2019: {"B01003": {"universe": "Total population (2019)", "variables": ["001E"]}},
        }
    }
    tools = _tools(record)
    tools["build_url"] = BuildUrlTool(
        allowed_tables=lambda: {"B01003"},
        latest_vintage=lambda dataset: 2024,
        table_facts=lambda dataset, year, table_id: (
            facts.get(dataset, {}).get(year, {}).get(table_id)
        ),
        last_geography=lambda: record.geography,
        allowed_geographies=lambda: {("county:201", "state:48")},
    )
    queue = [
        {
            "content": "",
            "tool_calls": [
                {"id": "1", "name": "build_url", "args": {"table_id": "B01003", "vintage": 2019}}
            ],
        },
        {"content": "done", "tool_calls": []},
    ]

    async def complete(
        messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        _ = messages, openai_tools
        return queue.pop(0)

    response = await run_ask("population", complete=complete, tools=tools, record=record)
    assert response.universe == "Total population (2019)"
    assert "/2019/acs/acs5" in response.url


async def test_fetch_with_no_rows_still_returns_the_url() -> None:
    record = ExecutionRecord()
    record.pool = [{"table_id": "B01003", "universe": "Total population", "members": []}]
    record.geography = {"for": "county:201", "in": "state:48", "geoid": "0500000US48201"}
    record.geographies = [dict(record.geography)]
    tools = _tools(record)
    tools["fetch_data"] = FetchDataTool(
        last_url=lambda: record.url,
        census_key=lambda: "secret",
        http_get=lambda url: (200, [["NAME", "GEO_ID", "B01003_001E", "B01003_001M"]]),
    )
    queue = [
        {
            "content": "",
            "tool_calls": [{"id": "1", "name": "build_url", "args": {"table_id": "B01003"}}],
        },
        {"content": "", "tool_calls": [{"id": "2", "name": "fetch_data", "args": {}}]},
        {"content": "No rows.", "tool_calls": []},
    ]

    async def complete(
        messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        _ = messages, openai_tools
        return queue.pop(0)

    response = await run_ask("population", complete=complete, tools=tools, record=record)
    assert response.url
    assert "key=" not in response.url
    assert "/2024/acs/acs5" in response.url
    assert response.rows == []
    assert response.moe == []
    assert response.geoid == "0500000US48201"


async def test_aborted_loop_still_returns_every_contract_field() -> None:
    record = ExecutionRecord()
    tools = _tools(record)
    queue = [
        {
            "content": "trying",
            "tool_calls": [
                {"id": "1", "name": "fetch_data", "args": {}},
                {"id": "2", "name": "fetch_data", "args": {}},
            ],
        }
    ]

    async def complete(
        messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        _ = messages, openai_tools
        return queue.pop(0)

    response = await run_ask("population", complete=complete, tools=tools, record=record)
    assert list(response.model_dump()) == list(CONTRACT_FIELDS)
    assert response.url == ""
    assert "secret" not in response.answer
    assert "key=" not in response.answer
