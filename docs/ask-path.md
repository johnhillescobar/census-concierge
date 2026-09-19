# Ask path — live behavior

`docs/ARCHITECTURE.md` is the short inventory. This file is the execution
record for `POST /ask` after slice 3 ([CC-2](https://johnhillescobar.atlassian.net/browse/CC-2) Done).

## Loop

`run_ask` is a hand-rolled loop: `_openai_complete` then `dispatch`. Not a
graph, not `create_agent`. The model stops by emitting text; there is no
`finish` tool. `finish_tools()` in `api/src/finish.py` fills required fields
when the model stops early.

Four tools:

| tool | module | does |
|---|---|---|
| `search_tables` | `tools.py` | `index.search` top-10, then `rerank.choose`; some wordings pin a table |
| `resolve_geography` | `geo.py` | ordered `GeoSpec` list from that vintage's `geography.json` |
| `build_url` | `tools.py` | availability matrix; empty `variables` → `001E` paired with `001M` |
| `fetch_data` | `fetch.py` | live Census; fans `years` and comparison geos (cap 5 in flight, 12 years) |

`assemble()` builds `AskResponse` from the execution record. `guards.evaluate()`
attaches warning codes from `docs/requirements.md`. None of them block.

## Contract

`AskResponse`: `answer`, `urls[]` (one key-redacted URL per attempted request),
`legs[]` (`for_spec` identifies the geography), year buckets (`requested` /
`attempted` / `succeeded` / `failed` / `omitted`), `rows`, `moe`, `geoid`,
`universe`, `table_id`, `alternatives[]`, `comparisons[]`, `warnings[]`.
Rows are dicts. There is no `http_ok`. Empty `urls` means the loop stopped
before `build_url`.

`CensusURL` redacts `&key=` in `__str__` / the response; `with_key()` is the
httpx site. Missing `CENSUS_API_KEY` / `OPENAI_API_KEY` raise `ValueError`.

## Years

`fetch_data(years=…)` is a parameter, not a fifth tool. ACS1 when Census
publishes every listed member with rows; else non-overlapping ACS5 end years.
Unpublished points stay omitted (`omission_reasons[]`, `vintage_gap_2020`,
`acs1_geography_ineligible`). A variable absent or redefined mid-range is
`variable_not_in_vintage`, not a silent join. Tract / block-group series that
cross 2020 emit `boundary_change_2020`.

## Geography

`resolve_geography` returns metadata-backed `for`/`in`, never model prose.
NAME listing ranks by place class, population, then GEO_ID; `specs[0]` is
selected and the rest stay on `geographies` so `ambiguous_place` still warns.
`versus` / `compared to` / `compare … to` emits one executable spec per side.
A named-county parent of a tract wildcard is `for=tract:*` without listing
tracts. A named ACS5 ZCTA is `for=zip code tabulation area:<code>` with no
`in=`. ACS1 has no ZCTA row and fail-closes. Non-expressible containment is
`geography_not_nested` with no invented fetch. A `:*` wildcard stays one GET.

## Comparisons and aggregation

`comparisons[]` carries both estimates, both MOEs, `MOE_diff`, and the 90%
conclusion. Place-vs-parent emits `shared_sample`. Additive areas combine via
`sqrt(Σ MOEᵢ²)` and warn past five (`moe_aggregation_degraded`). Combining
published medians is declined (`median_not_aggregatable`).

## UI

One Vite pane. After `npm --prefix web run build`, FastAPI serves `web/dist`
at `/` from the same origin as `POST /ask`. Census URLs are visible and
copyable (redacted). Sentinels render as `—`. Canvas, `ChartSpec`, and the
plan strip are slice 4 ([CC-11](https://johnhillescobar.atlassian.net/browse/CC-11)).
