"""Census GET deadline and one identical hedge."""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from src.ask import ExecutionRecord, assemble
from src.census_http import HEDGE_AFTER, TOTAL_DEADLINE, census_get
from src.census_url import CensusURL
from src.fetch import FetchDataResult, FetchDataTool

URL = (
    "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M"
    "&for=county:201&in=state:48"
)


def _ok() -> httpx.Response:
    return httpx.Response(
        200,
        json=[
            ["NAME", "GEO_ID", "B01003_001E", "B01003_001M"],
            ["Harris County, Texas", "0500000US48201", "100", "12"],
        ],
    )


def test_hedge_wait_is_above_the_clean_window_maximum() -> None:
    phases = httpx.Timeout(60.0)
    assert phases.connect == phases.read == phases.write == phases.pool == 60.0
    assert HEDGE_AFTER == 10.0
    assert TOTAL_DEADLINE == 60.0
    assert HEDGE_AFTER > 4.311 * 2


def test_the_client_timeout_disables_every_phase() -> None:
    seen: list[httpx.Timeout] = []

    def get(url: str, client: httpx.Client) -> httpx.Response:
        _ = url
        seen.append(client.timeout)
        return httpx.Response(204)

    census_get(URL, hedge_after=1, total=1, get=get)
    timeout = seen[0]
    assert timeout.connect is None
    assert timeout.read is None
    assert timeout.write is None
    assert timeout.pool is None


def test_a_response_inside_the_hedge_is_not_repeated() -> None:
    calls: list[str] = []

    def get(url: str, client: httpx.Client) -> httpx.Response:
        _ = client
        calls.append(url)
        return httpx.Response(500, text="no")

    response = census_get(URL, hedge_after=2, total=2, get=get)
    assert response.status_code == 500
    assert calls == [URL]


def test_the_first_response_back_wins() -> None:
    calls: list[str] = []

    def get(url: str, client: httpx.Client) -> httpx.Response:
        _ = client
        calls.append(url)
        if len(calls) == 1:
            time.sleep(0.8)
            return httpx.Response(200, text="slow")
        return httpx.Response(200, text="fast")

    response = census_get(URL, hedge_after=0.05, total=3, get=get)
    assert response.text == "fast"
    assert calls == [URL, URL]


def test_a_dropped_connection_is_retried_once_with_the_same_url() -> None:
    calls: list[str] = []
    live = f"{URL}&key=secret"

    def get(url: str, client: httpx.Client) -> httpx.Response:
        _ = client
        calls.append(url)
        if len(calls) == 1:
            raise httpx.ConnectError(f"dropped {url}")
        return _ok()

    response = census_get(live, hedge_after=5, total=5, get=get)
    assert response.status_code == 200
    assert calls == [live, live]


def test_a_second_connection_error_is_not_retried_again() -> None:
    calls: list[str] = []
    live = f"{URL}&key=secret"

    def get(url: str, client: httpx.Client) -> httpx.Response:
        _ = client
        calls.append(url)
        raise httpx.ConnectError(f"dropped {url}")

    with pytest.raises(httpx.ConnectError) as caught:
        census_get(live, hedge_after=5, total=5, get=get)
    assert calls == [live, live]
    assert "secret" not in str(caught.value)
    assert "key=secret" not in str(caught.value)


def test_a_read_timeout_is_not_retried() -> None:
    calls: list[int] = []

    def get(url: str, client: httpx.Client) -> httpx.Response:
        _ = url, client
        calls.append(1)
        raise httpx.ReadTimeout("read")

    with pytest.raises(httpx.ReadTimeout):
        census_get(URL, hedge_after=5, total=5, get=get)
    assert calls == [1]


def test_a_hung_pair_stops_on_the_wall_clock() -> None:
    hits: list[int] = []
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler name
            hits.append(1)
            release.wait(30)

        def log_message(self, format: str, *args: object) -> None:
            _ = format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    started = time.perf_counter()
    try:
        with pytest.raises(httpx.HTTPError) as caught:
            census_get(f"http://127.0.0.1:{port}/data?key=secret", hedge_after=0.2, total=2.0)
        elapsed = time.perf_counter() - started
    finally:
        release.set()
        server.shutdown()
    assert len(hits) == 2
    assert 1.2 <= elapsed < 5
    assert "secret" not in str(caught.value)


def _show(artifact: FetchDataResult) -> object:
    record = ExecutionRecord()
    record.table_id = "B01003"
    record.universe = "Total population"
    record.pool = [
        {
            "table_id": "B01003",
            "title": "Total Population",
            "universe": "Total population",
            "members": [],
        },
        {
            "table_id": "B11001",
            "title": "Household Type",
            "universe": "Households",
            "members": [],
        },
    ]
    record.fetch = artifact
    record.rows = list(artifact.rows)
    record.url = CensusURL(artifact.url) if artifact.url else None
    record.vintages = [("acs5", year) for year in artifact.attempted_years]
    return assemble("population", record)


async def test_a_retried_fetch_keeps_margin_geoid_universe_and_alternatives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def download(url: str, client: httpx.Client) -> httpx.Response:
        _ = client
        calls.append(url)
        if len(calls) == 1:
            raise httpx.ConnectError(f"dropped {url}")
        return _ok()

    monkeypatch.setattr("src.census_http._download", download)
    tool = FetchDataTool(last_url=lambda: CensusURL(URL), census_key=lambda: "secret")
    message = await tool.ainvoke(
        {"type": "tool_call", "name": "fetch_data", "args": {"years": [2024]}, "id": "c1"}
    )
    artifact = message.artifact
    response = _show(artifact)
    assert calls[0] == calls[1]
    assert "B01003_001M" in calls[0] and "GEO_ID" in calls[0]
    assert artifact.ok is True
    assert artifact.rows[0]["B01003_001M"] == "12"
    assert artifact.rows[0]["GEO_ID"] == "0500000US48201"
    assert "key=" not in artifact.url and "secret" not in artifact.url
    assert "B01003_001M" in response.urls[0] and "GEO_ID" in response.urls[0]
    assert response.moe[0]["B01003_001M"] == "12"
    assert response.geoid == "0500000US48201"
    assert response.universe == "Total population"
    assert any(item.table_id == "B11001" for item in response.alternatives)
    assert "secret" not in artifact.legs[0].detail


async def test_a_failed_fetch_keeps_the_url_universe_and_alternatives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def download(url: str, client: httpx.Client) -> httpx.Response:
        _ = client
        raise httpx.ConnectError(f"dropped {url}")

    monkeypatch.setattr("src.census_http._download", download)
    tool = FetchDataTool(last_url=lambda: CensusURL(URL), census_key=lambda: "secret")
    message = await tool.ainvoke(
        {"type": "tool_call", "name": "fetch_data", "args": {"years": [2024]}, "id": "c1"}
    )
    artifact = message.artifact
    response = _show(artifact)
    assert artifact.ok is False
    assert artifact.legs[0].status_code == 0
    assert "B01003_001M" in artifact.url and "GEO_ID" in artifact.url
    assert "key=" not in artifact.url and "secret" not in artifact.url
    assert "secret" not in artifact.legs[0].detail
    assert "B01003_001M" in response.urls[0] and "GEO_ID" in response.urls[0]
    assert response.universe == "Total population"
    assert any(item.table_id == "B11001" for item in response.alternatives)
