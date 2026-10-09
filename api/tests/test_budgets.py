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
