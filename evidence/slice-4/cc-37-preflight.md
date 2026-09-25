# CC-37 pre-flight — claims vs measured

Raw commands in this file. Settled on `origin/main` @ `ec5712b` (CC-88
post-merge). Jira `CC-37` To Do, parent CC-11. CC-88/CC-90/CC-89/CC-35 Done.
Did not Read E2E transcripts. Did not open sibling story descriptions.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| Every strip field already exists on returned `ResultPlan` / `Alternative` / `AskWarning.candidates`; a missing field is a CC-90/CC-89 correction, not a frontend shadow contract | `ResultPlan.model_fields` = `table_id`, `variables`, `dataset`, `years`, `requested_years`, `geographies`, `allow_overlapping_acs5`. `GeoSpec` has `name` + `geoid` (and `for_spec`/`in_spec`, not authority). `Alternative` required `table_id`, `title`, `universe`, `reason`. `AskWarning.candidates` is `GeoSpec[]`. `AskRequest.plan` is optional `ResultPlan`. OpenAPI matches. | **Holds.** Render and POST those fields. Do not invent years/geo DTOs. |
| `years` vs `requested_years` is already distinguished on the plan | `ResultPlan.years` = issued vintages; `requested_years` = fetch request list; `AskResponse.omitted_years` is the omitted bucket. `consistent()` 422s when `years` is not a subset of `requested_years`. | **Holds.** Edit requested years; show effective/omitted as display. On submit set `years` to the requested list so the subset check passes. |
| Submitting an edit is the existing `POST /ask` with `AskRequest.plan`; no extra route or tool | `api/src/main.py` one `@application.post("/ask")`. `web/src/ask.ts` already `JSON.stringify({ question, plan })`. `askFn` in `App` currently drops the plan argument (`(question: string) => Promise<AskResponse>`). | **Holds as a gap.** Thread `plan` through `askFn`. Do not add a route. |
| Geography must not submit arbitrary `for`/`in` | Empty-GEOID override 422s at `body` (`geography override requires an executable GEOID`). `clauses_from_geoid` is the authority. `AskWarning.candidates` already carry executable `GeoSpec`s (name, GEOID). | **Holds.** Picker over `plan.geographies` ∪ `ambiguous_place` candidates with GEOID. No `for`/`in` text control. |
| Validation failures are field-addressable on the existing 422 body | Unknown table: `loc=["body","plan","table_id"]`, `msg=invalid table_id override`. GEOID: `loc=["body"]`, msg names GEOID. ACS1+ZCTA / variable-outside-table / years-not-requested: `loc=["body","plan"]` with the validator message. `ask()` currently throws `ask failed (422)` and does not read the body. | **Holds as a gap.** Parse FastAPI `detail`. Map `loc` when it names a plan field; otherwise map GEOID → `geographies`, year messages → `years`, ZCTA/dataset → `dataset`, variable → `table_id`. No API change (api src is 4000/4000). |
| Prior result stays visible while a refinement runs; failure does not clear it | CC-88: `setResult` only on success; loading keeps the previous `AskResponse`. `App` has no plan-strip submit path yet. Canvas currently asserts `querySelector("form")` is null. | **Holds as a gap.** Reuse that state transition for plan apply. Question form stays in chat; the strip form is a second, labelled form. Update the workspace test to that invariant. |
| Alternatives are selectable table overrides, not prompt rewrites | Alternatives render as `table_id — reason` text. Title and universe are on the contract and unused. Clicking is not wired. | **Holds as a gap.** Show all four fields. Click POSTs `{...plan, table_id}` with variables filtered to that table (else `variable outside selected table` 422). |
| Consecutive ACS5 stays an explicit flag; `overlapping_vintage` still ships | `allow_overlapping_acs5` is on `ResultPlan`. Guard does not inspect the flag (CC-89). | **Holds.** Checkbox initializes from the plan. Do not hide the warning after a successful overlapping run. |
| No store, persistence, extra route, or budget raise | `rg zustand\|redux\|jotai\|localStorage web/src` → none. Routes 1, tools 4. `web src LOC 1471/3000`. `api src LOC 4000/4000` (no api edit). Chart/CSV UI not present; they consume the same `AskResponse` when those stories land. | **Holds.** One `AskResponse`. Extract `PlanStrip` so `App.tsx` stays a wiring file. |

## Probe output

```
ResultPlan ['table_id', 'variables', 'dataset', 'years', 'requested_years', 'geographies', 'allow_overlapping_acs5']
GeoSpec ['level', 'name', 'geoid', 'for_spec', 'in_spec', 'dataset', 'vintage', 'codes']
Alternative required ['table_id', 'title', 'universe', 'reason']
AskWarning ['code', 'detail', 'candidates']
AskRequest ['question', 'plan']
AskResponse has plan/chart/alternatives True True True
OpenAPI candidates items GeoSpec[]
```

```
unknown table 422 loc=['body','plan','table_id'] msg='Value error, invalid table_id override'
empty GEOID 422 loc=['body'] msg='Value error, geography override requires an executable GEOID'
ACS1+ZCTA 422 loc=['body','plan'] msg='Value error, ACS1 is not published for ZCTA'
variable outside table 422 loc=['body','plan'] msg='Value error, variable outside selected table'
effective years not requested 422 loc=['body','plan'] msg='Value error, effective years were not requested'
```

```
ok    api src LOC               4000 <= 4000
ok    largest file LOC           398 <= 400
ok    web src LOC               1471 <= 3000
ok    api routes                   1 <= 10
ok    agent tools                  4 <= 6
ok    domain models                9 <= 15
```

```
Springfield MO GEOID 1600000US2970000 place:70000 in=state:29
Springfield IL GEOID 1600000US1772000 place:72000 in=state:17
Springfield VA GEOID 1600000US5175344 place:75344 in=state:51
App.askFn (question: string) => Promise<AskResponse>  # plan dropped
ask.ts already POSTs { question, plan }
canvas form currently forbidden by App workspace test
```

## Decision

Editable compact strip on the canvas, initialized from `AskResponse.plan`.
Typed controls: table ID, dataset, requested year list, geography checkboxes
from returned `GeoSpec`s (plan + `ambiguous_place` candidates), overlapping-ACS5
checkbox. Apply POSTs the original `activeQuestion` plus that `ResultPlan`.
Alternatives are the same override with a new `table_id`. Parse 422 `detail`
in `ask.ts`; show the error beside the control. Keep the CC-88 loading/failure
rule. No new route, tool, store, or budget.

## Out of this ticket

Natural-language follow-ups (slice 6). Conversation storage (slice 5). Saved
plans. Auth. Arbitrary Census `for`/`in`. Chart rendering (CC-87) and CSV
(CC-49) — the strip replaces the same `AskResponse` they will read. Wildcard
listings without GEOID. Raising any budget.
