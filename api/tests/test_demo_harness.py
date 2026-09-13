"""Demo harness scoring: answered vs HTTP ok, merge, p95, slice scope."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_demo  # noqa: E402


def _body(**fields: Any) -> dict[str, Any]:
    payload = {
        "answer": "ok",
        "url": "https://api.census.gov/data/2024/acs/acs5?get=B01003_001E",
        "rows": [{"B01003_001E": "1"}],
        "moe": [],
        "geoid": "0500000US48201",
        "universe": "Total population",
        "table_id": "B01003",
        "alternatives": [],
        "warnings": [],
    }
    payload.update(fields)
    return payload


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


def test_ambiguous_place_with_empty_url_is_answered() -> None:
    entry = {"id": "t05", "expect_warning": "ambiguous_place"}
    body = _body(
        table_id="",
        url="",
        rows=[],
        warnings=[{"code": "ambiguous_place", "detail": "several Springfields"}],
    )
    assert run_demo.is_answered(entry, status_code=200, body=body) is True


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
    merged = run_demo.merge_evidence(existing, demo)
    assert merged["retrieval_at_10"] == 0.9
    assert merged["selector_at_1"] == 0.875
    assert merged["answered_rate"] == 0.72
    assert merged["p95_latency_seconds"] == 14.1
    assert merged["t_llm"] == 8.0
    assert merged["misses"] == ["old"]
    assert merged["demo"]["misses"] == [{"id": "q06"}]


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


def test_gated_rate_uses_long_tail() -> None:
    trials = [
        run_demo.Trial(
            id="q01",
            text="core",
            tier="core",
            repeat=1,
            http_ok=True,
            answered=True,
            expected_table="B01003",
            table_id="B01003",
            url="https://example",
            warnings=[],
            latency_s=1.0,
            t_llm=0.5,
            t_census_api=0.2,
            t_ours=0.3,
            detail="",
        ),
        run_demo.Trial(
            id="q05",
            text="tail",
            tier="long_tail",
            repeat=1,
            http_ok=True,
            answered=False,
            expected_table="B08301",
            table_id="",
            url="",
            warnings=[],
            latency_s=2.0,
            t_llm=1.0,
            t_census_api=0.4,
            t_ours=0.6,
            detail="empty url",
        ),
    ]
    summary = run_demo.summarize(trials, repeat=1, prompt="p", index="i")
    assert summary["answered_rate"] == 0.0
    assert summary["by_tier"]["core"]["answered_rate"] == 1.0
    assert summary["t_llm"] == 0.75
