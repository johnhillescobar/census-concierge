"""ResultPlan is assembled from executed artifacts, not answer prose."""

from __future__ import annotations

import json

import pytest
from ask_fixtures import _harris
from pydantic import ValidationError
from src.ask import ExecutionRecord, assemble
from src.census_url import CensusURL
from src.contract import GeoSpec, ResultPlan
from src.fetch import FetchDataResult


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


def test_one_year_county_plan_matches_the_built_url() -> None:
    url = CensusURL(
        "https://api.census.gov/data/2024/acs/acs5"
        "?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=county:201&in=state:48&key=SECRET"
    )
    geo = _harris()
    record = ExecutionRecord(
        table_id="B01003",
        universe="Total population",
        url=url,
        geography=geo,
        geographies=[geo],
        fetch=_fetch(
            urls=[str(url)],
            requested_years=[2024],
            attempted_years=[2024],
            succeeded_years=[2024],
            dataset="acs5",
        ),
    )
    plan = assemble("Harris County has data.", record).plan
    table, suffixes = url.estimate_table()
    assert plan.table_id == table == "B01003"
    assert plan.variables == [f"{table}_{item}" for item in suffixes]
    assert plan.dataset == url.dataset == "acs5"
    assert plan.years == [url.year] == [2024]
    assert plan.requested_years == [2024]
    assert plan.geographies[0].for_spec == "county:201"
    assert plan.geographies[0].in_spec == "state:48"
    assert plan.geographies[0].geoid == "0500000US48201"
    dumped = json.dumps(plan.model_dump())
    assert "key=" not in dumped
    assert "SECRET" not in dumped


def test_series_plan_omits_the_2020_gap() -> None:
    denver = GeoSpec(
        level="place",
        name="Denver city, Colorado",
        geoid="1600000US0820000",
        for_spec="place:20000",
        in_spec="state:08",
        dataset="acs1",
        vintage=2024,
    )
    url = CensusURL(
        "https://api.census.gov/data/2024/acs/acs1"
        "?get=NAME,GEO_ID,B28001_001E,B28001_001M&for=place:20000&in=state:08"
    )
    requested = list(range(2017, 2025))
    attempted = [2017, 2018, 2019, 2021, 2022, 2023, 2024]
    record = ExecutionRecord(
        question="Number of cell phones in Denver since 2017",
        table_id="B28001",
        url=url,
        geographies=[denver],
        fetch=_fetch(
            urls=[str(url.with_year(year)) for year in attempted],
            requested_years=requested,
            attempted_years=attempted,
            succeeded_years=attempted,
            omitted_years=[2020],
            omission_reasons=["vintage_gap_2020"],
            dataset="acs1",
        ),
    )
    plan = assemble("households with a smartphone", record).plan
    assert plan.requested_years == requested
    assert plan.years == attempted
    assert 2020 not in plan.years
    assert plan.dataset == "acs1"
    assert plan.table_id == "B28001"
    assert plan.variables == ["B28001_001E"]


def test_comparison_plan_keeps_two_ordered_geographies() -> None:
    austin = GeoSpec(
        level="place",
        name="Austin city, Texas",
        geoid="1600000US4805000",
        for_spec="place:05000",
        in_spec="state:48",
        dataset="acs5",
        vintage=2024,
    )
    texas = GeoSpec(
        level="state",
        name="Texas",
        geoid="0400000US48",
        for_spec="state:48",
        dataset="acs5",
        vintage=2024,
    )
    austin_url = CensusURL(
        "https://api.census.gov/data/2024/acs/acs5"
        "?get=NAME,GEO_ID,B25064_001E,B25064_001M&for=place:05000&in=state:48"
    )
    texas_url = CensusURL(
        "https://api.census.gov/data/2024/acs/acs5"
        "?get=NAME,GEO_ID,B25064_001E,B25064_001M&for=state:48"
    )
    record = ExecutionRecord(
        table_id="B25064",
        url=austin_url,
        geographies=[austin, texas, GeoSpec(level="place", name="spare")],
        geo_status={"legal": True, "detail": "", "nested": True, "compare": True},
        fetch=_fetch(
            urls=[str(austin_url), str(texas_url)],
            requested_years=[2024],
            attempted_years=[2024],
            succeeded_years=[2024],
            dataset="acs5",
        ),
    )
    plan = assemble("Austin vs Texas", record).plan
    assert [geo.for_spec for geo in plan.geographies] == ["place:05000", "state:48"]
    assert [geo.geoid for geo in plan.geographies] == ["1600000US4805000", "0400000US48"]
    assert plan.variables == ["B25064_001E"]
    assert plan.table_id == austin_url.estimate_table()[0]


def test_failed_fetch_still_returns_the_built_plan() -> None:
    url = CensusURL(
        "https://api.census.gov/data/2024/acs/acs5"
        "?get=NAME,GEO_ID,B25064_001E,B25064_001M&for=place:99999&in=state:48"
    )
    geo = GeoSpec(
        level="place", for_spec="place:99999", in_spec="state:48", dataset="acs5", vintage=2024
    )
    record = ExecutionRecord(
        table_id="B25064",
        url=url,
        geographies=[geo],
        fetch=_fetch(
            ok=False,
            urls=[str(url)],
            requested_years=[2024],
            attempted_years=[2024],
            failed_years=[2024],
            status_code=400,
            dataset="acs5",
        ),
    )
    response = assemble("Census returned HTTP 400.", record)
    assert response.urls == [str(url)]
    assert response.plan.table_id == "B25064"
    assert response.plan.variables == ["B25064_001E"]
    assert response.plan.years == [2024]
    assert response.plan.geographies[0].for_spec == "place:99999"


def test_wildcard_plan_is_one_star_geography() -> None:
    geo = GeoSpec(
        level="county",
        name="Oregon counties",
        for_spec="county:*",
        in_spec="state:41",
        dataset="acs5",
        vintage=2024,
    )
    url = CensusURL(
        "https://api.census.gov/data/2024/acs/acs5"
        "?get=NAME,GEO_ID,B19013_001E,B19013_001M&for=county:*&in=state:41"
    )
    record = ExecutionRecord(
        table_id="B19013",
        url=url,
        geographies=[geo],
        fetch=_fetch(
            urls=[str(url)],
            requested_years=[2024],
            attempted_years=[2024],
            dataset="acs5",
        ),
    )
    plan = assemble("all counties in Oregon", record).plan
    assert [geo.for_spec for geo in plan.geographies] == ["county:*"]
    assert plan.geographies[0].in_spec == "state:41"


def test_nonoverlapping_acs5_plan_does_not_list_omitted_years() -> None:
    requested = list(range(2017, 2024))
    attempted = [2017, 2022]
    url = CensusURL(
        "https://api.census.gov/data/2022/acs/acs5"
        "?get=NAME,GEO_ID,B23025_001E,B23025_001M&for=place:44350&in=state:50"
    )
    geo = GeoSpec(
        level="place", for_spec="place:44350", in_spec="state:50", dataset="acs5", vintage=2022
    )
    record = ExecutionRecord(
        table_id="B23025",
        url=url,
        geographies=[geo],
        fetch=_fetch(
            urls=[str(url.with_year(2017)), str(url)],
            requested_years=requested,
            attempted_years=attempted,
            succeeded_years=attempted,
            omitted_years=[2018, 2019, 2020, 2021, 2023],
            omission_reasons=["overlapping_vintage"] * 5,
            dataset="acs5",
            acs1_ineligible=True,
        ),
    )
    plan = assemble("two ACS5 points", record).plan
    assert plan.years == attempted
    assert plan.requested_years == requested
    assert 2018 not in plan.years


def test_built_url_without_fetch_keeps_the_url_year() -> None:
    url = CensusURL(
        "https://api.census.gov/data/2024/acs/acs5"
        "?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=county:201&in=state:48"
    )
    plan = assemble("x", ExecutionRecord(table_id="B01003", url=url, geographies=[_harris()])).plan
    assert plan.years == [2024]
    assert plan.requested_years == [2024]
    assert plan.variables == ["B01003_001E"]


def test_omitted_years_are_not_filled_from_the_url() -> None:
    url = CensusURL(
        "https://api.census.gov/data/2022/acs/acs5"
        "?get=NAME,GEO_ID,B23025_001E,B23025_001M&for=place:44350&in=state:50"
    )
    plan = assemble(
        "x",
        ExecutionRecord(
            table_id="B23025",
            url=url,
            fetch=_fetch(
                requested_years=[2018, 2019],
                attempted_years=[],
                omitted_years=[2018, 2019],
                omission_reasons=["overlapping_vintage", "overlapping_vintage"],
                dataset="acs5",
            ),
        ),
    ).plan
    assert plan.years == []
    assert plan.requested_years == [2018, 2019]


def test_overlapping_override_is_on_the_plan() -> None:
    record = ExecutionRecord(allow_overlapping_acs5=True, table_id="B19013")
    assert assemble("x", record).plan.allow_overlapping_acs5 is True


def test_empty_record_still_has_a_plan() -> None:
    plan = assemble("", ExecutionRecord()).plan
    assert plan.table_id == ""
    assert plan.variables == []
    assert plan.geographies == []


def test_acs1_zcta_record_still_ships_the_url() -> None:
    url = CensusURL(
        "https://api.census.gov/data/2023/acs/acs1"
        "?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=zip code tabulation area:90210"
    )
    geo = GeoSpec(
        level="zip code tabulation area",
        for_spec="zip code tabulation area:90210",
        dataset="acs1",
        vintage=2023,
    )
    response = assemble(
        "Census returned HTTP 400.",
        ExecutionRecord(
            table_id="B01003",
            url=url,
            geographies=[geo],
            fetch=_fetch(
                ok=False,
                urls=[str(url)],
                requested_years=[2023],
                attempted_years=[2023],
                failed_years=[2023],
                dataset="acs1",
            ),
        ),
    )
    assert response.urls == [str(url)]
    assert "key=" not in response.urls[0]
    assert response.plan.table_id == "B01003"
    assert response.plan.dataset == "acs1"
    assert response.plan.geographies == []
    assert response.plan.years == [2023]
    assert response.plan.variables == ["B01003_001E"]


def test_acs1_zcta_clause_without_level_still_ships_the_url() -> None:
    url = CensusURL(
        "https://api.census.gov/data/2023/acs/acs1"
        "?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=zip code tabulation area:90210"
    )
    response = assemble(
        "Census returned HTTP 400.",
        ExecutionRecord(
            table_id="B01003",
            url=url,
            geographies=[GeoSpec(for_spec="zip code tabulation area:90210")],
            fetch=_fetch(
                ok=False,
                urls=[str(url)],
                requested_years=[2023],
                attempted_years=[2023],
                failed_years=[2023],
                dataset="acs1",
            ),
        ),
    )
    assert response.urls == [str(url)]
    assert response.plan.geographies == []
    assert response.plan.years == [2023]
    assert response.plan.variables == ["B01003_001E"]


def test_plan_rejects_acs1_zcta() -> None:
    with pytest.raises(ValidationError, match="ZCTA"):
        ResultPlan(
            dataset="acs1",
            geographies=[
                GeoSpec(level="zip code tabulation area", for_spec="zip code tabulation area:90210")
            ],
        )


def test_plan_rejects_acs1_zcta_clause_without_level() -> None:
    with pytest.raises(ValidationError, match="ZCTA"):
        ResultPlan(
            dataset="acs1",
            geographies=[GeoSpec(for_spec="zip code tabulation area:90210")],
        )


def test_plan_rejects_variable_from_another_table() -> None:
    with pytest.raises(ValidationError, match="variable"):
        ResultPlan(table_id="B01003", variables=["B19013_001E"])


def test_plan_rejects_margin_ids() -> None:
    with pytest.raises(ValidationError, match="variable"):
        ResultPlan(table_id="B01003", variables=["B01003_001M"])


def test_plan_rejects_years_that_were_not_requested() -> None:
    with pytest.raises(ValidationError, match="requested"):
        ResultPlan(requested_years=[2024], years=[2023, 2024])


def test_geoid_reconstructs_census_clauses() -> None:
    from src.contract import clauses_from_geoid

    assert clauses_from_geoid("0500000US48201") == ("county", "county:201", "state:48")
    assert clauses_from_geoid("1600000US4805000") == ("place", "place:05000", "state:48")
    assert clauses_from_geoid("0400000US48") == ("state", "state:48", "")
    assert clauses_from_geoid("860Z200US90210") == (
        "zip code tabulation area",
        "zip code tabulation area:90210",
        "",
    )
    assert clauses_from_geoid("0100000US") == ("us", "us:1", "")
    assert clauses_from_geoid("0500000US48") is None
    assert clauses_from_geoid("county:201") is None
    assert clauses_from_geoid("") is None


def test_geoid_bind_copies_plan_dataset() -> None:
    from src.contract import bind_override_geographies

    plan = ResultPlan.model_validate(
        {"dataset": "acs1", "geographies": [{"geoid": "0500000US48201"}]}
    )
    bound = bind_override_geographies(plan)
    assert bound.geographies[0].dataset == "acs1"
    assert bound.geographies[0].for_spec == "county:201"
