# CC-74 pre-flight — claims vs measured

Raw command output: `evidence/slice-3/cc-74-preflight.txt`.

Settled on `origin/main` @ `452fd90` (CC-14 PR #49 merged). Jira `CC-74` To Do, parent CC-2, supersedes CC-69. CC-28 and CC-72 are Done.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| Every point identifies dataset, vintage/end year, period, table, variable, GEOID, estimate, matching 90% MOE | Rows are Census dicts plus `year`; `AskResponse.table_id` / `geoid` are response-level; `estimatePairs` already pairs `B…E` with `B…M`. No `dataset`, `vintage`, or `period` on a point. `ask.py` `_loc` 400/400 | **Holds as a gap.** Stamp those keys onto each row at assemble (untyped dicts, no `SeriesPoint` model). Period is ACS1 `YYYY` / ACS5 `{year-4}-{year}`. Do not add a domain model. |
| Missing or sentinel MOE is explicit and never represented as usable zero | `_MISSING` in `guards.py` already drops sentinels from numeric compare/combine. `_moe_rows` copies `"-555555555"` onto `moe[]`. Web `formatCensusValue` renders sentinels as `—`, not `0`. `formatCensusValue("0")` is untested | **Holds as a gap on the contract.** `moe[]` maps sentinels to `None`. Leave the Census string on `rows` (as returned). Real `"0"` stays `"0"`. |
| `t13` emits localized `boundary_change_2020` when a tract/block-group series crosses the redraw | `t13` exists (`expect_warning = "boundary_change_2020"`). `evaluate` names: overlapping_vintage … vintage_gap_2020 … geography_not_nested — **no** `boundary_change_2020`. ACS tract/block-group geography switches at 2020 ACS (2016–2020) vs 2015–2019 / 2010 definitions (census.gov geography-changes 2020). `GeoSpec.level` is `"tract"` / `"block group"`; AFFGEOID `140…` / `150…` | **Holds as a gap.** Guard on requested∪attempted∪row years with a year ≤2019 and a year ≥2020, only at tract/block group. Detail names the geo and the ACS periods. |
| Warning identifies affected periods/geographies and survives assembly and partial failure | `vintage_gap_2020` already ships through `assemble`. `fetch` series `span_years` then destaggers ACS5: **2018–2022 attempted is `[2018]` only** (`nonoverlapping_acs5`). 2017–2022 is `[2017, 2022]` | **Holds as a constraint.** Crossing is on **requested** years, not only attempted, or destaggered t13 never warns. Partial failure (one leg failed) still warns. County/place series do not. |
| Contract, generated client, and behavior tests stay synchronized | `AskResponse.warnings` description omits `boundary_change_2020`. Rows are `additionalProperties`. `generate_client.py --check` already exists | **Holds as a gap.** Update the warning-code description; regen client in the same commit. No new required field. |
| CC-28 and CC-72 must be Done | Both Jira Done | **Holds.** Reuse `FetchDataResult.requested_years` / `dataset`, `GeoSpec.level`, `assemble`/`evaluate`. No fifth tool. |
| Room in the budgets | `ask.py` **400/400**; `guards.py` **355**; `fetch.py` **368**; `geo.py` **352**; `vintages.py` **131**; domain models **6/15**; files **22/40**; `doc_lines` **1781/1800** | **Holds as a constraint.** Move `_moe_rows` into `guards` so `ask.py` can call `stamp_provenance`. Put `period_for` / stamp in `vintages.py`. No PLAN/DESIGN prose; checkbox + ARCHITECTURE only. |

## Decision

Stamp provenance onto existing row dicts at assemble. Null sentinel MOEs in `moe[]`. Add `boundary_change_2020` to `evaluate`, firing when a tract or block-group series' requested years cross 2020, with periods and geography in `detail`. Tests: t13 requested-span, block group, county negative, pre-only / post-only negative, partial failure, provenance keys, sentinel vs real zero. Mutation-check each.

## Out of this ticket

`variable_not_in_vintage` / per-year `variables.json` (PLAN, t14). Year-over-year significance (PLAN; t13 note). Place-vs-parent shared samples. Plan strip / charts (slice 4). Geometry conversion, TIGER, a fifth tool, raising `max_file_loc`.
