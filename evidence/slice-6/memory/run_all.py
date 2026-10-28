#!/usr/bin/env python3
"""CC-123: the pre-registered run sequence, one fresh process per run, resumable.

    uv run python evidence/slice-6/memory/run_all.py

Order (design: ../memory-experiment-design.md): arm P interleaved M, C, B three times, then arm T
once per tree, then the leaf arms. A run whose output already ends in a footer is skipped, so a
reaped session resumes where it stopped. Run it from the CC-123 worktree.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TREES = {
    "M": ROOT,
    "C": ROOT.parent / "census-cc-123-C",
    "B": ROOT.parent / "census-cc-123-B",
}
PROBE = ROOT / "scripts" / "memory_probe.py"


def finished(path: Path) -> bool:
    if not path.exists():
        return False
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    return bool(lines) and json.loads(lines[-1]).get("kind") == "footer"


def jobs() -> list[tuple[str, list[str]]]:
    plan: list[tuple[str, list[str]]] = []
    for repeat in (1, 2, 3):
        for tree in ("M", "C", "B"):
            out = f"w1-{tree}-P-r{repeat}.jsonl"
            plan.append((out, ["run", "--tree", str(TREES[tree]), "--arm", "P"]))
    for tree in ("M", "C", "B"):
        plan.append((f"w1-{tree}-T.jsonl", ["run", "--tree", str(TREES[tree]), "--arm", "T"]))
    for path, iterations in (("L1", 300), ("L2", 300), ("L3", 100), ("L4", 100), ("L5", 100)):
        plan.append(
            (
                f"leaf-{path}-M.jsonl",
                ["leaf", "--tree", str(TREES["M"]), "--path", path]
                + ["--iterations", str(iterations)],
            )
        )
    for path in ("L6a", "L6b"):
        plan.append((f"leaf-{path}-M.jsonl", ["leaf", "--tree", str(TREES["M"]), "--path", path]))
    plan.append(
        (
            "leaf-L5c-C.jsonl",
            ["leaf", "--tree", str(TREES["C"]), "--path", "L5c", "--iterations", "100"],
        )
    )
    return plan


def main() -> int:
    for out, args in jobs():
        target = HERE / out
        if finished(target):
            print(f"skip   {out}", flush=True)
            continue
        if target.exists():
            target.rename(target.with_suffix(".partial"))
        print(f"start  {out}", flush=True)
        log = (HERE / f"{out}.log").open("w", encoding="utf-8")
        code = subprocess.run(
            [sys.executable, str(PROBE), *args, "--out", str(target)],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        ).returncode
        print(f"done   {out} exit={code}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
