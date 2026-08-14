#!/usr/bin/env python3
"""Enforce the complexity budgets in budgets.toml.

Runs in well under a second so it can sit in every pre-commit and CI run.
Exits non-zero on any violation.

    python scripts/check_budgets.py
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_SRC = ROOT / "api" / "src"
WEB_SRC = ROOT / "web" / "src"

SKIP_DIRS = {"__pycache__", ".venv", "node_modules", ".git", "dist", "build"}


@dataclass
class Check:
    name: str
    actual: float
    limit: float
    # "max" = actual must not exceed limit; "min" = actual must not fall below
    direction: str = "max"

    @property
    def ok(self) -> bool:
        return self.actual <= self.limit if self.direction == "max" else self.actual >= self.limit


def _py_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [p for p in root.rglob("*.py") if not SKIP_DIRS & set(p.parts)]


def _source_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    if not root.exists():
        return []
    return [
        p
        for p in root.rglob("*")
        if p.suffix in suffixes and p.is_file() and not SKIP_DIRS & set(p.parts)
    ]


def _loc(path: Path) -> int:
    """Physical lines, excluding blanks and whole-line comments."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    total = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        total += 1
    return total


def _count_pattern(files: list[Path], pattern: re.Pattern[str]) -> int:
    total = 0
    for path in files:
        try:
            total += len(pattern.findall(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return total


TOOL_IO_BASES = ("ToolInput", "ToolResult")


def _count_subclasses(
    files: list[Path], base_name: str, exclude: frozenset[str] = frozenset()
) -> int:
    """Classes declaring `base_name` among their bases.

    Direct bases only. Deep hierarchies are not a shape this project allows, so a
    subclass hidden two levels down is a budget problem in its own right — and it
    is what makes the tool-I/O split below work: a `ToolInput` subclass does not
    declare `BaseModel`, so it never lands in the domain count.
    """
    total = 0
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name in exclude:
                continue
            for base in node.bases:
                name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                if name == base_name:
                    total += 1
                    break
    return total


def _count_tools(files: list[Path]) -> int:
    """Agent tools, however they are declared.

    The canonical form is a `BaseTool` subclass with `_arun`. The `@tool`
    decorator is counted too, so the budget cannot be sidestepped by switching
    styles halfway through.
    """
    return _count_subclasses(files, "BaseTool") + _count_pattern(
        files, re.compile(r"^\s*@tool\b", re.MULTILINE)
    )


def _prompt_tokens() -> int:
    """Approximate tokens in the system prompt: string-literal chars / 4.

    chars/4 keeps this checker dependency-free. It is an alarm, not a meter — a
    prompt near the limit should be shortened, not measured more precisely.
    Counting string literals rather than whole files means imports and `def`
    lines do not inflate the number.
    """
    files: list[Path] = []
    for candidate in (API_SRC / "prompts.py", API_SRC / "prompts"):
        if candidate.is_file():
            files.append(candidate)
        elif candidate.is_dir():
            files.extend(_py_files(candidate))

    chars = 0
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                chars += len(node.value)
    return chars // 4


def _count_dependencies() -> int:
    pyproject = ROOT / "api" / "pyproject.toml"
    if not pyproject.exists():
        return 0
    with pyproject.open("rb") as handle:
        data = tomllib.load(handle)
    return len(data.get("project", {}).get("dependencies", []))


def _latest_evidence(key: str) -> float | None:
    """Read a metric from the most recent `make demo` / `make eval` run."""
    import json

    path = ROOT / "evidence" / "latest.json"
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get(key)
    except (OSError, ValueError):
        return None
    return float(value) if isinstance(value, (int, float)) else None


def collect(budgets: dict, structural_only: bool = False) -> list[Check]:
    api_files = _py_files(API_SRC)
    web_files = _source_files(WEB_SRC, (".ts", ".tsx", ".js", ".jsx"))
    size, shape = budgets["size"], budgets["shape"]

    checks = [
        Check("api src LOC", sum(_loc(p) for p in api_files), size["api_src_loc"]),
        Check("api src files", len(api_files), size["api_src_files"]),
        Check(
            "largest file LOC",
            max((_loc(p) for p in api_files), default=0),
            size["max_file_loc"],
        ),
        Check("web src LOC", sum(_loc(p) for p in web_files), size["web_src_loc"]),
        Check("system prompt tokens", _prompt_tokens(), size["system_prompt_tokens"]),
        Check(
            "graph nodes",
            _count_pattern(api_files, re.compile(r"\.add_node\s*\(")),
            shape["graph_nodes"],
        ),
        Check("agent tools", _count_tools(api_files), shape["agent_tools"]),
        Check(
            "api routes",
            _count_pattern(
                api_files,
                re.compile(r"^\s*@\w+\.(?:get|post|put|patch|delete)\s*\(", re.MULTILINE),
            ),
            shape["api_routes"],
        ),
        Check(
            "tool schemas",
            sum(_count_subclasses(api_files, base) for base in TOOL_IO_BASES),
            shape["tool_schemas"],
        ),
        Check(
            "domain models",
            _count_subclasses(api_files, "BaseModel", exclude=frozenset(TOOL_IO_BASES)),
            shape["domain_models"],
        ),
        Check("direct dependencies", _count_dependencies(), shape["direct_dependencies"]),
    ]

    # Evidence-backed checks are skipped silently until a run has produced them,
    # so the gate is usable on day one.
    #
    # --structural-only drops them entirely. That exists for ONE reason: the
    # scoreboard is legitimately red until slice 0 ships, and a CI job that is
    # always red teaches everyone to ignore CI. So the structural checks run as
    # their own always-green job, and the quality floors run as a separate job
    # that is honestly red. Never use this flag to make a real failure go away.
    if structural_only:
        return checks

    p95 = _latest_evidence("p95_latency_seconds")
    if p95 is not None:
        checks.append(Check("p95 latency (s)", p95, budgets["performance"]["p95_latency_seconds"]))

    for key, limit_key in (
        ("retrieval_at_1", "retrieval_at_1_min"),
        ("answered_rate", "answered_rate_min"),
    ):
        value = _latest_evidence(key)
        if value is not None:
            checks.append(Check(key, value, budgets["quality"][limit_key], direction="min"))

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--structural-only",
        action="store_true",
        help="skip the evidence-backed quality floors; see the note in collect()",
    )
    args = parser.parse_args()

    with (ROOT / "budgets.toml").open("rb") as handle:
        budgets = tomllib.load(handle)

    checks = collect(budgets, structural_only=args.structural_only)
    width = max(len(c.name) for c in checks)

    print("\nBUDGETS\n")
    for check in checks:
        status = "ok  " if check.ok else "FAIL"
        comparator = "<=" if check.direction == "max" else ">="
        actual = f"{check.actual:>8.6g}"
        print(f"  {status}  {check.name:<{width}}  {actual} {comparator} {check.limit:g}")

    failed = [c for c in checks if not c.ok]
    if not failed:
        print("\nAll budgets met.\n")
        return 0

    print(f"\n{len(failed)} budget(s) exceeded:\n")
    for check in failed:
        print(f"  - {check.name}: {check.actual:g} (limit {check.limit:g})")
    print(
        "\n"
        "STOP. Do not edit budgets.toml to make this pass.\n"
        "\n"
        "A budget exceeded means one of two things:\n"
        "  1. The change is carrying complexity it does not need -> simplify it.\n"
        "  2. The product genuinely outgrew the budget -> stop and ask the human,\n"
        "     who will raise it in a separate commit with a written reason.\n"
        "\n"
        "Raising a limit yourself defeats the only mechanism protecting this\n"
        "project from the failure mode it was built to avoid.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
