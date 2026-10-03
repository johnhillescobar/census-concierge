#!/usr/bin/env python3
"""Enforce the invariants that are mechanically checkable.

Companion to `check_budgets.py`. Budgets count things; this checks that specific
mistakes have not been made. Everything here is greppable and unambiguous — the
judgment calls live in the review playbook, not in this file.

    python scripts/check_invariants.py
    python scripts/check_invariants.py --base origin/main   # adds budget-diff, new-regex

Exits non-zero on any violation. Every check is printed by name, pass or fail.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_SRC = ROOT / "api" / "src"
API_TESTS = ROOT / "api" / "tests"
WEB_SRC = ROOT / "web" / "src"
SCRIPTS = ROOT / "scripts"
EVIDENCE = ROOT / "evidence"

SKIP_DIRS = {"__pycache__", ".venv", "node_modules", ".git", "dist", "build"}

# Budget sections where a LARGER number is weaker, versus where a SMALLER one is.
CEILING_SECTIONS = ("size", "shape", "performance")
FLOOR_SECTIONS = ("quality",)

BANNED_MODULE = re.compile(
    r"_(manager|orchestrator|factory|policy|strategy|service)\.(py|ts|tsx|js|jsx)$"
)
EMPTY_SECRET = re.compile(
    r"""(?:os\.environ\.get|os\.getenv)\(\s*["'](CENSUS_API_KEY|OPENAI_API_KEY|GEMINI_API_KEY)["']\s*,\s*["']{2}\s*\)"""
)
KEY_LEAK = re.compile(r"""(?i)[?&]key=(?!REDACTED(?:["'&\s]|$))[^&\s"']+""")
KEY_IN_URL = re.compile(r"[?&]key=", re.IGNORECASE)


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


def check_banned_module_names() -> list[Violation]:
    """Those suffixes hid orchestration the predecessor could not delete."""
    found: list[Violation] = []
    for root in (API_SRC, WEB_SRC):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or SKIP_DIRS & set(path.parts):
                continue
            if BANNED_MODULE.search(path.name):
                rel = path.relative_to(ROOT).as_posix()
                found.append(
                    Violation(
                        rel,
                        "forbidden module suffix: *_manager, *_orchestrator, "
                        "*_factory, *_policy, *_strategy, *_service",
                    )
                )
    return found


def check_no_clarification_layer() -> list[Violation]:
    """A clarification subsystem is a blocking question wearing a directory."""
    found: list[Violation] = []
    for root in (API_SRC, WEB_SRC):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if SKIP_DIRS & set(path.parts):
                continue
            if "clarif" in path.name.casefold():
                rel = path.relative_to(ROOT).as_posix()
                found.append(
                    Violation(
                        rel,
                        "blocking clarification is forbidden - candidates are results, "
                        "not a question the user cannot answer",
                    )
                )
    return found


def check_census_key_not_in_artifacts() -> list[Violation]:
    """Committed evidence JSON is user-visible. A live Census key must not be in it."""
    if not EVIDENCE.is_dir():
        return []
    found: list[Violation] = []
    for path in EVIDENCE.rglob("*.json"):
        if SKIP_DIRS & set(path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if KEY_LEAK.search(text):
            rel = path.relative_to(ROOT).as_posix()
            found.append(Violation(rel, "Census API key leaked into evidence JSON; redact &key="))
    return found


def check_no_empty_secret_defaults() -> list[Violation]:
    """`.get("CENSUS_API_KEY", "")` turns a missing key into an unauthenticated call."""
    return _scan(
        [*_py_files(API_SRC), *_py_files(SCRIPTS)],
        EMPTY_SECRET,
        "missing CENSUS_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY must fail closed, "
        "not default to empty",
    )


def check_key_attached_only_in_census_url() -> list[Violation]:
    """`&key=` in api/src belongs on CensusURL, not on a second formatter."""
    files = [path for path in _py_files(API_SRC) if path.name != "census_url.py"]
    return _scan(
        files,
        KEY_IN_URL,
        "&key= is attached only inside census_url.py (CensusURL.with_key / redact_text)",
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


REGEX_FUNCS = {
    "compile",
    "search",
    "match",
    "fullmatch",
    "sub",
    "subn",
    "findall",
    "finditer",
    "split",
}


def _regex_calls(source: str) -> int:
    """Count `re.<fn>(...)` call sites with the AST; a regex must not police regexes."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    return sum(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "re"
        and n.func.attr in REGEX_FUNCS
        for n in ast.walk(tree)
    )


def _regex_counts_now() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in _py_files(API_SRC):
        count = _regex_calls(path.read_text(encoding="utf-8"))
        if count:
            counts[path.relative_to(ROOT).as_posix()] = count
    return counts


def _regex_counts_at(ref: str) -> dict[str, int] | None:
    try:
        names = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", ref, "--", "api/src"],
            cwd=ROOT,
            capture_output=True,
            check=True,
            text=True,
        ).stdout.split()
        counts: dict[str, int] = {}
        for name in (n for n in names if n.endswith(".py")):
            blob = subprocess.run(
                ["git", "show", f"{ref}:{name}"], cwd=ROOT, capture_output=True, check=True
            ).stdout.decode("utf-8", errors="replace")
            if count := _regex_calls(blob):
                counts[name] = count
        return counts
    except (OSError, subprocess.CalledProcessError):
        return None


def check_no_new_regex(base: str) -> list[Violation]:
    """Regex is a last resort in this agent: the count in api/src may only go down.

    Understanding a question is the model's job; a pattern covers the phrasings its
    author imagined and silently fails the rest. A new regex needs a human commit that
    states why no non-regex code plus the model can do the job.
    """
    old = _regex_counts_at(base)
    if old is None:
        return []
    return [
        Violation(
            where,
            f"{old.get(where, 0)} -> {count} regex call(s). Regex is a last resort: let the "
            "model compose structure and have code validate it (CLAUDE.md, Do not).",
        )
        for where, count in sorted(_regex_counts_now().items())
        if count > old.get(where, 0)
    ]


def check_mandatory_catalogs() -> list[Violation]:
    """Agent catalogs must exist. Does not validate their prose."""
    found: list[Violation] = []
    for rel in (
        "docs/requirements.md",
        "docs/ask-path.md",
        "docs/retrieval.md",
        "docs/slices.md",
    ):
        if not (ROOT / rel).is_file():
            found.append(Violation(rel, "mandatory agent catalog is missing"))
    return found


CHECKS: tuple[tuple[str, Callable[[], list[Violation]]], ...] = (
    ("banned agent frameworks", check_banned_agent_frameworks),
    ("sqlite", check_no_sqlite),
    ("contextvars", check_no_contextvars),
    ("ticket-named tests", check_test_naming),
    ("prompt assertions", check_tests_do_not_touch_prompts),
    ("forbidden module names", check_banned_module_names),
    ("blocking clarification", check_no_clarification_layer),
    ("census key in artifacts", check_census_key_not_in_artifacts),
    ("empty secret defaults", check_no_empty_secret_defaults),
    ("key attached only via CensusURL", check_key_attached_only_in_census_url),
    ("mandatory catalogs", check_mandatory_catalogs),
)


def collect(base: str | None) -> list[tuple[str, list[Violation]]]:
    rows = [(name, check()) for name, check in CHECKS]
    if base:
        rows.append(("budget increases", check_budgets_not_weakened(base)))
        rows.append(("new regex", check_no_new_regex(base)))
    else:
        rows.append(("budget increases", []))
        rows.append(("new regex", []))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        help="git ref to diff budgets.toml against, e.g. origin/main. "
        "Skipped silently when the ref is unavailable.",
    )
    args = parser.parse_args()

    rows = collect(args.base)
    width = max(len(name) for name, _ in rows)
    print("\nINVARIANTS\n")
    failed = 0
    for name, violations in rows:
        if name in {"budget increases", "new regex"} and not args.base:
            print(f"  skip  {name:<{width}}  pass --base to diff against a ref")
            continue
        if not violations:
            print(f"  ok    {name:<{width}}")
            continue
        failed += len(violations)
        print(f"  FAIL  {name:<{width}}")
        for violation in violations:
            print(f"        {violation.where}")
            print(f"        {violation.message}")
    print()
    if not failed:
        print("All invariants held.\n")
        return 0
    print(f"{failed} violation(s).\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
