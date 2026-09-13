# CC-25 pre-flight — claims vs measured

Raw command output: `evidence/slice-1/cc-25-preflight.txt`.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| Slice 1 may continue; the loop already fills `AskResponse` | `origin/main` @ 7d14c79 includes CC-23; `assemble()` copies artifacts | **Holds.** This ticket polishes the contract, it does not rewire tools. |
| Declared body fields are `answer, url, rows, moe, geoid, universe, table_id, alternatives, warnings` | `AskResponse.model_fields`; OpenAPI `required` | **Holds.** Same nine names. `assemble()` always constructs all of them. |
| `url` is singular; `alternatives` and `warnings` are typed arrays | OpenAPI: `url.type=string` (no `items`); `alternatives.items.$ref=Alternative`; `warnings.items.$ref=AskWarning` | **Holds.** Slice 3 can grow `urls[]` without changing row/warning shapes. Rows are untyped dicts — no `url` key today. |
| URL includes dataset, vintage, E/M, `for`/`in`, and survives `fetch_data` failure | `BuildUrlTool` path `/year/acs/dataset`; `pair_margins`; `FetchDataResult.url` on 400 | **Holds** for the tool. Loop test already keeps the URL on HTTP 400. Header-only 200 (no rows) was not tested. |
| Every estimate is returned with its matching 90% MOE; an empty/unrelated `moe` field is not enough | `_moe_rows` keeps keys ending `M` plus `GEO_ID`/`NAME` | **Fails as written.** Column filtering is not pairing. An `E` without an `M` drops silently; `moe: []` on a successful fetch would still type-check. Assembler must map each `*_E` to `*_M`. |
| Every data row exposes a Census-compatible GEOID for TIGER joins | `get=` always asks `GEO_ID`; Census returns AFFGEOID `0500000US48201` | **Holds as a fetch, not as a contract.** Top-level `geoid` is `rows[0]`. A wildcard (many counties) would name the first county. Rows that omit `GEO_ID` are not filled from the resolved geography. |
| Universe is the selected table's published universe for that dataset and vintage | `build_url` reads `table_facts` from `availability.json.gz` | **Holds for ACS5 2020–2024.** **Fails for 2016–2019:** every table in those vintages has `universe=""`. Index universes (most recent vintage) are populated (`B19013=Households`, `B19113=Families`). Assembler should fall back to the search-hit universe when the matrix string is empty, and tests must inject vintage-specific facts so the fallback is not the only path. |
| Alternatives are structured `{table_id, reason}` explaining how they differ (universe, distribution vs median, collapsed, race iteration) | `assemble()` reasons are `"also retrieved"` / `"family member"` | **Fails.** CC-23 E2E shows those placeholders. `family_id("B19013A")=="B19013"`; `C15003` is a member of `B15003`; `C25045` is a member of `B25044` (stems need not match). Reasons must be classified from IDs + universes + titles, and collapsed only from the member list (the fold is evidence, not a stem regex). |
| Census keys absent from URLs, exceptions, logs, evidence | `CensusURL` strips `key=`; `with_key` is the httpx site | **Holds.** Do not format URLs any other way. |
| OpenAPI is stable and explicit for a future TS client | Components: `AskRequest`, `AskResponse`, `Alternative`, `AskWarning` | **Holds on names and `$ref`s.** Properties have no `description`. Add `Field(description=...)` so the schema documents the contract; do not assert on the wording. |
| Five slice-1 guards | Jira CC-22 | **Out of this ticket.** `warnings` stays a typed array, empty until CC-22. |
| `run_demo.py` / `make demo --repeat 3` | Jira CC-26 | **Out of this ticket.** E2E is `make eval` plus a live `POST /ask` (same as CC-23). |
| Room in the budgets | `check_budgets.py --structural-only` | **Holds for code.** tools 4/6, schemas 8/12, models 4/15, files 18/40, LOC 1906/4000, largest file 356/400 (`geo.py`), `ask.py` 286. **`doc_lines` 1800/1800.** A PLAN.md STATUS paragraph cannot be appended. See recommendation below. No new tool, route, model, or prescriptive doc. |

## Decision

Polish `assemble()` and the OpenAPI field descriptions. Do not add a tool, a guard, a fifth model, or `urls[]`. Classify alternative reasons; pair each estimate with its `M`; put AFFGEOID on every row and only set top-level `geoid` when it names one geography; keep the URL on fetch failure and on zero rows.

## Budget recommendation (not performed)

`doc_lines` 1800 → 1825. PLAN.md STATUS is the slice ledger the playbook requires after E2E; CC-19 and CC-23 already filled the cap. Appending CC-25's STATUS is ~8–12 lines. Deleting prior STATUS to make room would erase the evidence pointer the next session rebuilds from. `ARCHITECTURE.md` is already excluded for the same "must grow with the system" reason; PLAN STATUS is the other ledger. Do not raise `max_file_loc`, `domain_models`, or `api_src_files` — this change fits those.
