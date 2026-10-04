"""The multi-parent grid scorer: one wildcard URL per expected parent, rows present."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_grid  # noqa: E402

pytestmark = pytest.mark.usefixtures("gazetteer")

CELL = {"level": "county", "expected_parents": ["Ohio", "Michigan"]}
ROWS = [{"GEO_ID": "x"}]


def _url(code: str, scope: str = "county:*") -> str:
    return f"https://api.census.gov/data/2024/acs/acs5?get=NAME&for={scope}&in=state:{code}"


def _body(*urls: str, rows: list[dict[str, str]] = ROWS) -> dict[str, Any]:
    return {"urls": list(urls), "rows": rows}


def test_one_wildcard_url_per_expected_parent_passes() -> None:
    assert run_grid.cell_passes(CELL, _body(_url("39"), _url("26")))


def test_wrong_parent_set_fails() -> None:
    assert not run_grid.cell_passes(CELL, _body(_url("39"), _url("18")))


def test_missing_rows_fail() -> None:
    assert not run_grid.cell_passes(CELL, _body(_url("39"), _url("26"), rows=[]))


def test_non_wildcard_url_fails() -> None:
    assert not run_grid.cell_passes(CELL, _body(_url("39"), _url("26", "county:001")))


def test_national_url_without_a_parent_fails() -> None:
    bare = "https://api.census.gov/data/2024/acs/acs5?get=NAME&for=county:*"
    assert not run_grid.cell_passes(CELL, _body(bare, _url("26")))


def test_duplicate_parent_fails() -> None:
    cell = {"level": "tract", "expected_parents": ["Cook County", "DuPage County"]}
    same = "https://api.census.gov/data/2024/acs/acs5?get=NAME&for=tract:*&in=state:17+county:031"
    assert not run_grid.cell_passes(cell, _body(same, same))


def _tract_url(state: str, county: str) -> str:
    return (
        "https://api.census.gov/data/2024/acs/acs5?get=NAME"
        f"&for=tract:*&in=state:{state}+county:{county}"
    )


TRACT = {"level": "tract", "expected_parents": ["Cook County", "DuPage County"]}


def test_tract_cell_with_the_named_counties_passes() -> None:
    body = _body(_tract_url("17", "031"), _tract_url("17", "043"))
    assert run_grid.cell_passes(TRACT, body)


def test_tract_cell_with_same_named_counties_in_another_state_fails() -> None:
    body = _body(_tract_url("27", "053"), _tract_url("17", "043"))  # Hennepin MN beside DuPage IL
    assert not run_grid.cell_passes(TRACT, body)


def test_tract_cell_with_counties_the_cell_does_not_name_fails() -> None:
    body = _body(_tract_url("17", "031"), _tract_url("17", "097"))  # Cook and Lake IL
    assert not run_grid.cell_passes(TRACT, body)


def test_tract_cell_with_the_named_counties_in_two_states_fails() -> None:
    cell = {"level": "tract", "expected_parents": ["Marion County", "Hamilton County"]}
    body = _body(_tract_url("18", "097"), _tract_url("39", "061"))  # Marion IN, Hamilton OH
    assert not run_grid.cell_passes(cell, body)


def test_tract_cell_whose_names_fit_two_states_passes_in_either() -> None:
    cell = {"level": "tract", "expected_parents": ["Marion County", "Hamilton County"]}
    indiana = _body(_tract_url("18", "097"), _tract_url("18", "057"))
    ohio = _body(_tract_url("39", "101"), _tract_url("39", "061"))
    assert run_grid.cell_passes(cell, indiana) and run_grid.cell_passes(cell, ohio)


def test_geoid_is_read_from_an_in_clause_with_plain_string_operations() -> None:
    assert run_grid.geoid_of("state:17+county:031") == "17031"
    assert run_grid.geoid_of("state:17") == "17"
