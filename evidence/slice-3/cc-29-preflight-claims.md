# CC-29 pre-flight — combined umbrella vs measured

Settled on `feat/cc-29-series-guards` @ `32749b2` (CC-61 PR 33 + CC-60 PR 34).
`origin/main` was **not** merged in. Combined gates run against this branch first.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| CC-60, CC-61, CC-62 Done through their gate workflows | Jira + `git log origin/feat/cc-29-series-guards`; PRs 33 and 34. CC-62 has no PR, no comments, no commits | **CC-62 does not hold.** Marked Done with no implementation. Vintage-policy default remains CC-31. Overlapping-ACS5 *warning* already fires from slice 1 `overlapping_vintage`. Override persistence is the missing piece. |
| `t10` → `overlapping_vintage` | `evals/golden_questions.toml`; `guards.overlapping_vintage` | **Holds.** Same code as t01; consecutive ACS5 end years in `record.vintages` or `YYYY-YYYY` spans of 4. |
| `t15` → `zcta_not_zip` | `guards.zcta_not_zip`; tests in `test_guards.py` | **Holds.** ZIP language warns; valid ACS5 ZCTA still ships. |
| `t16` → `geography_not_nested` | `guards.geography_not_nested`; `geo_status["nested"]` | **Holds.** No invented fetch. |
| `t17` → `median_not_aggregatable` | `guards.median_not_aggregatable`; `finish_aggregation` | **Holds.** No combined median; `B19001` offered for B19013. |
| `t18` → `moe_aggregation_degraded` | `guards.moe_aggregation_degraded`; RSS `sqrt(sum(MOE_i^2))`; `n > 5` | **Holds.** |
| Warnings stay non-blocking | `assemble` always returns `AskResponse` with `warnings[]` | **Holds.** |
| Consecutive-ACS5 override cannot drop `overlapping_vintage` | no `AskRequest` override field; `assemble` has no strip path | **Holds as a gap (CC-62).** Warning already cannot be stripped because nothing removes it. Explicit override contract is not on this branch. |
| Combined tests cover t10 and t15–t18 | `api/tests/test_guards.py` | **Holds for unit tests.** Live demo subset still drops `t09+` (`is_slice1` in `run_demo.py`); those traps are Gate 1, not `make demo`. |

## Decision

Run Gate 1 / Gate 2 / E2E on this branch as-is. Do not merge `origin/main` (CC-63) until those gates persist. CC-62 override persistence is a child gap, not this gate session.

## Out of this gate

Merge of `origin/main` / CC-63 GeoSpec. Vintage selection (CC-31). Charts (slice 4).
