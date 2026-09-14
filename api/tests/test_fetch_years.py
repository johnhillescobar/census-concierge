"""fetch_data year fan-out: order, duplicates, bounds, partial failure, redaction."""

from __future__ import annotations

import threading
import time

import httpx
from src.census_url import CensusURL
from src.fetch import MAX_IN_FLIGHT, FetchDataTool, unique_years

TEMPLATE = CensusURL(
    "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M"
    "&for=county:201&in=state:48"
)


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
    assert artifact.rows == []
