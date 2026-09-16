# CC-70 pre-flight — claims vs measured

Raw command output: `evidence/slice-3/cc-70-preflight.txt`.

Settled on `origin/main` @ `d45618e` (CC-29 PR #36 merged; PR #37 docs). Jira `CC-70` To Do, parent CC-2, relates to CC-29. Copilot's three suppressed findings on PR #36 are this ticket.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| `"Washington state"` / `"the state of Washington"` leftover after `place_token` is treated as an unresolved named parent | `place_token(..., "washington")` returns `"state"`; `detect_level` on that parent is `"state"`; `in_parts` stays empty because host is neither `""` nor `"washington"`; fail-closed `county nested in unresolved state` | **Holds as a gap.** Both acceptance queries resolve `legal=False nested=True specs=[]` and assemble `geography_unsupported`. Bare `"all counties in Washington"` already ships `county:* in=state:53`. |
| Parentless ZCTA must not copy `in=state` before the nesting check | `"all ZCTAs in Oregon"` / `"ZCTAs within Oregon"` copy `in_parts["state"]="41"` then `legal_predicate` returns `None` with default `nested=True` | **Holds as a gap.** Assemble emits `geography_unsupported`. Same ZCTA against a *named* county (`all zctas in Harris County`) already emits `geography_not_nested` because `detect_level` finds `county` first. Live ACS5 2024 ZCTA `860` `requires=()` `wildcard=''`; `nests_in(zcta, state)` is False. |
| Legal state wildcards for places and counties stay legal | `all counties in Oregon` → `county:* in=state:41`; `all places in Oregon` → `place:* in=state:41`; q02 is that Oregon county wildcard | **Holds.** `"all places in Washington state"` currently fails the leftover-`state` path too — same host-check fix covers it. Do not broaden ZCTA into a state wildcard. |
| `moe_aggregation_degraded` and `finish_aggregation` run `combine_additive` twice | `guards.py:330` uses `record.rows`; `:355` uses assemble's `_rows_with_geoid` copy after `evaluate()` already ran the guard | **Holds.** Local arithmetic, not the p95 driver (Copilot's latency claim does not hold). Optional in this PR if it fits; warning `count` and combined `component_count` must stay the same number. |
| Largest file is 398/400; do not raise `max_file_loc` | `check_budgets.py --structural-only`: largest **398** (`ask.py`); `geo.py` **384/400**; `guards.py` **318/400**; `doc_lines` **1800/1800** | **Holds as a constraint.** Touch `geo.py` (16-line room). Do not edit `ask.py`. Do not edit PLAN/DESIGN. Deduping combine lives in `guards.py` if taken. |
| Do not reopen CC-29; no fourth implementation on that umbrella | CC-29 relates-to link; HEAD is merged `main`, not `feat/cc-29-series-guards` | **Holds.** New branch off `main`. |

## Decision

In `ResolveGeographyTool._arun`, treat a leftover host that is only a state descriptor (`state`, optionally with already-stripped noise words) as empty so `in_parts["state"]` gets the FIPS. Do **not** add `state` to `_NOISE`: `place_token("State College, Pennsylvania", "pennsylvania")` is `"state college"`. Copy `in=state` only when `nests_in(for_level, "state")`; otherwise leave `in_parts` empty so the existing `nested=False` fail-closed branch fires for `"all ZCTAs in Oregon"`. Places and counties keep the legal state wildcard.

Optional, same PR: compute `combine_additive` once in `finish_aggregation` and derive `moe_aggregation_degraded` from that result.

Regression tests for the four acceptance queries; mutation-check each. Named-ZCTA 90210 and `all counties in Oregon` stay legal.

## Out of this ticket

Reopening CC-29. Vintage policy (CC-31 / CC-68). Overlapping-ACS5 override persistence (CC-62). Multi-geography fetch (CC-64). ZCTA ACS1 rejection-before-fetch (CC-65). Charts and plan strip (slice 4). A fifth tool, route, or graph node. Raising `max_file_loc`.
