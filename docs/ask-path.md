# Ask path — live behavior

`docs/ARCHITECTURE.md` is the short inventory. This file is the execution
record for `POST /ask` after slice 3 ([CC-2](https://johnhillescobar.atlassian.net/browse/CC-2) Done).

## Loop

`run_ask` is a hand-rolled loop: `_openai_complete` then `dispatch`. Not a
graph, not `create_agent`. The model stops by emitting text; there is no
`finish` tool.

Four tools:

| tool | module | does |
|---|---|---|
| `search_tables` | `tools.py` | `index.search` top-10, then `rerank.choose`; wording pins live in `vintages.pinned_table` |
| `resolve_geography` | `geo.py` | ordered `GeoSpec` list from that vintage's `geography.json` |
| `build_url` | `tools.py` | availability matrix; empty `variables` → `001E` paired with `001M` |
| `fetch_data` | `fetch.py` | live Census; fans `years` and comparison geos (cap 5 in flight, 12 years) |

`assemble()` builds `AskResponse` from the execution record. `guards.evaluate()`
attaches warning codes from `docs/requirements.md`. None of them block.

## Finish path

`finish_tools()` in `api/src/finish.py` is not a generic filler. When the model
stops without a URL, or with the wrong listing level, an incomplete comparison,
a parentless tract pair, or an ACS1 request that never built `/acs/acs1`, it
retries: search (including a wording pin if the pool missed it); resolve
(listing rewrite; ACS1 dataset; nationwide fallback on universe mismatch);
build, unless `geo_status.nested` is False; then fetch. Non-expressible
containment stops — it does not invent nested `for`/`in`.

## Contract

`AskResponse`: `answer`, `urls[]` (one key-redacted URL per attempted request),
`legs[]` (`for_spec` identifies the geography), year buckets (`requested` /
`attempted` / `succeeded` / `failed` / `omitted`), `rows`, `moe`, `geoid`,
`universe`, `table_id`, `plan` (`ResultPlan`: selected table, estimate IDs from
the built URL, attempted years, requested years, ordered `GeoSpec`s,
`allow_overlapping_acs5`), `alternatives[]` (table ID, published title, universe,
why they differ), `comparisons[]`, `warnings[]`, optional `chart` (`ChartSpec`:
`type`, `x`, `y`, `series_by`, `title`, `show_moe`; no Vega/SVG/code) and
`chart_unavailable` when a model chart failed validation. Rows are dicts. There
is no `http_ok`. Empty `urls` means no legal URL was produced by `build_url` or
an attempted fetch — not that finish cleared the current pointer.

`CensusURL` redacts `&key=` in `__str__` / the response; `with_key()` is the
httpx site. Missing `CENSUS_API_KEY` / `OPENAI_API_KEY` raise `ValueError`.

## Years

`fetch_data(years=…)` is a parameter, not a fifth tool. A lone `in YYYY` or
`for YYYY` is that ACS5 end year (not latest). ACS1 when Census
publishes every listed member with rows; else non-overlapping ACS5 end years.
Unpublished points stay omitted (`omission_reasons[]`, `vintage_gap_2020`,
`acs1_geography_ineligible`). A variable absent or redefined mid-range — including
unpublished years before a table’s first in-matrix vintage when any dataset has a
published hole in the requested span — is `variable_not_in_vintage`, recorded on
the fetch artifact, not inferred from question text at assemble. Tract /
block-group series that
cross 2020 emit `boundary_change_2020`. An ACS1-ineligible comparison leg
destaggers **all** comparison legs to non-overlapping ACS5. A 204/404 ACS1
geography falls back to ACS5 and sets `acs1_geography_ineligible` even when
the requested years are not a series.

`allow_overlapping_acs5` is on `ResultPlan`, fetch / `plan_years`, and an
optional `AskRequest.plan` override. Consecutive ACS5 still warns
`overlapping_vintage`. Geography overrides are rebound from GEOID; submitted
`for`/`in` is not authority. Invalid overrides are HTTP 422 before `run_ask`.

## Geography

`resolve_geography` returns metadata-backed `for`/`in`, never model prose.
NAME listing ranks by place class, population, then GEO_ID; `specs[0]` is
selected. A leading token matches the NAME head or that head plus a Census
class, not an unrelated compound (`Queens` is not `Queens Gate CDP`). A
token that misses the NAME head is not retried as its last word (`valley` is
not a Valley county). A county token is the name before `county`, not the
sentence (`population of Harris County` and `what is harris county` are Harris). A
full-sentence query extracts the capitalized name after `in` / `for` / `of`
(lowercase `of` / `the` / `and` stay inside that name), not the whole question. An unspecified place with no NAME hit falls back to
the county listing; a query that already named city/place does not.
`ambiguous_place` carries ranked `GeoSpec` candidates (level, GEOID,
dataset/vintage, `for`/`in`).
`versus` / `compared to` / `compare … to` emits one executable spec per side.
A named-county parent of a tract wildcard is `for=tract:*` without listing
tracts. A named ACS5 ZCTA is `for=zip code tabulation area:<code>` with no
`in=`. ACS1 has no ZCTA row and fail-closes. Non-expressible containment is
`geography_not_nested` with no invented fetch. A `:*` wildcard stays one GET.

Runtime legality scans **all** matching `geography.json` rows
(`geo_entries()` / `legal_predicate()`). Do not use `geo_levels()`: that dict
is last-wins. `geo_levels()["county"]` is summary level 324; all counties in a
state is level 050.

An unsupported tract or block-group listing can still ship a **candidate**
wildcard URL (`legal=False`, `for=block group:*` / `tract:*`) with
`geography_unsupported`. That is not an empty `urls[]`. Empty `urls[]` means
the loop stopped before `build_url`.

## Comparisons and aggregation

`comparisons[]` carries both estimates, both MOEs, `MOE_diff`, and the 90%
conclusion. Place-vs-parent emits `shared_sample`. Additive areas combine via
`sqrt(Σ MOEᵢ²)` and warn past five (`moe_aggregation_degraded`). Combining
published medians is declined (`median_not_aggregatable`).

## UI

One Vite pane. After `npm --prefix web run build`, FastAPI serves `web/dist`
at `/` from the same origin as `POST /ask`. Census URLs are visible and
copyable (redacted). Sentinels render as `—`. The active dataset is one
normalized table (GEOID, estimate, matching MOE) from `AskResponse` rows;
a one-row scalar uses that same table. Canvas, `ChartSpec`, and the
plan strip are slice 4 ([CC-11](https://johnhillescobar.atlassian.net/browse/CC-11)).
