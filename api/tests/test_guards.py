"""Slice-1 guards: build an execution record, assert which warnings fire.

No LLM. A stub that always returns the same table would hide a broken guard.
"""

from __future__ import annotations

from ask_fixtures import ENTRIES, _geo_tool, _harris, _tools
from src.ask import ExecutionRecord, _absorb, assemble, dispatch
from src.contract import GeoSpec
from src.guards import MOE_COMBINE_FORMULA, evaluate
from src.retrieval.metadata import GeoLevel

T01 = "Compare median household income between 2015-2019 and 2018-2022"
T03 = "Is the poverty rate in tract 1201 higher than tract 1305?"
T06 = "What share of households are Black families earning over $75k?"
T17 = "What is the median household income across these five tracts combined?"
T18 = "Total population without health insurance across every tract in Wayne County"
T15 = "Median household income for ZIP code 10001 every year since 2018"
T16 = "Compare poverty by census tract within the city of Denver"
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
            geoid="860Z200US90210",
        )
    ]
    record.rows = [{"GEO_ID": "860Z200US90210", "B19013_001E": "100", "B19013_001M": "10"}]
    response = assemble("single vintage", record)
    assert response.warnings == []
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
