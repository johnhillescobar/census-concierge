"""Pairwise comparison work is bounded, and the bound never touches what the user is shown.

A listing of thousands of rows turned one question into millions of row pairs and gigabytes of
`Comparison` objects. The bound is row pairs x estimate columns; past it no pair is built, a warning
says so, and the rows, URL, MOE, GEOID and universe ship unchanged.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from ask_fixtures import _tools, only_dane
from src import compare
from src.ask import ExecutionRecord, run_ask
from src.compare import (
    MAX_COMPARISON_WORK,
    comparison_rows,
    comparison_too_large,
    comparison_work,
)
from src.guards import finish_aggregation

ASKS_FOR_A_COMPARISON = "Is poverty higher in one tract than in another?"
ASKS_FOR_NO_COMPARISON = "Poverty for every tract in the county"
Rows = list[dict[str, str | None]]


def _rows(geos: int, columns: int, *, years: tuple[str, ...] = ("",)) -> Rows:
    rows: Rows = []
    for year in years:
        for geo in range(geos):
            row: dict[str, str | None] = {"GEO_ID": f"0500000US{geo:011d}"}
            if year:
                row["year"] = year
            for column in range(columns):
                row[f"B25064_{column:04d}E"] = str(100 + geo + column)
                row[f"B25064_{column:04d}M"] = str(5 + column % 7)
            rows.append(row)
    return rows


def _record(question: str = ASKS_FOR_A_COMPARISON, rows: Rows | None = None) -> ExecutionRecord:
    record = ExecutionRecord(question=question)
    record.rows = rows or []
    return record


@pytest.fixture
def pairs_built(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts pair evaluations; past the bound, building even one is the failure."""
    calls: list[int] = []
    real = compare._pair_ok

    def spy(*args: Any, **kwargs: Any) -> bool:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(compare, "_pair_ok", spy)
    return calls


@pytest.fixture
def no_pair_may_be_built(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []

    def refuse(*args: Any, **kwargs: Any) -> bool:
        calls.append(1)
        raise AssertionError("a row pair was built past the work bound")

    monkeypatch.setattr(compare, "_pair_ok", refuse)
    return calls


@pytest.mark.parametrize(
    ("geos", "columns"),
    [
        (11, 1000),  # few rows, many estimate columns
        (400, 2),  # many rows, few estimate columns
        (317, 1),  # just over: 50,086 against the limit
        (5, 5001),  # just over: 50,010 against the limit
    ],
)
def test_work_over_the_bound_is_refused_before_any_pair_is_built(
    geos: int, columns: int, no_pair_may_be_built: list[int]
) -> None:
    rows = _rows(geos, columns)
    record = _record(rows=rows)
    work = comparison_work(rows, [f"B25064_{c:04d}E" for c in range(columns)])
    assert work > MAX_COMPARISON_WORK
    assert comparison_rows(record, rows) == []
    warning = comparison_too_large(record, rows)
    assert warning is not None and warning.code == "comparison_too_large"
    assert f"{work:,}" in warning.detail and f"{MAX_COMPARISON_WORK:,}" in warning.detail
    warnings, kept, _extra, compared = finish_aggregation(record, rows, set())
    assert [item.code for item in warnings] == ["comparison_too_large"]
    assert compared == [] and kept == rows  # every row still ships
    assert no_pair_may_be_built == []


def test_work_exactly_at_the_bound_does_not_warn() -> None:
    columns = 5000  # 5 rows are 10 pairs: exactly the documented limit of 50,000
    rows = _rows(5, columns)
    assert 10 * columns == MAX_COMPARISON_WORK == 50_000, "this shape must sit on the limit"
    assert comparison_too_large(_record(rows=rows), rows) is None


def test_the_work_it_counts_is_the_work_it_does(pairs_built: list[int]) -> None:
    rows = _rows(6, 4)  # 15 pairs x 4 estimate columns
    record = _record(rows=rows)
    work = comparison_work(rows, [f"B25064_{c:04d}E" for c in range(4)])
    assert work == 60
    assert len(comparison_rows(record, rows)) == work
    assert len(pairs_built) == work  # the bound predicts the real work exactly


@pytest.mark.parametrize(("limit", "refused"), [(63, False), (62, True)])
def test_the_bound_is_inclusive(
    monkeypatch: pytest.MonkeyPatch, pairs_built: list[int], limit: int, refused: bool
) -> None:
    monkeypatch.setattr(compare, "MAX_COMPARISON_WORK", limit)
    rows = _rows(7, 3)  # 21 pairs x 3 columns = 63
    record = _record(rows=rows)
    assert (comparison_too_large(record, rows) is not None) is refused
    assert (comparison_rows(record, rows) == []) is refused
    assert bool(pairs_built) is not refused


def test_the_largest_legitimate_fan_out_is_still_compared(pairs_built: list[int]) -> None:
    # 5 legs x 12 years x 25 columns: 60 rows is 1,770 pairs, and 25 columns is 44,250.
    rows = _rows(5, 25, years=tuple(str(2013 + n) for n in range(12)))
    record = _record(rows=rows)
    estimates = [key for key in rows[0] if key.endswith("E") and "_" in key]
    assert comparison_work(rows, estimates) == 44_250
    warnings, kept, _extra, compared = finish_aggregation(record, rows, set())
    assert "comparison_too_large" not in {item.code for item in warnings}
    assert kept == rows
    # one geography against another in the same year: 10 pairs x 12 years x 25 columns
    assert len(compared) == 10 * 12 * 25
    pair = compared[0]
    assert pair.moe_a and pair.moe_b and pair.threshold and pair.geoid_a != pair.geoid_b


def test_a_column_that_only_ends_in_e_is_not_an_estimate_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(compare, "MAX_COMPARISON_WORK", 3)
    rows = [{**row, "NAME": f"Tract {n}"} for n, row in enumerate(_rows(3, 1))]  # 3 pairs x 1
    record = _record(rows=rows)
    assert comparison_too_large(record, rows) is None
    assert len(comparison_rows(record, rows)) == 3


def test_a_comparison_asked_with_no_rows_has_no_work_and_no_warning() -> None:
    record = _record()
    assert comparison_too_large(record, []) is None
    assert comparison_rows(record, []) == []


def test_rows_without_a_geoid_do_not_count_toward_the_bound(pairs_built: list[int]) -> None:
    blank = [{**row, "GEO_ID": ""} for row in _rows(400, 2)]
    rows = [*blank, *_rows(4, 2)]
    record = _record(rows=rows)
    assert comparison_too_large(record, rows) is None
    assert len(comparison_rows(record, rows)) == 6 * 2  # only the four usable rows pair up


def test_nothing_is_warned_when_no_comparison_was_asked(
    no_pair_may_be_built: list[int],
) -> None:
    rows = _rows(400, 2)
    record = _record(ASKS_FOR_NO_COMPARISON, rows)
    assert comparison_too_large(record, rows) is None
    warnings, kept, _extra, compared = finish_aggregation(record, rows, set())
    assert warnings == [] and compared == [] and kept == rows
    assert no_pair_may_be_built == []


def test_overlapping_vintages_are_warned_once_and_not_as_too_large(
    no_pair_may_be_built: list[int],
) -> None:
    rows = _rows(400, 2)
    record = _record(rows=rows)
    record.vintages = [("acs5", 2019), ("acs5", 2022)]
    warnings, _kept, _extra, compared = finish_aggregation(record, rows, set())
    assert [item.code for item in warnings] == ["overlapping_vintage"]
    assert compared == []
    assert no_pair_may_be_built == []


def test_the_same_rows_with_distinct_vintages_are_warned_as_too_large() -> None:
    rows = _rows(400, 2)
    record = _record(rows=rows)
    record.vintages = [("acs5", 2017), ("acs5", 2022)]
    warnings, _kept, _extra, _compared = finish_aggregation(record, rows, set())
    assert [item.code for item in warnings] == ["comparison_too_large"]


SIX_THOUSAND = 6896  # the rows of a statewide tract listing


def _http(rows: int) -> Any:
    header = ["NAME", "B17001_001E", "B17001_001M", "GEO_ID", "state", "county", "tract"]
    body = [
        [f"Tract {n}", str(1000 + n % 90), str(30 + n % 11), f"1400000US55025{n:06d}", "55", "025"]
        + [f"{n:06d}"]
        for n in range(rows)
    ]
    return lambda url: (200, [header, *body])


async def test_a_listing_too_large_to_pair_still_returns_its_rows_url_and_margins(
    no_pair_may_be_built: list[int],
) -> None:
    question = "Is poverty higher in some tracts of Dane County, Wisconsin than others?"
    record = ExecutionRecord()
    tools = _tools(record)
    tools["fetch_data"].http_get = _http(SIX_THOUSAND)
    tools["resolve_geography"].list_geographies = only_dane
    steps = [
        ("search_tables", {"question": question}),
        ("resolve_geography", {"query": "every tract in Dane County, Wisconsin"}),
        ("build_url", {"table_id": "B17001"}),
        ("fetch_data", {}),
    ]
    reply = {
        "parents": [],
        "unit": "tract",
        "listing": True,
        "level": "tract",
        "named": ["Dane County, Wisconsin"],
        "numbered": [],
    }

    async def complete(
        messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not openai_tools:
            return {"content": json.dumps(reply), "tool_calls": []}
        done = len(record.timings)
        if done >= len(steps):
            return {"content": "Here is the listing.", "tool_calls": []}
        name, args = steps[done]
        return {"content": "", "tool_calls": [{"id": str(done), "name": name, "args": args}]}

    response = await run_ask(question, complete=complete, tools=tools, record=record)
    codes = [item.code for item in response.warnings]
    assert "comparison_too_large" in codes and "moe_not_significant" not in codes
    assert response.comparisons == []
    assert len(response.rows) == SIX_THOUSAND  # the fetch is never limited
    assert len({row["GEO_ID"] for row in response.rows}) == SIX_THOUSAND
    assert len(response.moe) == SIX_THOUSAND and "B17001_001M" in response.moe[0]
    assert response.urls and "tract:*" in response.urls[0] and "B17001_001M" in response.urls[0]
    assert response.universe and response.table_id == "B17001"
    assert no_pair_may_be_built == []
