# CC-87 pre-flight — claims vs measured

Raw commands in this file. Settled on `origin/main` @ `d84a788`. Jira `CC-87`
To Do→In Progress, parent CC-11. CC-34, CC-35, CC-88 are Done. Did not Read
E2E transcripts. Did not open sibling story descriptions.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| Selected Vega versions support layered line/bar marks plus error bars from inline data | `npm view`: vega **6.4.0**, vega-lite **6.4.3**, vega-embed **7.3.0**. `compile()` + `vega.parse()` of a layered spec with `data.values` (no `data.url`): line → marks `group,symbol,rule`; bar → `rect,rule`. Same with a null estimate row. `config.mark.invalid: "break-paths"` **throws** (`getDataSourcesForHandlingInvalidValues` undefined). `detail` on `segment` compiles. | **Holds, with a correction.** Translator assigns `segment` ids at year gaps. Do not emit `invalid: "break-paths"`. No React Vega wrapper. |
| A minimal production build reports the dependency/bundle delta and remains viable within the frontend budget | Pre-Vega `vite build`: JS **236.83 kB / gzip 74.10**. Static `import "vega-embed"`: JS **749.96 kB / gzip 256.97** (Δ +513.13 / +182.87), Vite 500 kB warning. `web src LOC` **2607/3000**. `api src LOC` **4000/4000** (no API edit). `direct_dependencies` is Python; npm chart deps do not count. | **Holds as a constraint.** Dynamic-import `vega-embed` on draw so the initial chunk stays near 237 kB. New TS must fit in **393** lines including tests. Do not raise a budget. |
| The translator can construct every Vega-Lite field and transform itself without accepting backend Vega JSON or external URLs | Generated `ChartSpec` is `type/x/y/series_by/title/show_moe` only (`packages/client/schema.d.ts`). `AskResponse.chart` is that type, not a Vega document. `web/src` has no vega-embed / react-vega. Proof spec used `data.values` only; compiled Vega JSON had **no** `"url"`. | **Holds.** Read typed `ChartSpec` fields. Build `data.values` from `DatasetRow[]`. Never spread API JSON into embed. |
| Normalized fixtures from CC-35 contain sufficient series and MOE fields | `DatasetRow` already has `year`, `period`, `geoid`, `name`, `variable`, `estimate`, `moe`, `universe`. Sentinels are `null`, not zero (`display.test.ts`). CC-35 live table: 36 GEOIDs, estimate+MOE. CC-34 live `q23` bar / Denver line. Two-geo and two-variable fixtures already in `display.test.ts`. | **Holds.** Do not invent a second row model. |

```
$ npm view vega version && npm view vega-lite version && npm view vega-embed version
6.4.0
6.4.3
7.3.0
```

```
$ node _cc87_vega_proof.mjs   # layered compile; then deleted
line-numeric OK url= false marks= group,symbol,rule
bar-numeric OK url= false marks= rect,rule
line-null OK url= false marks= group,symbol,rule
line-break FAIL Cannot destructure property 'marks' of 'getDataSourcesForHandlingInvalidValues(...)' as it is undefined.
line-filter OK
{"compiled":true,"parsed":true,"hasDataUrl":false,"markTypes":["group","symbol","rule"],"hasDetail":true}
```

```
$ npm run build   # web/, before vega import
dist/assets/index-DB7wVAIa.js   236.83 kB │ gzip: 74.10 kB

$ npm run build   # after static import "vega-embed" in main.tsx (reverted)
dist/assets/index-C4Rql_kx.js   749.96 kB │ gzip: 256.97 kB
```

```
$ uv run python scripts/check_budgets.py --structural-only

ok    api src LOC               4000 <= 4000
ok    web src LOC               2607 <= 3000
ok    api routes                   1 <= 10
ok    agent tools                  4 <= 6
ok    domain models                9 <= 15
ok    direct dependencies          7 <= 25
```

## Decision

Frontend translator: `ChartSpec` + `normalizeActiveDataset` → inline Vega-Lite
JSON (`data.values`, layered mark + `errorbar`, `detail.segment` at gaps).
`vega-embed(..., { actions: false, renderer: "svg" })` via dynamic import.
Over 12 series or 500 rows: "use the table", no partial chart. Invalid /
`chart_unavailable`: notice, table stays.

## Out of this ticket

CSV. Maps. PNG/SVG download. PDF. Chart persistence. Raising any budget.
Recreating ChartSpec or DatasetRow.
