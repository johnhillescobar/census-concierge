"""Budget checker: agent catalogs count toward doc_lines; ARCHITECTURE does not."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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
