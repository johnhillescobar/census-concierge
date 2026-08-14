#!/usr/bin/env python3
"""Enforce the invariants that are mechanically checkable.

Companion to `check_budgets.py`. Budgets count things; this checks that specific
mistakes have not been made. Everything here is greppable and unambiguous — the
judgment calls live in the review playbook, not in this file.

    python scripts/check_invariants.py
    python scripts/check_invariants.py --base origin/main   # adds the budget-diff check

Exits non-zero on any violation.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_SRC = ROOT / "api" / "src"
API_TESTS = ROOT / "api" / "tests"

SKIP_DIRS = {"__pycache__", ".venv", "node_modules", ".git", "dist", "build"}

# Budget sections where a LARGER number is weaker, versus where a SMALLER one is.
CEILING_SECTIONS = ("size", "shape", "performance")
FLOOR_SECTIONS = ("quality",)


@dataclass(frozen=True)
class Violation:
    where: str
    message: str


def _py_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [p for p in root.rglob("*.py") if not SKIP_DIRS & set(p.parts)]


def _scan(files: list[Path], pattern: re.Pattern[str], message: str) -> list[Violation]:
    found: list[Violation] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                rel = path.relative_to(ROOT).as_posix()
                found.append(Violation(f"{rel}:{lineno}", message))
    return found


def check_banned_agent_frameworks() -> list[Violation]:
    """The loop is ours. langchain_core.tools is fine; the agent runtime is not."""
    return _scan(
        _py_files(API_SRC),
        re.compile(r"\b(from langchain\.agents|create_agent|AgentExecutor)\b"),
        "the agent loop is hand-rolled: langchain.agents / create_agent / "
        "AgentExecutor are banned (see .cursor/rules/10-api-python.mdc)",
    )


def check_no_sqlite() -> list[Violation]:
    """The predecessor shipped a local checkpoints.db. This app is multi-user."""
    return _scan(
        _py_files(API_SRC),
        re.compile(r"\bimport sqlite3\b|\bsqlite3\.connect\b|sqlite\+|sqlite:///"),
        "SQLite cannot serve a multi-user app - use Postgres",
    )


def check_no_contextvars() -> list[Violation]:
    """The set/reset-token pattern is one refactor from cross-user leakage."""
    return _scan(
        _py_files(API_SRC),
        re.compile(r"\bimport contextvars\b|\bContextVar\b"),
        "pass context as function arguments; contextvars leak across users",
    )


def check_test_naming() -> list[Violation]:
    """A test named after a ticket cannot be interpreted or deleted later."""
    found: list[Violation] = []
    ticket = re.compile(r"test_[a-z]*_?\d{2,}[_.]", re.IGNORECASE)
    for path in _py_files(API_TESTS):
        if ticket.search(path.name):
            found.append(
                Violation(
                    path.relative_to(ROOT).as_posix(),
                    "tests are named for behaviour, not tickets - nobody can "
                    "later interpret or delete test_census_43_*",
                )
            )
    return found


def check_tests_do_not_touch_prompts() -> list[Violation]:
    """Asserting on prompt wording breaks on edits and survives regressions."""
    return _scan(
        _py_files(API_TESTS),
        re.compile(r"\bfrom\s+\S*prompts?\s+import\b|\bimport\s+\S*\.prompts\b"),
        "never assert on prompt wording - test behaviour (question in, table and URL out)",
    )


def _budgets_at(ref: str) -> dict[str, dict[str, float]] | None:
    try:
        blob = subprocess.run(
            ["git", "show", f"{ref}:budgets.toml"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    try:
        return tomllib.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None


def check_budgets_not_weakened(base: str) -> list[Violation]:
    """The one check that matters most: nobody may quietly widen a limit.

    Raising a ceiling or lowering a floor is a standalone human commit with a
    reason in the budget log. It is never part of a change that would otherwise
    fail.
    """
    old = _budgets_at(base)
    if old is None:
        return []
    with (ROOT / "budgets.toml").open("rb") as handle:
        new = tomllib.load(handle)

    found: list[Violation] = []
    for section, weakened in (
        *((s, lambda a, b: a > b) for s in CEILING_SECTIONS),
        *((s, lambda a, b: a < b) for s in FLOOR_SECTIONS),
    ):
        for key, new_value in new.get(section, {}).items():
            old_value = old.get(section, {}).get(key)
            if old_value is None or not isinstance(new_value, (int, float)):
                continue
            if weakened(new_value, old_value):
                found.append(
                    Violation(
                        f"budgets.toml [{section}] {key}",
                        f"{old_value:g} -> {new_value:g} weakens the budget. "
                        "This belongs in its own commit, by a human, with a "
                        "reason appended to the change log - never bundled "
                        "with the change it would otherwise block.",
                    )
                )
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        help="git ref to diff budgets.toml against, e.g. origin/main. "
        "Skipped silently when the ref is unavailable.",
    )
    args = parser.parse_args()

    violations: list[Violation] = [
        *check_banned_agent_frameworks(),
        *check_no_sqlite(),
        *check_no_contextvars(),
        *check_test_naming(),
        *check_tests_do_not_touch_prompts(),
    ]
    if args.base:
        violations.extend(check_budgets_not_weakened(args.base))

    print("\nINVARIANTS\n")
    if not violations:
        print("  ok    no violations\n")
        return 0

    for violation in violations:
        print(f"  FAIL  {violation.where}")
        print(f"        {violation.message}\n")
    print(f"{len(violations)} violation(s).\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
