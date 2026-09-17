# CC-73 pre-flight — claims vs measured

Raw command output: `evidence/slice-3/cc-73-preflight.txt`.

Settled on `origin/main` @ `a0de68c` (CC-72 PR #44 merged). Jira `CC-73` To Do, parent CC-2, supersedes CC-64. CC-28 is Done. CC-63 is In Review in Jira; GeoSpec shipped in PR #35 (`8461870`) and is on this HEAD.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| “All tracts in Wayne County, Michigan” emits one spec and URL using `for=tract:*&in=state:26 county:163` | live resolve `legal=False nested=True specs=[]` `tract nested in unresolved county`; ACS5 2024 tract row `requires=('state','county')` `wildcard_for='county'`; `legal_predicate` authorizes that pair; MI county listing n=83, Wayne is `county:163 in=state:26`; one GET of `tract:*&in=state:26 county:163` is **HTTP 200 / 627 rows** | **Holds as a gap.** Parent county is never listed, so the wildcard never emits. Resolve Wayne via that state's county listing, then emit **one** `tract:*` spec. Do not list 627 tracts. `all tracts in Michigan` stays illegal (`in={state}` is `None`). |
| “Median gross rent in Austin versus the Texas average” emits two ordered legs: Austin place then Texas state | q23 / versus queries list `place in=state:48` then match **0** (token is the whole sentence). `Austin, Texas` live is `place:05000 in=state:48` `1600000US4805000`; `Texas` is `state:48`; `the Texas average` matches no place. Fixture Austin is `place:4805000` (GEOID concat, not the live `for` code). B25064 Austin **1729±14** and Texas **1403±4** both HTTP 200 | **Holds as a gap.** Split on `versus` / `compared to` / `vs`; resolve each side; keep order. A right-hand side that is only the named state plus “average” is the state spec, not a place. |
| Wildcards are not expanded into one request per returned area; independent geographies remain independent legs | Oregon `county:* in=state:41` is already one spec and does not list. `CensusURL.for_is_wildcard` is True on the Wayne tract URL. `fetch_data` fans **years**, not specs; `last_url` / `last_geography` are singular; `_absorb` keeps `specs[0]` | **Holds as a gap on the fetch side.** Reuse year fan-out: rewrite `for`/`in` on the built URL (`with_geography`, like `with_year`). A wildcard spec stays one GET. Two comparison specs are two legs. Ranked same-name alternatives stay `specs[0]` (Springfield), not N fetches. |
| One failed geography leg retains its URL/reason without discarding successful legs or corrupting accounting | Year partial-failure already does this (`ok = any(leg.ok)`). `RequestLeg` fields are `year, url, ok, status_code, detail` only. `_pack` sets `attempted_years = [leg.year for leg in legs]` | **Holds as a gap.** Two geo legs in one vintage must not duplicate `2024` in the year buckets. `legs[]` carries geography identity (`for_spec` on `RequestLeg`, no new model). Year lists stay unique vintages. Client regen in the same commit. |
| CC-28 and CC-63 must be Done; reuse fan-out and GeoSpec | CC-28 Done; CC-63 In Review (no `e2e-post`); GeoSpec + years fan-out are on `a0de68c`. `FetchDataInput` is `years` only | **Holds as code, not as Jira.** Reuse `GeoSpec` / `plan_years` / `Semaphore(5)`. Do not wait on the CC-63 ticket close. Do not add a fifth tool. |
| Room in the budgets; tests + mutation check | `geo.py` **400/400**; `ask.py` **395**; `fetch.py` **341**; `doc_lines` **1800/1800**; tools **4/6**; schemas **8/12**; domain models **6/15**; files **21/40** | **Holds as a constraint.** Extract from `geo.py` before adding parent-resolution or versus-split. Touch `fetch.py` and `census_url.py`. Five lines in `ask.py`. No PLAN/DESIGN. |

## Decision

Extract enough out of `geo.py` to add: (1) named-county parent resolution so a tract wildcard becomes `for=tract:*&in=state:26 county:163` without listing tracts; (2) versus-split that emits `[Austin place, Texas state]` as the executable specs, not as `ambiguous_place` alternatives.

`fetch_data` fans those specs the way it fans years. `CensusURL.for_is_wildcard` keeps a `:*` spec as one Census GET. Independent specs are independent legs; a failed leg keeps its URL. `ambiguous_place` stays “one name, many matches” — two comparison legs must not trip it.

Tests: Wayne wildcard cardinality (one spec, one URL, 627 is a row count not a request count), versus order, wildcard preservation, two-leg success, partial geo failure. Mutation-check each.

## Out of this ticket

Statistical significance and warning wording (ticket). Place-vs-parent shared-sample note (PLAN / later). Overlapping-ACS5 override UI (CC-72). Charts and plan strip (slice 4). A fifth tool, route, or graph node. Raising `max_file_loc`. PLAN/DESIGN edits.
