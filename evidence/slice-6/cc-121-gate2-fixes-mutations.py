#!/usr/bin/env python3
"""CC-121 Gate 2 fixes: revert one behaviour at a time, run only its tests, expect a failure.

PYTHONUTF8=1 uv run python evidence/slice-6/cc-121-gate2-fixes-mutations.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "api" / "src" / "figures.py"
TESTS = "api/tests/test_figures.py"

MUTATIONS = [
    (
        "negative estimate loses its sign",
        "f\"{'-' if whole.startswith('-') else ''}{abs(int(whole)):,}{dot}{fraction}\"",
        'f"{abs(int(whole)):,}{dot}{fraction}"',
        "negative_estimate_keeps_its_sign",
    ),
    (
        "discovery answer may not name published vintages",
        "if published and not rows:",
        "if False and not rows:",
        "discovery",
    ),
    (
        "published years alone are not response text",
        "if published and not rows:",
        "if False and not rows:",
        "published_year_that_no_title_carries",
    ),
    (
        "published vintages offered even when rows were fetched",
        "if published and not rows:",
        "if published:",
        "not_fetched_is_flagged",
    ),
    (
        "pool titles and universes are not response text",
        "    texts += [f\"{hit.get('title')} {hit.get('universe')}\" for hit in pool]\n",
        "",
        "pool_table_may_be_named or discovery",
    ),
    (
        "the response URL is not response text",
        '        str(getattr(record, "url", "")),' + chr(10),
        "",
        "quoted_url",
    ),
    (
        "the geography clause is not response text",
        "for g in geographies if g]",
        "for g in geographies if False]",
        "quoted_url",
    ),
    (
        "prose without a number still builds the allowed set",
        "    if not numbers:\n        return []\n",
        "",
        "without_a_digit",
    ),
    (
        "a stray token is echoed without a bound",
        "n[:40]",
        "n",
        "long_stray",
    ),
]


def run(selector: str) -> tuple[int, str]:
    done = subprocess.run(
        ["uv", "run", "pytest", "-q", TESTS, "-k", selector, "-x"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    tail = [line for line in done.stdout.splitlines() if line.strip()][-1:]
    return done.returncode, "".join(tail)


def main() -> int:
    original = SRC.read_bytes().decode("utf-8")
    caught = 0
    try:
        for name, old, new, selector in MUTATIONS:
            assert original.count(old) == 1, f"old text occurs {original.count(old)} times: {name}"
            code, _ = run(selector)
            assert code == 0, f"the covering tests must pass on the true code: {name}"
            print(f"GOOD  {name}: tests pass on the true code (exit {code})")
            SRC.write_bytes(original.replace(old, new).encode("utf-8"))
            code, tail = run(selector)
            verdict = "BAD " if code == 1 else "MISS"
            caught += code == 1
            print(f"{verdict}  {name}: mutated code, exit {code}, {tail}")
            SRC.write_bytes(original.encode("utf-8"))
    finally:
        SRC.write_bytes(original.encode("utf-8"))
    print(f"CAUGHT {caught} of {len(MUTATIONS)}")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    sys.exit(main())
