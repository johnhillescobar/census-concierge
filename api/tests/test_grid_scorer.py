"""The multi-parent grid scorer: one wildcard URL per expected parent, rows present."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_grid  # noqa: E402

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
