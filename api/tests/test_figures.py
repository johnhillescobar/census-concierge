"""Figures in an answer: rendered from the rows by code; the model text is checked per digit."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from src import figures
from src.ask import ExecutionRecord, assemble
from src.census_url import CensusURL
from src.contract import take_chart
from src.fetch import FetchDataTool
from src.retrieval import metadata

COOK = {
    "NAME": "Cook County, Illinois",
    "GEO_ID": "0500000US17031",
    "state": "17",
    "county": "031",
    "year": "2023",
    "dataset": "acs5",
    "B19013_001E": "76000",
    "B19013_001M": "1200",
}
DUPAGE = {
    **COOK,
    "NAME": "DuPage County, Illinois",
    "GEO_ID": "0500000US17043",
    "county": "043",
    "B19013_001E": "99500",
    "B19013_001M": "2100",
}
TITLE = "Median Household Income in the Past 12 Months"


def _record(labels: dict[str, dict[str, str]] | None = None, facts: Any = None) -> SimpleNamespace:
    if labels is None:
        labels = {"2023": {"B19013_001E": "Median household income"}}
    return SimpleNamespace(
        fetch=SimpleNamespace(labels=labels, requested_years=[2023]),
        table_facts=facts
        or (lambda dataset, year, table: {"title": TITLE, "universe": "Households"}),
        universe="",
    )


def test_figures_carry_label_estimate_margin_place_geoid_and_vintage() -> None:
    answer, problem = figures.checked("Two counties compared.", [COOK, DUPAGE], _record())
    assert problem == ""
    assert answer.startswith("Two counties compared.\n\n")
    assert (
        "Median household income: 76,000 (margin of error 1,200), "
        "Cook County, Illinois (0500000US17031), acs5 2023."
    ) in answer
    assert (
        "Median household income: 99,500 (margin of error 2,100), "
        "DuPage County, Illinois (0500000US17043), acs5 2023."
    ) in answer
    assert answer.endswith(f"Table B19013: {TITLE}. Universe: Households")


def test_a_sentinel_is_never_shown_as_a_figure() -> None:
    sentinel = {**COOK, "B19013_001E": "-555555555", "B19013_001M": "-555555555"}
    unpublished = {**DUPAGE, "B19013_001M": "-555555555"}
    answer, _ = figures.checked("", [sentinel, unpublished], _record())
    assert "Median household income: not available, Cook County" in answer
    assert "99,500 (margin of error not published)" in answer
    assert "555,555,555" not in answer
    assert "555555555" not in answer


def test_a_long_result_shows_the_first_twenty_and_says_how_many_there_are() -> None:
    rows = [
        {**COOK, "GEO_ID": f"0500000US{17000 + i}", "B19013_001E": str(50000 + i)}
        for i in range(25)
    ]
    answer, _ = figures.checked("", rows, _record())
    assert sum(line.startswith("Median household income:") for line in answer.split("\n")) == 20
    assert "50,019 (margin" in answer
    assert "50,020" not in answer
    assert "20 of 25 figures shown" in answer


def test_a_number_the_response_does_not_carry_replaces_the_models_text() -> None:
    answer, problem = figures.checked("Cook County earns about 78,462.", [COOK], _record())
    assert "78,462" in problem
    assert "78,462" not in answer
    assert "Cook County earns" not in answer
    assert answer.startswith("Median household income: 76,000")


def test_numbers_that_equal_the_rows_pass_however_they_are_written() -> None:
    prose = "Cook County earns $76,000 in 2023, give or take 1,200."
    answer, problem = figures.checked(prose, [COOK], _record())
    assert problem == ""
    assert answer.startswith(prose)


def test_numbers_from_the_dataset_title_and_geography_columns_pass() -> None:
    prose = "ACS 5-year estimates for the past 12 months, county code 031 in state 17."
    answer, problem = figures.checked(prose, [COOK], _record())
    assert problem == ""
    assert answer.startswith(prose)
    _, wrong = figures.checked("For the past 14 months.", [COOK], _record())
    assert "14" in wrong


def test_a_number_equal_only_to_a_sentinel_is_not_carried() -> None:
    sentinel = {**COOK, "B19013_001E": "-555555555"}
    answer, problem = figures.checked("The estimate is 555555555.", [sentinel], _record())
    assert "555,555,555" in problem
    assert "The estimate is" not in answer


def test_nothing_fetched_leaves_a_clean_text_alone_and_removes_a_figure() -> None:
    nothing = SimpleNamespace(fetch=None, table_facts=None, universe="")
    assert figures.checked("Fetch failed; no estimates available.", [], nothing) == (
        "Fetch failed; no estimates available.",
        "",
    )
    assert figures.checked("", [], nothing) == ("", "")
    answer, problem = figures.checked("About 5,000 people live there.", [], nothing)
    assert answer == figures.NO_FIGURES
    assert "5,000" in problem


def test_each_vintage_is_read_with_its_own_label_title_and_universe() -> None:
    old, new = {**COOK, "year": "2022"}, COOK
    labels = {
        "2022": {"B19013_001E": "Median household income (2022 dollars)"},
        "2023": {"B19013_001E": "Median household income (2023 dollars)"},
    }

    def facts(dataset: str, year: int, table: str) -> dict[str, str]:
        return {"title": f"Income in {year} dollars", "universe": f"Households in {year}"}

    answer, problem = figures.checked("", [old, new], _record(labels, facts))
    assert problem == ""
    lines = answer.split("\n")
    assert lines[0].startswith("Median household income (2022 dollars): 76,000")
    assert lines[1].startswith("Median household income (2023 dollars): 76,000")
    assert "2022: Table B19013: Income in 2022 dollars. Universe: Households in 2022" in lines
    assert "2023: Table B19013: Income in 2023 dollars. Universe: Households in 2023" in lines


async def test_labels_are_looked_up_once_per_vintage(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int]] = []

    def lookup(dataset: str, year: int, wanted: set[str]) -> dict[str, str]:
        calls.append((dataset, year))
        return {key: f"label {year}" for key in wanted}

    monkeypatch.setattr(figures, "_labels", lookup)
    rows = [{**COOK, "year": str(y)} for y in (2021, 2022, 2023)] + [DUPAGE]
    found = await figures.labels_for(rows, "acs5")
    assert sorted(calls) == [("acs5", 2021), ("acs5", 2022), ("acs5", 2023)]
    assert found == {str(y): {"B19013_001E": f"label {y}"} for y in (2021, 2022, 2023)}


def test_a_failed_label_lookup_is_empty_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()  # the suite stubs _labels for every test; this one needs the real one

    def unreadable(dataset: str, year: int) -> dict[str, Any]:
        raise OSError("metadata cache missing")

    monkeypatch.setattr(metadata, "variables", unreadable)
    assert figures._labels("acs5", 2023, {"B19013_001E"}) == {}


def test_the_chart_survives_when_the_text_is_replaced() -> None:
    chart = {"type": "bar", "x": "geography", "y": "estimate", "title": "Income", "show_moe": True}
    envelope = json.dumps({"answer": "Cook County earns 99,999.", "chart": chart})
    warnings: list[Any] = []
    parts = take_chart(envelope, [COOK, DUPAGE], warnings, _record())
    assert parts["chart"] is not None
    assert parts["chart"].type == "bar"
    assert "99,999" not in parts["answer"]
    assert [item.code for item in warnings] == ["answer_figures_unverified"]


def test_assemble_adds_the_figures_and_warns_when_the_text_states_another() -> None:
    clean = assemble("Cook County framing.", ExecutionRecord(rows=[COOK], table_id="B19013"))
    assert clean.answer.startswith("Cook County framing.\n\n")
    assert (
        "B19013_001E: 76,000 (margin of error 1,200), "
        "Cook County, Illinois (0500000US17031), acs5 2023."
    ) in clean.answer
    assert "answer_figures_unverified" not in [item.code for item in clean.warnings]
    wrong = assemble("Cook County earns 78,462.", ExecutionRecord(rows=[COOK], table_id="B19013"))
    assert "answer_figures_unverified" in [item.code for item in wrong.warnings]
    assert "78,462" not in wrong.answer


async def test_fetch_data_carries_each_vintages_labels_on_its_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        figures, "_labels", lambda dataset, year, wanted: {key: f"label {year}" for key in wanted}
    )
    built = CensusURL(
        "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M"
        "&for=county:201&in=state:48"
    )

    def http_get(url: str) -> tuple[int, object]:
        year = int(url.split("/")[url.split("/").index("data") + 1])
        header = ["NAME", "GEO_ID", "B01003_001E", "B01003_001M"]
        return 200, [header, ["Harris County, Texas", "0500000US48201", str(year), "123"]]

    tool = FetchDataTool(last_url=lambda: built, census_key=lambda: "secret", http_get=http_get)
    message = await tool.ainvoke(
        {"type": "tool_call", "name": "fetch_data", "args": {"years": [2019, 2022]}, "id": "c1"}
    )
    assert message.artifact.labels == {
        "2019": {"B01003_001E": "label 2019"},
        "2022": {"B01003_001E": "label 2022"},
    }
