"""Demo harness scoring: answered vs HTTP ok, merge, p95, slice scope."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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


def test_slice3_and_holdout_are_out_of_scope() -> None:
    entries = [
        {"id": "q01", "tier": "core"},
        {"id": "q23", "tier": "long_tail"},
        {"id": "q24", "tier": "long_tail"},
        {"id": "t08", "tier": "trap"},
        {"id": "t09", "tier": "trap"},
        {"id": "t10", "tier": "trap"},
        {"id": "h01", "tier": "long_tail", "holdout": True},
    ]
    ids = [entry["id"] for entry in run_demo.select_questions(entries)]
    assert ids == ["q01", "q24", "t08"]


def test_golden_file_scope_matches_slice1() -> None:
    import tomllib

    with (ROOT / "evals" / "golden_questions.toml").open("rb") as handle:
        entries = tomllib.load(handle)["question"]
    picked = run_demo.select_questions(entries)
    ids = {entry["id"] for entry in picked}
    assert "h01" not in ids
    assert "t09" not in ids and "t18" not in ids
    assert "t01" in ids and "t08" in ids
    assert "q23" not in ids and "q24" in ids
    assert len(picked) == 51


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
