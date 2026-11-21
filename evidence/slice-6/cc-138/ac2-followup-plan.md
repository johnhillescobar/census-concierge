# CC-138 non-latency acceptance follow-up

Base `918ffb98c5de4c417bc211af583e4ad220f90e47`. The owner directed p95 to CC-3 and requested work on the remaining AC2 issues. The initial batch covered the reproducible alternatives defect and exact comparison arithmetic. The repair validation below records the final paired comparison.

| ID | Expected outcome | Verification |
| --- | --- | --- |
| TC1 | The application retrieves its normal published candidate pool even when the model requests one result. | Wire regression with a grounded alternative and an unpublished distractor |
| TC2 | A later search does not erase display candidates for a validated result or reopen those candidates for a new build. | Wire regression with different search pools, a rejected stale candidate, and a late provider failure |
| TC3 | Exact ties in answered and empty-result counts do not become regressions, and a zero bootstrap lower bound does not count as a proven gain. | Synthetic count-matched and target comparisons plus strict-loss controls |
| TC4 | The GEOID split, multi-URL results and bounded provider-failure handling remain verified. | Existing Responses, geography, and full offline suites |
| TC5 | A late search cannot erase the validated table's measure metadata or permit summing two medians. | Cold-review reproduction and assembly regression test |

Preflight reproduced empty alternatives through a singleton search or later replacement of a valid larger pool. The live benchmark recorded one alternatives miss alongside a wrong table and geography-level mismatch. It did not record the tool state, so the reproduction identifies reachable defects without assigning the live miss to one of them.

The comparator subagent reproduced equal trial totals failing after summing rounded fractions, equal empty totals reporting a positive delta, and a zero bootstrap bound incorrectly passing the positive-gain rule. The repair keeps paired family counts integral until conversion to rates. The scorer, cohort definitions, thresholds and registered results remain intact.

Before the repairs, all six new cases failed for the expected reasons. The three `/ask` responses still returned the selected table, URL and row, but omitted its legitimate alternatives. The three comparator failures matched the independent synthetic reproduction.

The owner approved the expanded cohorts, historical use of A0, and same-window comparison. L still requires an eligible merged-main run.

The first cold review reproduced a false total of 110,000 from two county medians after a later search emptied the working pool. Display and aggregation now resolve the same validated candidate metadata. The regression test failed on the old code because the median warning was absent.

The cold rerun reproduced the same false total for a pinned table outside the build's search pool. A result now retains the first pool containing its accepted table, including a matching search that arrives after the build. An unrelated pool cannot suppress that search. Tests cover standard selection, a pinned result with a late matching search, and a subsequent empty search after the match.

## Repair validation

The repair recovers an accepted Census plan after model failure when its fetch has yet to run. It keeps URLs and statuses for attempted legs and keeps additive poverty-bracket counts separate from true ratios and medians. At application commit `fa319f0f4cdbaaadcf5e531e6a93a730f813b86c`, 1,429 offline Python tests passed, with 34 skipped and 8 expected failures. Independent mutations reproduced both final failure paths. Ruff, mypy, structural budgets and automated invariants passed. The cold rerun flagged the inherited p95 scoreboard and two recovery cases. The final repair addressed both cases and reran the offline suite.

The measured checkout `7230143564dc56196f70976c97f0253ac85a3d3d` adds the same frozen cohorts used on the control overlay `35e5f5d4caa3407e11dd976e22288952ec2d5cc0` atop GitHub `main` at `84c3c80ae38d661028fd35c31c9feb44d67370ca`. The window collected B1, P1, P2 and B2 at repeat 3, for 1,248 demo trials. Comparisons reuse the pinned expanded A anchor and apply the original A checks to the unchanged long-tail cohort. The trap analysis clusters `t01/t10`, `t11/t23`, and `t16/t21` for 31 independent families.

The expanded questions are pinned in the measured commit for reproducibility. The publication branch uses the original golden file from `main` because two phrases in the expanded set flagged the repository's eval-leakage check.

| Block | Long-tail answered | Core answered | Trap answered | Selector | p95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| B1 | 92/120 | 84/90 | 90/102 | 32/40 | 22.759 s |
| P1 | 91/120 | 84/90 | 92/102 | 33/40 | 22.924 s |
| P2 | 93/120 | 83/90 | 92/102 | 32/40 | 21.503 s |
| B2 | 91/120 | 84/90 | 92/102 | 33/40 | 23.537 s |

Both pairs failed non-latency quality checks. P1 lost one long-tail trial and one all-repeats core case. Three long-tail families returned fewer rows, and long-tail empty answers rose from six to nine. P2 lost one core trial and two all-repeats core cases. Its standalone selector scored one fewer correct answer with identical selector code and inputs. Both candidates had row and empty-answer losses in the anchor checks. All 573 candidate results with rows carried the required contract fields. P2 passed 210/210 geography-grid trials and recorded synthetic alignment of 0.544. [Full aggregate](repair-window-comparison.txt) · [Closure matrix](../../closure/CC-138.toml)

A Windows file-sharing conflict blocked the runner's final status-log line after the comparator had saved its output and both ledger entries. Both entries were verified against the exact trial-snapshot hashes. The aggregate in this branch is a UTF-8 copy of the saved comparator output.
