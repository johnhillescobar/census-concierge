"""Invariant checker: named anti-patterns, key redaction, fail-closed secrets."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from src.ask import ExecutionRecord, _openai_complete, default_tools

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_invariants as inv  # noqa: E402


def test_invariants_name_the_forbidden_patterns() -> None:
    names = [name for name, _ in inv.CHECKS]
    blob = " ".join(names).lower()
    assert "forbidden module names" in blob
    assert "blocking clarification" in blob
    assert "census key in artifacts" in blob
    assert "empty secret defaults" in blob
    assert "budget increases" in {name for name, _ in inv.collect(None)}


def test_manager_module_name_fails_the_check(tmp_path: Path, monkeypatch: Any) -> None:
    api_src = tmp_path / "api" / "src"
    api_src.mkdir(parents=True)
    (api_src / "table_manager.py").write_text("x = 1\n")
    monkeypatch.setattr(inv, "ROOT", tmp_path)
    monkeypatch.setattr(inv, "API_SRC", api_src)
    monkeypatch.setattr(inv, "WEB_SRC", tmp_path / "web" / "src")
    found = inv.check_banned_module_names()
    assert found
    assert "table_manager.py" in found[0].where


def test_clarification_module_fails_the_check(tmp_path: Path, monkeypatch: Any) -> None:
    api_src = tmp_path / "api" / "src"
    api_src.mkdir(parents=True)
    (api_src / "clarification.py").write_text("x = 1\n")
    monkeypatch.setattr(inv, "ROOT", tmp_path)
    monkeypatch.setattr(inv, "API_SRC", api_src)
    monkeypatch.setattr(inv, "WEB_SRC", tmp_path / "web" / "src")
    found = inv.check_no_clarification_layer()
    assert found
    assert "clarification.py" in found[0].where


def test_leaked_census_key_in_evidence_json_fails_the_check(
    tmp_path: Path, monkeypatch: Any
) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "latest.json").write_text(
        '{"url": "https://api.census.gov/data/2024/acs/acs5?get=NAME&key=secretvalue"}\n'
    )
    monkeypatch.setattr(inv, "ROOT", tmp_path)
    monkeypatch.setattr(inv, "EVIDENCE", evidence)
    found = inv.check_census_key_not_in_artifacts()
    assert found
    assert "latest.json" in found[0].where


def test_empty_secret_default_fails_the_check(tmp_path: Path, monkeypatch: Any) -> None:
    api_src = tmp_path / "api" / "src"
    api_src.mkdir(parents=True)
    (api_src / "ask.py").write_text('os.environ.get("CENSUS_API_KEY", "")\n')
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    monkeypatch.setattr(inv, "ROOT", tmp_path)
    monkeypatch.setattr(inv, "API_SRC", api_src)
    monkeypatch.setattr(inv, "SCRIPTS", scripts)
    found = inv.check_no_empty_secret_defaults()
    assert found
    assert "CENSUS_API_KEY" in found[0].message


def test_key_query_outside_census_url_fails_the_check(tmp_path: Path, monkeypatch: Any) -> None:
    api_src = tmp_path / "api" / "src"
    api_src.mkdir(parents=True)
    (api_src / "census_url.py").write_text('pattern = r"[?&]key="\n')
    (api_src / "fetch.py").write_text('url = base + "&key=" + secret\n')
    monkeypatch.setattr(inv, "ROOT", tmp_path)
    monkeypatch.setattr(inv, "API_SRC", api_src)
    found = inv.check_key_attached_only_in_census_url()
    assert found
    assert "fetch.py" in found[0].where
    assert all("census_url.py" not in item.where for item in found)


@pytest.mark.parametrize("value", [None, ""])
def test_missing_census_key_fails_closed(monkeypatch: Any, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    else:
        monkeypatch.setenv("CENSUS_API_KEY", value)
    with pytest.raises(ValueError, match="missing CENSUS_API_KEY"):
        default_tools(ExecutionRecord())


async def test_missing_openai_key_fails_closed(monkeypatch: Any) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="missing OPENAI_API_KEY"):
        await _openai_complete([], [])
