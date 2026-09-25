# CC-87 owned live proof

Did not Read E2E transcripts. UI at `http://localhost:5173/` with live
`POST /ask` on this branch (keys via `--env-file .env`).

## Unpinned owned question

Bare *"Compare the population of Austin and Dallas since 2017."* resolved
Dallas city, Texas vs Lake Dallas (`ambiguous_place`). The canvas still drew
a line for the returned rows (Period 2021–2024, estimate ± MOE, table and
URLs beneath). Screenshot: `cc-87-multiyear.png`. Geography resolution is
not this story.

## Pinned Austin + Dallas (live POST /ask)

`POST /ask` with `AskRequest.plan` pinning `B01003` and GEOIDs
`1600000US4805000` / `1600000US4819000` returned 8 rows, `chart.series_by =
geography`, no `key=` in URLs. Summary: `cc-87-austin-dallas.json`.

Rendered in the UI:

- Two series: Austin city, Texas and Dallas city, Texas
- Legend titled Geography
- Period 2021, 2022, 2023, 2024 (2017–2019 `variable_not_in_vintage`; 2020
  `vintage_gap_2020` — not interpolated)
- Error bars match table MOE (Austin 2021: 964,000 ± 705)
- Complete GEOID/estimate/MOE table beneath; 8 Census URLs

Screenshot: `cc-87-austin-dallas.png`.

## Invalid-spec fixture

Same rows with `chart=null` and `chart_unavailable=true`. Notice: "Chart
could not be drawn. The table below is complete." Table, GEOIDs, URLs, and
warnings remain. Screenshot: `cc-87-invalid-spec.png`.
