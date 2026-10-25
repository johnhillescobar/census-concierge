"""The URL breadth grid scorer: each check fails on its own defect and only on that one."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import threading
import time
import types
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import url_grid  # noqa: E402

NL = chr(10)
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
    "table_id": "B01001",
    "in_spec": "state:39",
    "expected_geoid": "",
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


def _get_url(count: int) -> str:
    """A URL whose `get` asks for exactly `count` variables."""
    items = ["NAME", "GEO_ID", *(f"B01001_{i:03d}E" for i in range(1, count - 1))]
    return (
        f"https://api.census.gov/data/2024/acs/acs5?get={','.join(items)}&for=county:*&in=state:39"
    )


def test_exactly_fifty_variables_is_within_the_cap() -> None:
    assert url_grid.get_size(_get_url(50)) == 50
    assert _failed(CELL, _body(urls=[_get_url(50)])) == []
    assert _failed(CELL, _body(urls=[_get_url(51)])) == ["cap"]


def test_one_oversize_url_among_several_fails_cap() -> None:
    assert _failed(CELL, _body(urls=[URL, _get_url(51)])) == ["cap"]


def test_get_size_ignores_empty_items_and_a_missing_get() -> None:
    assert (
        url_grid.get_size("https://api.census.gov/data/2024/acs/acs5?get=NAME,&for=county:*") == 1
    )
    assert url_grid.get_size("https://api.census.gov/data/2024/acs/acs5?for=county:*") == 0


def test_chunked_whole_table_passes_each_url_alone_under_the_cap() -> None:
    def chunk(lo: int, hi: int) -> tuple[str, list[dict[str, str]]]:
        names = [f"B01001_{i:03d}{kind}" for i in range(lo, hi) for kind in "EM"]
        get = ",".join(["NAME", "GEO_ID", *names])
        url = f"https://api.census.gov/data/2024/acs/acs5?get={get}&for=county:*&in=state:39"
        return url, [{"GEO_ID": g, "year": "2024", **dict.fromkeys(names, "1")} for g in "ab"]

    (first, rows_a), (second, rows_b) = chunk(1, 16), chunk(16, 31)
    assert url_grid.get_size(first) + url_grid.get_size(second) > url_grid.CAP
    cell = {**CELL, "estimates": 30}
    assert _failed(cell, _body(urls=[first, second], rows=rows_a + rows_b)) == []


def test_urls_mixing_levels_fail_level() -> None:
    assert _failed(CELL, _body(urls=[URL, URL.replace("county:*", "tract:*")])) == ["level"]


def test_a_named_place_url_still_has_its_level() -> None:
    named = URL.replace("county:*", "county:001")
    cell = {**CELL, "scope": "named", "expected_rows": 1, "expected_geoid": "0500000US39001"}
    assert _failed(cell, _body(urls=[named], rows=[_row("0500000US39001")])) == []


def test_ok_leg_with_non_200_status_fails_only_http() -> None:
    assert _failed(CELL, _body(legs=[{"ok": True, "status_code": 204}])) == ["http"]
    assert _failed(CELL, _body(legs=[{"ok": False, "status_code": 200}])) == ["http"]


def test_no_request_legs_fails_only_http() -> None:
    assert _failed(CELL, _body(legs=[])) == ["http"]


def test_extra_geography_fails_only_cardinality() -> None:
    rows = [_row("a"), _row("b"), _row("c")]
    assert _failed(CELL, _body(rows=rows)) == ["cardinality"]


def test_no_rows_fails_every_row_check() -> None:
    expected = {"cardinality", "variables", "em_pairing", "geo_id", "table"}
    assert set(_failed(CELL, _body(rows=[]))) == expected


def test_blank_geo_id_is_not_a_geography() -> None:
    rows = [_row("a"), _row("")]
    assert _failed(CELL, _body(rows=rows)) == ["cardinality", "geo_id"]


def test_margins_do_not_count_as_estimates() -> None:
    assert _failed({**CELL, "estimates": 2}, _body()) == ["variables"]


def test_is_estimate_reads_variable_names() -> None:
    for key in ("B01001_001E", "B19013_001E", "C27001_002E"):
        assert url_grid.is_estimate(key), key
    for key in ("B01001_001M", "B01001_001EA", "B01001_TOTALE", "GEO_ID", "NAME", "year"):
        assert not url_grid.is_estimate(key), key


def test_every_estimate_needs_its_own_margin() -> None:
    rows = [
        {"GEO_ID": g, "B01001_001E": "5", "B01001_001M": "1", "B01001_002E": "7", "year": "2024"}
        for g in ("a", "b")
    ]
    assert _failed({**CELL, "estimates": 2}, _body(rows=rows)) == ["em_pairing"]


def test_unpublished_year_that_was_attempted_still_fails_years() -> None:
    cell = {**CELL, "years": [2019, 2020], "unpublished": [2020]}
    tried = _body(attempted_years=[2019, 2020], omitted_years=[], omission_reasons=[])
    assert _failed(cell, tried) == ["years"]


def test_omitted_year_without_any_reason_fails_years() -> None:
    cell = {**CELL, "years": [2019, 2020], "unpublished": [2020]}
    none = _body(attempted_years=[2019], omitted_years=[2020], omission_reasons=[])
    spaces = _body(attempted_years=[2019], omitted_years=[2020], omission_reasons=["  "])
    assert _failed(cell, none) == ["years"]
    assert _failed(cell, spaces) == ["years"]


def _trial(cell_id: str = "u000", repeat: int = 1, seconds: float = 1.0, **checks: Any) -> dict:
    scored = {**url_grid.score(CELL, _body()), **checks}
    return {
        "id": cell_id,
        "repeat": repeat,
        "checks": scored,
        "passed": url_grid.passed(scored),
        "seconds": seconds,
    }


def test_repeat_multiplies_the_trials_a_final_run_needs() -> None:
    cells = [CELL, {**CELL, "id": "u001"}]
    once = [_trial("u000"), _trial("u001")]
    twice = once + [_trial("u000", 2), _trial("u001", 2)]
    assert url_grid.summarize(cells, once, 2, "abc")["status"] == "PARTIAL"
    final = url_grid.summarize(cells, twice, 2, "abc")
    assert (final["status"], final["expected_trials"]) == ("FINAL", 4)


def test_summary_rates_leave_out_checks_a_cell_does_not_exercise() -> None:
    cells = [CELL, {**CELL, "id": "u001"}]
    summary = url_grid.summarize(cells, [_trial()], 1, "abc")
    assert "years" not in summary["checks"]
    assert summary["checks"]["cap"] == {"rate": 1.0, "n": 1}
    assert summary["pass_rate"] == 1.0


def test_summary_names_each_miss_and_only_its_failed_checks() -> None:
    summary = url_grid.summarize([CELL], [_trial(level=False)], 1, "abc")
    assert summary["misses"] == [{"id": "u000", "repeat": 1, "failed": ["level"]}]


def test_summary_p95_is_the_95th_percentile_trial() -> None:
    trials = [_trial(seconds=float(s)) for s in range(1, 101)]
    summary = url_grid.summarize([CELL], trials, 100, "abc")
    assert (summary["p95_seconds"], summary["max_seconds"]) == (95.0, 100.0)


# --- run(): what lands on disk, with the ask and the Census calls stood in --------------------


class _Asks:
    """Stands in for fastapi's TestClient: records each question and answers from a table."""

    def __init__(self) -> None:
        self.answers: dict[str, Any] = {}
        self.asked: list[str] = []

    def __call__(self, app: object) -> _Asks:
        return self

    def __enter__(self) -> _Asks:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def post(self, path: str, json: dict[str, str]) -> types.SimpleNamespace:
        self.asked.append(json["question"])
        answer = self.answers.get(json["question"], _body())
        if isinstance(answer, BaseException):
            raise answer
        return types.SimpleNamespace(status_code=200, json=lambda: answer)


class _Run:
    def __init__(self, tmp_path: Path, asks: _Asks) -> None:
        self.asks = asks
        self.latest, self.partial = tmp_path / "latest.json", tmp_path / "partial.json"
        self.log = tmp_path / "trials.jsonl"
        self.grid = tmp_path / "grid.toml"
        cells = [{**CELL, "id": f"u00{i}", "question": f"SEALED-QUESTION-{i}"} for i in range(2)]
        self.grid.write_text(url_grid.dump_toml({"generated": {}, "skipped": [], "cell": cells}))
        self.sha = hashlib.sha256(self.grid.read_bytes()).hexdigest()[:12]

    def go(self, **over: Any) -> dict[str, Any]:
        opts = {"repeat": 1, "limit": 0, "batch": 0, "workers": 1, "resume": False, "tag": ""}
        opts |= {"aggregate_only": False, "grid": self.grid, **over}
        assert url_grid.run(argparse.Namespace(**opts)) == 0
        suffix = "-".join(t for t in (opts["tag"], "subset" if opts["limit"] else "") if t)
        final, part = (self.tagged(p, suffix) for p in (self.latest, self.partial))
        return json.loads((final if final.exists() else part).read_text(encoding="utf-8"))

    @staticmethod
    def tagged(path: Path, suffix: str) -> Path:
        return path.with_stem(path.stem + f"-{suffix}") if suffix else path

    def logged(self, cell_id: str, repeat: int = 1, sha: str = "", git: str = "") -> None:
        row = {**_trial(cell_id, repeat), "grid_sha": sha or self.sha}
        row["git_sha"] = git or url_grid.git_sha()
        with self.log.open("a") as handle:
            handle.write(json.dumps(row) + "\n")


@pytest.fixture
def grid_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Run:
    asks = _Asks()
    harness = _Run(tmp_path, asks)
    monkeypatch.setattr(url_grid, "LATEST", harness.latest)
    monkeypatch.setattr(url_grid, "PARTIAL", harness.partial)
    monkeypatch.setattr(url_grid, "LOG", harness.log)
    monkeypatch.setattr("fastapi.testclient.TestClient", asks)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("CENSUS_API_KEY", "x")
    stub = types.ModuleType("src.main")
    stub.app = object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.main", stub)
    return harness


def test_a_partial_run_deletes_the_stale_final_scoreboard(grid_run: _Run) -> None:
    grid_run.latest.write_text('{"status": "FINAL"}')
    summary = grid_run.go(batch=1)
    assert not grid_run.latest.exists()
    assert (summary["status"], summary["trials"]) == ("PARTIAL", 1)
    assert grid_run.partial.exists()


def test_a_complete_run_writes_the_final_scoreboard_and_names_its_grid(grid_run: _Run) -> None:
    summary = grid_run.go()
    assert grid_run.latest.exists() and not grid_run.partial.exists()
    assert (summary["status"], summary["grid_sha"]) == ("FINAL", grid_run.sha)


def test_trials_recorded_against_another_grid_are_neither_skipped_nor_counted(
    grid_run: _Run,
) -> None:
    for cell_id in ("u000", "u001"):
        grid_run.logged(cell_id, sha="otherothergr")
    summary = grid_run.go(resume=True)
    assert len(grid_run.asks.asked) == 2
    assert (summary["status"], summary["trials"]) == ("FINAL", 2)


def test_logged_trials_outside_this_run_are_not_counted(grid_run: _Run) -> None:
    grid_run.logged("u999")  # a cell this grid does not have
    grid_run.logged("u000", repeat=2)  # a repeat this run did not ask for
    summary = grid_run.go(resume=True)
    assert (summary["status"], summary["trials"]) == ("FINAL", 2)


def test_resume_runs_only_the_trials_still_missing(grid_run: _Run) -> None:
    grid_run.logged("u000")
    summary = grid_run.go(resume=True)
    assert grid_run.asks.asked == ["SEALED-QUESTION-1"]
    assert (summary["status"], summary["trials"]) == ("FINAL", 2)


def test_without_resume_the_old_log_is_discarded_and_every_trial_reruns(grid_run: _Run) -> None:
    grid_run.logged("u000")
    grid_run.logged("u001")
    grid_run.go()
    assert len(grid_run.asks.asked) == 2
    assert len(grid_run.log.read_text().splitlines()) == 2


def test_a_crashed_ask_is_recorded_as_a_miss_not_an_aborted_run(grid_run: _Run) -> None:
    grid_run.asks.answers["SEALED-QUESTION-0"] = RuntimeError("boom")
    summary = grid_run.go()
    assert (summary["status"], summary["pass_rate"], summary["crashed"]) == ("FINAL", 0.5, 1)
    assert [miss["id"] for miss in summary["misses"]] == ["u000"]


def test_a_limit_run_is_a_subset_and_never_final(grid_run: _Run) -> None:
    summary = grid_run.go(limit=1)
    assert (summary["status"], summary["trials"]) == ("SUBSET", 1)
    assert not grid_run.latest.exists() and not grid_run.partial.exists()
    assert grid_run.tagged(grid_run.partial, "subset").exists()


def test_aggregate_only_reports_a_miss_count_never_cell_ids(
    grid_run: _Run, capsys: pytest.CaptureFixture[str]
) -> None:
    grid_run.asks.answers["SEALED-QUESTION-0"] = {}
    summary = grid_run.go(aggregate_only=True, tag="sealed")
    shown = capsys.readouterr()
    assert summary["misses"] == 1
    assert "SEALED-QUESTION" not in shown.out + shown.err
    assert "u000" not in shown.out + shown.err


# --- what a place, table and dataset mismatch costs, and what a sealed run may touch ---------


def test_a_different_parent_than_asked_fails_only_geography() -> None:
    other = URL.replace("in=state:39", "in=state:26")
    assert _failed(CELL, _body(urls=[other])) == ["geography"]


def test_a_listing_with_no_parent_when_one_was_asked_fails_geography() -> None:
    assert _failed(CELL, _body(urls=[URL.replace("&in=state:39", "")])) == ["geography"]


def test_a_different_place_than_asked_fails_only_geography() -> None:
    cell = {**CELL, "scope": "named", "expected_rows": 1, "expected_geoid": "0400000US34"}
    right, wrong = [_row("0400000US34")], [_row("0400000US48")]
    assert _failed(cell, _body(rows=right)) == []
    assert _failed(cell, _body(rows=wrong)) == ["geography"]


def test_a_different_table_than_asked_fails_only_table() -> None:
    other = [{**_row(g), "B01002_001E": "5", "B01002_001M": "1"} for g in ("a", "b")]
    assert _failed({**CELL, "table_id": "B01002"}, _body(rows=other)) == ["table"]
    assert _failed(CELL, _body(rows=other)) == ["table"]


def test_a_different_dataset_than_asked_fails_only_dataset() -> None:
    assert _failed({**CELL, "dataset": "acs1"}, _body()) == ["dataset"]


def test_a_published_year_that_was_never_attempted_fails_years() -> None:
    cell = {**CELL, "years": [2019, 2024], "unpublished": []}
    reasoned = _body(attempted_years=[2024], omitted_years=[2019], omission_reasons=["overlap"])
    assert _failed(cell, reasoned) == ["years"]


def test_a_table_missing_from_a_year_of_the_dataset_is_unpublished_there() -> None:
    matrix = {"acs1": {"2018": {"B01001": {}}, "2019": {"B99999": {}}}}
    assert url_grid.unpublished(matrix, "acs1", "B01001", [2018, 2019, 2020]) == [2019, 2020]


class _Census:
    def __init__(self, status: int) -> None:
        self.status = status

    def get(self, url: str) -> types.SimpleNamespace:
        return types.SimpleNamespace(status_code=self.status, json=lambda: [["NAME"], ["x"]])


def test_a_throttled_reference_call_is_an_error_never_an_empty_listing() -> None:
    with pytest.raises(RuntimeError, match="429"):
        url_grid.reference(_Census(429), "k", 2024, "county")  # type: ignore[arg-type]
    assert url_grid.reference(_Census(204), "k", 2024, "county") == []  # type: ignore[arg-type]
    assert url_grid.reference(_Census(200), "k", 2024, "county") == [["x"]]  # type: ignore[arg-type]


def test_a_sealed_run_needs_its_own_tag(grid_run: _Run) -> None:
    with pytest.raises(SystemExit, match="--tag"):
        grid_run.go(aggregate_only=True)


def test_a_sealed_run_leaves_the_visible_baseline_and_log_alone(grid_run: _Run) -> None:
    grid_run.latest.write_text('{"status": "FINAL", "pass_rate": 0.9}')
    grid_run.logged("u000")
    grid_run.go(aggregate_only=True, tag="sealed")
    assert json.loads(grid_run.latest.read_text())["pass_rate"] == 0.9
    assert len(grid_run.log.read_text().splitlines()) == 1


def test_a_smoke_run_leaves_the_recorded_baseline_alone(grid_run: _Run) -> None:
    grid_run.latest.write_text('{"status": "FINAL"}')
    grid_run.go(limit=1)
    assert grid_run.latest.exists()


def test_a_run_without_keys_stops_instead_of_scoring_an_outage(
    grid_run: _Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CENSUS_API_KEY")
    with pytest.raises(SystemExit, match="CENSUS_API_KEY"):
        grid_run.go()
    assert grid_run.asks.asked == []


def test_a_stale_partial_scoreboard_is_deleted_when_a_run_finishes(grid_run: _Run) -> None:
    grid_run.partial.write_text('{"status": "PARTIAL"}')
    grid_run.go()
    assert grid_run.latest.exists() and not grid_run.partial.exists()


def test_a_log_line_cut_short_by_an_interrupt_does_not_stop_a_resume(grid_run: _Run) -> None:
    grid_run.logged("u000")
    with grid_run.log.open("a") as handle:
        handle.write('{"id": "u001", "rep')
    summary = grid_run.go(resume=True)
    assert (summary["status"], summary["trials"]) == ("FINAL", 2)


def test_batches_accumulate_into_one_log_without_resume(grid_run: _Run) -> None:
    grid_run.go(batch=1)
    summary = grid_run.go(batch=1)
    assert (summary["status"], summary["trials"]) == ("FINAL", 2)


def test_each_trial_records_the_commit_it_ran_on(grid_run: _Run) -> None:
    summary = grid_run.go()
    assert summary["git_shas"] == [url_grid.git_sha()]


# --- run control: what a rerun, an interrupt or an old grid may and may not do ---------------


def test_trials_from_another_commit_are_asked_again_not_reused(grid_run: _Run) -> None:
    grid_run.logged("u000", git="oldcommit")
    grid_run.logged("u001", git="oldcommit")
    summary = grid_run.go(batch=2)
    assert len(grid_run.asks.asked) == 2
    assert summary["git_shas"] == [url_grid.git_sha()]


def test_a_duplicated_log_row_is_not_a_second_trial(grid_run: _Run) -> None:
    grid_run.logged("u000")
    grid_run.logged("u000")
    summary = grid_run.go(batch=1)
    assert grid_run.asks.asked == ["SEALED-QUESTION-1"]
    assert (summary["status"], summary["trials"]) == ("FINAL", 2)


def test_a_non_200_answer_is_counted_as_crashed(
    grid_run: _Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    post = grid_run.asks.post

    def throttled(path: str, json: dict[str, str]) -> types.SimpleNamespace:
        post(path, json)
        return types.SimpleNamespace(status_code=429, json=lambda: {})

    monkeypatch.setattr(grid_run.asks, "post", throttled)
    summary = grid_run.go()
    assert (summary["crashed"], summary["pass_rate"]) == (2, 0.0)


def test_zero_repeats_is_refused_not_scored_as_final(grid_run: _Run) -> None:
    with pytest.raises(SystemExit, match="repeat"):
        grid_run.go(repeat=0)


def test_a_grid_from_before_a_cell_field_was_added_is_refused_before_anything_is_deleted(
    grid_run: _Run,
) -> None:
    grid_run.latest.write_text('{"status": "FINAL"}')
    grid_run.grid.write_text(NL.join(["[[cell]]", 'id = "u000"', 'question = "q"']))
    with pytest.raises(SystemExit, match="regenerate"):
        grid_run.go()
    assert grid_run.latest.exists() and grid_run.asks.asked == []


def test_a_sealed_tag_must_say_sealed(grid_run: _Run) -> None:
    with pytest.raises(SystemExit, match="sealed"):
        grid_run.go(aggregate_only=True, tag="private")


def test_a_sealed_run_prints_no_cell_id_and_no_small_bucket(
    grid_run: _Run, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = grid_run.go(aggregate_only=True, tag="sealed")
    shown = capsys.readouterr()
    assert "u000" not in shown.out + shown.err and "u001" not in shown.out + shown.err
    assert summary["by_dimension"] == {}


def test_a_visible_run_keeps_every_dimension_bucket(grid_run: _Run) -> None:
    assert "level=county" in grid_run.go()["by_dimension"]


def test_an_interrupt_does_not_run_the_queued_trials_live(
    grid_run: _Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = threading.Event()
    post = grid_run.asks.post

    def slow(path: str, json: dict[str, str]) -> types.SimpleNamespace:
        if json["question"] == "SEALED-QUESTION-1":
            release.wait(timeout=3)  # the worker is busy here when the interrupt lands
        return post(path, json)

    cells = [{**CELL, "id": f"u00{i}", "question": f"SEALED-QUESTION-{i}"} for i in range(3)]
    grid_run.grid.write_text(url_grid.dump_toml({"generated": {}, "skipped": [], "cell": cells}))
    grid_run.asks.answers["SEALED-QUESTION-0"] = KeyboardInterrupt()
    monkeypatch.setattr(grid_run.asks, "post", slow)
    with pytest.raises(KeyboardInterrupt):
        grid_run.go()
    release.set()
    time.sleep(0.2)
    assert "SEALED-QUESTION-2" not in grid_run.asks.asked


def test_the_table_drawn_for_a_year_series_exists_in_one_of_its_years() -> None:
    matrix = {"acs1": {"2019": {"B2": {}}, "2020": {"B2": {}}}}
    rng = random.Random(0)
    drawn = {url_grid.table_for(rng, ["B1", "B2"], matrix, "acs1", [2019]) for _ in range(20)}
    assert drawn == {"B2"}
    assert url_grid.table_for(rng, ["B1"], matrix, "acs1", []) == "B1"


def test_a_flaky_reference_call_is_retried_before_it_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(url_grid.time, "sleep", lambda _s: None)
    statuses = iter([503, 429, 200])

    class Flaky:
        def get(self, url: str) -> types.SimpleNamespace:
            return types.SimpleNamespace(status_code=next(statuses), json=lambda: [["NAME"], ["x"]])

    assert url_grid.reference(Flaky(), "k", 2024, "county") == [["x"]]  # type: ignore[arg-type]


def test_git_sha_marks_uncommitted_code_as_dirty(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(cmd: list[str], **_kw: Any) -> types.SimpleNamespace:
        code = 1 if "diff" in cmd and fake.dirty else 0
        return types.SimpleNamespace(stdout="abc123\n", returncode=code)

    monkeypatch.setattr(url_grid.subprocess, "run", fake)
    fake.dirty = False  # type: ignore[attr-defined]
    assert url_grid.git_sha() == "abc123"
    fake.dirty = True  # type: ignore[attr-defined]
    assert url_grid.git_sha() == "abc123+dirty"


def test_two_rows_for_one_trial_do_not_stand_in_for_a_missing_trial() -> None:
    cells = [CELL, {**CELL, "id": "u001"}]
    once = _trial("u000")
    assert url_grid.summarize(cells, [once, once], 1, "abc")["status"] == "PARTIAL"
