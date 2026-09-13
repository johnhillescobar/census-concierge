"""Slice-1 guards: build an execution record, assert which warnings fire.

No LLM. A stub that always returns the same table would hide a broken guard.
"""

from __future__ import annotations

from src.ask import ExecutionRecord, assemble, dispatch
from src.geo import ResolveGeographyTool
from src.guards import evaluate
from src.retrieval.metadata import GeoLevel
from test_ask_loop import _tools
from test_ask_tools import ENTRIES, _list_geographies

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
    record.geographies = [
        {"name": "Springfield city, Illinois", "for": "place:1769000", "in": "state:17"},
        {"name": "Springfield city, Massachusetts", "for": "place:2567000", "in": "state:25"},
        {"name": "Springfield city, Missouri", "for": "place:2970000", "in": "state:29"},
    ]
    warnings = evaluate(record)
    assert [item.code for item in warnings] == ["ambiguous_place"]
    assert "Illinois" in warnings[0].detail
    assert "Massachusetts" in warnings[0].detail
    response = assemble("candidates listed", record)
    assert response.answer == "candidates listed"
    assert response.url == ""
    assert response.geoid == ""


def test_one_geography_is_not_ambiguous() -> None:
    record = ExecutionRecord()
    record.geographies = [{"name": "Harris County, Texas", "for": "county:201", "in": "state:48"}]
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
    tool = ResolveGeographyTool(list_geographies=_list_geographies, entries=entries)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "every block group in Wyoming"},
            "id": "bg1",
        }
    )
    artifact = message.artifact
    assert artifact.legal is False
    assert artifact.wildcard is True
    assert artifact.matches == []
    assert "block group" in artifact.detail


async def test_ambiguous_resolve_lands_on_the_response() -> None:
    record = ExecutionRecord(question="Population of Cook County")
    tools = _tools(record)
    await dispatch(
        tools["resolve_geography"], {"id": "2", "args": {"query": "Cook County"}}, record
    )
    response = assemble("three Cook Counties", record)
    assert len(record.geographies) == 3
    assert [item.code for item in response.warnings] == ["ambiguous_place"]
    assert response.answer == "three Cook Counties"
