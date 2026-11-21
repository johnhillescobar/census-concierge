# CC-138 non-latency acceptance follow-up

Base `918ffb98c5de4c417bc211af583e4ad220f90e47`. The owner directed p95 to a separate ticket and requested work on the remaining AC2 issues. The destination ticket and formal checker disposition are pending. This local batch covers the reproducible alternatives defect, exact comparison arithmetic, offline tests and verification. Keep measurement changes in a separate commit for the CC-133 follow-up. No registry edits, Jira writes, or live benchmark blocks are planned before comparable references and the run design are resolved.

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

Remaining acceptance work includes the A0 bridge or explicit applicability decision, the first eligible L disposition, the undersized core/trap cohorts, and a predeclared same-window B/P comparison. Wrong-table, geography and coverage issues need independent development evidence before changing execution. P95 scope and delivery remain separate from these checks.

The first cold review reproduced a false total of 110,000 from two county medians after a later search emptied the working pool. Display and aggregation now resolve the same validated candidate metadata. The regression test failed on the old code because the median warning was absent.

The cold rerun reproduced the same false total for a pinned table outside the build's search pool. A result now retains the first pool containing its accepted table, including a matching search that arrives after the build. An unrelated pool cannot suppress that search. Tests cover standard selection, a pinned result with a late matching search, and a subsequent empty search after the match.
