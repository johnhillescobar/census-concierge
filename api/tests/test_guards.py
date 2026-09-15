"""Slice-1 guards: build an execution record, assert which warnings fire.

No LLM. A stub that always returns the same table would hide a broken guard.
"""

from __future__ import annotations

from src.ask import ExecutionRecord, assemble, dispatch
from src.contract import GeoSpec
from src.guards import evaluate
from src.retrieval.metadata import GeoLevel
from test_ask_loop import _tools
from test_ask_tools import ENTRIES, _geo_tool, _harris

T01 = "Compare median household income between 2015-2019 and 2018-2022"
T03 = "Is the poverty rate in tract 1201 higher than tract 1305?"
T06 = "What share of households are Black families earning over $75k?"


def _codes(record: ExecutionRecord) -> list[str]:
    return [warning.code for warning in evaluate(record)]


def test_empty_record_emits_no_warnings() -> None:
    assert evaluate(ExecutionRecord()) == []


def test_overlapping_acs5_ranges_warn_without_a_second_fetch() -> None:
    record = ExecutionRecord(question=T01)
    assert _codes(record) == ["overlapping_vintage"]
    response = assemble("answer still ships", record)
    assert response.answer == "answer still ships"
    assert response.warnings[0].code == "overlapping_vintage"
    assert "2019" in response.warnings[0].detail
    assert "2022" in response.warnings[0].detail


def test_overlapping_vintages_from_build_url_calls() -> None:
    record = ExecutionRecord()
    record.vintages = [("acs5", 2019), ("acs5", 2022)]
    assert _codes(record) == ["overlapping_vintage"]


def test_non_overlapping_acs5_end_years_do_not_warn() -> None:
    record = ExecutionRecord()
    record.vintages = [("acs5", 2017), ("acs5", 2022)]
    assert _codes(record) == []


async def test_fetched_years_replace_the_built_template_vintage() -> None:
    record = ExecutionRecord()
    tools = _tools(record)
    record.pool = [{"table_id": "B01003", "universe": "Total population", "members": []}]
    record.geography = _harris()
    record.geographies = [_harris()]
    await dispatch(tools["build_url"], {"id": "1", "args": {"table_id": "B01003"}}, record)
    await dispatch(tools["fetch_data"], {"id": "2", "args": {"years": [2022]}}, record)
    assert record.vintages == [("acs5", 2022)]
    assert _codes(record) == []


async def test_overlapping_fetched_years_still_warn() -> None:
    record = ExecutionRecord()
    tools = _tools(record)
    record.pool = [{"table_id": "B01003", "universe": "Total population", "members": []}]
    record.geography = _harris()
    record.geographies = [_harris()]
    await dispatch(tools["build_url"], {"id": "1", "args": {"table_id": "B01003"}}, record)
    await dispatch(tools["fetch_data"], {"id": "2", "args": {"years": [2019, 2022]}}, record)
    assert record.vintages == [("acs5", 2019), ("acs5", 2022)]
    assert _codes(record) == ["overlapping_vintage"]


def test_indistinguishable_tracts_are_not_ranked() -> None:
    record = ExecutionRecord(question=T03)
    record.rows = [
        {"GEO_ID": "1400000US1915501201", "B17001_002E": "100", "B17001_002M": "50"},
        {"GEO_ID": "1400000US1915501305", "B17001_002E": "110", "B17001_002M": "50"},
    ]
    assert _codes(record) == ["moe_not_significant"]


def test_distinguishable_difference_does_not_warn() -> None:
    record = ExecutionRecord(question=T03)
    record.rows = [
        {"GEO_ID": "a", "B17001_002E": "1000", "B17001_002M": "10"},
        {"GEO_ID": "b", "B17001_002E": "2000", "B17001_002M": "10"},
    ]
    assert _codes(record) == []


def test_wildcard_rows_without_a_comparison_do_not_warn() -> None:
    record = ExecutionRecord(question="Median family income by county in Iowa")
    record.rows = [
        {"GEO_ID": "a", "B19113_001E": "1", "B19113_001M": "50"},
        {"GEO_ID": "b", "B19113_001E": "2", "B19113_001M": "50"},
    ]
    assert _codes(record) == []


def test_threshold_predicate_is_not_a_comparison() -> None:
    record = ExecutionRecord(
        question="Renters spending more than 30% of income on rent, by county in Arizona"
    )
    record.rows = [
        {"GEO_ID": "a", "B25070_007E": "1", "B25070_007M": "50"},
        {"GEO_ID": "b", "B25070_007E": "2", "B25070_007M": "50"},
    ]
    assert _codes(record) == []


def test_later_estimate_column_is_checked() -> None:
    record = ExecutionRecord(question=T03)
    record.rows = [
        {
            "GEO_ID": "a",
            "B17001_001E": "1000",
            "B17001_001M": "10",
            "B17001_002E": "100",
            "B17001_002M": "50",
        },
        {
            "GEO_ID": "b",
            "B17001_001E": "2000",
            "B17001_001M": "10",
            "B17001_002E": "110",
            "B17001_002M": "50",
        },
    ]
    assert _codes(record) == ["moe_not_significant"]


def test_unavailable_margins_are_not_compared() -> None:
    record = ExecutionRecord(question=T03)
    record.rows = [
        {"GEO_ID": "a", "B01003_001E": "100", "B01003_001M": "-555555555"},
        {"GEO_ID": "b", "B01003_001E": "110", "B01003_001M": "-555555555"},
    ]
    assert _codes(record) == []


def test_overlapping_vintages_do_not_compare_leftover_rows() -> None:
    record = ExecutionRecord(question=T01)
    record.vintages = [("acs5", 2019), ("acs5", 2022)]
    record.rows = [
        {"GEO_ID": "a", "B19013_001E": "100", "B19013_001M": "50"},
        {"GEO_ID": "b", "B19013_001E": "110", "B19013_001M": "50"},
    ]
    assert _codes(record) == ["overlapping_vintage"]


def test_illegal_geography_combination_warns() -> None:
    record = ExecutionRecord()
    record.geo_status = {
        "legal": False,
        "detail": "block group with in={'state': '56'} is not a legal combination",
    }
    assert _codes(record) == ["geography_unsupported"]
    assert "block group" in evaluate(record)[0].detail


def test_several_matching_places_are_the_result() -> None:
    record = ExecutionRecord(question="Population of Springfield")
    record.geographies = [GeoSpec(name=f"Springfield {i}") for i in range(15)]
    warnings = evaluate(record)
    assert [item.code for item in warnings] == ["ambiguous_place"]
    assert "Springfield 0" in warnings[0].detail
    assert "Springfield 14" in warnings[0].detail
    assert "+3 more" not in warnings[0].detail
    response = assemble("candidates listed", record)
    assert response.answer == "candidates listed"
    assert response.urls == []
    assert response.geoid == ""


def test_one_geography_is_not_ambiguous() -> None:
    record = ExecutionRecord()
    record.geographies = [_harris()]
    assert _codes(record) == []


def test_question_crossing_households_and_families_warns() -> None:
    record = ExecutionRecord(question=T06)
    warnings = evaluate(record)
    assert [item.code for item in warnings] == ["universe_mismatch"]
    assert "households" in warnings[0].detail
    assert "families" in warnings[0].detail


def test_family_income_alone_is_not_a_universe_mismatch() -> None:
    record = ExecutionRecord(question="Median family income by county in Iowa")
    assert _codes(record) == []


async def test_block_group_wildcard_in_a_state_is_illegal() -> None:
    entries = [
        *ENTRIES,
        GeoLevel("block group", "150", ("state", "county", "tract"), ("county", "tract"), "tract"),
    ]
    record = ExecutionRecord(question="Median household income for every block group in Wyoming")
    tool = _geo_tool(table=entries)
    await dispatch(tool, {"id": "bg1", "args": {"query": "every block group in Wyoming"}}, record)
    assert record.geo_status is not None
    assert record.geo_status["legal"] is False
    assert record.geographies == []
    response = assemble("answer still ships", record)
    assert [item.code for item in response.warnings] == ["geography_unsupported"]
    assert "block group" in response.warnings[0].detail
    assert response.answer == "answer still ships"


async def test_unknown_place_is_not_unsupported_geography() -> None:
    record = ExecutionRecord(question="Population of Atlantis, Texas")
    tools = _tools(record)
    await dispatch(
        tools["resolve_geography"], {"id": "2", "args": {"query": "Atlantis, Texas"}}, record
    )
    assert record.geo_status is not None
    assert record.geo_status["legal"] is True
    assert record.geographies == []
    assert _codes(record) == []


async def test_new_geography_drops_previous_fetch() -> None:
    record = ExecutionRecord()
    tools = _tools(record)
    record.pool = [{"table_id": "B01003", "universe": "Total population", "members": []}]
    await dispatch(
        tools["resolve_geography"],
        {"id": "1", "args": {"query": "Harris County, Texas"}},
        record,
    )
    await dispatch(tools["build_url"], {"id": "2", "args": {"table_id": "B01003"}}, record)
    await dispatch(tools["fetch_data"], {"id": "3", "args": {}}, record)
    assert record.rows
    await dispatch(
        tools["resolve_geography"], {"id": "4", "args": {"query": "Cook County"}}, record
    )
    assert record.url is None
    assert record.rows == []
    assert record.table_id == ""
    response = assemble("candidates listed", record)
    assert response.urls == []
    assert [item.code for item in response.warnings] == ["ambiguous_place"]
    assert response.answer == "candidates listed"


async def test_same_geography_keeps_the_fetch() -> None:
    record = ExecutionRecord()
    tools = _tools(record)
    record.pool = [{"table_id": "B01003", "universe": "Total population", "members": []}]
    await dispatch(
        tools["resolve_geography"],
        {"id": "1", "args": {"query": "Harris County, Texas"}},
        record,
    )
    await dispatch(tools["build_url"], {"id": "2", "args": {"table_id": "B01003"}}, record)
    await dispatch(tools["fetch_data"], {"id": "3", "args": {}}, record)
    rows = list(record.rows)
    await dispatch(
        tools["resolve_geography"],
        {"id": "4", "args": {"query": "Harris County, Texas"}},
        record,
    )
    assert record.rows == rows
    assert record.table_id == "B01003"


async def test_ambiguous_resolve_lands_on_the_response() -> None:
    record = ExecutionRecord(question="Population of Cook County")
    tools = _tools(record)
    await dispatch(
        tools["resolve_geography"], {"id": "2", "args": {"query": "Cook County"}}, record
    )
    response = assemble("three Cook Counties", record)
    assert len(record.geographies) == 3
    assert record.geography is not None
    assert record.geography.in_spec == "state:17"
    assert [item.code for item in response.warnings] == ["ambiguous_place"]
    assert response.answer == "three Cook Counties"
