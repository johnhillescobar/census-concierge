"""Direct unit tests for finish_tools: the recovery path run at the end of
every ask loop, regardless of whether the model's own turns hit an error.
"""

from __future__ import annotations

from ask_fixtures import _harris
from src.ask import ExecutionRecord, dispatch
from src.census_url import CensusURL
from src.fetch import FetchDataTool
from src.finish import finish_tools


def _fetch_tool(
    record: ExecutionRecord, status_code: int, estimate: str = "4838303"
) -> FetchDataTool:
    rows = [
        ["NAME", "GEO_ID", "B01003_001E", "B01003_001M", "state", "county"],
        ["Harris County, Texas", "0500000US48201", estimate, "123", "48", "201"],
    ]
    return FetchDataTool(
        last_url=lambda: record.url,
        census_key=lambda: "secret",
        question_years=lambda: [2024],
        published=lambda dataset: {2024},
        http_get=lambda url: (status_code, rows if status_code == 200 else "server error"),
    )


async def test_finish_tools_retries_fetch_after_a_failed_but_non_none_attempt() -> None:
    record = ExecutionRecord(question="population of Harris County, Texas")
    record.geographies = [_harris()]
    record.geography = record.geographies[0]
    record.url = CensusURL(
        "https://api.census.gov/data/2024/acs/acs5"
        "?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=county:201&in=state:48"
    )
    record.table_id = "B01003"
    record.pool = [{"table_id": "B01003", "title": "Total Population", "members": []}]

    failing = _fetch_tool(record, status_code=500)
    await dispatch(failing, {"id": "1", "args": {}}, record)
    assert record.fetch is not None
    assert record.fetch.ok is False

    tools = {"fetch_data": _fetch_tool(record, status_code=200)}
    await finish_tools(dispatch, tools, record)

    assert record.fetch is not None
    assert record.fetch.ok is True
    assert record.rows


async def test_finish_tools_does_not_refetch_an_already_successful_attempt() -> None:
    """A retry gate that fires unconditionally would refetch every request,
    doubling API calls for the common (already-succeeded) case."""
    record = ExecutionRecord(question="population of Harris County, Texas")
    record.geographies = [_harris()]
    record.geography = record.geographies[0]
    record.url = CensusURL(
        "https://api.census.gov/data/2024/acs/acs5"
        "?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=county:201&in=state:48"
    )
    record.table_id = "B01003"
    record.pool = [{"table_id": "B01003", "title": "Total Population", "members": []}]

    succeeding = _fetch_tool(record, status_code=200, estimate="4838303")
    await dispatch(succeeding, {"id": "1", "args": {}}, record)
    assert record.fetch is not None
    assert record.fetch.ok is True
    first_rows = record.rows

    # A different estimate: if the retry gate wrongly refires, this value would
    # show up in record.rows instead of the original successful fetch's.
    tools = {"fetch_data": _fetch_tool(record, status_code=200, estimate="9999999")}
    await finish_tools(dispatch, tools, record)

    assert record.rows == first_rows
