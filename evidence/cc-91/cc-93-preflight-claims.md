# CC-93 pre-flight — claims vs measured

Raw command output: `evidence/cc-91/cc-93-preflight.txt`.

Settled on `main` @ `e6ae064` (CC-92 post-merge E2E). Jira `CC-93` To Do, parent CC-91.
CC-76 post-merge scoreboard (`evidence/slice-3/demo-miss-analysis.md`, `git show cce74f4:evidence/latest.json`):
empty-URL trials exist; the harness reports them as `wrong table (none)` when `expect_table` is set.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| A legal URL can disappear from `urls[]` on warning / no-row / failed-fetch / unresolved assembly | `clear_series` (called from `_absorb` on every `build_url` and on geography change) sets `record.url` and `record.fetch` to empty. `series_from_record` then returns `urls=[]`. Trace: Denver `B17001` URL present, `clear_series`, assemble empty. `test_tract_within_place_drops_a_city_url` pins the unresolved finish path | **Holds.** Retention is lost at clear, not at Census. |
| Empty-URL live misses where a legal request existed, excluding never-built | CC-76 post-merge: `t16` never builds (`nested=False`). `t17` has no named tracts. `q39`/`q41`/`t07`/`q17` empty rows have no scoreboard proof a URL was built (ticket forbids raw transcripts). Owned mechanism is the measured wipe, not those IDs | **Holds as a constraint.** Do not invent URLs for `t16` from scratch. Do not pin golden IDs. Keep already-built URLs when finish clears the current pointer. |
| Retention is from execution artifacts, not prose | `assemble` takes `**series_from_record(record)` only. No URL parsed from `answer` | **Holds.** Fix `clear_series` / `series_from_record`. |
| Secrets stay redacted; dataset/vintage/E/M/`for`/`in` stay on the URL | Trace URL with `&key=secret` assembled as redacted `CensusURL` before the wipe. Wipe drops the whole URL | **Holds as a constraint.** Re-store via `str(CensusURL(...))`. |
| CC-90 / CC-89 must not be in flight | Both Jira **To Do** | **Holds.** No ResultPlan. No contract change. |

## Decision

Before `clear_series` wipes the current pointer, copy redacted `fetch.urls` and `record.url` onto `record.retained_urls`. `series_from_record` ships current fetch/built URLs when present, else the retained list. Do not invent a URL when that list is empty.

## Out of this ticket

Choosing a table/geography when none was resolved (`q39`/`q41` retrieval). Candidate UI. Informal regions. ResultPlan (CC-90). Plan overrides (CC-89). New tools/routes/dependencies/graph nodes. Budget changes.
