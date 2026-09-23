# CC-35 pre-flight — claims vs measured

Raw commands in this file. Settled on `origin/main` @ `0d6ffd0` (CC-34
post-merge). Jira `CC-35` To Do, parent CC-11. Did not Read E2E transcripts.
Did not open CC-11 sibling descriptions. `demo.trials` stores a row *count*,
not payloads; row shape is from `assemble()` / `stamp_provenance` /
`moe_rows`, which is the live boundary.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| Existing `estimatesByGeography` path and current multi-row table, including the separate scalar-list that must be removed | `rg estimatesByGeography web/src` → `display.ts:93`, `App.tsx:43`, `display.test.ts`. `App.tsx` branches: scalar `ul.estimates` when `areas.length === 1 && !multi` (lines 121–132); `table.geo-table` when `multi` (lines 133–166). Tests: `B01003_001E: 4838303 ± 123` (list) vs Oregon counties (table) | **Holds.** One function already walks rows; the UI still has two shapes. |
| Row/MOE index alignment and exact E-to-M suffix pairing for q02, a multi-variable fixture, and a multi-year fixture | `assemble()` on q02-shaped Baker/Benton `B19013` rows; Denver two-variable row (`B19013_001E/M` + `B19013_002E/M`); Denver 2019+2024 series. Output below. `moe_rows` pairs `{key[:-1]}M` on the **same** row (`api/src/vintages.py`). `fetch._tag_year` stamps `year` per GET | **Holds.** `len(rows)==len(moe)`; GEO_ID matches at the same index; `001E` does not take `002M`. |
| Current response rows carry dataset, vintage/period, table, GEOID, and variable provenance | Same `assemble()` output: each row has `dataset`, `year`, `vintage`, `period`, `table_id`, `GEO_ID`, and the `E`/`M` keys. `universe` is **not** on the row; it is `AskResponse.universe` (envelope). Ticket allows “universe available from the active response.” Do not infer year/dataset/period from URLs or neighboring rows | **Holds.** Envelope universe is the only gap; copy that field, do not invent the rest. |
| Normalization can stay frontend-owned without backend per-row models or a table/grid dependency | `AskResponse.rows` are untyped dicts (`contract.py`). `web/package.json` has no grid library (`rg ag-grid\|tanstack\|datagrid web` empty). `api src LOC` **4000/4000** — no backend lines. `web src LOC` 1018/3000 | **Holds.** Do not raise a budget. Do not add a domain model per row. |

## Probe output (assemble, not transcripts)

```
period_for acs5 2024 2020-2024
period_for acs1 2023 2023
--- q02-shaped assemble
n_rows 2 n_moe 2 geoid '' universe Households table B19013
0 dataset acs5 year 2024 vintage 2024 period 2020-2024 table_id B19013 GEO_ID 0500000US41001
0 E 52000 moe_M 2400 index_geoid_match True exact_suffix True
1 dataset acs5 year 2024 vintage 2024 period 2020-2024 table_id B19013 GEO_ID 0500000US41003
1 E 71000 moe_M 3100 index_geoid_match True exact_suffix True
--- multi-var
001E->001M 110 6
002E->002M 90 5
no_cross True
--- multi-year
0 year 2019 vintage 2019 period 2015-2019 dataset acs5 table_id B19013 E 100 M 5
1 year 2024 vintage 2024 period 2020-2024 dataset acs5 table_id B19013 E 110 M 6
--- universe on row? False response.universe Households
```

`CC-34` live-chart capture (`evidence/slice-4/cc-34-live-chart.json`, not a
transcript): q23 `rows=2` with two GEOIDs; Denver income `rows=7` with years
2017–2019 and 2021–2024.

## Active result

Jira CC-88 is still To Do. Committed state is `App` `result: AskResponse | null`
(`web/src/App.tsx`). This story uses that field. No second canvas store.

## Decision

Replace `estimatesByGeography` + the scalar `<ul>` with one
`normalizeActiveDataset` that emits one visible row per geography × year ×
`E` variable. Table, later chart, and later CSV read that array. Invalid or
missing MOE is `null` (render `—`), never borrowed, never zero. Sentinels
are `null` in the stored raw fields. Locale grouping is display-only.

## Out of this ticket

Two-pane shell (CC-88). Plan strip (CC-37). CSV (CC-49). Vega rendering
(CC-87). `ResultPlan` (CC-90). Raising any budget. Backend row models.
