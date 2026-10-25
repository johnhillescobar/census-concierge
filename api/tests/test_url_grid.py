"""The URL breadth grid scorer: each check fails on its own defect and only on that one."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import url_grid  # noqa: E402

CELL: dict[str, Any] = {
    "id": "u000",
    "level": "county",
    "depth": 1,
    "scope": "listing",
    "var_count": "1",
    "time": "latest",
    "dataset": "acs5",
    "estimates": 1,
    "expected_rows": 2,
    "fail_closed": False,
    "years": [],
    "unpublished": [],
}
URL = "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B01001_001E,B01001_001M&for=county:*&in=state:39"


def _row(geoid: str, **extra: str | None) -> dict[str, str | None]:
    return {
        "GEO_ID": geoid,
        "B01001_001E": "5",
        "B01001_001M": "1",
        "year": "2024",
        **extra,
    }


def _body(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "urls": [URL],
        "legs": [{"ok": True, "status_code": 200}],
        "rows": [_row("0500000US39001"), _row("0500000US39003")],
        "attempted_years": [2024],
        "omitted_years": [],
        "omission_reasons": [],
    }
    return {**body, **over}


def _failed(cell: dict[str, Any], body: dict[str, Any]) -> list[str]:
    return [k for k, v in url_grid.score(cell, body).items() if v is False]


def test_a_sound_answer_fails_no_check() -> None:
    assert _failed(CELL, _body()) == []
    assert url_grid.passed(url_grid.score(CELL, _body()))


def test_url_over_the_fifty_variable_cap_fails_only_cap() -> None:
    wide = URL.replace("B01001_001E", ",".join(f"B01001_{i:03d}E" for i in range(1, 52)))
    assert _failed(CELL, _body(urls=[wide])) == ["cap"]


def test_group_counts_as_one_variable() -> None:
    assert url_grid.get_size(URL.replace("B01001_001E,B01001_001M", "group(B01001)")) == 3


def test_wrong_level_fails_only_level() -> None:
    assert _failed(CELL, _body(urls=[URL.replace("county:*", "tract:*")])) == ["level"]


def test_failed_leg_fails_only_http() -> None:
    legs = [{"ok": True, "status_code": 200}, {"ok": False, "status_code": 400}]
    assert _failed(CELL, _body(legs=legs)) == ["http"]


def test_missing_geography_fails_only_cardinality() -> None:
    assert _failed(CELL, _body(rows=[_row("0500000US39001")])) == ["cardinality"]


def test_cardinality_is_counted_per_year() -> None:
    rows = [_row("a"), _row("b"), _row("a", year="2023")]
    assert _failed(CELL, _body(rows=rows)) == ["cardinality"]


def test_chunked_urls_merge_into_one_geography_row_count() -> None:
    rows = [_row("a"), _row("b"), _row("a"), _row("b")]
    assert _failed(CELL, _body(rows=rows)) == []


def test_fewer_estimates_than_asked_fails_only_variables() -> None:
    assert _failed({**CELL, "estimates": 24}, _body()) == ["variables"]


def test_estimate_without_margin_fails_only_em_pairing() -> None:
    rows = [{"GEO_ID": g, "B01001_001E": "5", "year": "2024"} for g in ("a", "b")]
    assert _failed(CELL, _body(rows=rows)) == ["em_pairing"]


def test_row_without_geo_id_fails_geo_id() -> None:
    rows = [_row("a"), _row("")]
    assert "geo_id" in _failed(CELL, _body(rows=rows))


def test_unpublished_year_must_be_omitted_with_a_reason() -> None:
    cell = {**CELL, "years": [2019, 2020], "unpublished": [2020]}
    silent = _body(attempted_years=[2019], omitted_years=[], omission_reasons=[])
    blank = _body(attempted_years=[2019], omitted_years=[2020], omission_reasons=[""])
    named = _body(attempted_years=[2019], omitted_years=[2020], omission_reasons=["gap_2020"])
    assert _failed(cell, silent) == ["years"]
    assert _failed(cell, blank) == ["years"]
    assert _failed(cell, named) == []


def test_requested_year_nobody_accounted_for_fails_years() -> None:
    cell = {**CELL, "years": [2019, 2021]}
    assert _failed(cell, _body(attempted_years=[2019])) == ["years"]


def test_unpublished_level_passes_only_by_returning_no_rows() -> None:
    cell = {**CELL, "fail_closed": True, "expected_rows": 0}
    assert url_grid.passed(url_grid.score(cell, _body(rows=[], legs=[])))
    assert _failed(cell, _body()) == ["cardinality"]


def test_no_url_at_all_fails_cap_and_level() -> None:
    assert {"cap", "level"} <= set(_failed(CELL, _body(urls=[])))


def test_run_with_missing_trials_is_never_final() -> None:
    cells = [CELL, {**CELL, "id": "u001"}]
    trial = {"id": "u000", "repeat": 1, "checks": url_grid.score(CELL, _body()), "passed": True}
    trial["seconds"] = 1.0
    partial = url_grid.summarize(cells, [trial], 1, "abc")
    assert (partial["status"], partial["complete"]) == ("PARTIAL", False)
    both = [trial, {**trial, "id": "u001"}]
    assert url_grid.summarize(cells, both, 1, "abc")["status"] == "FINAL"
    assert url_grid.summarize(cells, both, 1, "abc", subset=True)["status"] == "SUBSET"
