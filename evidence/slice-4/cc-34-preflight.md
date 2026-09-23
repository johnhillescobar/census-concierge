# CC-34 pre-flight — claims vs measured

Raw commands in this file. Settled on `origin/main` @ `762b1f8`. Jira `CC-34`
To Do, parent CC-11. Slice 3 post-merge E2E is closed (CC-91 Done). Did not
Read E2E transcripts. Did not open CC-11 sibling stories.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| The existing completion can return the NL answer plus a narrow structured chart choice in the same tool loop | `api/src/ask.py` `_openai_complete` already returns `content` on the stop turn (`tool_calls` empty). `run_ask` assigns that string to `answer` with no second `complete()` call. Parsing `{answer, chart}` from that same `content` adds no model call, no fifth tool, no route, no graph node | **Holds.** |
| Strict Pydantic can reject extra fields and code/SVG-like payloads before they reach the generated client | Ran `ChartSpec` with `extra="forbid"` and `show_moe: Literal[True]`. Valid bar accepted. `vega` / `svg` extras → `extra_forbidden`. `type=scatter` and `show_moe=False` → `literal_error` | **Holds.** |
| q23 and multi-year records have enough to validate `x`, `series_by`, and MOE without duplicating row data | `evidence/latest.json` scoreboard (not transcripts): q23 3/3 answered, `rows=2` (two GEOIDs). t09 Denver since 2017 `rows=7`. q01 `rows=1`. Assemble already stamps `year`/`GEO_ID` (`stamp_provenance`) and matching `M` (`moe_rows`). `ChartSpec` names roles on those fields | **Holds.** |
| Added schema/prompt text fits budgets | Structural at this SHA: api LOC 3923/4000, files 24/40, ask.py **399/400**, prompt 205/1200, docs 1577/1800, domain models 7/15, tools 4, routes 1, deps 7, p95 18.664/20, answered_rate 0.867. Plan: +1 `ChartSpec` (8/15), parse in `contract.py` (ask.py stays 399 via `**take_chart`), ~45 prompt tokens, no new tool/route/dep/file required | **Holds.** Do not raise a budget. |

## Decision

Parse `{answer, chart}` from the existing stop-turn `content`. Validate with
`extra="forbid"` enums. Invalid payload → `chart=null` and `chart_unavailable=true`.
Scalar / structural mismatch → `chart=null`, not unavailable. Prose-only content
keeps today's answer path. No second model call.

## Out of this ticket

Rendering (CC-87). Plan strip, canvas shell, CSV, `ResultPlan`. Vega grammar.
Raising any budget.
