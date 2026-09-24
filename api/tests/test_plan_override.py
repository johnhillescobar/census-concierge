"""Typed plan overrides pin the four-tool path; the model cannot undo them."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

from ask_fixtures import _harris, _tools
from src.ask import ExecutionRecord, run_ask
from src.contract import ResultPlan, apply_override


def _complete(queue: list[dict[str, Any]]):
    async def complete(
        messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        _ = messages, openai_tools
        return queue.pop(0)

    return complete


def _script(table: str, place: str) -> list[dict[str, Any]]:
    return [
        {
            "content": "",
            "tool_calls": [
                {"id": "1", "name": "search_tables", "args": {"question": "wrong question"}}
            ],
        },
        {
            "content": "",
            "tool_calls": [{"id": "2", "name": "resolve_geography", "args": {"query": place}}],
        },
        {
            "content": "",
            "tool_calls": [{"id": "3", "name": "build_url", "args": {"table_id": table}}],
        },
        {
            "content": "",
            "tool_calls": [{"id": "4", "name": "fetch_data", "args": {"years": [2019]}}],
        },
        {"content": "done.", "tool_calls": []},
    ]


async def test_table_override_wins_over_model_args() -> None:
    record = ExecutionRecord()
    plan = ResultPlan(table_id="B19013", geographies=[_harris()])
    apply_override(record, plan)
    response = await run_ask(
        "population of Harris County",
        complete=_complete(_script("B01003", "Harris County, Texas")),
        tools=_tools(record),
        record=record,
        override=plan,
    )
    assert response.table_id == "B19013"
    assert response.plan.table_id == "B19013"
    assert "B19013_001E" in response.urls[0]
    assert "B19013_001M" in response.urls[0]
    assert parse_qs(urlsplit(response.urls[0]).query)["for"] == ["county:201"]


async def test_geography_override_ignores_browser_for_in_and_model_place() -> None:
    record = ExecutionRecord()
    plan = ResultPlan.model_validate(
        {
            "geographies": [
                {"geoid": "0500000US17031", "for_spec": "county:999", "in_spec": "state:00"}
            ]
        }
    )
    apply_override(record, plan)
    response = await run_ask(
        "population of Harris County",
        complete=_complete(_script("B01003", "Harris County, Texas")),
        tools=_tools(record),
        record=record,
        override=plan,
    )
    query = parse_qs(urlsplit(response.urls[0]).query)
    assert query["for"] == ["county:031"]
    assert query["in"] == ["state:17"]
    assert response.plan.geographies[0].geoid == "0500000US17031"
    assert response.plan.geographies[0].for_spec == "county:031"


async def test_overlapping_override_fetches_consecutive_years_and_warns() -> None:
    record = ExecutionRecord()
    years = list(range(2017, 2024))
    plan = ResultPlan(
        table_id="B19013",
        requested_years=years,
        geographies=[_harris()],
        allow_overlapping_acs5=True,
    )
    apply_override(record, plan)
    question = "Plot median household income for Harris County every year from 2017 to 2023"
    response = await run_ask(
        question,
        complete=_complete(_script("B01003", "Harris County, Texas")),
        tools=_tools(record),
        record=record,
        override=plan,
    )
    assert response.plan.allow_overlapping_acs5 is True
    assert response.attempted_years == years
    assert response.plan.years == years
    assert any(item.code == "overlapping_vintage" for item in response.warnings)
    assert all("B19013_001M" in url for url in response.urls)


async def test_overlapping_override_off_restores_destagger() -> None:
    record = ExecutionRecord()
    years = list(range(2017, 2024))
    plan = ResultPlan(
        table_id="B19013",
        requested_years=years,
        geographies=[_harris()],
        allow_overlapping_acs5=False,
    )
    apply_override(record, plan)
    tools = _tools(record)

    def http_get(url: str) -> tuple[int, object]:
        if "/acs/acs1" in url:
            return 404, "unpublished"
        return (
            200,
            [
                ["NAME", "B19013_001E", "B19013_001M", "GEO_ID", "state", "county"],
                ["Harris County, Texas", "1", "1", "0500000US48201", "48", "201"],
            ],
        )

    tools["fetch_data"].http_get = http_get
    question = "Plot median household income for Harris County every year from 2017 to 2023"
    response = await run_ask(
        question,
        complete=_complete(_script("B01003", "Harris County, Texas")),
        tools=tools,
        record=record,
        override=plan,
    )
    assert response.plan.allow_overlapping_acs5 is False
    assert response.attempted_years == [2017, 2022]


async def test_combined_table_geography_year_override() -> None:
    record = ExecutionRecord()
    plan = ResultPlan(
        table_id="B19013B",
        variables=["B19013B_001E"],
        requested_years=[2022],
        geographies=[
            {
                "geoid": "0500000US17031",
                "for_spec": "county:999",
                "in_spec": "state:00",
            }
        ],
    )
    apply_override(record, plan)
    response = await run_ask(
        "population of Harris County in 2024",
        complete=_complete(_script("B01003", "Harris County, Texas")),
        tools=_tools(record),
        record=record,
        override=plan,
    )
    query = parse_qs(urlsplit(response.urls[0]).query)
    assert response.table_id == "B19013B"
    assert response.plan.variables == ["B19013B_001E"]
    assert query["for"] == ["county:031"]
    assert query["in"] == ["state:17"]
    assert response.attempted_years == [2022]
    assert "B19013B_001M" in response.urls[0]
    assert response.plan.geographies[0].for_spec == "county:031"


async def test_race_iteration_override_is_a_deliberate_selection() -> None:
    record = ExecutionRecord()
    plan = ResultPlan(table_id="B19013B", geographies=[_harris()])
    apply_override(record, plan)
    response = await run_ask(
        "median household income in Harris County",
        complete=_complete(_script("B19013", "Harris County, Texas")),
        tools=_tools(record),
        record=record,
        override=plan,
    )
    assert response.table_id == "B19013B"
    assert response.plan.table_id == "B19013B"
