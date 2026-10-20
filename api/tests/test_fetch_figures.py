"""What the model is shown after fetch_data: labelled figures, never more than it was given."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from src import figures
from src.ask import ExecutionRecord, dispatch
from src.census_url import CensusURL
from src.fetch import FetchDataTool
from src.figures import MAX_FIGURES
from src.retrieval.metadata import Variable

URL = CensusURL(
    "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M"
    "&for=county:*&in=state:48"
)
HEADER = ["NAME", "GEO_ID", "B01003_001E", "B01003_001M"]
SENTINEL = "-555555555"
LABEL = "Estimate!!Total:!!Male:"
LABELS = figures._labels  # the real lookup; conftest stubs it for every other test
LOOKUPS: list[tuple[str, int]] = []
ASKED: list[tuple[str, int, str]] = []


@pytest.fixture(autouse=True)
def labels(monkeypatch: pytest.MonkeyPatch) -> None:
    LOOKUPS.clear()
    ASKED.clear()

    def found(dataset: str, year: int) -> dict[str, Variable]:
        LOOKUPS.append((dataset, year))
        return {"B01003_001E": Variable("B01003_001E", "B01003", LABEL, "Total Population")}

    monkeypatch.setattr(figures.metadata, "variables", found)
    monkeypatch.setattr(figures, "_labels", LABELS)


def _tool(
    payload: Any,
    universe: str = "Total population",
    status: int = 200,
    fail: str = "",
    title: str | Callable[[int], str] = "",
) -> Any:
    def facts(dataset: str, year: int, table: str) -> dict[str, Any]:
        ASKED.append((dataset, year, table))
        said = title(year) if callable(title) else title
        return {"title": said, "universe": universe, "variables": ["001E", "001M"]}

    def http_get(url: str) -> tuple[int, Any]:
        return (500, "error") if fail and f"/{fail}/" in url else (status, payload)

    return FetchDataTool(
        last_url=lambda: URL, census_key=lambda: "secret", http_get=http_get, table_facts=facts
    )


async def _content(tool: Any, years: list[int] | None = None) -> str:
    call = {"type": "tool_call", "name": "fetch_data", "args": {"years": years or []}, "id": "c"}
    return str((await tool.ainvoke(call)).content)


def _county(n: int, est: str | None = None, moe: str | None = "7") -> list[str | None]:
    return [f"County {n}, Texas", f"0500000US48{n:03d}", est or str(1000 + n), moe]


def _line(content: str, needle: str) -> str:
    return next(item for item in content.splitlines() if needle in item)


async def test_tool_content_carries_value_margin_label_place_geoid_vintage_and_universe() -> None:
    tool = _tool([HEADER, _county(1), _county(2)])
    content = await _content(tool)
    assert _line(content, "County 1,") == (
        "Total: - Male: | 1001 (margin of error 7) | County 1, Texas (0500000US48001) | acs5 2024"
    )
    assert "1002 (margin of error 7)" in _line(content, "County 2,")
    assert content.splitlines()[-1] == "Universe: Total population"
    assert ASKED[-1] == ("acs5", 2024, "B01003") and LOOKUPS == [("acs5", 2024)]


async def test_label_is_the_census_label_without_estimate_prefix_or_double_colons() -> None:
    line = _line(await _content(_tool([HEADER, _county(1)])), "County 1,")
    assert line.startswith("Total: - Male: |") and "::" not in line and "Estimate" not in line


async def test_sentinel_estimate_and_margin_are_never_shown_as_figures() -> None:
    content = await _content(_tool([HEADER, _county(1, est=SENTINEL), _county(2, moe=SENTINEL)]))
    assert SENTINEL not in content
    assert _line(content, "County 1,") == (
        "Total: - Male: | not available | County 1, Texas (0500000US48001) | acs5 2024"
    )
    assert "1002 (margin of error not published)" in _line(content, "County 2,")


async def test_a_row_without_a_margin_column_says_not_published() -> None:
    payload = [HEADER[:3], ["County 1, Texas", "0500000US48001", "1001"]]
    assert "1001 (margin of error not published)" in await _content(_tool(payload))


async def test_the_cap_counts_figures_not_rows() -> None:
    header = ["NAME", "GEO_ID", *(f"B01003_{n:03d}{k}" for n in (1, 2, 3) for k in "EM")]
    rows = [[f"County {n}, Texas", f"0500000US48{n:03d}", *(str(n)) * 6] for n in range(1, 9)]
    tool = _tool([header, *rows])
    message = await tool.ainvoke({"type": "tool_call", "name": "fetch_data", "args": {}, "id": "c"})
    shown = [item for item in str(message.content).splitlines() if "| acs5 2024" in item]
    assert len(shown) == MAX_FIGURES
    assert f"{MAX_FIGURES} of 24 figures shown; the other 4 were fetched." in str(message.content)
    assert "County 8," not in str(message.content)
    assert len(message.artifact.rows) == 8


async def test_a_missing_label_cache_falls_back_to_the_variable_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for failure in (OSError("no cache"), EOFError("truncated"), ValueError("corrupt")):

        def broken(*_args: object, failure: Exception = failure) -> dict[str, Variable]:
            raise failure

        monkeypatch.setattr(figures.metadata, "variables", broken)
        content = await _content(_tool([HEADER, _county(1)]))
        assert _line(content, "County 1,").startswith("B01003_001E | 1001 (margin of error 7) |")


async def test_labels_and_universe_come_from_the_years_that_returned_rows() -> None:
    tool = _tool([HEADER, _county(1)], fail="2022")
    content = await _content(tool, years=[2019, 2022])
    assert LOOKUPS == [("acs5", 2019)] and ASKED[-1] == ("acs5", 2019, "B01003")
    assert "acs5 2019" in content


async def test_no_universe_line_when_the_table_has_none() -> None:
    content = await _content(_tool([HEADER, _county(1)], universe=""))
    assert "Universe" not in content and "1001" in content


async def test_failed_fetch_content_has_no_figures() -> None:
    content = await _content(_tool("error", status=500))
    assert "fetch failed" in content
    assert "Universe" not in content and "margin of error" not in content and "|" not in content


async def test_the_tool_text_never_carries_the_census_key() -> None:
    content = await _content(_tool([HEADER, _county(1)]))
    assert "secret" not in content and "key=" not in content


async def test_the_string_the_model_receives_includes_the_figures() -> None:
    record = ExecutionRecord()
    call = {"id": "1", "name": "fetch_data", "args": {}}
    seen = await dispatch(_tool([HEADER, _county(1)]), call, record)
    assert "1001 (margin of error 7)" in seen
    assert record.rows and record.rows[0]["B01003_001E"] == "1001"


async def test_the_closing_line_names_the_table_and_its_universe() -> None:
    content = await _content(_tool([HEADER, _county(1)], title="Total Population"))
    assert content.splitlines()[-1] == "Table B01003: Total Population. Universe: Total population"


async def test_each_year_is_labelled_with_its_own_vintage(monkeypatch: pytest.MonkeyPatch) -> None:
    def found(dataset: str, year: int) -> dict[str, Variable]:
        label = f"Estimate!!Income (in {year} dollars)"
        return {"B01003_001E": Variable("B01003_001E", "B01003", label, "Income")}

    monkeypatch.setattr(figures.metadata, "variables", found)
    content = await _content(_tool([HEADER, _county(1)]), years=[2019, 2024])
    assert "Income (in 2019 dollars) | 1001 (margin of error 7) | County 1, Texas" in _line(
        content, "acs5 2019"
    )
    assert "Income (in 2024 dollars) | 1001 (margin of error 7) | County 1, Texas" in _line(
        content, "acs5 2024"
    )


async def test_a_title_that_changed_between_years_is_attributed_to_its_years() -> None:
    tool = _tool([HEADER, _county(1)], title=lambda year: f"Income (in {year} dollars)")
    lines = (await _content(tool, years=[2019, 2024])).splitlines()
    assert lines[-2:] == [
        "2019: Table B01003: Income (in 2019 dollars). Universe: Total population",
        "2024: Table B01003: Income (in 2024 dollars). Universe: Total population",
    ]


async def test_one_closing_line_when_the_table_did_not_change_between_years() -> None:
    content = await _content(_tool([HEADER, _county(1)], title="Population"), years=[2019, 2024])
    closing = [item for item in content.splitlines() if item.startswith(("Table", "20"))]
    assert closing == ["Table B01003: Population. Universe: Total population"]
