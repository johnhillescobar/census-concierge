"""fetch_data year fan-out: order, duplicates, bounds, partial failure, redaction."""

from __future__ import annotations

import threading
import time

import httpx
from src.census_url import CensusURL
from src.contract import GeoSpec
from src.fetch import MAX_IN_FLIGHT, MAX_YEARS, FetchDataTool, unique_years

TEMPLATE = CensusURL(
    "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M"
    "&for=county:201&in=state:48"
)
WILDCARD = CensusURL(
    "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M"
    "&for=county:*&in=state:50"
)
PUBLISHED = {
    "acs5": set(range(2016, 2025)),
    "acs1": {2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024},
}


def _ok_payload(year: int) -> list[list[str]]:
    return [
        ["NAME", "GEO_ID", "B01003_001E", "B01003_001M"],
        ["Harris County, Texas", "0500000US48201", str(year), "123"],
    ]


def _year_from(url: str) -> int:
    bits = url.split("/")
    return int(bits[bits.index("data") + 1])


def test_unique_years_keeps_first_requested_order() -> None:
    assert unique_years([2019, 2022, 2019, 2024, 2022]) == [2019, 2022, 2024]
    assert unique_years([]) == []


def test_with_year_rewrites_the_path_and_keeps_the_query() -> None:
    rewritten = TEMPLATE.with_year(2019)
    assert rewritten.year == 2019
    assert "/2019/acs/acs5" in str(rewritten)
    assert "B01003_001E" in str(rewritten)
    assert "B01003_001M" in str(rewritten)
    assert "for=county:201" in str(rewritten)
    assert "key=" not in str(rewritten)
    assert TEMPLATE.year == 2024
    assert TEMPLATE.dataset == "acs5"


def test_with_dataset_rewrites_acs5_to_acs1() -> None:
    switched = TEMPLATE.with_dataset("acs1").with_year(2019)
    assert switched.dataset == "acs1"
    assert switched.year == 2019
    assert "/2019/acs/acs1" in str(switched)
    assert "for=county:201" in str(switched)
    assert TEMPLATE.dataset == "acs5"


def test_with_geography_rewrites_for_and_in() -> None:
    rewritten = TEMPLATE.with_geography("tract:*", "state:26 county:163")
    assert rewritten.for_is_wildcard() is True
    assert "for=tract:*" in str(rewritten)
    encoded = str(rewritten)
    assert "in=state:26 county:163" in encoded or "in=state:26+county:163" in encoded
    assert "county:201" not in encoded
    assert TEMPLATE.for_is_wildcard() is False
    assert "for=county:201" in str(TEMPLATE)


def test_for_is_wildcard_detects_star_listings() -> None:
    listing = CensusURL(str(TEMPLATE).replace("county:201", "county:*"))
    assert listing.for_is_wildcard() is True
    assert TEMPLATE.for_is_wildcard() is False


async def test_ordered_success_tags_year_and_pairs_margins() -> None:
    seen: list[int] = []

    def http_get(url: str) -> tuple[int, object]:
        assert "key=secret" in url
        year = _year_from(url)
        seen.append(year)
        assert "B01003_001E" in url and "B01003_001M" in url
        return 200, _ok_payload(year)

    tool = FetchDataTool(last_url=lambda: TEMPLATE, census_key=lambda: "secret", http_get=http_get)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": [2019, 2022, 2024]},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.ok is True
    assert artifact.requested_years == [2019, 2022, 2024]
    assert artifact.attempted_years == [2019, 2022, 2024]
    assert artifact.succeeded_years == [2019, 2022, 2024]
    assert artifact.failed_years == []
    assert artifact.omitted_years == []
    assert artifact.omission_reasons == []
    assert [leg.year for leg in artifact.legs] == [2019, 2022, 2024]
    assert [url.split("/")[4] for url in artifact.urls] == ["2019", "2022", "2024"]
    assert [row["year"] for row in artifact.rows] == ["2019", "2022", "2024"]
    assert [row["B01003_001E"] for row in artifact.rows] == ["2019", "2022", "2024"]
    assert all("key=" not in url for url in artifact.urls)


async def test_duplicate_years_are_fetched_once_in_first_order() -> None:
    seen: list[int] = []

    def http_get(url: str) -> tuple[int, object]:
        year = _year_from(url)
        seen.append(year)
        return 200, _ok_payload(year)

    tool = FetchDataTool(last_url=lambda: TEMPLATE, census_key=lambda: "secret", http_get=http_get)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": [2019, 2022, 2019]},
            "id": "c1",
        }
    )
    assert seen == [2019, 2022]
    assert message.artifact.requested_years == [2019, 2022]
    assert message.artifact.urls[0].split("/")[4] == "2019"
    assert message.artifact.urls[1].split("/")[4] == "2022"


async def test_three_legs_overlap_and_eight_never_exceed_five() -> None:
    lock = threading.Lock()
    inflight = 0
    peak = 0

    def http_get(url: str) -> tuple[int, object]:
        nonlocal inflight, peak
        with lock:
            inflight += 1
            peak = max(peak, inflight)
        time.sleep(0.15)
        with lock:
            inflight -= 1
        return 200, _ok_payload(_year_from(url))

    three = FetchDataTool(last_url=lambda: TEMPLATE, census_key=lambda: "secret", http_get=http_get)
    started = time.perf_counter()
    message = await three.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": [2018, 2020, 2022]},
            "id": "c1",
        }
    )
    elapsed = time.perf_counter() - started
    assert message.artifact.ok is True
    assert peak > 1
    assert peak <= MAX_IN_FLIGHT
    assert elapsed < 0.40

    inflight = 0
    peak = 0
    eight = FetchDataTool(last_url=lambda: TEMPLATE, census_key=lambda: "secret", http_get=http_get)
    years = [2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024]
    message = await eight.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": years},
            "id": "c2",
        }
    )
    assert message.artifact.attempted_years == years
    assert peak == MAX_IN_FLIGHT


async def test_partial_failure_keeps_successful_rows_and_failed_url() -> None:
    def http_get(url: str) -> tuple[int, object]:
        year = _year_from(url)
        if year == 2022:
            return 400, f"unknown vintage for {url}"
        return 200, _ok_payload(year)

    tool = FetchDataTool(last_url=lambda: TEMPLATE, census_key=lambda: "secret", http_get=http_get)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": [2019, 2022, 2024]},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.ok is True
    assert artifact.succeeded_years == [2019, 2024]
    assert artifact.failed_years == [2022]
    assert [row["year"] for row in artifact.rows] == ["2019", "2024"]
    assert artifact.legs[1].ok is False
    assert artifact.legs[1].status_code == 400
    assert "/2022/acs/acs5" in artifact.legs[1].url
    assert "key=" not in artifact.legs[1].url
    assert "secret" not in artifact.legs[1].detail
    assert "key=secret" not in artifact.legs[1].detail
    assert "failed 2022 HTTP 400" in message.content
    assert all("key=" not in url for url in artifact.urls)


async def test_timeout_keeps_the_url_and_does_not_drop_other_years() -> None:
    def http_get(url: str) -> tuple[int, object]:
        year = _year_from(url)
        if year == 2019:
            raise httpx.TimeoutException(f"timed out for {url}")
        return 200, _ok_payload(year)

    tool = FetchDataTool(last_url=lambda: TEMPLATE, census_key=lambda: "secret", http_get=http_get)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": [2019, 2024]},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.ok is True
    assert artifact.failed_years == [2019]
    assert artifact.succeeded_years == [2024]
    assert artifact.legs[0].status_code == 0
    assert "/2019/acs/acs5" in artifact.legs[0].url
    assert "secret" not in artifact.legs[0].detail
    assert [row["year"] for row in artifact.rows] == ["2024"]


async def test_years_without_a_built_url_are_omitted() -> None:
    tool = FetchDataTool(last_url=lambda: None, census_key=lambda: "secret")
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": [2019, 2022]},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.ok is False
    assert artifact.urls == []
    assert artifact.requested_years == [2019, 2022]
    assert artifact.attempted_years == []
    assert artifact.omitted_years == [2019, 2022]
    assert artifact.omission_reasons == ["no_url", "no_url"]
    assert artifact.rows == []


async def test_years_beyond_the_cap_are_omitted() -> None:
    seen: list[int] = []
    years = list(range(2012, 2025))

    def http_get(url: str) -> tuple[int, object]:
        year = _year_from(url)
        seen.append(year)
        return 200, _ok_payload(year)

    tool = FetchDataTool(
        last_url=lambda: TEMPLATE,
        census_key=lambda: "secret",
        http_get=http_get,
        allow_overlapping_acs5=True,
    )
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": years},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert MAX_YEARS == 12
    assert seen == list(range(2012, 2024))
    assert artifact.requested_years == years
    assert artifact.attempted_years == list(range(2012, 2024))
    assert artifact.omitted_years == [2024]
    assert artifact.omission_reasons == ["max_years"]
    assert artifact.ok is True


async def test_all_legs_failed_content_names_year_and_status() -> None:
    def http_get(url: str) -> tuple[int, object]:
        return 400, f"unknown vintage for {url}"

    tool = FetchDataTool(last_url=lambda: TEMPLATE, census_key=lambda: "secret", http_get=http_get)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": [2022]},
            "id": "c1",
        }
    )
    assert message.artifact.ok is False
    assert "failed 2022 HTTP 400" in message.content
    assert "secret" not in message.content
    assert "key=secret" not in message.content
    assert "/2022/acs/acs5" in message.content


def _published(dataset: str) -> set[int]:
    return PUBLISHED[dataset]


async def test_consecutive_acs5_destaggers_when_acs1_is_ineligible() -> None:
    seen: list[tuple[str, int]] = []

    def http_get(url: str) -> tuple[int, object]:
        dataset = "acs1" if "/acs/acs1" in url else "acs5"
        year = _year_from(url)
        seen.append((dataset, year))
        if dataset == "acs1":
            return 204, ""
        return 200, _ok_payload(year)

    tool = FetchDataTool(
        last_url=lambda: TEMPLATE,
        census_key=lambda: "secret",
        http_get=http_get,
        published=_published,
    )
    years = list(range(2017, 2024))
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": years},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert ("acs1", 2024) in seen
    assert artifact.dataset == "acs5"
    assert artifact.acs1_ineligible is True
    assert artifact.requested_years == years
    assert artifact.attempted_years == [2017, 2022]
    assert artifact.omitted_years == [2018, 2019, 2020, 2021, 2023]
    assert artifact.omission_reasons == ["overlapping_vintage"] * 5
    assert all("/acs/acs5" in url for url in artifact.urls)
    assert 2020 not in {year for dataset, year in seen if dataset == "acs5"}


async def test_consecutive_acs1_eligible_omits_2020_and_does_not_fetch_it() -> None:
    seen: list[tuple[str, int]] = []

    def http_get(url: str) -> tuple[int, object]:
        dataset = "acs1" if "/acs/acs1" in url else "acs5"
        year = _year_from(url)
        seen.append((dataset, year))
        return 200, _ok_payload(year)

    tool = FetchDataTool(
        last_url=lambda: TEMPLATE,
        census_key=lambda: "secret",
        http_get=http_get,
        published=_published,
    )
    years = list(range(2018, 2023))
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": years},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.dataset == "acs1"
    assert artifact.acs1_ineligible is False
    assert artifact.attempted_years == [2018, 2019, 2021, 2022]
    assert artifact.omitted_years == [2020]
    assert artifact.omission_reasons == ["vintage_gap_2020"]
    assert 2020 not in {year for _dataset, year in seen}
    assert {dataset for dataset, year in seen if year in artifact.attempted_years} == {"acs1"}
    assert all("/acs/acs1" in url for url in artifact.urls)
    assert "omitted 2020:vintage_gap_2020" in message.content


async def test_overlapping_acs5_override_fetches_consecutive_years() -> None:
    seen: list[int] = []

    def http_get(url: str) -> tuple[int, object]:
        seen.append(_year_from(url))
        assert "/acs/acs5" in url
        return 200, _ok_payload(_year_from(url))

    tool = FetchDataTool(
        last_url=lambda: TEMPLATE,
        census_key=lambda: "secret",
        http_get=http_get,
        published=_published,
        allow_overlapping_acs5=True,
    )
    years = list(range(2017, 2024))
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": years},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.dataset == "acs5"
    assert artifact.acs1_ineligible is False
    assert artifact.attempted_years == years
    assert artifact.omitted_years == []
    assert seen == years


async def test_acs1_series_with_a_2020_hole_still_omits_the_gap() -> None:
    seen: list[tuple[str, int]] = []

    def http_get(url: str) -> tuple[int, object]:
        dataset = "acs1" if "/acs/acs1" in url else "acs5"
        year = _year_from(url)
        seen.append((dataset, year))
        return 200, _ok_payload(year)

    tool = FetchDataTool(
        last_url=lambda: TEMPLATE,
        census_key=lambda: "secret",
        http_get=http_get,
        published=_published,
    )
    years = [2018, 2019, 2021, 2022]
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": years},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.dataset == "acs1"
    assert artifact.requested_years == [2018, 2019, 2020, 2021, 2022]
    assert artifact.attempted_years == years
    assert artifact.omitted_years == [2020]
    assert artifact.omission_reasons == ["vintage_gap_2020"]
    assert 2020 not in {year for _dataset, year in seen}


async def test_acs1_probe_server_error_destaggers_without_ineligible_warning() -> None:
    def http_get(url: str) -> tuple[int, object]:
        if "/acs/acs1" in url:
            return 500, "upstream"
        return 200, _ok_payload(_year_from(url))

    tool = FetchDataTool(
        last_url=lambda: TEMPLATE,
        census_key=lambda: "secret",
        http_get=http_get,
        published=_published,
    )
    years = list(range(2017, 2024))
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": years},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.dataset == "acs5"
    assert artifact.acs1_ineligible is False
    assert artifact.attempted_years == [2017, 2022]


async def test_acs1_wildcard_listing_stays_on_acs5() -> None:
    seen: list[str] = []

    def http_get(url: str) -> tuple[int, object]:
        dataset = "acs1" if "/acs/acs1" in url else "acs5"
        seen.append(dataset)
        if dataset == "acs1":
            return 200, [
                ["NAME", "GEO_ID", "B01003_001E", "B01003_001M"],
                ["Chittenden County, Vermont", "0500000US50007", "1", "1"],
            ]
        return 200, _ok_payload(_year_from(url))

    tool = FetchDataTool(
        last_url=lambda: WILDCARD,
        census_key=lambda: "secret",
        http_get=http_get,
        published=_published,
    )
    years = list(range(2017, 2024))
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": years},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert "acs1" not in seen
    assert artifact.dataset == "acs5"
    assert artifact.acs1_ineligible is True
    assert artifact.attempted_years == [2017, 2022]
    assert all("/acs/acs5" in url for url in artifact.urls)


async def test_acs1_header_only_probe_is_ineligible() -> None:
    def http_get(url: str) -> tuple[int, object]:
        if "/acs/acs1" in url:
            return 200, [["NAME", "GEO_ID", "B01003_001E", "B01003_001M"]]
        return 200, _ok_payload(_year_from(url))

    tool = FetchDataTool(
        last_url=lambda: TEMPLATE,
        census_key=lambda: "secret",
        http_get=http_get,
        published=_published,
    )
    years = list(range(2017, 2024))
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": years},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.dataset == "acs5"
    assert artifact.acs1_ineligible is True
    assert artifact.attempted_years == [2017, 2022]


async def test_acs1_probe_bad_request_destaggers_without_ineligible_warning() -> None:
    def http_get(url: str) -> tuple[int, object]:
        if "/acs/acs1" in url:
            return 400, "unknown variable"
        return 200, _ok_payload(_year_from(url))

    tool = FetchDataTool(
        last_url=lambda: TEMPLATE,
        census_key=lambda: "secret",
        http_get=http_get,
        published=_published,
    )
    years = list(range(2017, 2024))
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": years},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.dataset == "acs5"
    assert artifact.acs1_ineligible is False
    assert artifact.attempted_years == [2017, 2022]


async def test_ineligible_series_with_a_2020_hole_accounts_for_the_span() -> None:
    def http_get(url: str) -> tuple[int, object]:
        if "/acs/acs1" in url:
            return 204, ""
        return 200, _ok_payload(_year_from(url))

    tool = FetchDataTool(
        last_url=lambda: TEMPLATE,
        census_key=lambda: "secret",
        http_get=http_get,
        published=_published,
    )
    years = [2018, 2019, 2021, 2022]
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": years},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.dataset == "acs5"
    assert artifact.requested_years == [2018, 2019, 2020, 2021, 2022]
    assert 2020 in artifact.omitted_years
    assert len(artifact.omitted_years) == len(artifact.omission_reasons)


async def test_acs1_unpublished_earlier_year_destaggers_to_acs5() -> None:
    seen: list[tuple[str, int]] = []

    def http_get(url: str) -> tuple[int, object]:
        dataset = "acs1" if "/acs/acs1" in url else "acs5"
        year = _year_from(url)
        seen.append((dataset, year))
        if dataset == "acs1" and year == 2017:
            return 204, ""
        return 200, _ok_payload(year)

    tool = FetchDataTool(
        last_url=lambda: TEMPLATE,
        census_key=lambda: "secret",
        http_get=http_get,
        published=_published,
    )
    years = list(range(2017, 2024))
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": years},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.dataset == "acs5"
    assert artifact.acs1_ineligible is True
    assert artifact.attempted_years == [2017, 2022]
    assert ("acs1", 2024) in seen
    assert ("acs1", 2017) in seen
    assert ("acs5", 2017) in seen
    assert ("acs5", 2022) in seen
    assert all("/acs/acs5" in url for url in artifact.urls)


async def test_acs1_malformed_probe_destaggers_without_ineligible_warning() -> None:
    def http_get(url: str) -> tuple[int, object]:
        if "/acs/acs1" in url:
            return 200, [["NAME", "GEO_ID"], None]
        return 200, _ok_payload(_year_from(url))

    tool = FetchDataTool(
        last_url=lambda: TEMPLATE,
        census_key=lambda: "secret",
        http_get=http_get,
        published=_published,
    )
    years = list(range(2017, 2024))
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": years},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.dataset == "acs5"
    assert artifact.acs1_ineligible is False
    assert artifact.attempted_years == [2017, 2022]


def _for_clause(url: str) -> str:
    marker = "&for="
    start = url.find(marker)
    if start < 0:
        marker = "?for="
        start = url.find(marker)
    if start < 0:
        return ""
    rest = url[start + len(marker) :]
    amp = rest.find("&")
    return rest if amp < 0 else rest[:amp]


AUSTIN = GeoSpec(
    level="place",
    name="Austin city, Texas",
    for_spec="place:4805000",
    in_spec="state:48",
    geoid="1600000US4805000",
    dataset="acs5",
    vintage=2024,
)
TEXAS = GeoSpec(
    level="state",
    name="Texas",
    for_spec="state:48",
    geoid="0400000US48",
    dataset="acs5",
    vintage=2024,
)
WAYNE_TRACTS = GeoSpec(
    level="tract",
    name="all tracts in Wayne County, Michigan",
    for_spec="tract:*",
    in_spec="state:26 county:163",
    dataset="acs5",
    vintage=2024,
)


def _geo_payload(name: str, geoid: str, year: int) -> list[list[str]]:
    return [
        ["NAME", "GEO_ID", "B01003_001E", "B01003_001M"],
        [name, geoid, str(year), "4"],
    ]


async def test_wildcard_spec_is_one_request_even_when_many_rows_return() -> None:
    seen: list[str] = []
    rows = [
        ["NAME", "GEO_ID", "B01003_001E", "B01003_001M"],
        *[[f"Census Tract {i}", f"1400000US26163{i:06d}", "10", "1"] for i in range(627)],
    ]

    def http_get(url: str) -> tuple[int, object]:
        seen.append(url)
        assert _for_clause(url) == "tract:*"
        assert "in=state:26 county:163" in url or "in=state:26+county:163" in url
        return 200, rows

    tool = FetchDataTool(
        last_url=lambda: TEMPLATE,
        last_geographies=lambda: [WAYNE_TRACTS],
        census_key=lambda: "secret",
        http_get=http_get,
    )
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": [2024]},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert len(seen) == 1
    assert len(artifact.urls) == 1
    assert len(artifact.legs) == 1
    assert artifact.legs[0].for_spec == "tract:*"
    assert len(artifact.rows) == 627
    assert artifact.attempted_years == [2024]


async def test_comparison_specs_are_two_successful_legs() -> None:
    seen: list[str] = []

    def http_get(url: str) -> tuple[int, object]:
        clause = _for_clause(url)
        seen.append(clause)
        if clause.startswith("place:"):
            return 200, _geo_payload("Austin city, Texas", "1600000US4805000", 2024)
        return 200, _geo_payload("Texas", "0400000US48", 2024)

    tool = FetchDataTool(
        last_url=lambda: TEMPLATE,
        last_geographies=lambda: [AUSTIN, TEXAS],
        census_key=lambda: "secret",
        http_get=http_get,
    )
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": [2024]},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert seen == ["place:4805000", "state:48"]
    assert artifact.ok is True
    assert artifact.attempted_years == [2024]
    assert artifact.succeeded_years == [2024]
    assert artifact.failed_years == []
    assert [leg.for_spec for leg in artifact.legs] == ["place:4805000", "state:48"]
    assert all(leg.ok for leg in artifact.legs)
    assert [row["NAME"] for row in artifact.rows] == ["Austin city, Texas", "Texas"]
    assert all("key=" not in url for url in artifact.urls)


async def test_one_failed_geography_keeps_its_url_and_the_other_rows() -> None:
    def http_get(url: str) -> tuple[int, object]:
        clause = _for_clause(url)
        if clause.startswith("state:"):
            return 400, f"unknown geography for {url}"
        return 200, _geo_payload("Austin city, Texas", "1600000US4805000", 2024)

    tool = FetchDataTool(
        last_url=lambda: TEMPLATE,
        last_geographies=lambda: [AUSTIN, TEXAS],
        census_key=lambda: "secret",
        http_get=http_get,
    )
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "fetch_data",
            "args": {"years": [2024]},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.ok is True
    assert artifact.attempted_years == [2024]
    assert artifact.succeeded_years == [2024]
    assert artifact.failed_years == [2024]
    assert [row["NAME"] for row in artifact.rows] == ["Austin city, Texas"]
    assert artifact.legs[0].ok is True
    assert artifact.legs[1].ok is False
    assert artifact.legs[1].status_code == 400
    assert artifact.legs[1].for_spec == "state:48"
    assert "for=state:48" in artifact.legs[1].url
    assert "key=" not in artifact.legs[1].url
    assert "secret" not in artifact.legs[1].detail
    assert len(artifact.urls) == 2
