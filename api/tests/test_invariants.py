"""Invariant checker: named anti-patterns, key redaction, fail-closed secrets."""

from __future__ import annotations

import re
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
    assert "mandatory catalogs" in blob
    assert "budget increases" in {name for name, _ in inv.collect(None)}


def test_invariants_print_every_named_pattern(capsys: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(sys, "argv", ["check_invariants.py"])
    assert inv.main() == 0
    out = capsys.readouterr().out
    for name, _ in inv.CHECKS:
        assert re.search(rf"ok\s+{re.escape(name)}", out)


@pytest.mark.parametrize("filename", ["table_manager.py", "table_manager.js"])
def test_manager_module_name_fails_the_check(
    tmp_path: Path, monkeypatch: Any, filename: str
) -> None:
    api_src = tmp_path / "api" / "src"
    api_src.mkdir(parents=True)
    (api_src / filename).write_text("x = 1\n")
    monkeypatch.setattr(inv, "ROOT", tmp_path)
    monkeypatch.setattr(inv, "API_SRC", api_src)
    monkeypatch.setattr(inv, "WEB_SRC", tmp_path / "web" / "src")
    found = inv.check_banned_module_names()
    assert found
    assert filename in found[0].where


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


def test_clarification_directory_fails_the_check(tmp_path: Path, monkeypatch: Any) -> None:
    api_src = tmp_path / "api" / "src"
    nested = api_src / "clarification"
    nested.mkdir(parents=True)
    (nested / "flow.py").write_text("x = 1\n")
    monkeypatch.setattr(inv, "ROOT", tmp_path)
    monkeypatch.setattr(inv, "API_SRC", api_src)
    monkeypatch.setattr(inv, "WEB_SRC", tmp_path / "web" / "src")
    found = inv.check_no_clarification_layer()
    assert found
    assert any("clarification" in item.where for item in found)


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


def test_redacted_prefix_in_evidence_json_fails_the_check(tmp_path: Path, monkeypatch: Any) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "latest.json").write_text(
        '{"url": "https://api.census.gov/data/2024/acs/acs5?get=NAME&key=REDACTEDlive-token"}\n'
    )
    monkeypatch.setattr(inv, "ROOT", tmp_path)
    monkeypatch.setattr(inv, "EVIDENCE", evidence)
    found = inv.check_census_key_not_in_artifacts()
    assert found
    assert "latest.json" in found[0].where


def test_missing_agent_catalog_fails_the_check(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(inv, "ROOT", tmp_path)
    found = inv.check_mandatory_catalogs()
    assert {item.where for item in found} == {
        "docs/requirements.md",
        "docs/ask-path.md",
        "docs/retrieval.md",
        "docs/slices.md",
    }


def test_present_agent_catalogs_pass_the_check() -> None:
    assert inv.check_mandatory_catalogs() == []


def test_exact_redacted_key_in_evidence_json_passes_the_check(
    tmp_path: Path, monkeypatch: Any
) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "latest.json").write_text(
        '{"url": "https://api.census.gov/data/2024/acs/acs5?get=NAME&key=REDACTED"}\n'
    )
    monkeypatch.setattr(inv, "ROOT", tmp_path)
    monkeypatch.setattr(inv, "EVIDENCE", evidence)
    assert inv.check_census_key_not_in_artifacts() == []


@pytest.mark.parametrize("secret", ["CENSUS_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"])
def test_empty_secret_default_fails_the_check(
    tmp_path: Path, monkeypatch: Any, secret: str
) -> None:
    api_src = tmp_path / "api" / "src"
    api_src.mkdir(parents=True)
    (api_src / "ask.py").write_text(f'os.environ.get("{secret}", "")\n')
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    monkeypatch.setattr(inv, "ROOT", tmp_path)
    monkeypatch.setattr(inv, "API_SRC", api_src)
    monkeypatch.setattr(inv, "SCRIPTS", scripts)
    found = inv.check_no_empty_secret_defaults()
    assert found
    assert "ask.py" in found[0].where


def test_key_query_outside_census_url_fails_the_check(tmp_path: Path, monkeypatch: Any) -> None:
    api_src = tmp_path / "api" / "src"
    api_src.mkdir(parents=True)
    (api_src / "census_url.py").write_text('attached = "&key="\n')
    (api_src / "fetch.py").write_text('url = base + "&KEY=" + secret\n')
    monkeypatch.setattr(inv, "ROOT", tmp_path)
    monkeypatch.setattr(inv, "API_SRC", api_src)
    found = inv.check_key_attached_only_in_census_url()
    wheres = [item.where for item in found]
    assert any("fetch.py" in where for where in wheres)
    assert all("census_url.py" not in where for where in wheres)


@pytest.mark.parametrize("value", [None, ""])
def test_missing_census_key_fails_closed(monkeypatch: Any, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    else:
        monkeypatch.setenv("CENSUS_API_KEY", value)
    with pytest.raises(ValueError, match="missing CENSUS_API_KEY"):
        default_tools(ExecutionRecord())


@pytest.mark.parametrize("value", [None, ""])
async def test_missing_openai_key_fails_closed(monkeypatch: Any, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OPENAI_API_KEY", value)
    with pytest.raises(ValueError, match="missing OPENAI_API_KEY"):
        await _openai_complete([], [])


def test_regex_call_sites_are_counted_without_a_regex() -> None:
    source = (
        "import re\nA = re.compile('x')\nre.search('a', 'b')\nnot_re.compile('y')\nre.escape('z')\n"
    )
    assert inv._regex_calls(source) == 2


def test_a_file_that_gains_a_regex_fails_the_check(monkeypatch: Any) -> None:
    monkeypatch.setattr(inv, "_regex_counts_at", lambda ref: {"api/src/a.py": 1})
    monkeypatch.setattr(inv, "_regex_counts_now", lambda: {"api/src/a.py": 2})
    assert [v.where for v in inv.check_no_new_regex("main")] == ["api/src/a.py"]


def test_a_new_file_with_a_regex_fails_the_check(monkeypatch: Any) -> None:
    monkeypatch.setattr(inv, "_regex_counts_at", lambda ref: {})
    monkeypatch.setattr(inv, "_regex_counts_now", lambda: {"api/src/new.py": 1})
    assert [v.where for v in inv.check_no_new_regex("main")] == ["api/src/new.py"]


def test_removing_a_regex_passes_the_check(monkeypatch: Any) -> None:
    monkeypatch.setattr(inv, "_regex_counts_at", lambda ref: {"api/src/a.py": 3})
    monkeypatch.setattr(inv, "_regex_counts_now", lambda: {"api/src/a.py": 1})
    assert inv.check_no_new_regex("main") == []


def test_regex_imported_by_name_or_under_an_alias_is_counted() -> None:
    assert inv._regex_calls("from re import sub, compile\n") == 2
    assert inv._regex_calls("import re as rx\nrx.search('a', 'b')\n") == 1
    assert inv._regex_calls("from re import escape\n") == 0


def test_importing_another_regex_engine_or_a_star_import_is_counted() -> None:
    assert inv._regex_calls("import regex\n") == 1
    assert inv._regex_calls("import regex as rx\nrx.compile('a')\n") == 2
    assert inv._regex_calls("from re import *\n") == 1


def _budgets(tmp_path: Path, monkeypatch: Any, body: str) -> None:
    (tmp_path / "budgets.toml").write_text(body, encoding="utf-8")
    monkeypatch.setattr(inv, "ROOT", tmp_path)


def test_a_limit_that_disagrees_with_its_last_log_line_fails_the_check(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _budgets(
        tmp_path,
        monkeypatch,
        "[size]\napi_src_loc = 4400\n# --- budget change log ---\n"
        "# 2026-10-02  [size] api_src_loc  4300 -> 4340  CC-103\n",
    )
    found = inv.check_budget_log_matches_values()
    assert [v.where for v in found] == ["budgets.toml [size] api_src_loc"]
    assert "4400" in found[0].message and "4340" in found[0].message


def test_a_limit_that_matches_its_last_log_line_passes_the_check(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _budgets(
        tmp_path,
        monkeypatch,
        "[size]\napi_src_loc = 4340\n# --- budget change log ---\n"
        "# 2026-10-02  [size] api_src_loc  4300 -> 4340  CC-103\n",
    )
    assert inv.check_budget_log_matches_values() == []


def test_only_the_last_log_line_for_a_field_counts(tmp_path: Path, monkeypatch: Any) -> None:
    _budgets(
        tmp_path,
        monkeypatch,
        "[size]\napi_src_loc = 4250\n# --- budget change log ---\n"
        "# 2026-09-25  [size] api_src_loc 4000 -> 4100  a\n"
        "# 2026-09-29  [size] api_src_loc 4100 -> 4250  b\n",
    )
    assert inv.check_budget_log_matches_values() == []


def test_two_log_entries_on_one_line_are_both_read(tmp_path: Path, monkeypatch: Any) -> None:
    _budgets(
        tmp_path,
        monkeypatch,
        "[size]\nweb_src_loc = 9998\napi_src_loc = 9999\n# --- budget change log ---\n"
        "# 2026-09-27  [size] web_src_loc 3010 -> 3100  reason"
        "# 2026-09-29  [size] api_src_loc 4100 -> 4250  b\n",
    )
    assert {v.where for v in inv.check_budget_log_matches_values()} == {
        "budgets.toml [size] web_src_loc",
        "budgets.toml [size] api_src_loc",
    }


def test_a_limit_change_the_check_cannot_read_fails_the_check(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _budgets(
        tmp_path,
        monkeypatch,
        "[size]\napi_src_loc = 4340\n# --- budget change log ---\n"
        "# 2026-10-02  [size] api_src_loc 4300->4340  CC-103\n",
    )
    assert [v.where for v in inv.check_budget_log_matches_values()] == ["budgets.toml change log"]


def test_the_budget_log_leakage_and_exemption_checks_are_registered() -> None:
    assert {"budget log matches values", "eval phrasing in api/src"} <= {
        name for name, _ in inv.CHECKS
    }
    assert "new exemptions" in {name for name, _ in inv.collect(None)}


def test_collect_runs_the_exemption_check_when_given_a_base(monkeypatch: Any) -> None:
    monkeypatch.setattr(inv, "_budgets_at", lambda ref: None)
    monkeypatch.setattr(inv, "_regex_counts_at", lambda ref: None)
    monkeypatch.setattr(inv, "check_no_new_exemptions", lambda base: [inv.Violation("x", "y")])
    assert dict(inv.collect("main"))["new exemptions"]


def _base_has(monkeypatch: Any, texts: dict[str, str]) -> None:
    monkeypatch.setattr(inv, "_text_at", lambda ref, rel: texts.get(rel))


def test_a_waiver_added_since_the_base_fails_the_check(tmp_path: Path, monkeypatch: Any) -> None:
    head = "[size]\nx = 1\n# --- budget change log ---\n"
    _budgets(
        tmp_path,
        monkeypatch,
        head + "# 2026-10-04  [waiver] p95_latency_seconds RUN 21.7 CC-113 why\n",
    )
    _base_has(monkeypatch, {"budgets.toml": head})
    found = inv.check_no_new_exemptions("origin/main")
    assert [v.where for v in found] == ["budgets.toml"]
    assert "[waiver]" in found[0].message


def test_a_leakage_baseline_entry_added_since_the_base_fails_the_check(
    tmp_path: Path, monkeypatch: Any
) -> None:
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "leakage_baseline.txt").write_text(
        "gram4|a b c d|api/src/x.py  # r\ngram4|e f g h|api/src/x.py  # r\n", encoding="utf-8"
    )
    monkeypatch.setattr(inv, "ROOT", tmp_path)
    _base_has(monkeypatch, {"evals/leakage_baseline.txt": "gram4|a b c d|api/src/x.py  # r\n"})
    found = inv.check_no_new_exemptions("origin/main")
    assert [v.where for v in found] == ["evals/leakage_baseline.txt"]
    assert "e f g h" in found[0].message


def test_exemptions_already_at_the_base_pass_the_check(tmp_path: Path, monkeypatch: Any) -> None:
    text = (
        "[size]\nx = 1\n# --- budget change log ---\n# d  [waiver] p95_latency_seconds R 1 CC-1 w\n"
    )
    _budgets(tmp_path, monkeypatch, text)
    _base_has(monkeypatch, {"budgets.toml": text})
    assert inv.check_no_new_exemptions("origin/main") == []


def test_an_exemption_file_that_does_not_exist_at_the_base_is_skipped(
    tmp_path: Path, monkeypatch: Any
) -> None:
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "leakage_baseline.txt").write_text(
        "gram4|a b c d|api/src/x.py  # r\n", encoding="utf-8"
    )
    monkeypatch.setattr(inv, "ROOT", tmp_path)
    _base_has(monkeypatch, {})
    assert inv.check_no_new_exemptions("origin/main") == []


def test_a_renamed_budget_field_is_checked_under_its_new_name(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _budgets(
        tmp_path,
        monkeypatch,
        "[quality]\nnew_min = 0.60\n# --- budget change log ---\n"
        "# 2026-09-11  [quality] old_min 0.95 -> new_min 0.50  renamed\n",
    )
    assert [v.where for v in inv.check_budget_log_matches_values()] == [
        "budgets.toml [quality] new_min"
    ]


def _leak_repo(
    tmp_path: Path,
    monkeypatch: Any,
    question: str,
    sources: dict[str, str],
    baseline: str = "",
) -> None:
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "q.toml").write_text(
        f'[[question]]\nid = "q1"\ntext = "{question}"\n', encoding="utf-8"
    )
    if baseline:
        (tmp_path / "evals" / "leakage_baseline.txt").write_text(baseline, encoding="utf-8")
    api_src = tmp_path / "api" / "src"
    api_src.mkdir(parents=True)
    for name, text in sources.items():
        (api_src / name).write_text(text, encoding="utf-8")
    monkeypatch.setattr(inv, "ROOT", tmp_path)
    monkeypatch.setattr(inv, "API_SRC", api_src)


INCOME_Q = "Median household income for every block group in Wayne County"


def test_a_four_word_eval_phrase_in_a_string_literal_fails_the_check(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _leak_repo(
        tmp_path,
        monkeypatch,
        INCOME_Q,
        {"tools.py": 'HINT = "show median household income for every county"\n'},
    )
    found = inv.check_no_eval_phrasing_in_api_src()
    assert found
    assert "gram4" in found[0].message and found[0].where.startswith("api/src/tools.py:1")


def test_a_four_word_eval_phrase_in_a_comment_fails_the_check(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _leak_repo(
        tmp_path,
        monkeypatch,
        INCOME_Q,
        {"geo.py": "# show median household income for every county\nx = 1\n"},
    )
    assert any("gram4" in v.message for v in inv.check_no_eval_phrasing_in_api_src())


def test_two_eval_words_inside_a_regex_fail_the_check_across_a_word_boundary(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _leak_repo(
        tmp_path,
        monkeypatch,
        "Number of cell phones in Denver since 2017",
        {"vintages.py": 'import re\nPIN = re.compile(r"\\bcell phones\\b")\n'},
    )
    found = inv.check_no_eval_phrasing_in_api_src()
    assert [("regex2" in v.message) for v in found] == [True]


def test_the_same_two_words_outside_a_regex_do_not_fail_the_check(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _leak_repo(
        tmp_path,
        monkeypatch,
        "Number of cell phones in Denver since 2017",
        {"vintages.py": 'HINT = "cell phones"\n'},
    )
    assert inv.check_no_eval_phrasing_in_api_src() == []


def test_a_longer_phrase_stands_for_the_shorter_ones_inside_it(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _leak_repo(
        tmp_path,
        monkeypatch,
        "Compare median gross rent in Austin to the Texas average",
        {"vintages.py": 'import re\nPIN = re.compile(r"median gross rent")\n'},
    )
    found = inv.check_no_eval_phrasing_in_api_src()
    assert len(found) == 1 and "median gross rent" in found[0].message


def test_a_place_in_a_tool_description_fails_the_check_but_not_elsewhere(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _leak_repo(
        tmp_path,
        monkeypatch,
        "Compare Springfield with Dayton",
        {"tools.py": 'DESC = "e.g. Springfield"\n', "geo.py": 'STATE = "Springfield"\n'},
    )
    found = inv.check_no_eval_phrasing_in_api_src()
    assert [v.where.split(":")[0] for v in found] == ["api/src/tools.py"]
    assert "place" in found[0].message


def test_a_baselined_hit_passes_and_a_new_hit_still_fails(tmp_path: Path, monkeypatch: Any) -> None:
    _leak_repo(
        tmp_path,
        monkeypatch,
        "Compare Springfield with Dayton",
        {"tools.py": 'DESC = "e.g. Springfield"\n'},
        baseline="place|springfield|api/src/tools.py  # known\n",
    )
    assert inv.check_no_eval_phrasing_in_api_src() == []
    (tmp_path / "api" / "src" / "prompts.py").write_text('P = "try Dayton"\n', encoding="utf-8")
    found = inv.check_no_eval_phrasing_in_api_src()
    assert [v.where.split(":")[0] for v in found] == ["api/src/prompts.py"]


def test_a_pattern_given_by_keyword_or_inside_an_f_string_is_read_as_a_regex(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _leak_repo(
        tmp_path,
        monkeypatch,
        "Number of cell phones in Denver since 2017",
        {
            "a.py": 'import re\nre.search(pattern=r"\\bcell phones\\b", string=q)\n',
            "b.py": 'import re\nre.compile(rf"\\bcell phones {suffix}\\b")\n',
        },
    )
    found = inv.check_no_eval_phrasing_in_api_src()
    assert sorted(v.where.split(":")[0] for v in found) == ["api/src/a.py", "api/src/b.py"]


def test_a_file_with_a_byte_order_mark_is_still_scanned_and_counted(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _leak_repo(
        tmp_path,
        monkeypatch,
        INCOME_Q,
        {"tools.py": '\ufeffHINT = "show median household income for every county"\n'},
    )
    assert inv.check_no_eval_phrasing_in_api_src()
    assert inv._regex_calls("\ufeffimport re\nre.compile('x')\n") == 1


def test_a_baseline_entry_whose_hit_is_gone_fails_the_check(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _leak_repo(
        tmp_path,
        monkeypatch,
        "Compare Springfield with Dayton",
        {"tools.py": "x = 1\n"},
        baseline="place|springfield|api/src/tools.py  # known\n",
    )
    found = inv.check_no_eval_phrasing_in_api_src()
    assert [v.where for v in found] == ["evals/leakage_baseline.txt"]
    assert "stale" in found[0].message
