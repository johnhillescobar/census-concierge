"""Pre-flight for CC-143: the rule on origin/main, judging unchanged main against unchanged main.

    git show origin/main:scripts/metric_compare.py > <scratch>/old_metric_compare.py
    uv run python evidence/slice-6/cc-143/old_rule.py <scratch>/old_metric_compare.py

Run from the repository root. Aggregates only: nobody reads the trials.
"""

import importlib.util
import subprocess
import sys
import tomllib
from pathlib import Path

spec = importlib.util.spec_from_file_location("old_mc", sys.argv[1])
assert spec is not None and spec.loader is not None
old = importlib.util.module_from_spec(spec)
sys.modules["old_mc"] = old
spec.loader.exec_module(old)
old.ROOT = Path.cwd()
text = subprocess.run(
    ["git", "show", "origin/main:evals/metric_protocol.toml"], capture_output=True, check=True
).stdout.decode("utf-8")
protocol = tomllib.loads(text)
runs = {n: old.load_run(f"evidence/metrics/runs/{n}.json") for n in ("main-b1", "main-b2")}
for cand, ref in (("main-b1", "main-b2"), ("main-b2", "main-b1")):
    checks = old.evaluate(runs[cand], runs[ref], "B", protocol)
    print(f"origin/main rule, {cand} against {ref} (one code, 29c0518): {old.verdict(checks)}")
    for c in checks:
        print(f"  {c.status:<12} {c.name:<28} {c.detail}")
