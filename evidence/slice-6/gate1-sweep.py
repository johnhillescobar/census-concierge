"""Operator sweep over the new code of CC-121: which small changes does test_figures.py miss?

Complements the named mutations in gate1-mutations.py. Those revert one behaviour each and run
the one test that covers it. This sweep asks the opposite question: which small changes to the
code does the whole of test_figures.py NOT notice? Each survivor is then read by a person: it is
either an equivalent change (same behaviour) or a missing test.

Mutants come from the ast module (no regex, no word list): a comparison flipped, and/or swapped,
`not` dropped, an `if` condition negated, an integer shifted by one, a string emptied, a
statement deleted. The mutated module is written as unparsed source, run in a child pytest
(first failure stops it), and the file is restored byte for byte in a `finally` block. From the
repository root:

    uv run python -B evidence/slice-6/gate1-sweep.py <figures|contract> [first] [last]
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIGURES_TESTS = ["api/tests/test_figures.py"]
TARGETS: dict[str, tuple[str, set[str] | None, list[str]]] = {
    "figures": ("api/src/figures.py", None, FIGURES_TESTS),
    # take_chart also draws charts; the older chart tests guard the code that was already there
    "contract": (
        "api/src/contract.py",
        {"_warn_unverified", "take_chart"},
        [*FIGURES_TESTS, "api/tests/test_chart.py"],
    ),
}
SWAPS: dict[type, type] = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
}


class Sweep(ast.NodeTransformer):
    """Walks the module once. With `index` set, applies the index-th mutation it meets.

    Every call records the sites it saw in `self.sites` as (line, operator), so the first walk
    (index -1, nothing applied) lists them and each later walk applies exactly one.
    """

    def __init__(self, index: int, only: set[str] | None) -> None:
        self.index = index
        self.only = only
        self.inside = only is None
        self.sites: list[tuple[int, str]] = []

    def hit(self, node: ast.AST, operator: str) -> bool:
        if not self.inside:
            return False
        self.sites.append((getattr(node, "lineno", 0), operator))
        return len(self.sites) - 1 == self.index

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        was = self.inside
        if self.only is not None and node.name in self.only:
            self.inside = True
        result = self.generic_visit(node)
        self.inside = was
        return result

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        for i, op in enumerate(node.ops):
            if type(op) in SWAPS and self.hit(
                node, f"{type(op).__name__} -> {SWAPS[type(op)].__name__}"
            ):
                node.ops[i] = SWAPS[type(op)]()
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)
        swapped = ast.Or if isinstance(node.op, ast.And) else ast.And
        if self.hit(node, f"{type(node.op).__name__} -> {swapped.__name__}"):
            node.op = swapped()
        return node

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.op, ast.Not) and self.hit(node, "drop not"):
            return node.operand
        return node

    def negate(self, node: ast.If | ast.IfExp) -> ast.AST:
        self.generic_visit(node)
        if self.hit(node, "negate condition"):
            node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
        return node

    visit_If = negate  # type: ignore[assignment]
    visit_IfExp = negate  # type: ignore[assignment]

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if type(node.value) is int and node.value > 1:
            if self.hit(node, f"int {node.value} -> {node.value + 1}"):
                return ast.copy_location(ast.Constant(node.value + 1), node)
        elif isinstance(node.value, str) and node.value and self.hit(node, "string emptied"):
            return ast.copy_location(ast.Constant(""), node)
        return node

    def drop(self, node: ast.stmt) -> ast.AST:
        self.generic_visit(node)
        if self.hit(node, "statement deleted"):
            return ast.copy_location(ast.Pass(), node)
        return node

    def visit_Expr(self, node: ast.Expr) -> ast.AST:
        return node if isinstance(node.value, ast.Constant) else self.drop(node)  # docstrings stay

    visit_Assign = drop  # type: ignore[assignment]
    visit_AugAssign = drop  # type: ignore[assignment]
    visit_Return = drop  # type: ignore[assignment]


def pytest(tests: list[str]) -> int:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
    done = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", *tests, "-x", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    return done.returncode


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "figures"
    path, only, tests = TARGETS[which]
    original = (ROOT / path).read_bytes()
    source = original.decode("utf-8").replace(chr(13) + chr(10), chr(10))
    lines = source.splitlines()
    listing = Sweep(-1, only)
    listing.visit(ast.parse(source))
    total = len(listing.sites)
    first = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    last = min(int(sys.argv[3]) if len(sys.argv) > 3 else total - 1, total - 1)
    print(f"{path}: {total} mutation sites; running {first}..{last}", flush=True)
    killed = survived = 0
    try:
        for index in range(first, last + 1):
            sweep = Sweep(index, only)
            mutant = sweep.visit(ast.parse(source))
            ast.fix_missing_locations(mutant)
            line, operator = sweep.sites[index]
            (ROOT / path).write_bytes(ast.unparse(mutant).encode("utf-8"))
            if pytest(tests) == 0:
                survived += 1
                print(
                    f"SURVIVED  #{index} line {line} [{operator}]  {lines[line - 1].strip()}",
                    flush=True,
                )
            else:
                killed += 1
    finally:
        (ROOT / path).write_bytes(original)
    print(f"TALLY  {killed} killed, {survived} survived of {killed + survived} mutants run")
    clean = subprocess.run(["git", "diff", "--quiet", "--", path], cwd=ROOT, check=False)
    print("RESTORED (git diff --quiet is clean)" if clean.returncode == 0 else "NOT RESTORED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
