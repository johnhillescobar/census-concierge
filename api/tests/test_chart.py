"""Validated ChartSpec on assemble: roles only, extra fields rejected."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from src.ask import ExecutionRecord, assemble
from src.contract import ChartSpec

AUSTIN = {
    "NAME": "Austin city, Texas",
    "GEO_ID": "1600000US4805000",
    "year": "2024",
    "B25064_001E": "1729",
    "B25064_001M": "14",
}
TEXAS = {
    "NAME": "Texas",
    "GEO_ID": "0400000US48",
    "year": "2024",
    "B25064_001E": "1403",
    "B25064_001M": "4",
}
DENVER_2019 = {
    "NAME": "Denver city, Colorado",
    "GEO_ID": "1600000US0820000",
    "year": "2019",
    "B19013_001E": "100",
    "B19013_001M": "5",
}
DENVER_2024 = {
    "NAME": "Denver city, Colorado",
    "GEO_ID": "1600000US0820000",
    "year": "2024",
    "B19013_001E": "110",
    "B19013_001M": "6",
}
HARRIS = {
    "NAME": "Harris County, Texas",
    "GEO_ID": "0500000US48201",
    "year": "2024",
    "B01003_001E": "4838303",
    "B01003_001M": "123",
}

BAR = {
    "type": "bar",
    "x": "geography",
    "y": "estimate",
    "title": "Median gross rent",
    "show_moe": True,
}
LINE = {
    "type": "line",
    "x": "year",
    "y": "estimate",
    "title": "Median household income",
    "show_moe": True,
}


def _envelope(answer: str, chart: dict | None) -> str:
    return json.dumps({"answer": answer, "chart": chart})


def test_year_series_keeps_a_line_chart() -> None:
    record = ExecutionRecord(rows=[DENVER_2019, DENVER_2024])
    response = assemble(_envelope("Income rose.", LINE), record)
    assert response.answer == "Income rose."
    assert response.chart is not None
    assert response.chart.model_dump() == {**LINE, "series_by": None}
    assert response.chart_unavailable is False
    assert [row["year"] for row in response.rows] == ["2019", "2024"]
    assert response.moe[0]["B19013_001M"] == "5"


def test_two_geographies_keep_a_bar_chart() -> None:
    record = ExecutionRecord(rows=[AUSTIN, TEXAS])
    response = assemble(_envelope("Austin is higher.", BAR), record)
    assert response.chart is not None
    assert response.chart.type == "bar"
    assert response.chart.x == "geography"
    assert response.chart.y == "estimate"
    assert response.chart.show_moe is True
    assert response.chart_unavailable is False
    assert [row["GEO_ID"] for row in response.rows] == [AUSTIN["GEO_ID"], TEXAS["GEO_ID"]]


def test_geography_series_over_years_is_kept() -> None:
    austin_2019 = {**AUSTIN, "year": "2019", "B25064_001E": "1600"}
    texas_2019 = {**TEXAS, "year": "2019", "B25064_001E": "1300"}
    spec = {**LINE, "series_by": "geography", "title": "Rent by place"}
    record = ExecutionRecord(rows=[austin_2019, AUSTIN, texas_2019, TEXAS])
    response = assemble(_envelope("Both rose.", spec), record)
    assert response.chart is not None
    assert response.chart.series_by == "geography"
    assert response.chart.x == "year"
    assert len(response.rows) == 4


def test_variable_series_is_kept() -> None:
    row_2019 = {
        **DENVER_2019,
        "B19013_001E": "100",
        "B19013_001M": "5",
        "B19013_002E": "80",
        "B19013_002M": "4",
    }
    row_2024 = {
        **DENVER_2024,
        "B19013_001E": "110",
        "B19013_001M": "6",
        "B19013_002E": "90",
        "B19013_002M": "5",
    }
    spec = {**LINE, "series_by": "variable", "title": "Two income measures"}
    record = ExecutionRecord(rows=[row_2019, row_2024])
    response = assemble(_envelope("Two measures.", spec), record)
    assert response.chart is not None
    assert response.chart.series_by == "variable"
    assert "B19013_002E" in response.rows[0]


def test_scalar_result_has_no_chart() -> None:
    record = ExecutionRecord(rows=[HARRIS])
    response = assemble(_envelope("Population is 4.8 million.", BAR), record)
    assert response.chart is None
    assert response.chart_unavailable is False
    assert response.answer == "Population is 4.8 million."
    assert response.rows[0]["B01003_001E"] == "4838303"
    assert response.moe[0]["B01003_001M"] == "123"


def test_prose_answer_stays_a_prose_answer() -> None:
    record = ExecutionRecord(rows=[HARRIS])
    response = assemble("Harris County has data.", record)
    assert response.answer == "Harris County has data."
    assert response.chart is None
    assert response.chart_unavailable is False


def test_unknown_chart_type_is_discarded() -> None:
    record = ExecutionRecord(rows=[AUSTIN, TEXAS])
    payload = {**BAR, "type": "scatter"}
    response = assemble(_envelope("Austin is higher.", payload), record)
    assert response.chart is None
    assert response.chart_unavailable is True
    assert response.answer == "Austin is higher."
    assert len(response.rows) == 2
    assert response.moe[0]["B25064_001M"] == "14"


def test_extra_vega_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ChartSpec.model_validate({**BAR, "vega": {"mark": "bar"}})
    record = ExecutionRecord(rows=[AUSTIN, TEXAS])
    response = assemble(_envelope("Austin is higher.", {**BAR, "mark": "bar"}), record)
    assert response.chart is None
    assert response.chart_unavailable is True
    assert [row["GEO_ID"] for row in response.rows] == [AUSTIN["GEO_ID"], TEXAS["GEO_ID"]]


def test_svg_payload_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ChartSpec.model_validate({**BAR, "svg": "<svg onload=alert(1)>"})
    with pytest.raises(ValidationError):
        ChartSpec.model_validate({**BAR, "title": "<svg><script>alert(1)</script></svg>"})
    with pytest.raises(ValidationError):
        ChartSpec.model_validate({**BAR, "show_moe": False})
    record = ExecutionRecord(rows=[AUSTIN, TEXAS])
    urls_before = list(record.rows)
    response = assemble(
        _envelope("Austin is higher.", {**BAR, "html": "<script>alert(1)</script>"}),
        record,
    )
    assert response.chart is None
    assert response.chart_unavailable is True
    assert response.rows[0]["B25064_001E"] == urls_before[0]["B25064_001E"]
    assert response.warnings == []


def test_fenced_json_still_extracts_the_chart() -> None:
    record = ExecutionRecord(rows=[DENVER_2019, DENVER_2024])
    blob = "```json\n" + _envelope("Income rose.", LINE) + "\n```"
    response = assemble(blob, record)
    assert response.answer == "Income rose."
    assert response.chart is not None
    assert response.chart.type == "line"


def test_overlapping_acs5_years_do_not_keep_a_line_chart() -> None:
    earlier = {**DENVER_2019, "year": "2018", "B19013_001E": "90", "B19013_001M": "4"}
    record = ExecutionRecord(
        question="Median household income in Denver in 2018 and 2019",
        rows=[earlier, DENVER_2019],
        vintages=[("acs5", 2018), ("acs5", 2019)],
    )
    response = assemble(_envelope("Income rose.", LINE), record)
    assert "overlapping_vintage" in {item.code for item in response.warnings}
    assert response.chart is None
    assert response.chart_unavailable is False
    assert len(response.rows) == 2
