# Ask path — live behavior

`docs/ARCHITECTURE.md` is the short inventory. This file is the execution record for `POST /ask` after slice 3 ([CC-2](https://johnhillescobar.atlassian.net/browse/CC-2) Done).

## Loop

`run_ask` is a hand-rolled loop: `_openai_complete` then `dispatch`. Not a
graph, not `create_agent`. The model stops by emitting text; there is no
`finish` tool.

Four tools:

| tool | module | does |
|---|---|---|
| `search_tables` | `tools.py` | `index.search` top-30 (`POOL_DEPTH`) on the model's `topic` (the question if none), keeping only tables the dataset's latest vintage publishes, then `rerank.choose` over the full question; the answer lists the pick plus the best 9; no wording pin picks or adds a table |
| `resolve_geography` | `geo.py` | ordered `GeoSpec` list from the model's structured places and that vintage's `geography.json` |
| `build_url` | `tools.py` | availability matrix; empty `variables` → `001E` paired with `001M` |
| `fetch_data` | `fetch.py` | live Census; fans `years` and comparison geos (cap 5 in flight, 12 years) |

`assemble()` builds `AskResponse` from the execution record. `guards.evaluate()`
attaches warning codes from `docs/requirements.md`. None of them block. Answer figures: `docs/ARCHITECTURE.md`.

## Finish path

`finish_tools()` in `api/src/finish.py` is not a generic filler. When the model
stops without a URL, or with the wrong listing level, an incomplete comparison,
or an ACS1 request that never built `/acs/acs1`, it
retries: search (only if the pool is empty); resolve
(from the model's own split report, including its dataset and years; never from the question's words);
build, unless `geo_status.nested` is False; then fetch. Non-expressible
containment stops — it does not invent nested `for`/`in`.

A listing the loop resolved to the wrong parents, the wrong level, or nothing gets one extra model call
([CC-103](https://johnhillescobar.atlassian.net/browse/CC-103)). It needs only the question, so
`run_ask` starts it as a task beside the loop (`plan_split` in `finish.py`) and `finish_tools` uses its
finished result; the end of the request never calls the model. For a listing the model reports
`{parents, unit, parent_level}`; for a direct request or comparison, `places`. `resolve_geography` re-runs
with them when the loop's resolution is not one all-wildcard spec per parent at `unit`, or a comparison
shows fewer legs than `places`. Nothing reported means nothing is resolved: finish never reads the question
for a place or level. A failed call or repair never fails the answer and restores the loop's own
resolution; the task is always cancelled when the request ends.
`ExecutionRecord.intent` (`GeoIntent`, `geo_level.py`) is the one place the model's requests are kept: the loop's
calls fill `levels`, `legs` and `unmet`, the split report fills the rest once (`adopt`). `legs` tracks single-place
calls (a same-place refinement, "Springfield" then "Springfield, Illinois", replaces its entry); finish replays
them as one `places` call. What ran is `record.geographies`; what the lookup guessed is `geo_status["inferred"]`.
`fetch_data` retries when `record.fetch is None or not record.fetch.ok`, not bare `is None`.

If a tool fails twice in a row, `run_ask` catches that and — if `finish_tools`
went on to recover real rows anyway — replaces the raw `"<tool> failed
twice"` string with a plain, deterministic sentence built from the record
(never a second model call). If nothing was recovered, the raw failure stays
visible rather than being papered over.

## Contract

`AskResponse`: `answer` (framing, then the figures code renders), `urls[]` (one key-redacted URL per
attempted request), `legs[]` (`for_spec` identifies the geography), year buckets (`requested` /
`attempted` / `succeeded` / `failed` / `omitted`), `rows`, `moe`, `geoid`, `universe`, `table_id`,
`plan` (`ResultPlan`: selected table, estimate IDs from the built URL, attempted years, requested years,
ordered `GeoSpec`s, `allow_overlapping_acs5`), `alternatives[]` (table ID, published title, universe,
why they differ), `comparisons[]`, `warnings[]`, optional `chart` (`ChartSpec`: `type`, `x`, `y`,
`series_by`, `title`, `show_moe`; no Vega/SVG/code) and `chart_unavailable` when a model chart failed
validation. Rows are dicts. There is no `http_ok`. Empty `urls` means no legal URL was produced by
`build_url` or an attempted fetch — not that finish cleared the current pointer.

`CensusURL` redacts `&key=` in `__str__` / the response; `with_key()` is the
httpx site. Missing `CENSUS_API_KEY` / `OPENAI_API_KEY` raise `ValueError`.

## Years

`fetch_data(years=…)` is a parameter, not a fifth tool. The years and the product (`build_url.dataset`)
are what the model states in its calls, or in the split report when it stopped short; the question's words are
never read for them. A stated lone year is that ACS5 end year (not latest). ACS1 when Census publishes every listed member with rows; else non-overlapping ACS5
end years. Unpublished points stay omitted (`omission_reasons[]`, `vintage_gap_2020`,
`acs1_geography_ineligible`). A variable absent or redefined mid-range — including unpublished years
before a table’s first in-matrix vintage when any dataset has a published hole in the requested span —
is `variable_not_in_vintage`, recorded on the fetch artifact, not inferred from question text at
assemble. Tract / block-group series that cross 2020 emit `boundary_change_2020`. An ACS1-ineligible
comparison leg destaggers **all** comparison legs to non-overlapping ACS5. A 204/404 ACS1 geography
falls back to ACS5 and sets `acs1_geography_ineligible` even when the requested years are not a series.

`allow_overlapping_acs5` is on `ResultPlan`, fetch / `plan_years`, and an optional `AskRequest.plan`
override. Consecutive ACS5 still warns `overlapping_vintage`. Geography overrides are rebound from
GEOID; submitted `for`/`in` is not authority. Invalid overrides are HTTP 422 before `run_ask`.

## Geography

`resolve_geography` returns metadata-backed `for`/`in`, never model prose, and takes no sentence
([CC-104](https://johnhillescobar.atlassian.net/browse/CC-104)). Inputs: `places` (a direct request; 2+ is a
comparison), `parents` (a listing: every `level` unit inside them) with `parent_level` (null = state), `level`
/ `levels`. Each entry is "Place, ST" or a state alone; its state is an exact lookup on the entry (`state_of`),
its NAME token the part before the first comma. `level` `us` with no place is the nation; a null level and
no place, a listing without `level`, or a non-state parent without `parent_level` is refused for repair.
NAME listing ranks by place class, population, then GEO_ID; `specs[0]` is selected. A token matches the NAME
head or that head plus a Census class, not an unrelated compound (`Queens` is not `Queens Gate CDP`) and
is not retried as its last word. A place with a null level and no NAME hit falls back to the county listing,
flagged inferred. A listing parent (county, or the place a tract lies in) named without its state is searched across states and taken only if its best match has 4 times the people of the next (`dominant`, Census population, no list of cities); otherwise `ambiguous_place` returns the ranked candidates and nothing is selected, built or fetched. A direct single place keeps the largest match with the others as alternatives. A blank
parent fails the whole call. `ambiguous_place` carries ranked `GeoSpec` candidates (level, GEOID,
dataset/vintage, `for`/`in`). Comparison legs resolve concurrently and merge.
A named-county parent of a tract wildcard is `for=tract:*` without listing
tracts. A named ACS5 ZCTA is `for=zip code tabulation area:<code>` with no
`in=`. ACS1 has no ZCTA row and fail-closes. Non-expressible containment is
`geography_not_nested` with no invented fetch, except tracts in one named place (ACS5): the `county (or part)` row names its counties and their tracts are fetched county-wide with `geography_not_nested` naming the counties (`geo_within.py`; the place boundary is not applied). A `:*` wildcard stays one GET.

A question must carry what its level needs ([CC-102](https://johnhillescobar.atlassian.net/browse/CC-102)).
The split call (`plan_split`) also reports the question's `level`, the places it `named`, the levels of those
identified only by number inside another (`numbered`), whether a county is named (`county_named`), whether a
phrase points at a place without naming it (`pointing`), and whether it `asks_for` `tables` (which table holds
something: never stopped) or `data`. On the first turn (by index), before any tool runs, `finish.incomplete` compares that with `_NEEDS`,
the minimum the API accepts (ACS5 2023): every tract or block group, the state; one county or place by number,
the state; one tract, state and county; one block group, state, county and tract. A reported name gives the state
with or without it written ("Los Angeles"): resolution finds it by NAME. For a unit identified by its number
only the parents the question states (`given`) count, not ones the model supplied; a report without `given` keeps the name rule. An entry with a digit is a code and must
ground itself (`state_of`, a GEOID); a number filed under `named` is not a place. The report is never matched
against the question's words. Short of it, `run_ask` returns at once: `geography_unsupported`, a code-written answer, no
search, fetch, URL or candidates. Any failure, a missing report or a late one fails open.

The level is the model's statement, not a reading of the question
([CC-114](https://johnhillescobar.atlassian.net/browse/CC-114)). `resolve_geography.level` is required:
a published level name, or null when the question names none; `levels` pairs one per place with
comparison legs (else refused for repair). A call without `level` is refused for repair (two refusals
stop the tool). Code runs the stated level exactly. A name not published for the dataset fails with the
published names and that refusal stands: finish neither re-resolves nor falls back, so no
URL is built; a resend at another level leaves the refused level unmet, so the mismatch names it.
`intent.levels` keeps one stated level per leg; a call that resolved nothing, and finish's repair calls
(`"origin": "repair"`), never change it. A level the model stated that could not be served (an
unsupported, refused, empty or partial result, or the call raised) stays unmet until a legal call serves it.
`geography_level_mismatch` fires when a fetched `for=` level was not stated, or a stated or unmet level
has no URL (an override is held to its own plan's levels). `geography_level_unverified` fires when no
level was stated, or code inferred one (the county fallback). A bare name with a stated null resolves to a
state or place by NAME match, unflagged.

Runtime legality scans **all** matching `geography.json` rows
(`geo_entries()` / `legal_predicate()`). Do not use `geo_levels()`: that dict
is last-wins. `geo_levels()["county"]` is summary level 324; all counties in a
state is level 050.

An unsupported tract or block-group listing can still ship a **candidate**
wildcard URL (`legal=False`, `for=block group:*` / `tract:*`) with
`geography_unsupported`. That is not an empty `urls[]`. Empty `urls[]` means
the loop stopped before `build_url`, or the question was refused as incomplete.

## Comparisons and aggregation

`comparisons[]` carries both estimates, both MOEs, `MOE_diff`, and the 90%
conclusion. Pairing is skipped before any pair is built when row pairs x estimate columns
exceeds `MAX_COMPARISON_WORK` (`comparison_too_large`); rows, URL and MOE still return.
Place-vs-parent emits `shared_sample`. Additive areas combine via
`sqrt(Σ MOEᵢ²)` and warn past five (`moe_aggregation_degraded`). Combining
published medians is declined (`median_not_aggregatable`).

## UI

Two Vite panes: chat (form and answer) and one active canvas dataset.
After `npm --prefix web run build`, FastAPI serves `web/dist`
at `/` from the same origin as `POST /ask`. Census URLs are visible and
copyable (redacted). Sentinels render as `—`. The active dataset is one
normalized table (GEOID, estimate, matching MOE) from `AskResponse` rows;
a one-row scalar uses that same table. The canvas plan strip shows the
executed `ResultPlan` (dataset, requested vs fetched years, table,
geographies with GEOID, overlapping ACS5). Edits and alternative clicks
POST that plan with the original question; they do not rewrite prompt
text. Geography is a picker over returned `GeoSpec`s. A 422 or network
failure keeps the prior dataset and shows the error on the strip.
`ChartSpec` and CSV also read this `AskResponse`. A validated `chart` renders
as frontend Vega-Lite SVG over the normalized rows; a failed spec, embed, or
over-limit series notices and keeps the table. Geography series are keyed by GEOID.
