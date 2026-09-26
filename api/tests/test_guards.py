"""Slice-1 guards: build an execution record, assert which warnings fire.

No LLM. A stub that always returns the same table would hide a broken guard.
"""

from __future__ import annotations

import pytest
from ask_fixtures import ENTRIES, _geo_tool, _harris, _tools
from src.ask import ExecutionRecord, _absorb, assemble, dispatch
from src.census_url import CENSUS_API, CensusURL
from src.contract import GeoSpec
from src.fetch import FetchDataResult, clear_series
from src.guards import MOE_COMBINE_FORMULA, evaluate
from src.retrieval.metadata import GeoLevel
from src.tools import BuildUrlResult
from src.vintages import moe_rows, period_for

T01 = "Compare median household income between 2015-2019 and 2018-2022"
T03 = "Is the poverty rate in tract 1201 higher than tract 1305?"
T06 = "What share of households are Black families earning over $75k?"
T17 = "What is the median household income across these five tracts combined?"
T18 = "Total population without health insurance across every tract in Wayne County"
T15 = "Median household income for ZIP code 10001 every year since 2018"
T16 = "Compare poverty by census tract within the city of Denver"
T11 = "Unemployment in Middlebury, Vermont each year since 2017"
T12 = "1-year ACS poverty for Fresno County, 2018 through 2022"
T13 = "Broadband subscription trend by census tract in Wayne County, 2018 to 2022"
T09 = "Number of cell phones in Denver since 2017"
T14 = "How has the share of households with a computer changed since 2013?"
Q24 = "Median household income for ZCTA 90210"


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


def test_from_to_consecutive_acs5_years_overlap() -> None:
    record = ExecutionRecord(
        question="Plot median household income for Cuyahoga County every year from 2017 to 2023"
    )
    assert _codes(record) == ["overlapping_vintage"]


def _fetch(**fields: object) -> FetchDataResult:
    payload: dict[str, object] = {
        "ok": True,
        "url": "",
        "urls": [],
        "rows": [],
        "status_code": 200,
        "detail": "",
        "legs": [],
        "requested_years": [],
        "attempted_years": [],
        "succeeded_years": [],
        "failed_years": [],
        "omitted_years": [],
        "omission_reasons": [],
        "dataset": "acs5",
        "acs1_ineligible": False,
    }
    payload.update(fields)
    return FetchDataResult.model_validate(payload)


def test_small_place_series_warns_acs1_ineligible() -> None:
    record = ExecutionRecord(question=T11)
    record.vintages = [("acs5", 2017), ("acs5", 2022)]
    record.fetch = _fetch(
        acs1_ineligible=True,
        requested_years=list(range(2017, 2024)),
        attempted_years=[2017, 2022],
        succeeded_years=[2017, 2022],
        omitted_years=[2018, 2019, 2020, 2021, 2023],
        omission_reasons=["overlapping_vintage"] * 5,
        urls=[
            "https://api.census.gov/data/2017/acs/acs5?get=NAME",
            "https://api.census.gov/data/2022/acs/acs5?get=NAME",
        ],
    )
    assert _codes(record) == ["acs1_geography_ineligible"]
    response = assemble("two ACS5 points", record)
    assert response.warnings[0].code == "acs1_geography_ineligible"
    assert "65,000" not in response.warnings[0].detail
    assert "not published" in response.warnings[0].detail.casefold()
    assert response.attempted_years == [2017, 2022]
    assert response.omission_reasons == ["overlapping_vintage"] * 5


def test_acs1_fallback_year_warns_ineligible_geography() -> None:
    record = ExecutionRecord()
    record.table_id = "B01003"
    record.universe = "total population"
    record.fetch = _fetch(
        acs1_ineligible=True,
        dataset="acs5",
        requested_years=[2024],
        attempted_years=[2024],
        succeeded_years=[2024],
        urls=[
            "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M"
            "&for=place:44275&in=state:50"
        ],
        rows=[
            {
                "GEO_ID": "1600000US5044275",
                "NAME": "Middlebury CDP, Vermont",
                "B01003_001E": "7220",
                "B01003_001M": "12",
                "year": "2024",
            }
        ],
    )
    record.rows = list(record.fetch.rows)
    assert _codes(record) == ["acs1_geography_ineligible"]
    response = assemble("ACS5 still ships", record)
    assert response.warnings[0].code == "acs1_geography_ineligible"
    assert response.urls == list(record.fetch.urls)
    assert response.table_id == "B01003"
    assert response.universe == "total population"
    assert response.rows[0]["dataset"] == "acs5"
    assert response.rows[0]["vintage"] == "2024"
    assert response.rows[0]["GEO_ID"] == "1600000US5044275"
    assert response.rows[0]["B01003_001E"] == "7220"
    assert response.moe[0]["B01003_001M"] == "12"


def test_acs1_eligible_geography_does_not_warn() -> None:
    record = ExecutionRecord()
    record.fetch = _fetch(
        dataset="acs1",
        acs1_ineligible=False,
        requested_years=[2024],
        attempted_years=[2024],
        succeeded_years=[2024],
        urls=[
            "https://api.census.gov/data/2024/acs/acs1?get=NAME,GEO_ID,B01003_001E,B01003_001M"
            "&for=county:201&in=state:48"
        ],
    )
    assert "acs1_geography_ineligible" not in _codes(record)


def test_acs1_span_crossing_2020_warns_and_keeps_the_gap() -> None:
    record = ExecutionRecord(question=T12)
    record.vintages = [("acs1", year) for year in (2018, 2019, 2021, 2022)]
    record.fetch = _fetch(
        dataset="acs1",
        requested_years=list(range(2018, 2023)),
        attempted_years=[2018, 2019, 2021, 2022],
        succeeded_years=[2018, 2019, 2021, 2022],
        omitted_years=[2020],
        omission_reasons=["vintage_gap_2020"],
        urls=["https://api.census.gov/data/2018/acs/acs1?get=NAME"],
        rows=[
            {"year": "2018", "B17001_001E": "1", "B17001_001M": "1"},
            {"year": "2019", "B17001_001E": "1", "B17001_001M": "1"},
            {"year": "2021", "B17001_001E": "1", "B17001_001M": "1"},
            {"year": "2022", "B17001_001E": "1", "B17001_001M": "1"},
        ],
    )
    assert _codes(record) == ["vintage_gap_2020"]
    response = assemble("four years, 2020 absent", record)
    assert response.warnings[0].code == "vintage_gap_2020"
    assert response.omitted_years == [2020]
    assert "2020" not in [row.get("year") for row in response.rows]


def test_sparse_acs1_years_do_not_infer_a_2020_gap() -> None:
    record = ExecutionRecord()
    record.fetch = _fetch(
        dataset="acs1",
        requested_years=[2018, 2022],
        attempted_years=[2018, 2022],
        succeeded_years=[2018, 2022],
    )
    assert "vintage_gap_2020" not in _codes(record)


def test_acs1_2020_gap_inferred_from_requested_years() -> None:
    record = ExecutionRecord()
    record.fetch = _fetch(
        dataset="acs1",
        requested_years=list(range(2018, 2023)),
        attempted_years=[2018, 2019, 2021, 2022],
        succeeded_years=[2018, 2019, 2021, 2022],
    )
    assert _codes(record) == ["vintage_gap_2020"]


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


def test_versus_series_does_not_warn_on_same_place_years() -> None:
    record = ExecutionRecord(question="Median rent in Austin versus the Texas average")
    record.rows = [
        {"GEO_ID": "a", "year": "2017", "B25064_001E": "100", "B25064_001M": "50"},
        {"GEO_ID": "a", "year": "2022", "B25064_001E": "110", "B25064_001M": "50"},
        {"GEO_ID": "b", "year": "2017", "B25064_001E": "1000", "B25064_001M": "10"},
        {"GEO_ID": "b", "year": "2022", "B25064_001E": "2000", "B25064_001M": "10"},
    ]
    assert _codes(record) == []


def test_versus_series_warns_when_same_year_legs_are_indistinguishable() -> None:
    record = ExecutionRecord(question="Median rent in Austin versus the Texas average")
    record.rows = [
        {"GEO_ID": "a", "year": "2017", "B25064_001E": "100", "B25064_001M": "50"},
        {"GEO_ID": "b", "year": "2017", "B25064_001E": "110", "B25064_001M": "50"},
        {"GEO_ID": "a", "year": "2022", "B25064_001E": "1000", "B25064_001M": "10"},
        {"GEO_ID": "b", "year": "2022", "B25064_001E": "2000", "B25064_001M": "10"},
    ]
    response = assemble("versus series", record)
    assert [item.code for item in response.warnings] == ["moe_not_significant"]
    assert {item.year for item in response.comparisons} == {"2017", "2022"}


def test_equal_threshold_is_not_distinguishable() -> None:
    record = ExecutionRecord(question=T03)
    record.rows = [
        {"GEO_ID": "a", "B17001_002E": "100", "B17001_002M": "6"},
        {"GEO_ID": "b", "B17001_002E": "110", "B17001_002M": "8"},
    ]
    response = assemble("not ranked", record)
    assert [item.code for item in response.warnings] == ["moe_not_significant"]
    pair = response.comparisons[0]
    assert pair.threshold == "10"
    assert pair.estimate_a == "100"
    assert pair.estimate_b == "110"
    assert pair.moe_a == "6"
    assert pair.moe_b == "8"
    assert pair.distinguishable is False


def test_year_over_year_indistinguishable_change() -> None:
    record = ExecutionRecord(question="Compare poverty in 2017 to 2022")
    record.rows = [
        {"GEO_ID": "a", "year": "2017", "B17001_002E": "100", "B17001_002M": "50"},
        {"GEO_ID": "a", "year": "2022", "B17001_002E": "110", "B17001_002M": "50"},
    ]
    response = assemble("not change", record)
    assert [item.code for item in response.warnings] == ["moe_not_significant"]
    assert response.comparisons[0].distinguishable is False
    assert response.comparisons[0].geoid_a == "a"
    assert response.comparisons[0].geoid_b == "a"
    assert response.comparisons[0].year == ""


def test_parent_place_exposes_shared_sample_and_conclusion() -> None:
    record = ExecutionRecord(question="Compare median gross rent in Austin to the Texas average")
    record.geographies = [
        GeoSpec(
            name="Austin city, Texas",
            level="place",
            for_spec="place:4805000",
            in_spec="state:48",
            geoid="1600000US4805000",
        ),
        GeoSpec(name="Texas", level="state", for_spec="state:48", geoid="0400000US48"),
    ]
    record.geo_status = {
        "legal": True,
        "detail": "",
        "nested": True,
        "compare": True,
        "compare_count": 2,
    }
    record.rows = [
        {"GEO_ID": "1600000US4805000", "B25064_001E": "1729", "B25064_001M": "14"},
        {"GEO_ID": "0400000US48", "B25064_001E": "1403", "B25064_001M": "4"},
    ]
    response = assemble("Austin vs Texas", record)
    assert [item.code for item in response.warnings] == ["shared_sample"]
    pair = response.comparisons[0]
    assert pair.distinguishable is True
    assert pair.shared_sample is True
    assert pair.estimate_a == "1729"
    assert pair.estimate_b == "1403"
    assert pair.moe_a == "14"
    assert pair.moe_b == "4"
    assert float(pair.threshold) > 14


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
    record.geographies = [
        GeoSpec(
            name=f"Springfield {i}",
            level="place",
            for_spec=f"place:{i}",
            in_spec="state:17",
            geoid=f"1600000US17{i:05d}",
            dataset="acs5",
            vintage=2024,
        )
        for i in range(15)
    ]
    warnings = evaluate(record)
    assert [item.code for item in warnings] == ["ambiguous_place"]
    assert "Springfield 0" in warnings[0].detail
    assert "Springfield 14" in warnings[0].detail
    assert "+3 more" not in warnings[0].detail
    assert [row.geoid for row in warnings[0].candidates] == [
        spec.geoid for spec in record.geographies
    ]
    first = warnings[0].candidates[0]
    assert first.level == "place"
    assert first.for_spec == "place:0"
    assert first.in_spec == "state:17"
    assert first.dataset == "acs5"
    assert first.vintage == 2024
    built = CensusURL(
        f"{CENSUS_API}/{first.vintage}/acs/{first.dataset}"
        f"?get=NAME,GEO_ID,B01003_001E,B01003_001M&for={first.for_spec}&in={first.in_spec}"
        "&key=secret"
    )
    assert "place:0" in str(built)
    assert "state:17" in str(built)
    assert "key=" not in str(built)
    response = assemble("candidates listed", record)
    assert response.answer == "candidates listed"
    assert response.urls == []
    assert response.geoid == ""
    assert response.warnings[0].candidates == warnings[0].candidates


def test_one_geography_is_not_ambiguous() -> None:
    record = ExecutionRecord()
    record.geographies = [_harris()]
    assert _codes(record) == []
    response = assemble("Harris County, Texas", record)
    assert response.warnings == []


def test_comparison_legs_are_not_ambiguous_places() -> None:
    record = ExecutionRecord(question="Median gross rent in Austin versus the Texas average")
    record.geographies = [
        GeoSpec(
            name="Austin city, Texas",
            level="place",
            for_spec="place:4805000",
            in_spec="state:48",
        ),
        GeoSpec(name="Texas", level="state", for_spec="state:48"),
    ]
    record.geo_status = {
        "legal": True,
        "detail": "",
        "nested": True,
        "compare": True,
        "compare_count": 2,
    }
    assert _codes(record) == ["shared_sample"]


def test_comparison_with_leftover_matches_still_warns() -> None:
    record = ExecutionRecord(question="Springfield versus the Texas average")
    record.geographies = [
        GeoSpec(name="Springfield city, Missouri", level="place"),
        GeoSpec(name="Texas", level="state", for_spec="state:48"),
        GeoSpec(name="Springfield city, Illinois", level="place"),
    ]
    record.geo_status = {"legal": True, "detail": "", "nested": True, "compare": True}
    assert _codes(record) == ["ambiguous_place"]


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
    assert [row.for_spec for row in record.geographies] == ["block group:*"]
    assert record.geographies[0].in_spec == "state:56"
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


async def test_new_geography_clears_current_fetch_but_keeps_the_url() -> None:
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
    assert response.urls
    assert "county:201" in response.urls[0]
    assert "B01003_001E" in response.urls[0]
    assert "key=" not in response.urls[0]
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


def _count_rows(n: int) -> list[dict[str, str | None]]:
    margins = ("3", "4", "12", "0", "0", "0")
    return [{"GEO_ID": f"g{i}", "B01003_001E": "10", "B01003_001M": margins[i]} for i in range(n)]


def test_median_combine_warns_without_fetched_rows() -> None:
    record = ExecutionRecord(question=T17, table_id="B19013")
    assert _codes(record) == ["median_not_aggregatable"]


def test_combined_median_is_not_invented() -> None:
    record = ExecutionRecord(question=T17, table_id="B19013")
    record.rows = [
        {
            "GEO_ID": "a",
            "B19013_001E": "40000",
            "B19013_001M": "200",
            "B01003_001E": "100",
            "B01003_001M": "10",
        },
        {
            "GEO_ID": "b",
            "B19013_001E": "80000",
            "B19013_001M": "200",
            "B01003_001E": "300",
            "B01003_001M": "10",
        },
        {
            "GEO_ID": "c",
            "B19013_001E": "50000",
            "B19013_001M": "200",
            "B01003_001E": "100",
            "B01003_001M": "10",
        },
        {
            "GEO_ID": "d",
            "B19013_001E": "50000",
            "B19013_001M": "200",
            "B01003_001E": "100",
            "B01003_001M": "10",
        },
        {
            "GEO_ID": "e",
            "B19013_001E": "50000",
            "B19013_001M": "200",
            "B01003_001E": "100",
            "B01003_001M": "10",
        },
    ]
    response = assemble("declined", record)
    assert [item.code for item in response.warnings] == ["median_not_aggregatable"]
    assert [row.get("GEO_ID") for row in response.rows] == ["a", "b", "c", "d", "e"]
    values = {row.get("B19013_001E") for row in response.rows}
    assert values == {"40000", "80000", "50000"}
    assert any(item.table_id == "B19001" for item in response.alternatives)
    bracket = next(item for item in response.alternatives if item.table_id == "B19001")
    assert bracket.title == "Household Income"
    assert bracket.universe == "Households"
    assert bracket.reason == "distribution versus median"


def test_bracket_alternative_is_not_duplicated() -> None:
    record = ExecutionRecord(question=T17, table_id="B19013")
    record.pool = [
        {
            "table_id": "B19013",
            "title": "Median Household Income",
            "universe": "Households",
            "members": [],
        },
        {
            "table_id": "B19001",
            "title": "Household Income",
            "universe": "Households",
            "members": [],
        },
    ]
    response = assemble("declined", record)
    assert [item.table_id for item in response.alternatives].count("B19001") == 1


def test_combined_margin_is_rss_not_linear() -> None:
    record = ExecutionRecord(question=T18, table_id="B27001")
    record.rows = [
        {"GEO_ID": "a", "B27001_001E": "10", "B27001_001M": "3"},
        {"GEO_ID": "b", "B27001_001E": "20", "B27001_001M": "4"},
        {"GEO_ID": "c", "B27001_001E": "30", "B27001_001M": "12"},
    ]
    response = assemble("summed", record)
    assert response.warnings == []
    combined = response.rows[-1]
    assert combined["B27001_001E"] == "60"
    assert combined["B27001_001M"] == "13"
    assert combined["MOE_formula"] == MOE_COMBINE_FORMULA
    assert combined["component_count"] == "3"
    assert combined["GEO_ID"] == ""
    assert response.moe[-1]["B27001_001M"] == "13"


def test_five_areas_combine_without_degraded_warning() -> None:
    record = ExecutionRecord(question=T18, table_id="B01003")
    record.rows = _count_rows(5)
    response = assemble("summed", record)
    assert response.warnings == []
    combined = response.rows[-1]
    assert combined["B01003_001E"] == "50"
    assert combined["B01003_001M"] == "13"
    assert combined["component_count"] == "5"


def test_six_areas_warn_and_keep_the_rss_total() -> None:
    record = ExecutionRecord(question=T18, table_id="B01003")
    record.rows = _count_rows(6)
    response = assemble("summed", record)
    assert [item.code for item in response.warnings] == ["moe_aggregation_degraded"]
    assert "6" in response.warnings[0].detail
    assert MOE_COMBINE_FORMULA in response.warnings[0].detail
    combined = response.rows[-1]
    assert combined["B01003_001E"] == "60"
    assert combined["B01003_001M"] == "13"
    assert len(response.rows) == 7


def test_sentinel_area_is_dropped_not_zeroed() -> None:
    record = ExecutionRecord(question=T18, table_id="B01003")
    rows = _count_rows(6)
    rows[5]["B01003_001E"] = "-555555555"
    rows[5]["B01003_001M"] = "-555555555"
    record.rows = rows
    response = assemble("summed", record)
    assert response.warnings == []
    combined = response.rows[-1]
    assert combined["B01003_001E"] == "50"
    assert combined["B01003_001M"] == "13"
    assert combined["component_count"] == "5"


def test_area_without_a_margin_is_not_a_component() -> None:
    record = ExecutionRecord(question=T18, table_id="B01003")
    rows = _count_rows(3)
    rows[2]["B01003_001M"] = "-555555555"
    record.rows = rows
    response = assemble("summed", record)
    combined = response.rows[-1]
    assert combined["B01003_001E"] == "20"
    assert combined["B01003_001M"] == "5"
    assert combined["component_count"] == "2"


def test_all_sentinel_inputs_produce_no_combined_row() -> None:
    record = ExecutionRecord(question=T18, table_id="B01003")
    record.rows = [
        {"GEO_ID": "a", "B01003_001E": "-555555555", "B01003_001M": "-555555555"},
        {"GEO_ID": "b", "B01003_001E": "-888888888", "B01003_001M": "3"},
    ]
    response = assemble("nothing to add", record)
    assert response.warnings == []
    assert [row.get("GEO_ID") for row in response.rows] == ["a", "b"]


def test_wildcard_listing_is_not_combined() -> None:
    record = ExecutionRecord(
        question="Total population by tract in Wayne County", table_id="B01003"
    )
    record.rows = _count_rows(6)
    response = assemble("listed", record)
    assert response.warnings == []
    assert len(response.rows) == 6


def test_year_tagged_rows_combine_within_vintage_not_across() -> None:
    record = ExecutionRecord(question=T18, table_id="B01003")
    rows: list[dict[str, str | None]] = []
    for year in ("2019", "2022"):
        for i, margin in enumerate(("3", "4", "12")):
            rows.append(
                {
                    "GEO_ID": f"g{i}",
                    "year": year,
                    "B01003_001E": "10",
                    "B01003_001M": margin,
                }
            )
    record.rows = rows
    response = assemble("summed", record)
    assert response.warnings == []
    combined = [row for row in response.rows if row.get("component_count")]
    assert len(combined) == 2
    assert {row.get("year") for row in combined} == {"2019", "2022"}
    for row in combined:
        assert row["B01003_001E"] == "30"
        assert row["B01003_001M"] == "13"
        assert row["component_count"] == "3"
        assert row["GEO_ID"] == ""


def test_combined_statistical_area_is_not_a_sum() -> None:
    record = ExecutionRecord(
        question="Population of the Dallas combined statistical area by county",
        table_id="B01003",
    )
    record.rows = _count_rows(6)
    response = assemble("listed", record)
    assert response.warnings == []
    assert len(response.rows) == 6


def test_rent_median_combine_does_not_offer_income_brackets() -> None:
    record = ExecutionRecord(
        question="What is the median gross rent across these five tracts combined?",
        table_id="B25064",
    )
    response = assemble("declined", record)
    assert [item.code for item in response.warnings] == ["median_not_aggregatable"]
    assert all(item.table_id != "B19001" for item in response.alternatives)
    assert "B19001" not in response.warnings[0].detail


def test_a_rate_is_not_summed_across_areas() -> None:
    record = ExecutionRecord(
        question="Unemployment rate across every tract in Wayne County", table_id="B23025"
    )
    record.rows = [
        {"GEO_ID": "a", "B23025_005E": "10", "B23025_005M": "3"},
        {"GEO_ID": "b", "B23025_005E": "20", "B23025_005M": "4"},
        {"GEO_ID": "c", "B23025_005E": "30", "B23025_005M": "12"},
    ]
    response = assemble("listed", record)
    assert response.warnings == []
    assert [row.get("GEO_ID") for row in response.rows] == ["a", "b", "c"]


def test_derived_measures_are_not_summed_across_areas() -> None:
    for question in (
        "share of households across every tract",
        "poverty ratio across these counties",
        "gini index across every tract",
        "population density across these counties",
        "income per-capita across every tract",
    ):
        record = ExecutionRecord(question=question, table_id="B01003")
        record.rows = _count_rows(3)
        response = assemble("listed", record)
        assert [row.get("GEO_ID") for row in response.rows] == ["g0", "g1", "g2"], question
        assert all(not row.get("component_count") for row in response.rows), question


def test_combine_wording_sums_additive_counts() -> None:
    for question in (
        "combine these counties",
        "total population of these counties combined",
    ):
        record = ExecutionRecord(question=question, table_id="B01003")
        record.rows = _count_rows(3)
        response = assemble("summed", record)
        combined = response.rows[-1]
        assert combined["B01003_001E"] == "30", question
        assert combined["component_count"] == "3", question


def test_race_iteration_median_does_not_use_overall_brackets() -> None:
    record = ExecutionRecord(
        question="aggregate household income across every tract",
        table_id="B19013A",
    )
    record.pool = [
        {
            "table_id": "B19013",
            "title": "Median Household Income",
            "universe": "Households",
            "members": ["B19013A"],
        }
    ]
    record.rows = [
        {"GEO_ID": "a", "B19013A_001E": "40000", "B19013A_001M": "200"},
        {"GEO_ID": "b", "B19013A_001E": "80000", "B19013A_001M": "200"},
        {"GEO_ID": "c", "B19013A_001E": "50000", "B19013A_001M": "200"},
    ]
    response = assemble("declined", record)
    assert [item.code for item in response.warnings] == ["median_not_aggregatable"]
    assert [row.get("GEO_ID") for row in response.rows] == ["a", "b", "c"]
    assert all(item.table_id != "B19001" for item in response.alternatives)
    assert "B19001" not in response.warnings[0].detail


def test_combined_row_requires_the_same_areas_per_variable() -> None:
    record = ExecutionRecord(question=T18, table_id="B27001")
    record.rows = [
        {
            "GEO_ID": "a",
            "B27001_001E": "10",
            "B27001_001M": "3",
            "B27001_002E": "1",
            "B27001_002M": "1",
        },
        {
            "GEO_ID": "b",
            "B27001_001E": "20",
            "B27001_001M": "4",
            "B27001_002E": "-555555555",
            "B27001_002M": "-555555555",
        },
        {
            "GEO_ID": "c",
            "B27001_001E": "30",
            "B27001_001M": "12",
            "B27001_002E": "2",
            "B27001_002M": "1",
        },
    ]
    response = assemble("listed", record)
    assert [row.get("GEO_ID") for row in response.rows] == ["a", "b", "c"]
    assert all(not row.get("component_count") for row in response.rows)


def test_zip_language_warns_without_blocking_a_zcta_row() -> None:
    record = ExecutionRecord(question=T15)
    record.rows = [
        {
            "GEO_ID": "860Z200US10001",
            "NAME": "ZCTA5 10001",
            "B19013_001E": "99000",
            "B19013_001M": "5000",
        }
    ]
    assert _codes(record) == ["zcta_not_zip"]
    response = assemble("ZCTA, not ZIP", record)
    assert response.answer == "ZCTA, not ZIP"
    assert [item.code for item in response.warnings] == ["zcta_not_zip"]
    assert "10001" in response.warnings[0].detail
    assert "ACS1" in response.warnings[0].detail
    assert "nest" in response.warnings[0].detail
    assert "2020" in response.warnings[0].detail
    assert [row.get("GEO_ID") for row in response.rows] == ["860Z200US10001"]


def test_zcta_wording_does_not_emit_zcta_not_zip() -> None:
    record = ExecutionRecord(question=Q24)
    record.geographies = [
        GeoSpec(
            name="ZCTA5 90210",
            level="zip code tabulation area",
            for_spec="zip code tabulation area:90210",
        )
    ]
    record.geography = record.geographies[0]
    record.rows = [{"GEO_ID": "860Z200US90210", "B19013_001E": "100", "B19013_001M": "10"}]
    response = assemble("single vintage", record)
    assert response.warnings == []
    assert response.geoid == "860Z200US90210"
    assert [row.get("GEO_ID") for row in response.rows] == ["860Z200US90210"]


async def test_tract_within_a_place_does_not_invent_a_fetch() -> None:
    record = ExecutionRecord(question=T16)
    tools = _tools(record)
    await dispatch(tools["resolve_geography"], {"id": "2", "args": {"query": T16}}, record)
    assert record.geo_status is not None
    assert record.geo_status["legal"] is False
    assert record.geo_status["nested"] is False
    assert record.geographies == []
    assert record.geography is None
    response = assemble("containment is not expressible", record)
    assert [item.code for item in response.warnings] == ["geography_not_nested"]
    assert "tract" in response.warnings[0].detail
    assert "place" in response.warnings[0].detail
    assert "Denver" in response.warnings[0].detail
    assert response.rows == []
    assert response.urls == []
    assert response.answer == "containment is not expressible"


async def test_zctas_in_a_state_warn_as_not_nested() -> None:
    for query in ("all ZCTAs in Oregon", "ZCTAs within Oregon"):
        record = ExecutionRecord(question=query)
        tools = _tools(record)
        await dispatch(tools["resolve_geography"], {"id": "2", "args": {"query": query}}, record)
        response = assemble("ZCTAs nest in nothing", record)
        assert record.geographies == []
        assert [item.code for item in response.warnings] == ["geography_not_nested"], query
        assert response.urls == []


async def test_named_zcta_with_a_state_warns_as_not_nested() -> None:
    query = "Median household income for ZCTA 90210 in Oregon"
    record = ExecutionRecord(question=query)
    tools = _tools(record)
    await dispatch(tools["resolve_geography"], {"id": "2", "args": {"query": query}}, record)
    response = assemble("ZCTAs nest in nothing", record)
    assert record.geographies == []
    assert [item.code for item in response.warnings] == ["geography_not_nested"]
    assert response.urls == []


async def test_zcta_inside_a_county_is_not_nested() -> None:
    record = ExecutionRecord(question="all zctas in Harris County")
    tools = _tools(record)
    await dispatch(
        tools["resolve_geography"],
        {"id": "2", "args": {"query": "all zctas in Harris County"}},
        record,
    )
    response = assemble("ZCTAs nest in nothing", record)
    assert record.geographies == []
    assert [item.code for item in response.warnings] == ["geography_not_nested"]


async def test_zcta_inside_a_place_is_not_a_national_wildcard() -> None:
    tool = _geo_tool()
    for query in (
        "zctas inside Denver",
        "zip codes inside Denver",
        "census tract within Denver",
        "places inside Denver",
        "cities inside Denver",
        "all zip codes in Denver",
        "every zcta in Denver",
        "all places in Denver",
        "all counties in Denver",
        "cities inside Denver, Colorado",
        "places inside Denver, CO",
        "counties inside Denver, Colorado",
        "the part of ZIP 80202 inside Denver",
        "ZCTA 80202 inside Denver",
        "ZIP 80202 inside Denver",
        "ZIP 80202 in Denver",
        "ZCTA 80202 in Denver",
    ):
        message = await tool.ainvoke(
            {
                "type": "tool_call",
                "name": "resolve_geography",
                "args": {"query": query},
                "id": "c1",
            }
        )
        assert message.artifact.specs == [], query
        assert message.artifact.legal is False, query
        assert message.artifact.nested is False, query


def test_dict_geo_artifact_preserves_nested_false() -> None:
    record = ExecutionRecord(question=T16)
    _absorb(
        record,
        "resolve_geography",
        {
            "matches": [],
            "legal": False,
            "detail": "tract does not nest in place (Denver)",
            "nested": False,
        },
    )
    assert record.geo_status is not None
    assert record.geo_status["nested"] is False
    assert [item.code for item in assemble("no fetch", record).warnings] == ["geography_not_nested"]


def test_published_zcta_name_is_not_zip_language() -> None:
    record = ExecutionRecord(question="Median household income for zip code tabulation area 90210")
    assert _codes(record) == []


async def test_tract_within_a_county_is_not_a_nesting_warning() -> None:
    record = ExecutionRecord(question="poverty by census tract within Wayne County")
    tools = _tools(record)
    await dispatch(
        tools["resolve_geography"],
        {"id": "2", "args": {"query": "poverty by census tract within Wayne County"}},
        record,
    )
    assert record.geo_status is not None
    assert record.geo_status["nested"] is not False
    assert "geography_not_nested" not in _codes(record)


def _wayne_tracts() -> GeoSpec:
    return GeoSpec(
        level="tract",
        name="all tracts in Wayne County, Michigan",
        for_spec="tract:*",
        in_spec="state:26 county:163",
        dataset="acs5",
    )


def test_tract_series_crossing_2020_warns_from_requested_years() -> None:
    record = ExecutionRecord(question=T13, table_id="B28002")
    record.geographies = [_wayne_tracts()]
    record.fetch = _fetch(
        dataset="acs5",
        requested_years=list(range(2018, 2023)),
        attempted_years=[2018],
        succeeded_years=[2018],
        omitted_years=[2019, 2020, 2021, 2022],
        omission_reasons=["overlapping_vintage"] * 4,
        rows=[
            {
                "GEO_ID": "1400000US26163500100",
                "NAME": "Census Tract 5001",
                "year": "2018",
                "B28002_004E": "10",
                "B28002_004M": "2",
            }
        ],
    )
    record.rows = list(record.fetch.rows)
    assert _codes(record) == ["boundary_change_2020"]
    response = assemble("still ships", record)
    warning = response.warnings[0]
    assert warning.code == "boundary_change_2020"
    assert "tract" in warning.detail
    assert "Wayne County" in warning.detail
    assert period_for("acs5", 2018) in warning.detail
    assert period_for("acs5", 2022) in warning.detail
    row = response.rows[0]
    assert row["dataset"] == "acs5"
    assert row["vintage"] == "2018"
    assert row["period"] == "2014-2018"
    assert row["table_id"] == "B28002"
    assert row["GEO_ID"] == "1400000US26163500100"
    assert row["B28002_004E"] == "10"
    assert response.moe[0]["B28002_004M"] == "2"


def test_block_group_series_crossing_2020_warns() -> None:
    record = ExecutionRecord()
    record.geographies = [
        GeoSpec(
            level="block group",
            name="block groups in tract 5001",
            for_spec="block group:*",
            in_spec="state:26 county:163 tract:500100",
        )
    ]
    record.fetch = _fetch(
        dataset="acs5",
        requested_years=[2019, 2022],
        attempted_years=[2019, 2022],
        succeeded_years=[2019, 2022],
    )
    assert _codes(record) == ["boundary_change_2020"]
    assert "block group" in evaluate(record)[0].detail
    assert "2015-2019" in evaluate(record)[0].detail
    assert "2018-2022" in evaluate(record)[0].detail


def test_county_series_crossing_2020_does_not_warn_boundary() -> None:
    record = ExecutionRecord(question=T13)
    record.geographies = [
        GeoSpec(level="county", name="Wayne County", for_spec="county:163", in_spec="state:26")
    ]
    record.fetch = _fetch(
        dataset="acs5",
        requested_years=list(range(2018, 2023)),
        attempted_years=[2018],
        succeeded_years=[2018],
    )
    assert "boundary_change_2020" not in _codes(record)


def test_tract_series_entirely_before_or_after_redraw_does_not_warn() -> None:
    before = ExecutionRecord()
    before.geographies = [_wayne_tracts()]
    before.fetch = _fetch(requested_years=[2016, 2017, 2018, 2019], attempted_years=[2016])
    after = ExecutionRecord()
    after.geographies = [_wayne_tracts()]
    after.fetch = _fetch(requested_years=[2021, 2022, 2023], attempted_years=[2021])
    assert _codes(before) == []
    assert _codes(after) == []


def test_boundary_warning_survives_partial_fetch_failure() -> None:
    record = ExecutionRecord(table_id="B28002")
    record.geographies = [_wayne_tracts()]
    record.fetch = _fetch(
        dataset="acs5",
        requested_years=[2017, 2022],
        attempted_years=[2017, 2022],
        succeeded_years=[2022],
        failed_years=[2017],
        rows=[
            {
                "GEO_ID": "1400000US26163500100",
                "year": "2022",
                "B28002_004E": "10",
                "B28002_004M": "2",
            }
        ],
    )
    record.rows = list(record.fetch.rows)
    response = assemble("one year failed", record)
    assert [item.code for item in response.warnings] == ["boundary_change_2020"]
    assert "2013-2017" in response.warnings[0].detail
    assert "2018-2022" in response.warnings[0].detail
    assert response.failed_years == [2017]
    assert response.rows[0]["period"] == "2018-2022"


def test_tract_geoid_without_a_spec_still_warns() -> None:
    record = ExecutionRecord()
    record.rows = [
        {"GEO_ID": "1400000US26163500100", "year": "2018", "B28002_004E": "1", "B28002_004M": "1"},
        {"GEO_ID": "1400000US26163500100", "year": "2022", "B28002_004E": "2", "B28002_004M": "1"},
    ]
    assert _codes(record) == ["boundary_change_2020"]


def test_sentinel_moe_is_none_not_zero() -> None:
    record = ExecutionRecord(table_id="B01003")
    record.rows = [{"GEO_ID": "0500000US48201", "B01003_001E": "10", "B01003_001M": "-555555555"}]
    record.vintages = [("acs5", 2024)]
    response = assemble("ships", record)
    assert response.moe[0]["B01003_001M"] is None
    assert response.rows[0]["B01003_001M"] == "-555555555"
    assert moe_rows(record.rows)[0]["B01003_001M"] is None
    assert response.rows[0]["period"] == "2020-2024"


def test_published_zero_moe_is_kept() -> None:
    record = ExecutionRecord(table_id="B01003")
    record.rows = [{"GEO_ID": "0500000US48201", "B01003_001E": "10", "B01003_001M": "0"}]
    response = assemble("ships", record)
    assert response.moe[0]["B01003_001M"] == "0"


def _computer_facts(dataset: str, year: int, table_id: str) -> dict[str, object] | None:
    del dataset
    if table_id != "B28001" or year < 2017:
        return None
    return {
        "title": "Types of Computers in Household",
        "universe": "Households",
        "variables": ["001E", "002E", "005E"],
    }


def test_cell_phones_warn_before_fetch() -> None:
    record = ExecutionRecord(question=T09)
    assert _codes(record) == ["measure_unavailable"]
    warning = evaluate(record)[0]
    assert "smartphone" in warning.detail
    assert "Households" in warning.detail
    assert "B28001" in warning.detail


def test_computer_share_is_not_a_missing_measure() -> None:
    record = ExecutionRecord(question=T14, table_id="B28001")
    assert "measure_unavailable" not in _codes(record)


def test_absent_computer_years_are_named_and_the_url_ships() -> None:
    record = ExecutionRecord(question=T14, table_id="B28001")
    record.fetch = _fetch(
        urls=["https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B28001_002E,B28001_002M"],
        requested_years=list(range(2013, 2025)),
        attempted_years=[2017, 2022],
        omitted_years=[2013, 2014, 2015, 2016],
        omission_reasons=["variable_not_in_vintage"] * 4,
        dataset="acs5",
    )
    warning = next(item for item in evaluate(record) if item.code == "variable_not_in_vintage")
    assert "2013" in warning.detail
    assert "2016" in warning.detail
    response = assemble("ships", record)
    assert response.urls
    assert response.warnings[0].code == "variable_not_in_vintage"


def test_mismatched_omission_arrays_fail_closed() -> None:
    record = ExecutionRecord(question=T14, table_id="B28001")
    record.fetch = _fetch(
        omitted_years=[2013, 2014, 2015],
        omission_reasons=["variable_not_in_vintage"],
        dataset="acs5",
    )
    with pytest.raises(ValueError, match="zip"):
        evaluate(record)


def test_acs1_2020_gap_is_not_a_missing_variable() -> None:
    def facts(dataset: str, year: int, table_id: str) -> dict[str, object] | None:
        assert dataset == "acs1" and table_id == "B17001"
        if year == 2020:
            return None
        return {"title": "Poverty Status", "universe": "Population", "variables": ["001E"]}

    record = ExecutionRecord(question=T12, table_id="B17001", table_facts=facts)
    record.published_vintages = lambda dataset: {2018, 2019, 2021, 2022}
    record.fetch = _fetch(
        dataset="acs1",
        requested_years=list(range(2018, 2023)),
        attempted_years=[2018, 2019, 2021, 2022],
        omitted_years=[2020],
        omission_reasons=["vintage_gap_2020"],
        urls=["https://api.census.gov/data/2018/acs/acs1?get=NAME"],
    )
    assert "variable_not_in_vintage" not in _codes(record)
    assert "vintage_gap_2020" in _codes(record)


def test_acs1_years_before_introduction_are_named() -> None:
    record = ExecutionRecord(question=T14, table_id="B28001")
    record.fetch = _fetch(
        urls=[
            "https://api.census.gov/data/2016/acs/acs1?get=NAME,GEO_ID,B28001_001E,B28001_001M&for=us:1"
        ],
        requested_years=list(range(2013, 2025)),
        attempted_years=[2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024],
        omitted_years=[2013, 2014, 2015, 2020],
        omission_reasons=["variable_not_in_vintage"] * 3 + ["vintage_gap_2020"],
        dataset="acs1",
    )
    warning = next(item for item in evaluate(record) if item.code == "variable_not_in_vintage")
    assert "2013" in warning.detail
    assert "2016" not in warning.detail
    assert "vintage_gap_2020" in _codes(record)


def test_unchanged_computer_years_do_not_warn() -> None:
    record = ExecutionRecord(
        question="Share of households with a computer in 2017 and 2024",
        table_id="B28001",
        table_facts=_computer_facts,
    )
    record.fetch = _fetch(
        requested_years=[2017, 2024], attempted_years=[2017, 2024], dataset="acs5"
    )
    assert "variable_not_in_vintage" not in _codes(record)


def test_redefined_universe_is_named_from_fetch_omissions() -> None:
    record = ExecutionRecord(question=T14, table_id="B19013")
    record.fetch = _fetch(
        requested_years=[2019, 2024],
        attempted_years=[2024],
        omitted_years=[2019],
        omission_reasons=["variable_not_in_vintage"],
        dataset="acs5",
    )
    warning = next(item for item in evaluate(record) if item.code == "variable_not_in_vintage")
    assert "2019" in warning.detail


def test_overlapping_vintage_still_ships_the_url() -> None:
    record = ExecutionRecord(
        question=T01,
        url=CensusURL(
            "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B19013_001E,B19013_001M"
            "&for=us:1"
        ),
    )
    response = assemble("answer still ships", record)
    assert [item.code for item in response.warnings] == ["overlapping_vintage"]
    assert response.urls


def test_measure_unavailable_still_ships_the_url() -> None:
    record = ExecutionRecord(question=T09, table_id="B28001")
    record.fetch = _fetch(
        urls=["https://api.census.gov/data/2023/acs/acs1?get=NAME,GEO_ID,B28001_005E,B28001_005M"],
        requested_years=[2017, 2023],
        attempted_years=[2017, 2023],
    )
    response = assemble("ships", record)
    assert [item.code for item in response.warnings] == ["measure_unavailable"]
    assert response.urls


def test_all_incompatible_years_still_ship_the_built_url() -> None:
    built = CensusURL(
        "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B28001_002E,B28001_002M"
        "&for=place:20000&in=state:08"
    )
    record = ExecutionRecord(
        question=T14, table_id="B28001", url=built, table_facts=_computer_facts
    )
    record.fetch = _fetch(
        urls=[],
        requested_years=[2013, 2016],
        omitted_years=[2013, 2016],
        omission_reasons=["variable_not_in_vintage", "variable_not_in_vintage"],
        dataset="acs5",
    )
    response = assemble("ships", record)
    assert response.urls == [str(built)]
    assert any(item.code == "variable_not_in_vintage" for item in response.warnings)


_RETAINED = (
    "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B17001_001E,B17001_001M"
    "&for=place:20000&in=state:08"
)


def test_warning_only_keeps_url_after_series_clear() -> None:
    built = CensusURL(_RETAINED.replace("B17001", "B19013"))
    record = ExecutionRecord(question=T01, url=built, table_id="B19013")
    clear_series(record)
    response = assemble("warning only", record)
    assert [item.code for item in response.warnings] == ["overlapping_vintage"]
    assert response.urls == [str(built)]
    assert "key=" not in response.urls[0]


def test_no_row_fetch_survives_series_clear() -> None:
    record = ExecutionRecord(
        url=CensusURL(_RETAINED), table_id="B17001", fetch=_fetch(urls=[_RETAINED], rows=[])
    )
    clear_series(record)
    response = assemble("no rows", record)
    assert response.urls == [_RETAINED]
    assert response.rows == []


def test_failed_fetch_survives_series_clear() -> None:
    record = ExecutionRecord(
        url=CensusURL(_RETAINED),
        table_id="B17001",
        fetch=_fetch(
            ok=False,
            urls=[_RETAINED],
            status_code=0,
            requested_years=[2024],
            attempted_years=[2024],
            failed_years=[2024],
        ),
    )
    clear_series(record)
    response = assemble("timed out", record)
    assert response.urls == [_RETAINED]
    assert response.failed_years == []
    assert response.rows == []


def test_unresolved_empty_fetch_keeps_the_built_url() -> None:
    keyed = f"{_RETAINED}&key=secret"
    record = ExecutionRecord(url=CensusURL(keyed), table_id="B17001")
    clear_series(record)
    record.fetch = _fetch(ok=False, urls=[], detail="call build_url before fetch_data")
    response = assemble("unresolved", record)
    assert response.urls == [_RETAINED]
    assert "key=" not in response.urls[0]
    assert "secret" not in "".join(response.urls)


def test_failed_rebuild_keeps_the_previous_url() -> None:
    keyed = f"{_RETAINED}&key=secret"
    record = ExecutionRecord(url=CensusURL(keyed), table_id="B17001")
    _absorb(
        record,
        "build_url",
        BuildUrlResult(
            ok=False,
            url="",
            table_id="B17001",
            variables=[],
            dataset="acs5",
            vintage=2024,
            detail="not in pool",
        ),
    )
    response = assemble("unresolved", record)
    assert record.url is None
    assert response.urls == [_RETAINED]
    assert "key=" not in response.urls[0]


def test_series_clear_without_a_built_url_stays_empty() -> None:
    record = ExecutionRecord()
    clear_series(record)
    assert assemble("never built", record).urls == []
