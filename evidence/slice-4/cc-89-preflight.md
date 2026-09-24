# CC-89 pre-flight — claims vs measured

Raw commands in this file. Settled on `origin/main` @ `61566e8` (CC-90
post-merge). Jira `CC-89` In Progress, parent CC-11. CC-90 Done. Did not
Read E2E transcripts. Did not open sibling story descriptions.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| Existing `ExecutionRecord`, tool authority hooks, availability matrix, and geography metadata can enforce pinned values without a new route or tool | `ExecutionRecord` has `allow_overlapping_acs5`, `geographies`, `pool`, `table_facts`. `BuildUrlTool.allowed_tables` / `allowed_geographies` are callbacks. `FetchDataTool.question_years` is a callback; `allow_overlapping_acs5` is copied at `default_tools` construction. `dispatch` passes `call["args"]` through unchanged (`pin`/`override` absent). `_allowed` is search pool + members only. `availability.load()` + `table_facts` reject unknown tables at `build_url` with no Census GET. `legal_predicate` + `geo_entries` are local. One route (`POST /ask`), four tools. | **Holds as a gap.** Pin at `dispatch` + seed the record before `default_tools`. Do not add a route or tool. |
| Current internal `allow_overlapping_acs5` returns consecutive years and retains `overlapping_vintage` when explicitly seeded | `plan_years(..., allow_overlapping_acs5=False)` on 2017–2023 → attempted `[2017, 2022]`. Same with `True` → `[2017..2023]`. `overlapping_vintage` reads the question + ACS5 vintages and **does not inspect the flag**; seeded `True` still warns. `FetchDataTool` already fans the plan. | **Holds.** |
| Every proposed override field has one authoritative validation source and a concrete invalid fixture | See table below. | **Holds.** |
| A representative combined override can flow through the four existing tools without depending on model compliance | Scripted loop already drives search → resolve → build → fetch. Authority is the callbacks and `dispatch` args, not the model. `fetch` currently **merges** tool `years` with `question_years()`, so an override year list must be the `question_years` result too or destaggered years get expanded back. | **Holds as a gap.** Pin args in `dispatch`; point `question_years` at the override list. |
| Geography must not trust raw browser `for`/`in` | `GeoSpec.for_spec` is what `build_url` / `CensusURL.with_geography` execute. AFFGEOID on prior `ResultPlan`s is structured (`0500000US48201`, `1600000US4805000`, `860Z200US90210`). `legal_predicate` on ACS5 2024 ZCTA is code `860`; ACS1 2023 ZCTA is `None`. `ResultPlan.consistent` already 422s ACS1+ZCTA. Empty-GEOID `for`/`in` has no local authority. | **Holds.** Reconstruct clauses from GEOID. Reject a geography override with no parseable GEOID rather than execute browser `for`/`in`. Wildcard listings without GEOID are rejected (do not invent a listing subsystem). |
| Contract fits budgets | `check_budgets.py --structural-only`: api src LOC **3999/4000**, largest file **394/400** (`fetch.py`), domain models **9/15**, routes 1, tools 4. `AskRequest` is `question` only; extra `plan` is ignored. | **Holds as a constraint.** Reuse `ResultPlan` (no second override shape). Net `api/src` lines must be ≤0. Do not raise a budget. Regenerated `packages/client` is the drift gate. |

## Override field → authority → invalid fixture

| field | authority | invalid fixture |
| --- | --- | --- |
| `table_id` | availability matrix via existing `table_facts` | `NOPE` / absent id for dataset+years |
| `variables` | matrix suffixes for that table; `pair_margins` still adds `M`; `ResultPlan.consistent` rejects a prefix outside `table_id` | `B19013_999E`; `B01003_001E` on `table_id=B19013` |
| `dataset` / years | `plan_years` + matrix membership; 2020 ACS1 stays omitted | ACS1+ZCTA (below); unpublished years omit, they do not 422 |
| `geographies` | AFFGEOID → `for`/`in`; `legal_predicate` when `geography.json` is cached; never submitted `for_spec` | empty GEOID with `for=county:201`; ACS1 + ZCTA GEOID |
| `allow_overlapping_acs5` | `FetchDataTool` / `plan_years` flag; `overlapping_vintage` still fires | not a 422; `False` is the destagger default |

Race iterations (`B19013B`) and collapsed members are matrix IDs. `_allowed` must union the override table so a deliberate pick is not dropped as “not in the search pool.” Retrieval still ranks the family; the override is the selection.

## Probe output

```
ExecutionRecord ['allow_overlapping_acs5', 'fetch', 'geo_status', 'geographies', ...]
AskRequest properties ['question']; extra plan dumped as {'question': 'hello'}
ResultPlan ['table_id', 'variables', 'dataset', 'years', 'requested_years', 'geographies', 'allow_overlapping_acs5']
_allowed B19013 pool → {'B19013', 'B19013A', 'B19013B'}
family_id B19013B → B19013
pair_margins ['B19013_001E', 'B19013_001M']
ResultPlan ACS1+ZCTA REJECT ACS1 is not published for ZCTA
ResultPlan B01003_001E on B19013 REJECT variable outside selected table
plan_years default attempted [2017, 2022]; override [2017..2023]
overlapping_vintage with flag True → overlapping_vintage
legal_predicate county+state 050; ACS5 ZCTA 860; ACS1 ZCTA None; tract in state only None
drop_incompatible 999E omitted variable_not_in_vintage; NOPE omitted
```

```
acs5 2024 geography.json.gz True, 65 rows
acs1 2023 geography.json.gz True, 19 rows, ZCTA legal_predicate None
availability.json.gz True
B19013 acs5 2024 True ['001E']; B19013B True; NOPE None
fetch merges asked years: True
FetchDataTool.allow_overlapping_acs5 is a bool copied at default_tools
dispatch does not rewrite args
t10 requested_years [2017..2023]
```

```
ok    api src LOC               3999 <= 4000
ok    largest file LOC           394 <= 400
ok    domain models                9 <= 15
ok    api routes                   1 <= 10
ok    agent tools                  4 <= 6
```

## Decision

Optional `AskRequest.plan: ResultPlan | None`. Same model as the response.
`POST /ask` stays the only route. Incoming geographies are rebound from GEOID
before the loop; submitted `for`/`in` is discarded. Seed
`record.allow_overlapping_acs5` and override years **before** `default_tools`.
`dispatch` overwrites `build_url` / `fetch_data` args from the plan and skips
`resolve_geography` when geos are pinned, so the model cannot undo the edit.
`overlapping_vintage` stays a guard. Invalid GEOID / ACS1+ZCTA / unknown table
are HTTP 422; `run_ask` is not called (no Census GET).

Compact existing `api/src` to pay for the helpers. Do not raise a budget.

## Out of this ticket

Plan-strip UI (CC-37). Two-pane shell (CC-88). CSV, Vega, persistence,
follow-up language, auth, wildcard listings without GEOID, raising any budget.
