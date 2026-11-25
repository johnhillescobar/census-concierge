"""CC-143: what the proposed rule says about the four stored runs, and the L they would seed.

    uv run python evidence/slice-6/cc-143/stored_runs.py

Run from the repository root. Aggregates only, and it writes nothing: `build_entry` is what
`register L` would store, printed instead of saved.
"""

import json
import sys

sys.path.insert(0, "scripts")
import metric_compare as mc  # noqa: E402

protocol = mc.load_protocol()
MAIN = ["evidence/metrics/runs/main-b1.json", "evidence/metrics/runs/main-b2.json"]
CC104 = ["evidence/metrics/runs/cc104-p1.json", "evidence/metrics/runs/cc104-p2.json"]
runs = {path: mc.load_run(path) for path in (*MAIN, *CC104)}
entry = mc.build_entry(MAIN, runs[MAIN[0]].hashes["head"], "seed", legacy=False)
print("L seeded from the two stored runs of main:")
print("  metrics ", json.dumps(entry["metrics"]))
print("  blockers", entry["blockers"])
print("  hashes  ", json.dumps(entry["hashes"]))


def show(title: str, checks: list[mc.Check]) -> None:
    print(f"\n{title}: VERDICT {mc.verdict(checks)}")
    for c in checks:
        status = c.status if c.blocking else f"({c.status})"
        print(f"  {status:<10} {c.kind:<4} {c.name:<28} {c.detail}")


def name(path: str) -> str:
    return path.rsplit("/", 1)[-1]


for cand, ref in (
    (MAIN[0], MAIN[1]),
    (MAIN[1], MAIN[0]),
    (CC104[0], CC104[1]),
    (CC104[1], CC104[0]),
):
    title = f"same code, {name(cand)} against {name(ref)}"
    show(title, mc.evaluate(runs[cand], runs[ref], "B", protocol))
pool, base = [runs[p] for p in CC104], [runs[p] for p in MAIN]
show("stored CC-104 pool against stored main pool (2x2)", mc.evaluate(pool, base, "B", protocol))
for path in MAIN:
    title = f"one main run against the L seed (1x2), {name(path)}"
    show(title, mc.evaluate(runs[path], base, "L", protocol))
