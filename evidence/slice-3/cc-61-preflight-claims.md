# CC-61 pre-flight — claims vs measured

Raw command output: `evidence/slice-3/cc-61-preflight.txt`.

Settled on `origin/main` @ `918304c` (CC-28 merged; slice-3 year fan-out shipped).

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| `t17` / `t18` are golden traps for `median_not_aggregatable` and `moe_aggregation_degraded` | `evals/golden_questions.toml`; `scripts/verify_golden.py` — t17 `B19013` Households; t18 `B27001` Civilian noninstitutionalized population | **Holds.** Tables exist. Warning codes appear only in the golden file, not in `api/src`. |
| Guards are pure functions over the execution record, evaluated once at assemble | `evaluate()` loops five slice-1 guards; `assemble()` calls `evaluate(record)`; `GuardRecord` has `question`, `vintages`, `geo_status`, `geographies`, `rows` — no `table_id` | **Holds as a gap.** Add two slice-3 guards to that loop. No fifth tool, no new route, no graph node. |
| Medians cannot be averaged or population-weighted | no combiner exists; `math.sqrt` unused for aggregation (only `moe_not_significant` RSS of two margins) | **Holds as a gap.** Decline the computation. Weighted mean of 40k/80k with pops 100/300 is 70000; simple mean is 60000 — tests must reject both. |
| Additive estimates sum; combined MOE is `sqrt(sum(MOE_i^2))`, never a linear sum | `math.sqrt(3**2+4**2+12**2) == 13`; linear sum is 19 | **Holds.** Stdlib; no new dependency. Output must name the formula and the component count. |
| More than five areas emits `moe_aggregation_degraded`; five does not | no area-count threshold exists | **Holds as a gap.** Boundary is `n > 5`. |
| Response offers `B19001` bracket-distribution as the approximation | `_how_differs` already classifies `B19001` vs `B19013` as `distribution versus median` when both titles are in the pool; assemble does not inject `B19001` on a median-combine miss | **Holds as a gap.** Inject `B19001` when the median warning fires if the pool did not already include it. |
| Independent of CC-30 / CC-31 | `fetch_data` already returns multi-row wildcards; `resolve_geography` still returns one selected spec | **Holds.** Combine whatever `rows` already contain. Do not add geography lists or vintage policy. |
| Room in the budgets | `check_budgets.py --structural-only` | **Holds with a constraint.** `ask.py` **393/400** — aggregation math must not live there. `guards.py` **136/400**. `doc_lines` **1800/1800** — do not edit PLAN/DESIGN. `api src files` 20/40; `agent tools` 4/6; `api routes` 1/10; `domain models` 5/15 (reuse `AskWarning` / `Alternative`). |

## Decision

Two guards on the existing `evaluate()` loop. `t17` (median + combine intent in the question) emits `median_not_aggregatable` and `assemble` adds no combined median row; it offers `B19001`. Additive combine intent over `rows` appends one combined row whose estimates are sums and whose margins are RSS; `n > 5` adds `moe_aggregation_degraded`. Sentinels are dropped from the component set, not treated as zero. `finish_aggregation()` in `guards.py` is the assemble hook so `ask.py` stays under 400.

## Out of this ticket

ZCTA / non-nesting (CC-60, after CC-30). Overlapping-ACS5 override persistence (CC-62, after CC-31). Geography lists (CC-30). Vintage policy (CC-31). Charts (slice 4). A fifth tool.
