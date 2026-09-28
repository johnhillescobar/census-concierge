# CC-49 owned live proof — q04, "Poverty rate by census tract in Detroit"

Run against `feat/cc-49-csv-export` (tip `35c72fe`) built and served for real:
`npm --prefix web run build` then `uv run uvicorn src.main:app --port 8000` with
`.env` exported into the shell (`api/src` deliberately does not auto-load
`.env` — only the eval/demo scripts do, per `pyproject.toml`'s comment; a
fresh dev pointed at `make serve` without exporting first gets a 500 with
`ValueError: missing CENSUS_API_KEY`, which is what happened on the first
attempt here before the shell was fixed — not a CC-49 bug). Driven with a real
Chromium browser via Playwright (not vitest/jsdom, which cannot do this — see
`cc-49-preflight.md`).

## 1. Initial ask, download, and comparison

Typed the exact `q04` text from `evals/golden_questions.toml`: "Poverty rate
by census tract in Detroit". The agent resolved **Detroit city, Michigan**
(`1600000US2622000`), table `B17001`, one row — not per-census-tract
geography. This is a pre-existing retrieval/geography-resolution behavior
unrelated to CC-49 (CSV export renders whatever `normalizeActiveDataset`
returns, proven row-count-agnostic by the multi-row fixtures already in
`display.test.ts`/`chart.test.tsx`/`csv.test.ts`); not fixed here, noted for
whoever owns geography-granularity inference.

Visible table:

| GEOID | Name | Dataset | Year | Period | Table | Variable | Estimate | MOE |
|---|---|---|---|---|---|---|---|---|
| 1600000US2622000 | Detroit city, Michigan | acs5 | 2024 | 2020-2024 | B17001 | B17001_001E | 628,888 | 541 |

Clicked "Download CSV" -> `B17001-acs5-2024.csv`. Full byte-level check
(`python -c "open(...).read()"` plus a raw-bytes check for the BOM and line
endings):

```
dataset,vintage,period,table_id,variable,GEO_ID,NAME,estimate,moe,universe
acs5,2024,2020-2024,B17001,B17001_001E,1600000US2622000,"Detroit city, Michigan",628888,541,Population for whom poverty status is determined
```

- Row count: 1, matches the visible table's 1 row.
- GEOID, variable verbatim: `1600000US2622000`, `B17001_001E`.
- Estimate/MOE raw, unformatted: `628888` / `541` (table shows `628,888` / `541` with display-only comma grouping from `formatCensusNumber`, which the CSV correctly bypasses).
- Universe matches the "Universe" definition shown next to the table.
- First 3 bytes of the file: `EF BB BF` (UTF-8 BOM) — confirms the Gate-2 BOM fix works in a real browser, not just the mocked unit test.
- Line ending: `\r\n` throughout.
- Filename: `B17001-acs5-2024.csv`, matching `table_id-dataset-vintage.csv`.

## 2. Successful plan refinement -> CSV replaced

Clicked the "B17001A" related-table button (Sex-by-Age poverty, White-alone
universe). Plan strip updated to table `B17001A`, universe "White alone
population for whom poverty status is determined", table now shows estimate
`70,715` / MOE `2,631`.

Downloaded again -> filename changed to `B17001A-acs5-2024.csv`
(`evidence/slice-4/cc-49-live-proof-B17001A-acs5-2024.csv`, kept as an
artifact):

```
dataset,vintage,period,table_id,variable,GEO_ID,NAME,estimate,moe,universe
acs5,2024,2020-2024,B17001A,B17001A_001E,1600000US2622000,"Detroit city, Michigan",70715,2631,White alone population for whom poverty status is determined
```

Table id, variable, raw estimate/MOE, and universe all updated to match the
amended result — CC-49's "post-refinement replacement" criterion, live.

## 3. Failed plan refinement -> export stays bound to the prior result

Opened "Edit plan", replaced the Table field with `NOPEXX`, clicked Apply.
UI showed the field-level alert "invalid table_id override"; the visible
table, URL, and metadata stayed on `B17001A` (unchanged).

Downloaded CSV again without changing anything else: filename was still
`B17001A-acs5-2024.csv`, byte-identical to the successful-refinement
download above. The rejected `NOPEXX` override never touched the exported
file — CC-49's "failed refinement leaves export bound to the still-visible
previous result" criterion, live.

## Not separately re-proven live here

"No export control when there are no normalized rows" is covered by
`App.test.tsx`'s Census-fetch-failure test (`rentFailure` fixture, asserts
`screen.queryByRole("button", { name: "Download CSV" })` is null) and was not
re-chased live — reliably reproducing a live zero-row Census response is not
deterministic to trigger on demand the way the unit fixture is.

## Cleanup

Server (`uv run uvicorn`) stopped after this proof. `.playwright-mcp/` is
gitignored; its downloaded CSVs are scratch except the one copied into this
evidence directory.
