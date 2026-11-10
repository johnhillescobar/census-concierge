"""Demo harness scoring: answered vs HTTP ok, merge, p95, slice scope."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_demo  # noqa: E402


def _body(**fields: Any) -> dict[str, Any]:
    payload = {
        "answer": "ok",
        "urls": ["https://api.census.gov/data/2024/acs/acs5?get=B01003_001E"],
        "requested_years": [],
        "attempted_years": [],
        "succeeded_years": [],
        "failed_years": [],
        "omitted_years": [],
        "omission_reasons": [],
        "legs": [],
        "rows": [{"B01003_001E": "1"}],
        "moe": [],
        "geoid": "0500000US48201",
        "universe": "Total population",
        "table_id": "B01003",
        "alternatives": [],
        "warnings": [],
    }
    if "url" in fields:
        url = fields.pop("url")
        fields.setdefault("urls", [url] if url else [])
    payload.update(fields)
    return payload


def _root(
    status_code: int, content_type: str, text: str, acao: str | None = None
) -> SimpleNamespace:
    headers = {"content-type": content_type}
    if acao is not None:
        headers["access-control-allow-origin"] = acao
    return SimpleNamespace(
        get=lambda _path: SimpleNamespace(status_code=status_code, headers=headers, text=text)
    )


_VITE_INDEX = '<title>census-concierge</title><div id="root"></div>'


def test_html_index_is_a_served_build() -> None:
    info = run_demo.inspect_served_build(_root(200, "text/html; charset=utf-8", _VITE_INDEX))
    assert run_demo.served_build_ok(info) is True


def test_missing_index_is_not_a_served_build() -> None:
    info = run_demo.inspect_served_build(_root(404, "application/json", '{"detail":"Not Found"}'))
    assert run_demo.served_build_ok(info) is False


def test_json_root_is_not_a_served_build() -> None:
    info = run_demo.inspect_served_build(
        _root(200, "application/json", '{"title":"census-concierge"}')
    )
    assert run_demo.served_build_ok(info) is False


def test_product_name_in_body_is_not_a_served_build() -> None:
    info = run_demo.inspect_served_build(
        _root(
            200,
            "text/html; charset=utf-8",
            '<html><title>Error</title><p>census-concierge</p><div id="root"></div></html>',
        )
    )
    assert run_demo.served_build_ok(info) is False


def test_title_without_root_is_not_a_served_build() -> None:
    info = run_demo.inspect_served_build(
        _root(200, "text/html; charset=utf-8", "<title>census-concierge</title>")
    )
    assert run_demo.served_build_ok(info) is False


def test_cors_header_is_not_a_served_build() -> None:
    info = run_demo.inspect_served_build(
        _root(
            200,
            "text/html; charset=utf-8",
            _VITE_INDEX,
            acao="*",
        )
    )
    assert run_demo.served_build_ok(info) is False


def test_http_ok_is_not_answered() -> None:
    entry = {"id": "q01", "expect_table": "B01003"}
    body = _body(table_id="", url="", rows=[])
    assert run_demo.http_ok(200) is True
    assert run_demo.is_answered(entry, status_code=200, body=body) is False


def test_empty_url_is_not_answered_when_a_table_was_expected() -> None:
    entry = {"id": "t01", "expect_table": "B19013", "expect_warning": "overlapping_vintage"}
    body = _body(
        table_id="B19013",
        url="",
        rows=[],
        warnings=[{"code": "overlapping_vintage", "detail": "overlap"}],
    )
    assert run_demo.is_answered(entry, status_code=200, body=body) is False
    assert run_demo.miss_detail(entry, status_code=200, body=body) == "empty url"


def test_urls_array_scores_as_the_product_url() -> None:
    entry = {"id": "q01", "expect_table": "B01003"}
    body = _body(urls=["https://api.census.gov/data/2019/acs/acs5?get=B01003_001E"])
    assert run_demo.is_answered(entry, status_code=200, body=body) is True
    missing = _body(urls=[], table_id="B01003")
    assert run_demo.is_answered(entry, status_code=200, body=missing) is False
    assert run_demo.miss_detail(entry, status_code=200, body=missing) == "empty url"


def test_ambiguous_place_with_empty_url_is_answered() -> None:
    entry = {"id": "t05", "expect_warning": "ambiguous_place"}
    body = _body(
        table_id="",
        url="",
        rows=[],
        warnings=[{"code": "ambiguous_place", "detail": "several Springfields"}],
    )
    assert run_demo.is_answered(entry, status_code=200, body=body) is True


def test_geography_not_nested_with_empty_url_is_answered() -> None:
    entry = {"id": "t16", "expect_table": "B17001", "expect_warning": "geography_not_nested"}
    body = _body(
        table_id="",
        url="",
        rows=[],
        warnings=[{"code": "geography_not_nested", "detail": "tract does not nest in place"}],
    )
    assert run_demo.is_answered(entry, status_code=200, body=body) is True


def test_median_not_aggregatable_with_empty_url_is_answered() -> None:
    entry = {
        "id": "t17",
        "expect_table": "B19013",
        "expect_warning": "median_not_aggregatable",
    }
    body = _body(
        table_id="",
        url="",
        rows=[],
        warnings=[{"code": "median_not_aggregatable", "detail": "cannot combine medians"}],
    )
    assert run_demo.is_answered(entry, status_code=200, body=body) is True


def test_warning_only_without_url_is_not_answered() -> None:
    entry = {"id": "t03", "expect_warning": "moe_not_significant"}
    body = _body(
        table_id="",
        url="",
        rows=[],
        warnings=[{"code": "moe_not_significant", "detail": "swamped"}],
    )
    assert run_demo.is_answered(entry, status_code=200, body=body) is False
    assert run_demo.miss_detail(entry, status_code=200, body=body) == "empty url"


def test_warning_only_with_url_is_answered() -> None:
    entry = {"id": "t04", "expect_warning": "geography_unsupported"}
    body = _body(
        table_id="",
        url="https://api.census.gov/data/2024/acs/acs5?get=B19013_001E",
        rows=[],
        warnings=[{"code": "geography_unsupported", "detail": "block group"}],
    )
    assert run_demo.is_answered(entry, status_code=200, body=body) is True


def test_a_question_with_no_geography_is_answered_only_by_the_warning_and_no_url() -> None:
    entry = {"id": "t03", "expect_warning": "geography_unsupported", "expect_no_url": True}
    warned = [{"code": "geography_unsupported", "detail": "tract needs state and county"}]
    said = _body(table_id="", url="", rows=[], warnings=warned)
    assert run_demo.is_answered(entry, status_code=200, body=said) is True
    shown = _body(table_id="", rows=[], warnings=warned, urls=["https://api.census.gov/data/x"])
    assert run_demo.is_answered(entry, status_code=200, body=shown) is False
    assert "URL was shown" in run_demo.miss_detail(entry, status_code=200, body=shown)
    # a refusal is a refusal only if nothing was searched: a table, rows or candidates mean it ran
    for ran in (
        _body(table_id="B01003", urls=[], rows=[], warnings=warned),
        _body(table_id="", urls=[], rows=[{"NAME": "x"}], warnings=warned),
        _body(
            table_id="", urls=[], rows=[], warnings=warned, alternatives=[{"table_id": "B01001"}]
        ),
    ):
        assert run_demo.is_answered(entry, status_code=200, body=ran) is False
    silent = _body(table_id="", url="", rows=[], warnings=[])
    assert run_demo.is_answered(entry, status_code=200, body=silent) is False
    assert run_demo.miss_detail(entry, status_code=200, body=silent).startswith("missing warning")


def test_a_golden_question_that_expects_no_url_expects_the_geography_warning() -> None:
    import tomllib

    with (ROOT / "evals" / "golden_questions.toml").open("rb") as handle:
        entries = tomllib.load(handle)["question"]
    no_url = [entry for entry in entries if entry.get("expect_no_url")]
    assert no_url, "the trap that names no geography must be scored as the warning and no URL"
    assert all(entry.get("expect_warning") == "geography_unsupported" for entry in no_url)
    assert all(entry["tier"] == "trap" for entry in no_url)


def test_warning_and_table_without_rows_is_not_answered() -> None:
    entry = {"id": "t01", "expect_table": "B19013", "expect_warning": "overlapping_vintage"}
    body = _body(
        table_id="B19013",
        rows=[],
        warnings=[{"code": "overlapping_vintage", "detail": "overlap"}],
    )
    assert run_demo.is_answered(entry, status_code=200, body=body) is False
    assert run_demo.miss_detail(entry, status_code=200, body=body) == "no rows"


def test_wrong_table_is_not_answered() -> None:
    entry = {"id": "q01", "expect_table": "B01003"}
    assert run_demo.is_answered(entry, status_code=200, body=_body(table_id="B19013")) is False


def test_p95_is_the_tail_not_the_mean() -> None:
    values = [1.0] * 94 + [20.0] * 6
    assert run_demo.percentile(values, 95) == 20.0
    assert sum(values) / len(values) < 3


def test_merge_keeps_retrieval_metrics() -> None:
    existing = {"retrieval_at_10": 0.9, "selector_at_1": 0.875, "misses": ["old"]}
    demo = {
        "answered_rate": 0.72,
        "p95_latency_seconds": 14.1,
        "t_llm": 8.0,
        "t_census_api": 1.2,
        "t_ours": 0.4,
        "prompt_hash": "abc",
        "index_hash": "def",
        "misses": [{"id": "q06"}],
    }
    merged = run_demo.merge_evidence(existing, demo, answered_floor=0.70)
    assert merged["retrieval_at_10"] == 0.9
    assert merged["selector_at_1"] == 0.875
    assert merged["answered_rate"] == 0.72
    assert merged["p95_latency_seconds"] == 14.1
    assert merged["t_llm"] == 8.0
    assert merged["misses"] == ["old"]
    assert merged["demo"]["misses"] == [{"id": "q06"}]


def test_a_first_miss_is_not_promoted_to_the_gated_key() -> None:
    existing = {"retrieval_at_10": 0.9}
    demo = {
        "answered_rate": 0.256,
        "p95_latency_seconds": 14.1,
        "t_llm": 8.0,
        "t_census_api": 1.2,
        "t_ours": 0.4,
        "prompt_hash": "abc",
        "index_hash": "def",
    }
    merged = run_demo.merge_evidence(existing, demo, answered_floor=0.70)
    assert "answered_rate" not in merged
    assert merged["demo"]["answered_rate"] == 0.256
    assert merged["retrieval_at_10"] == 0.9


def test_over_ceiling_p95_stays_in_demo_only() -> None:
    existing = {
        "p95_latency_seconds": 14.164,
        "t_llm": 3.941,
        "t_census_api": 2.755,
        "t_ours": 2.84,
        "retrieval_at_10": 0.9,
    }
    demo = {
        "answered_rate": 0.80,
        "p95_latency_seconds": 31.013,
        "t_llm": 6.048,
        "t_census_api": 4.56,
        "t_ours": 4.013,
        "prompt_hash": "abc",
        "index_hash": "def",
    }
    merged = run_demo.merge_evidence(existing, demo, answered_floor=0.70, p95_ceiling=20.0)
    assert merged["p95_latency_seconds"] == 14.164
    assert merged["t_llm"] == 3.941
    assert merged["demo"]["p95_latency_seconds"] == 31.013


def test_a_regression_from_a_prior_rate_stays_on_the_gated_key() -> None:
    existing = {"answered_rate": 0.80, "retrieval_at_10": 0.9}
    demo = {
        "answered_rate": 0.256,
        "p95_latency_seconds": 14.1,
        "t_llm": 8.0,
        "t_census_api": 1.2,
        "t_ours": 0.4,
        "prompt_hash": "abc",
        "index_hash": "def",
    }
    merged = run_demo.merge_evidence(existing, demo, answered_floor=0.70)
    assert merged["answered_rate"] == 0.256


def test_holdout_is_out_of_scope() -> None:
    entries = [
        {"id": "q01", "tier": "core"},
        {"id": "q23", "tier": "long_tail"},
        {"id": "q24", "tier": "long_tail"},
        {"id": "t08", "tier": "trap"},
        {"id": "t09", "tier": "trap"},
        {"id": "t10", "tier": "trap"},
        {"id": "t15", "tier": "trap"},
        {"id": "h01", "tier": "long_tail", "holdout": True},
    ]
    ids = [entry["id"] for entry in run_demo.select_questions(entries)]
    assert ids == ["q01", "q23", "q24", "t08", "t09", "t10", "t15"]


def test_golden_file_scope_includes_comparison_traps() -> None:
    import tomllib

    with (ROOT / "evals" / "golden_questions.toml").open("rb") as handle:
        entries = tomllib.load(handle)["question"]
    picked = run_demo.select_questions(entries)
    ids = {entry["id"] for entry in picked}
    assert "h01" not in ids
    assert "t09" in ids and "t14" in ids
    assert "t15" in ids and "t18" in ids
    assert "t01" in ids and "t08" in ids
    assert "q23" in ids and "q24" in ids
    assert len(picked) == 62


def test_key_in_a_url_is_a_leak() -> None:
    clean = "https://api.census.gov/data/2024/acs/acs5?get=B01003_001E&for=county:201"
    dirty = clean + "&key=secretvalue"
    assert run_demo.leaks_key(clean) is False
    assert run_demo.leaks_key(dirty) is True
    assert run_demo.leaks_key(clean + "&key=REDACTED") is False
    assert run_demo.leaks_key(json.dumps({"url": dirty})) is True


def _trial(**fields: Any) -> run_demo.Trial:
    payload: dict[str, Any] = {
        "id": "q01",
        "text": "core",
        "tier": "core",
        "repeat": 1,
        "http_ok": True,
        "answered": True,
        "expected_table": "B01003",
        "table_id": "B01003",
        "url": "https://example",
        "warnings": [],
        "latency_s": 1.0,
        "t_llm": 0.5,
        "t_census_api": 0.2,
        "t_ours": 0.3,
        "detail": "",
    }
    payload.update(fields)
    return run_demo.Trial(**payload)


def test_gated_rate_uses_long_tail() -> None:
    trials = [
        _trial(),
        _trial(
            id="q05",
            text="tail",
            tier="long_tail",
            answered=False,
            expected_table="B08301",
            table_id="",
            url="",
            latency_s=2.0,
            t_llm=1.0,
            t_census_api=0.4,
            t_ours=0.6,
            detail="empty url",
        ),
    ]
    summary = run_demo.summarize(trials, repeat=1, prompt="p", index="i")
    assert summary["answered_rate"] == 0.0
    assert summary["overall_answered_rate"] == 0.5
    assert summary["by_tier"]["core"]["answered_rate"] == 1.0
    assert summary["t_llm"] == 0.75
    assert [row["id"] for row in summary["trials"]] == ["q01", "q05"]
    assert summary["trials"][0]["answered"] is True
    assert [row["id"] for row in summary["misses"]] == ["q05"]


def test_core_only_run_does_not_count_as_gated_rate() -> None:
    summary = run_demo.summarize([_trial()], repeat=1, prompt="p", index="i")
    assert summary["answered_rate"] == 0.0
    assert summary["overall_answered_rate"] == 1.0
    assert "long_tail" not in summary["by_tier"]
    assert summary["by_tier"]["core"]["answered_rate"] == 1.0


def test_overall_answered_rate_uses_all_trials() -> None:
    trials = [
        _trial(),
        _trial(
            id="q05",
            text="tail",
            tier="long_tail",
            answered=False,
            expected_table="B08301",
            table_id="",
            url="",
            latency_s=2.0,
            t_llm=1.0,
            t_census_api=0.4,
            t_ours=0.6,
            detail="empty url",
        ),
        _trial(id="t01", text="trap", tier="trap"),
    ]
    summary = run_demo.summarize(trials, repeat=1, prompt="p", index="i")
    assert summary["answered_rate"] == 0.0
    assert summary["overall_answered_rate"] == 0.667


def test_wrong_geography_level_is_not_answered() -> None:
    entry = {"id": "q04", "expect_table": "B17001", "expect_geo_level": "tract"}
    place = "https://api.census.gov/data/2024/acs/acs5?get=B17001_001E&for=place:22000&in=state:26"
    tract = "https://api.census.gov/data/2024/acs/acs5?get=B17001_001E&for=tract:*&in=state:26"
    wrong = _body(table_id="B17001", urls=[place])
    assert run_demo.is_answered(entry, status_code=200, body=wrong) is False
    assert run_demo.miss_detail(entry, status_code=200, body=wrong) == "wrong geography level place"
    assert run_demo.is_answered(entry, status_code=200, body=_body(table_id="B17001", urls=[tract]))
    mixed = _body(table_id="B17001", urls=[tract, place])  # every leg must be at the level
    assert run_demo.is_answered(entry, status_code=200, body=mixed) is False


def test_a_list_of_expected_levels_is_scored_per_leg() -> None:
    entry = {"id": "q23", "expect_table": "B25064", "expect_geo_level": ["place", "state"]}
    base = "https://api.census.gov/data/2024/acs/acs5?get=B25064_001E&for="
    place, state = f"{base}place:05000&in=state:48", f"{base}state:48"
    county = f"{base}county:201&in=state:48"

    def scored(*urls: str) -> bool:
        body = _body(table_id="B25064", urls=list(urls))
        return run_demo.is_answered(entry, status_code=200, body=body)

    assert scored(place, state) is True
    assert scored(state, place, place) is True  # repeated years of one leg are still that leg
    assert scored(place) is False  # a leg that was never fetched
    assert scored(place, county) is False  # a leg fetched at a level nobody expected
    body = _body(table_id="B25064", urls=[place])
    assert (
        run_demo.miss_detail(entry, status_code=200, body=body) == "missing geography level state"
    )


def test_geography_level_is_decoded_from_the_for_clause() -> None:
    url = "https://api.census.gov/data/2024/acs/acs5?get=B19013_001E&for=zip+code+tabulation+area:90210"
    assert run_demo.fetched_level(url) == "zip code tabulation area"
    assert run_demo.fetched_level("https://api.census.gov/data/2024/acs/acs5?get=NAME") == ""


def test_overlapping_calls_in_one_bucket_count_once() -> None:
    clock = run_demo.Clock()
    clock.spans = {"llm": [(0.0, 3.0), (1.0, 2.5), (5.0, 6.0)]}
    assert clock.llm == 4.0


def test_buckets_add_up_without_double_counting() -> None:
    clock = run_demo.Clock()
    clock.spans = {
        "llm": [(0.0, 2.0)],
        "rerank": [(2.0, 5.0)],
        "census": [(6.0, 7.0), (6.5, 7.5)],
    }
    assert clock.seconds("rerank") == 3.0
    assert clock.census == 1.5
    assert clock.seconds() == 6.5
    clock.reset()
    assert clock.seconds() == 0.0


def test_search_split_reaches_the_summary_and_the_record() -> None:
    trials = [_trial(t_rerank=2.0, t_embed=0.2), _trial(t_rerank=4.0, t_embed=0.4)]
    summary = run_demo.summarize(trials, repeat=1, prompt="p", index="i")
    assert summary["t_rerank"] == 3.0
    assert summary["t_embed"] == 0.3
    assert summary["trials"][0]["t_rerank"] == 2.0


class _Reply:
    status_code = 200

    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    def json(self) -> dict[str, Any]:
        return self._body


class _Client:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    def post(self, path: str, json: dict[str, Any]) -> _Reply:
        _ = path, json
        return _Reply(self._body)


def _contract(**fields: Any) -> tuple[bool, bool, bool, bool]:
    entry = {"id": "q05", "text": "t", "tier": "long_tail", "expect_table": "B01003"}
    trial = run_demo._ask(_Client(_body(**fields)), run_demo.Clock(), entry, 1)
    record = run_demo.trial_record(trial)
    return (
        record["has_moe"],
        record["has_geoid"],
        record["has_universe"],
        record["has_alternatives"],
    )


def test_each_trial_records_which_response_contract_fields_the_answer_carried() -> None:
    moe = [{"B01003_001M": "5"}]
    rows = [{"GEO_ID": "0500000US48201", "B01003_001E": "1", "B01003_001M": "5"}]
    full = _contract(rows=rows, moe=moe, universe="Households", alternatives=[])
    assert full == (True, True, True, False)
    bare = _contract(rows=rows, moe=moe, universe="", alternatives=[{"table_id": "B19013"}])
    assert bare[2:] == (False, True)


def test_a_moe_row_with_only_names_is_not_a_margin_of_error() -> None:
    names_only = [{"GEO_ID": "0500000US48201", "NAME": "Harris County, Texas"}]
    assert _contract(moe=names_only)[0] is False


def test_geoid_is_judged_per_row_not_from_the_empty_top_level_field() -> None:
    rows = [{"GEO_ID": "0500000US48201", "B01003_001E": "1"}, {"GEO_ID": "0500000US48203"}]
    assert _contract(rows=rows, geoid="")[1] is True
    assert _contract(rows=[*rows, {"B01003_001E": "3"}], geoid="x")[1] is False


def test_no_rows_is_not_a_geoid() -> None:
    assert _contract(rows=[], geoid="x")[1] is False


def test_a_margin_of_error_counts_when_its_column_was_fetched_even_if_suppressed() -> None:
    from src.vintages import moe_rows

    estimate_only = [{"GEO_ID": "0500000US17031", "NAME": "Cook", "B01001_001E": "5"}]
    with_margin = [{**estimate_only[0], "B01001_001M": "3"}]
    suppressed = [{**estimate_only[0], "B01001_001M": "-555555555"}]
    nulled = [{**estimate_only[0], "B01001_001M": None}]
    assert _contract(rows=estimate_only, moe=moe_rows(estimate_only))[0] is False  # never fetched
    assert _contract(rows=with_margin, moe=moe_rows(with_margin))[0] is True
    assert _contract(rows=suppressed, moe=moe_rows(suppressed))[0] is True  # fetched, then withheld
    assert _contract(rows=nulled, moe=moe_rows(nulled))[0] is True


def test_one_margin_of_error_does_not_cover_a_second_estimate() -> None:
    row = {"GEO_ID": "0500000US17031", "B01001_001E": "5", "B01001_002E": "3", "B01001_001M": "1"}
    assert _contract(rows=[row])[0] is False
    assert _contract(rows=[{**row, "B01001_002M": "1"}])[0] is True


def test_every_row_must_carry_its_margins_and_a_row_with_no_estimate_has_none() -> None:
    full = {"GEO_ID": "1", "B01001_001E": "5", "B01001_001M": "1"}
    assert _contract(rows=[full, {"GEO_ID": "2", "B01001_001E": "4"}])[0] is False
    assert _contract(rows=[full, {"GEO_ID": "2"}])[0] is False
    assert _contract(rows=[full, {**full, "GEO_ID": "2"}])[0] is True


def test_a_run_records_the_head_and_hashes_it_was_scored_under(tmp_path: Path) -> None:
    import metric_compare

    summary = run_demo.summarize([_trial()], repeat=1, prompt="p", index="i")
    stamp = summary["provenance"]
    assert set(stamp) == set(metric_compare.PROVENANCE_KEYS)
    assert len(stamp["head"]) == 40
    saved = tmp_path / "latest.json"
    saved.write_text(json.dumps({"retrieval_at_10": 0.9, "demo": summary}), encoding="utf-8")
    assert metric_compare.load_run(saved).hashes == stamp  # what the comparator reads back


def test_the_recorded_head_is_the_checked_out_head() -> None:
    import subprocess

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=run_demo.ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert run_demo.provenance()["head"] == head


def test_a_provenance_failure_keeps_the_run_with_no_stamp(monkeypatch: pytest.MonkeyPatch) -> None:
    import metric_compare

    def broken() -> dict[str, Any]:
        raise KeyError("question")

    monkeypatch.setattr(metric_compare, "hashes", broken)
    assert run_demo.provenance() == {}
    summary = run_demo.summarize([_trial()], repeat=1, prompt="p", index="i")
    assert summary["provenance"] == {} and summary["trials"]


def test_a_stamp_taken_at_the_start_is_the_one_summarize_records() -> None:
    stamp = {"head": "a" * 40}
    summary = run_demo.summarize([_trial()], repeat=1, prompt="p", index="i", stamp=stamp)
    assert summary["provenance"] == stamp


def test_a_response_with_no_rows_has_no_margin_of_error() -> None:
    assert _contract(rows=[], moe=[{"B01003_001M": "5"}])[0] is False


def test_a_run_whose_checkout_moved_part_way_carries_no_stamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = {"head": "a" * 40, "scorer": "s"}
    monkeypatch.setattr(run_demo, "provenance", lambda: {"head": "a" * 40})
    assert run_demo.unmoved(started) == started
    monkeypatch.setattr(run_demo, "provenance", lambda: {"head": "b" * 40})
    assert run_demo.unmoved(started) == {}
    monkeypatch.setattr(run_demo, "provenance", lambda: {})  # git failed at the end
    assert run_demo.unmoved(started) == {}
