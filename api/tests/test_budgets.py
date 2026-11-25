"""Budget checker: agent catalogs count toward doc_lines; ARCHITECTURE does not."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_budgets as bud  # noqa: E402

CATALOGS = (
    ("requirements.md", 3),
    ("ask-path.md", 5),
    ("retrieval.md", 7),
    ("slices.md", 11),
)


def _write_lines(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"line-{i}" for i in range(count)) + "\n", encoding="utf-8")


BUDGETS = {"performance": {"p95_latency_seconds": 20.0}}
RUN = "2026-10-02T02:25:10+00:00"


LOG_HEADER = "# --- budget change log ---\n"


def _latest(
    tmp_path: Path, monkeypatch: Any, payload: dict[str, Any], log: str = "", header: bool = True
) -> None:
    (tmp_path / "evidence").mkdir(exist_ok=True)
    (tmp_path / "evidence" / "latest.json").write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "budgets.toml").write_text((LOG_HEADER if header else "") + log, encoding="utf-8")
    monkeypatch.setattr(bud, "ROOT", tmp_path)


def _empty_sources(tmp_path: Path, monkeypatch: Any) -> None:
    """Keep the gate off the live api/web trees: their size is not this test's business."""
    monkeypatch.setattr(bud, "API_SRC", tmp_path / "api" / "src")
    monkeypatch.setattr(bud, "WEB_SRC", tmp_path / "web" / "src")


def _demo(p95: float, *, run: str = RUN, trials: list[float] | None = None) -> dict[str, Any]:
    return {
        "p95_latency_seconds": p95,
        "generated_at": run,
        "trials": [{"latency_s": s} for s in trials or []],
    }


def test_p95_is_read_from_the_runs_own_demo_block_not_the_stale_top_level_key(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _latest(tmp_path, monkeypatch, {"p95_latency_seconds": 19.2, "demo": _demo(21.7)})
    check = bud._p95_check(BUDGETS)
    assert check is not None
    assert check.actual == 21.7 and not check.ok


def test_p95_falls_back_to_the_top_level_key_when_there_is_no_demo_block(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _latest(tmp_path, monkeypatch, {"p95_latency_seconds": 19.2})
    check = bud._p95_check(BUDGETS)
    assert check is not None and check.actual == 19.2 and check.ok


def test_p95_check_names_the_slowest_trial_that_p95_leaves_out(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _latest(tmp_path, monkeypatch, {"demo": _demo(18.9, trials=[3.0, 820.4, 9.0])})
    check = bud._p95_check(BUDGETS)
    assert check is not None and "820.4" in check.note


WAIVER = f"# 2026-10-04  [waiver] p95_latency_seconds {RUN} 21.701 CC-113 research under way\n"


def test_an_over_ceiling_p95_passes_only_with_a_waiver_for_that_run(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _latest(tmp_path, monkeypatch, {"demo": _demo(21.701)}, log=WAIVER)
    check = bud._p95_check(BUDGETS)
    assert check is not None and check.ok and not check.within
    assert "CC-113" in check.waived


def test_a_waiver_for_another_run_or_another_value_does_not_apply(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _latest(tmp_path, monkeypatch, {"demo": _demo(21.701, run="a-newer-run")}, log=WAIVER)
    other_run = bud._p95_check(BUDGETS)
    _latest(tmp_path, monkeypatch, {"demo": _demo(24.0)}, log=WAIVER)
    other_value = bud._p95_check(BUDGETS)
    assert other_run is not None and not other_run.ok
    assert other_value is not None and not other_value.ok


def test_an_under_ceiling_p95_needs_no_waiver(tmp_path: Path, monkeypatch: Any) -> None:
    log = f"# 2026-10-04  [waiver] p95_latency_seconds {RUN} 18.928 CC-113 not needed\n"
    _latest(tmp_path, monkeypatch, {"demo": _demo(18.928)}, log=log)
    check = bud._p95_check(BUDGETS)
    assert check is not None and check.within and check.waived == ""


@pytest.mark.parametrize(
    "demo", [None, [], "x", {"p95_latency_seconds": None}, {"p95_latency_seconds": True}]
)
def test_an_unusable_demo_block_fails_instead_of_reading_the_stale_key(
    tmp_path: Path, monkeypatch: Any, demo: Any
) -> None:
    _latest(tmp_path, monkeypatch, {"p95_latency_seconds": 19.2, "demo": demo})
    check = bud._p95_check(BUDGETS)
    assert check is not None and not check.ok


def test_a_waiver_tolerates_rounding_but_not_a_different_p95(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _latest(tmp_path, monkeypatch, {"demo": _demo(21.7014)}, log=WAIVER)
    rounded = bud._p95_check(BUDGETS)
    _latest(tmp_path, monkeypatch, {"demo": _demo(21.703)}, log=WAIVER)
    different = bud._p95_check(BUDGETS)
    assert rounded is not None and rounded.ok
    assert different is not None and not different.ok


def test_a_waiver_written_above_the_log_header_is_ignored(tmp_path: Path, monkeypatch: Any) -> None:
    _latest(tmp_path, monkeypatch, {"demo": _demo(21.701)}, log=WAIVER + LOG_HEADER, header=False)
    check = bud._p95_check(BUDGETS)
    assert check is not None and not check.ok


def test_collect_gates_p95_and_structural_only_leaves_it_out(
    tmp_path: Path, monkeypatch: Any
) -> None:
    real = tomllib.loads((ROOT / "budgets.toml").read_text(encoding="utf-8"))
    _latest(tmp_path, monkeypatch, {"demo": _demo(21.7)})
    _empty_sources(tmp_path, monkeypatch)
    assert "p95 latency (s)" in [c.name for c in bud.collect(real)]
    assert "p95 latency (s)" not in [c.name for c in bud.collect(real, structural_only=True)]


def test_main_labels_a_waived_p95_and_counts_it(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    _latest(tmp_path, monkeypatch, {"demo": _demo(21.701)})
    _empty_sources(tmp_path, monkeypatch)
    real = (ROOT / "budgets.toml").read_text(encoding="utf-8")
    (tmp_path / "budgets.toml").write_text(real + "\n" + WAIVER, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_budgets.py"])
    assert bud.main() == 0
    out = capsys.readouterr().out
    assert "waive " in out and "waived by owner: CC-113" in out
    assert "1 waived by the owner" in out


def test_a_file_with_a_byte_order_mark_is_still_counted_by_the_shape_budgets(
    tmp_path: Path, monkeypatch: Any
) -> None:
    src = tmp_path / "api" / "src"
    src.mkdir(parents=True)
    bom = chr(0xFEFF)
    (src / "tools.py").write_text(
        bom + "class A(BaseTool): pass\nclass B(BaseTool): pass\n", encoding="utf-8"
    )
    (src / "prompts.py").write_text(bom + 'ROLE = "' + "x" * 400 + '"\n', encoding="utf-8")
    monkeypatch.setattr(bud, "API_SRC", src)
    assert bud._count_subclasses([src / "tools.py"], "BaseTool") == 2
    assert bud._prompt_tokens() == 100


def test_doc_lines_counts_each_agent_catalog(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(bud, "ROOT", tmp_path)
    _write_lines(tmp_path / "CLAUDE.md", 1)
    docs = tmp_path / "docs"
    for name, count in CATALOGS:
        _write_lines(docs / name, count)
    _write_lines(docs / "ARCHITECTURE.md", 100)

    expected = 1 + sum(count for _name, count in CATALOGS)
    assert bud._doc_lines() == expected

    for name, count in CATALOGS:
        path = docs / name
        path.unlink()
        assert bud._doc_lines() == expected - count, name
        _write_lines(path, count)

    for name in ("AGENTS.md", ".agents/skills/run-slice/SKILL.md"):
        path = tmp_path / name
        _write_lines(path, 7)
        assert bud._doc_lines() == expected + 7, name
        path.unlink()


# --- exceptions: a floor main already misses, recorded by the owner ----------------------------

EXCEPTION = {
    "metric": "p95_latency_seconds",
    "baseline": 29.0,
    "approved": "2026-11-24 owner",
    "ticket": "CC-9",
}


def _rule() -> dict[str, Any]:
    text = (ROOT / "evals" / "metric_protocol.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)["rule"]


def _exception_toml(**changed: Any) -> str:
    entry = {**EXCEPTION, **changed}
    lines = [f"{key} = {json.dumps(value)}" for key, value in entry.items()]
    return "\n[[exception]]\n" + "\n".join(lines) + "\n"


def test_an_over_ceiling_p95_is_excepted_while_no_worse_than_the_owners_baseline(
    tmp_path: Path, monkeypatch: Any
) -> None:
    budgets = {**BUDGETS, "exception": [EXCEPTION]}
    step = _rule()["p95_rise_max_seconds"]
    _latest(tmp_path, monkeypatch, {"demo": _demo(29.0 + step)})
    check = bud._p95_check(budgets)
    assert check is not None and check.ok and not check.within
    assert "CC-9" in check.excepted and "29" in check.excepted
    assert not bud._p95_check(BUDGETS).ok  # the same run with no exception on record
    _latest(tmp_path, monkeypatch, {"demo": _demo(29.0 + step + 0.01)})
    worse = bud._p95_check(budgets)
    assert worse is not None and not worse.ok and not worse.excepted  # worse, by the rule


def test_a_waived_run_is_reported_as_waived_not_excepted(tmp_path: Path, monkeypatch: Any) -> None:
    _latest(tmp_path, monkeypatch, {"demo": _demo(21.701)}, log=WAIVER)
    check = bud._p95_check({**BUDGETS, "exception": [EXCEPTION]})
    assert check is not None and check.waived and not check.excepted


def _main_with(tmp_path: Path, monkeypatch: Any, extra: str, **latest: float) -> int:
    payload = {"demo": _demo(19.0), "retrieval_at_10": 0.9, "answered_rate": 0.72, **latest}
    _latest(tmp_path, monkeypatch, payload)
    _empty_sources(tmp_path, monkeypatch)
    real = (ROOT / "budgets.toml").read_text(encoding="utf-8")
    kept = real.split("[[exception]]")[0]  # the owner's own exceptions are not this test's
    (tmp_path / "budgets.toml").write_text(kept + extra, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_budgets.py"])
    return bud.main()


def test_main_labels_an_excepted_quality_floor_and_counts_it(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    held = _exception_toml(metric="selector_at_1_min", baseline=0.5)
    assert _main_with(tmp_path, monkeypatch, "", selector_at_1=0.425) == 1  # a plain miss
    assert "FAIL  selector_at_1" in capsys.readouterr().out
    assert _main_with(tmp_path, monkeypatch, held, selector_at_1=0.425) == 0
    out = capsys.readouterr().out
    assert "excpt selector_at_1" in out and "CC-9 restores it" in out
    assert "1 excepted by the owner" in out


def test_main_fails_a_floor_that_fell_past_its_exception(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    drop = _rule()["selector_drop_max"]
    held = _exception_toml(metric="selector_at_1_min", baseline=round(0.425 + drop + 0.02, 3))
    assert _main_with(tmp_path, monkeypatch, held, selector_at_1=0.425) == 1
    assert "FAIL  selector_at_1" in capsys.readouterr().out


def test_an_exception_for_one_floor_does_not_cover_another(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    held = _exception_toml(metric="selector_at_1_min", baseline=0.5)
    assert _main_with(tmp_path, monkeypatch, held, selector_at_1=0.8, answered_rate=0.6) == 1
    assert "FAIL  answered_rate" in capsys.readouterr().out


@pytest.mark.parametrize(
    "changed", [{"ticket": ""}, {"baseline": "0.5"}, {"metric": "doc_lines"}, {"approved": " "}]
)
def test_a_malformed_exception_is_itself_a_failure_and_excuses_nothing(
    tmp_path: Path, monkeypatch: Any, capsys: Any, changed: dict[str, Any]
) -> None:
    good = _exception_toml(metric="selector_at_1_min", baseline=0.5)
    bad = _exception_toml(**{"metric": "selector_at_1_min", "baseline": 0.5, **changed})
    assert _main_with(tmp_path, monkeypatch, good + bad, selector_at_1=0.425) == 1
    out = capsys.readouterr().out
    assert "FAIL  malformed exceptions" in out and "FAIL  selector_at_1" in out
    assert _main_with(tmp_path, monkeypatch, bad, selector_at_1=0.8) == 1  # even when unused
