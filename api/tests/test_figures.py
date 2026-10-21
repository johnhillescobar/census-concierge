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
from src.fetch import FetchDataResult, FetchDataTool
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


# --- Adversarial probes. Code output only, seeded rows, no model, no prose assertions. ---------


def _fetch(**fields: Any) -> FetchDataResult:
    base: dict[str, Any] = {
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
    }
    return FetchDataResult(**{**base, **fields})


def _wide(columns: int = 25) -> dict[str, str | None]:
    """One row, one place, `columns` estimate variables (each with its margin)."""
    return {
        "NAME": "Cook County, Illinois",
        "GEO_ID": "0500000US17031",
        "year": "2023",
        "dataset": "acs5",
        **{f"B01001_{i:03d}E": str(1000 + i) for i in range(1, columns + 1)},
        **{f"B01001_{i:03d}M": str(i) for i in range(1, columns + 1)},
    }


def _envelope(text: str, chart: Any = None) -> str:
    return json.dumps({"answer": text, "chart": chart})


@pytest.mark.parametrize("written", ["76,001", "75,999", "7600", "760,000"])
def test_a_figure_that_differs_in_any_digit_is_not_carried(written: str) -> None:
    answer, problem = figures.checked(f"Cook County earns {written}.", [COOK, DUPAGE], _record())
    assert problem
    assert "Cook County earns" not in answer
    assert answer.startswith("Median household income: 76,000")


@pytest.mark.parametrize("written", ["76.000", "99.500"])
def test_a_period_is_not_read_as_a_thousands_separator(written: str) -> None:
    answer, problem = figures.checked(f"Cook County earns {written}.", [COOK, DUPAGE], _record())
    assert problem
    assert "Cook County earns" not in answer


def test_a_range_of_two_carried_figures_passes() -> None:
    prose = "Incomes run 76,000-99,500 across the two counties."
    answer, problem = figures.checked(prose, [COOK, DUPAGE], _record())
    assert problem == ""
    assert answer.startswith(prose)


@pytest.mark.parametrize(
    "separator",
    ["-", "–", "—", "/", "|"],
    ids=["hyphen", "en_dash", "em_dash", "slash", "pipe"],
)
def test_a_stray_figure_after_a_separator_is_found(separator: str) -> None:
    prose = f"Incomes run 76,000{separator}78,462."
    answer, problem = figures.checked(prose, [COOK, DUPAGE], _record())
    assert "78,462" in problem
    assert "Incomes run" not in answer


def test_a_fraction_is_two_figures_and_neither_is_carried() -> None:
    answer, problem = figures.checked("About 1/2 of households.", [COOK], _record())
    assert problem
    assert "About 1/2" not in answer


def test_a_rounded_figure_with_a_magnitude_word_is_not_carried() -> None:
    big = {**COOK, "B19013_001E": "2132000", "B19013_001M": "9000"}
    answer, problem = figures.checked("Cook County has 2.1 million people.", [big], _record())
    assert "2.1" in problem
    assert "Cook County has" not in answer
    assert "2,132,000" in answer


@pytest.mark.parametrize("word", ["nan", "NaN", "inf", "Infinity", "-inf", "+Infinity"])
def test_words_float_would_read_are_not_figures(word: str) -> None:
    prose = f"The value {word} is a word here, not a figure."
    answer, problem = figures.checked(prose, [COOK], _record())
    assert problem == ""
    assert answer.startswith(prose)


@pytest.mark.parametrize(
    "written",
    ["$78,462", "78,462%", "**78,462**", "(78,462)", '"78,462"', "78,462;"],
    ids=["dollar", "percent", "bold", "parenthesis", "double_quote", "semicolon"],
)
def test_marks_around_a_figure_do_not_hide_it(written: str) -> None:
    answer, problem = figures.checked(f"Cook County earns {written} a year.", [COOK], _record())
    assert "78,462" in problem
    assert "Cook County earns" not in answer


def test_a_sentinel_written_in_the_models_text_is_replaced() -> None:
    gone = {**COOK, "B19013_001E": "-555555555", "B19013_001M": "-555555555"}
    for written in ("-555555555", "555,555,555", "-555,555,555"):
        answer, problem = figures.checked(f"The estimate is {written}.", [gone], _record())
        assert "555,555,555" in problem
        assert "The estimate is" not in answer


@pytest.mark.parametrize(
    ("dataset", "named", "stray"), [("acs1", "1-year", "5-year"), ("acs5", "5-year", "1-year")]
)
def test_the_dataset_decides_which_span_the_text_may_name(
    dataset: str, named: str, stray: str
) -> None:
    row = {**COOK, "dataset": dataset}
    answer, problem = figures.checked(f"These are {named} estimates.", [row], _record())
    assert problem == ""
    assert answer.startswith(f"These are {named} estimates.")
    answer, problem = figures.checked(f"These are {stray} estimates.", [row], _record())
    assert problem
    assert "These are" not in answer


def test_the_fips_digits_of_a_geoid_are_carried() -> None:
    answer, problem = figures.checked("Cook County is FIPS 17031.", [COOK], _record())
    assert problem == ""
    assert answer.startswith("Cook County is FIPS 17031.")
    _, wrong = figures.checked("Cook County is FIPS 17032.", [COOK], _record())
    assert "17,032" in wrong


@pytest.mark.parametrize(
    "field",
    ["requested_years", "attempted_years", "succeeded_years", "failed_years", "omitted_years"],
)
def test_every_year_the_fetch_reports_may_be_named(field: str) -> None:
    record = SimpleNamespace(fetch=_fetch(**{field: [2019]}), table_facts=None, universe="")
    answer, problem = figures.checked("The 2019 vintage is reported.", [COOK], record)
    assert problem == ""
    assert answer.startswith("The 2019 vintage is reported.")
    _, wrong = figures.checked("The 2018 vintage is not reported.", [COOK], record)
    assert "2,018" in wrong


def test_the_period_of_a_vintage_may_be_named_in_a_real_response() -> None:
    record = ExecutionRecord(rows=[COOK], table_id="B19013")
    prose = "ACS 2019-2023 5-year estimates for Cook County."
    response = assemble(prose, record)
    assert response.answer.startswith(prose)
    assert "answer_figures_unverified" not in [item.code for item in response.warnings]


@pytest.mark.xfail(
    strict=True,
    reason="a token float() cannot read is skipped, so a figure glued to a mark passes unchecked",
)
@pytest.mark.parametrize(
    "written",
    ["$78k", "±99,999", "−178,462", "“99,999”", "99,999USD"],
    ids=["k_suffix", "plus_minus", "unicode_minus", "curly_quotes", "currency_code"],
)
def test_a_figure_glued_to_a_mark_float_cannot_read_is_still_checked(written: str) -> None:
    answer, problem = figures.checked(f"Cook County earns {written} a year.", [COOK], _record())
    assert problem
    assert "Cook County earns" not in answer


@pytest.mark.parametrize(
    ("drop", "tail"),
    [(("year", "dataset"), ""), (("year",), ", acs5"), (("dataset",), ", 2023")],
    ids=["neither", "no_year", "no_dataset"],
)
def test_a_row_with_no_year_or_dataset_renders_no_vintage_text(
    drop: tuple[str, ...], tail: str
) -> None:
    row = {k: v for k, v in COOK.items() if k not in drop}
    answer, _ = figures.checked("", [row], _record({}))
    head = "B19013_001E: 76,000 (margin of error 1,200), Cook County, Illinois (0500000US17031)"
    assert answer.split("\n")[0] == f"{head}{tail}."
    assert "None" not in answer
    assert "  " not in answer


@pytest.mark.parametrize(
    ("drop", "place"),
    [
        (("NAME",), "(0500000US17031)"),
        (("GEO_ID",), "Cook County, Illinois"),
        (("NAME", "GEO_ID"), ""),
    ],
    ids=["no_name", "no_geoid", "no_place"],
)
def test_a_row_missing_part_of_its_place_renders_the_rest(
    drop: tuple[str, ...], place: str
) -> None:
    row = {k: v for k, v in COOK.items() if k not in drop}
    answer, _ = figures.checked("", [row], _record({}))
    head = "B19013_001E: 76,000 (margin of error 1,200)"
    expected = f"{head}, {place}, acs5 2023." if place else f"{head}, acs5 2023."
    assert answer.split("\n")[0] == expected
    assert "None" not in answer


def test_only_estimate_columns_are_rendered_as_figures() -> None:
    row = {**COOK, "B19013_001EA": "-", "B19013_001MA": "-", "table_id": "B19013"}
    answer, _ = figures.checked("", [row], _record())
    shown = [line.split(":")[0] for line in answer.split("\n") if "(margin of error" in line]
    assert shown == ["Median household income"]


def test_one_wide_row_shows_twenty_figures_and_counts_the_rest() -> None:
    answer, _ = figures.checked("", [_wide()], _record({}))
    lines = answer.split("\n")
    assert sum("(margin of error" in line for line in lines) == 20
    assert lines[19].startswith("B01001_020E: 1,020 (margin of error 20), Cook County")
    assert "B01001_021E" not in answer
    assert "20 of 25 figures shown; the table has the rest." in lines


def test_a_result_with_a_place_but_no_estimate_cells_renders_no_figures() -> None:
    place = {k: v for k, v in COOK.items() if k not in ("B19013_001E", "B19013_001M")}
    record = _record()
    record.universe = "Households"
    assert figures.checked("Framing only.", [place], record) == ("Framing only.", "")
    answer, problem = figures.checked("Framing says 78,462.", [place], record)
    assert answer == figures.NO_FIGURES
    assert "78,462" in problem


def test_the_universe_comes_from_the_table_facts_then_from_the_record() -> None:
    record = _record(facts=lambda dataset, year, table: {"title": TITLE, "universe": "Per 2023"})
    record.universe = "Households"
    answer, _ = figures.checked("", [COOK], record)
    assert answer.endswith(f"Table B19013: {TITLE}. Universe: Per 2023")
    record = _record(facts=lambda dataset, year, table: {"title": TITLE})
    record.universe = "Households"
    answer, _ = figures.checked("", [COOK], record)
    assert answer.endswith(f"Table B19013: {TITLE}. Universe: Households")
    record = _record(facts=lambda dataset, year, table: None)
    record.universe = "Households"
    answer, _ = figures.checked("", [COOK], record)
    assert answer.endswith("\nUniverse: Households")
    assert "Table B19013" not in answer


def test_the_facts_line_is_printed_once_when_every_vintage_agrees() -> None:
    record = _record(facts=lambda dataset, year, table: {"title": TITLE, "universe": "Households"})
    answer, _ = figures.checked("", [{**COOK, "year": "2022"}, COOK], record)
    lines = answer.split("\n")
    assert lines[-1] == f"Table B19013: {TITLE}. Universe: Households"
    assert sum(line.endswith("Universe: Households") for line in lines) == 1


def test_a_figure_keeps_its_decimals_and_its_sign() -> None:
    share = {**COOK, "B19013_001E": "12.50", "B19013_001M": "0.25"}
    drop = {**COOK, "GEO_ID": "0500000US17043", "B19013_001E": "-12", "B19013_001M": "0"}
    answer, problem = figures.checked("", [share, drop], _record())
    assert problem == ""
    assert "Median household income: 12.50 (margin of error 0.25)" in answer
    assert "Median household income: -12 (margin of error 0)" in answer


def test_a_label_loses_its_estimate_prefix_and_joins_its_levels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.undo()  # the suite stubs _labels for every test; this one needs the real one
    found = {
        "B01001_001E": SimpleNamespace(label="Estimate!!Total:"),
        "B01001_002E": SimpleNamespace(label="Estimate!!Total:!!Male:"),
    }
    monkeypatch.setattr(metadata, "variables", lambda dataset, year: found)
    wanted = {"B01001_002E", "B01001_999E"}
    assert figures._labels("acs5", 2023, wanted) == {"B01001_002E": "Total: - Male:"}


async def test_labels_are_asked_for_every_variable_of_a_vintage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[int, set[str]] = {}

    def lookup(dataset: str, year: int, wanted: set[str]) -> dict[str, str]:
        seen[year] = set(wanted)
        return {}

    monkeypatch.setattr(figures, "_labels", lookup)
    rows = [COOK, {**COOK, "B19013_002E": "5"}, {**COOK, "year": "2022"}]
    await figures.labels_for(rows, "acs5")
    assert seen == {2023: {"B19013_001E", "B19013_002E"}, 2022: {"B19013_001E"}}


async def test_labels_are_asked_only_for_the_figures_that_are_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[set[str]] = []

    def lookup(dataset: str, year: int, wanted: set[str]) -> dict[str, str]:
        seen.append(set(wanted))
        return {}

    monkeypatch.setattr(figures, "_labels", lookup)
    await figures.labels_for([_wide()], "acs5")
    assert [len(wanted) for wanted in seen] == [20]
    assert "B01001_021E" not in seen[0]


async def test_rows_without_a_vintage_are_not_looked_up(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def lookup(dataset: str, year: int, wanted: set[str]) -> dict[str, str]:
        calls.append(year)
        return {}

    monkeypatch.setattr(figures, "_labels", lookup)
    rows = [{**COOK, "year": ""}, {k: v for k, v in COOK.items() if k != "year"}]
    assert await figures.labels_for(rows, "acs5") == {}
    assert calls == []


def test_assemble_renders_the_labels_the_fetch_carried() -> None:
    labels = {"2023": {"B19013_001E": "Median household income"}}
    fetch = _fetch(rows=[COOK], requested_years=[2023], labels=labels)
    record = ExecutionRecord(rows=[COOK], table_id="B19013", fetch=fetch)
    response = assemble("Framing.", record)
    assert "Median household income: 76,000 (margin of error 1,200)" in response.answer


async def test_fetch_data_looks_labels_up_in_the_dataset_it_fetched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, int]] = []

    def lookup(dataset: str, year: int, wanted: set[str]) -> dict[str, str]:
        asked.append((dataset, year))
        return {}

    monkeypatch.setattr(figures, "_labels", lookup)
    built = CensusURL(
        "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M"
        "&for=county:201&in=state:48"
    )

    def http_get(url: str) -> tuple[int, object]:
        header = ["NAME", "GEO_ID", "B01003_001E", "B01003_001M"]
        return 200, [header, ["Harris County, Texas", "0500000US48201", "4", "123"]]

    tool = FetchDataTool(last_url=lambda: built, census_key=lambda: "secret", http_get=http_get)
    await tool.ainvoke(
        {"type": "tool_call", "name": "fetch_data", "args": {"years": [2019, 2022]}, "id": "c1"}
    )
    assert sorted(asked) == [("acs5", 2019), ("acs5", 2022)]


def test_take_chart_without_a_record_leaves_the_text_alone() -> None:
    warnings: list[Any] = []
    parts = take_chart(_envelope("Cook County earns 99,999."), [COOK, DUPAGE], warnings)
    assert parts["answer"] == "Cook County earns 99,999."
    assert warnings == []


def test_take_chart_without_a_warnings_list_still_replaces_the_text() -> None:
    parts = take_chart(_envelope("Cook County earns 99,999."), [COOK, DUPAGE], None, _record())
    assert "99,999" not in parts["answer"]
    assert parts["answer"].startswith("Median household income: 76,000")


def test_take_chart_warns_only_when_it_replaced_the_text() -> None:
    kept: list[Any] = []
    parts = take_chart(_envelope("Two counties compared."), [COOK, DUPAGE], kept, _record())
    assert kept == []
    assert parts["answer"].startswith("Two counties compared.\n\n")
    replaced: list[Any] = []
    take_chart(_envelope("Cook County earns 99,999."), [COOK, DUPAGE], replaced, _record())
    assert [item.code for item in replaced] == ["answer_figures_unverified"]
    assert "99,999" in replaced[0].detail


@pytest.mark.parametrize("fenced", [False, True], ids=["bare_json", "fenced_json"])
def test_take_chart_checks_the_text_inside_the_envelope(fenced: bool) -> None:
    sent = _envelope("Two counties compared.")
    if fenced:
        sent = f"```json\n{sent}\n```"
    parts = take_chart(sent, [COOK, DUPAGE], [], _record())
    assert parts["answer"].startswith("Two counties compared.\n\nMedian household income: 76,000")
    assert "```" not in parts["answer"]
    assert '"answer"' not in parts["answer"]


def test_take_chart_checks_a_reply_that_is_not_json() -> None:
    warnings: list[Any] = []
    parts = take_chart("Cook County earns 99,999.", [COOK, DUPAGE], warnings, _record())
    assert "99,999" not in parts["answer"]
    assert [item.code for item in warnings] == ["answer_figures_unverified"]


def test_take_chart_after_a_failed_fetch_keeps_a_clean_text_and_replaces_a_figure() -> None:
    warnings: list[Any] = []
    clean = _envelope("Fetch failed; no estimates available.")
    assert take_chart(clean, [], warnings, _record())["answer"] == (
        "Fetch failed; no estimates available."
    )
    assert warnings == []
    parts = take_chart(_envelope("About 5,000 people live there."), [], warnings, _record())
    assert parts["answer"] == figures.NO_FIGURES
    assert [item.code for item in warnings] == ["answer_figures_unverified"]


def test_the_models_own_chart_spec_survives_when_the_text_is_replaced() -> None:
    chart = {"type": "bar", "x": "geography", "y": "estimate", "title": "Income", "show_moe": True}
    parts = take_chart(_envelope("Cook County earns 99,999.", chart), [COOK, DUPAGE], [], _record())
    assert "99,999" not in parts["answer"]
    assert parts["chart"] is not None
    assert parts["chart"].title == "Income"
