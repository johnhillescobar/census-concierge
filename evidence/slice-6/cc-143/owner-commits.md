# CC-143: the commits only the owner can make

`check_invariants.py --base origin/main` rejects each of these on a branch, by design. They go
straight onto `main`, each as its own commit, in this order. Everything else is in the PR.

## 1. `budgets.toml`: exceptions for the floors main already misses (AC8, AC9 first commit)

Insert above the `# --- budget change log ---` line. Baselines are the pooled values of the two
stored runs of main 29c0518 (`stored-runs.txt`, "L seeded from the two stored runs of main").
The ticket on each line is the one that restores the floor: `CC-127` is where PLAN.md says the
20 s ceiling is judged; the other two are yours to name (I found no open ticket that owns the
selector's fall from 0.75 to 0.425, or the long-tail rate).

```toml
# Floors main already misses (CC-143). Owner-only, in its own commit: check_invariants rejects one
# added with any other change. An exception holds while the value is no worse than its baseline
# by the rule in evals/metric_protocol.toml; delete it when its ticket restores the floor.
[[exception]]
metric   = "answered_rate_min"
baseline = 0.683
approved = "<date> <owner>"
ticket   = "CC-<n>"

[[exception]]
metric   = "selector_at_1_min"
baseline = 0.5875
approved = "<date> <owner>"
ticket   = "CC-<n>"

[[exception]]
metric   = "p95_latency_seconds"
baseline = 28.844
approved = "<date> <owner>"
ticket   = "CC-127"
```

`uv run python scripts/check_budgets.py` then prints `excpt` on those rows instead of `FAIL`.
The code that reads them is in the PR; until it merges, main ignores the block.

## 2. `evals/metric_protocol.toml`: ratify the rule (AC9 second commit)

Commit this branch's file (`git show cc-143/acceptance-gate:evals/metric_protocol.toml`) with any
number you want changed, and replace the header paragraph that starts `PROPOSED, NOT RATIFIED`
with your ratification line. The numbers and what each costs are in `noise.txt`.

Between this commit and the merge of the PR, the tests on main fail: the code there still reads
`sampling.max_regression`, which the ratified file no longer has. Merge the PR straight after.

If you change a number, tell me: `TC1` (both stored same-code pairs pass) needs
`rate_drop_max >= 0.067`, `small_group_lost_questions >= 0.67`, `empty_rise_max >= 0.017`,
`rows_lost_questions_max >= 1`, `selector_drop_max >= 0.325` and `p95_rise_max_seconds >= 1.93`;
`TC2` (6 broken long-tail questions fail) needs `rate_drop_max < 0.083`.

## 3. After the PR merges: seed L (AC7)

```
uv run python scripts/metric_compare.py register L evidence/metrics/runs/main-b1.json evidence/metrics/runs/main-b2.json --head 29c051860b8430d4319ad918669e18351dc9e779 --label "seed: the two stored runs of main 29c0518 (2026-11-24), judged under the rule ratified in CC-143"
git add evidence/metrics/references.json && git commit -m "CC-143: seed reference L from the stored runs of main"
```

## 4. Then AC13

One `make eval` + `make demo` run on merged main, and
`uv run python scripts/metric_compare.py compare <post-merge run> --record`. If a row is red, the
three-step rule in `docs/playbooks/run-slice.md` applies.
