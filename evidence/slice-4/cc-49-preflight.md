# CC-49 pre-flight

Claims checked against the code before implementation started.

| Claim | Command | Result |
| --- | --- | --- |
| CC-35 exposes one normalized row array with every required CSV column, no re-parsing | `Read web/src/display.ts` | `normalizeActiveDataset(response): DatasetRow[]` (`display.ts:107`). `DatasetRow` carries `dataset, year, period, tableId, variable, geoid, name, estimate, moe, universe` — a 1:1 cover of the required CSV columns (`dataset, vintage, period, table_id, variable, GEO_ID, NAME, estimate, moe, universe`; field names differ, values don't). `App.tsx:82` already computes `dataset = normalizeActiveDataset(result)` once per render and passes the same array to the table and chart; CSV reuses that identical array — no second normalization pass, per `docs/ARCHITECTURE.md`'s "CSV consumes that same `AskResponse`; it must not keep a second copy." |
| Census sentinels are already resolved to `null` before reaching `DatasetRow` | `Read web/src/display.ts:18-26,48-53` | `censusRaw()` maps the sentinel set (`-999999999` etc.) and `""` to `null` before `estimate`/`moe` are populated (`display.ts:120-121`). So the CSV serializer's job for "sentinel" is only: `null` field → empty CSV cell, never `"0"` or the raw sentinel digits — it never sees a sentinel string itself. |
| A dependency-free serializer can pass concrete comma/quote/newline/empty/sentinel/Unicode/formula-like-text fixtures | Written as `rowsToCsv` in new `web/src/csv.ts`, exercised in new `web/src/csv.test.ts` | Confirmed after writing (see Gate 1 evidence). Pure string logic, zero imports beyond `DatasetRow`'s type — no CSV package added. |
| Native `Blob`/object-URL download works in the project's test environment | `cd web && npx vitest run` against a throwaway test calling `URL.createObjectURL(new Blob(...))` | **Failed as claimed**: jsdom 26 (this repo's `vitest` `environment: "jsdom"`) throws `TypeError: URL.createObjectURL is not a function` — jsdom does not implement it. Real browsers do, and so does Playwright's browser context, which is what the ticket's live-proof step uses. **Correction**: unit tests cover (a) the pure `rowsToCsv`/`csvFilename` serializer with no Blob dependency, and (b) the download-wiring logic (`anchor.download`, `.click()`, `URL.revokeObjectURL` called) against a minimal same-shape stub added to `web/src/test-setup.ts` (guarded so it only installs when the real API is absent, i.e. never in a real browser). Byte-level Blob/download behavior itself is proven only by the ticket's required live browser demo, not by vitest — this was true of the claim's intent but not of jsdom's actual capability, so the pre-flight table records the correction rather than silently downgrading the test. |
| Filename/row-count mechanism for the owned live proof (`q04`, Detroit poverty rate by tract) | `Read web/src/App.tsx` (table rendering), design of `csvFilename` | Filename is built from the same `table_id` / `dataset` / vintage already shown in the "Working dataset" meta list (`App.tsx:104-115`), sanitized to `[A-Za-z0-9_-]`. Row count is `normalizeActiveDataset(result).length` — identical to the number of `<tr>` rows `EstimatesTable` renders, so it is mechanically comparable against the visible table during the live proof. The literal filename string and tract count for `q04` depend on live Census data (today's resolved table/dataset/vintage and the number of Detroit tracts) and are not knowable before running the app; they are captured during the live-proof step itself, not fixed here. |
| `budgets.toml` headroom before writing code | `uv run python scripts/check_budgets.py` | `web_src_loc` 3003/3100 — only **97 lines** of headroom for `csv.ts`, its test file, `App.tsx` wiring, and any additions to existing App tests. Flagged as a real constraint: the implementation must stay compact, and if it doesn't fit the budget is not raised — the change is cut down or the user is asked, per `CLAUDE.md`. |

## Design decisions driven by pre-flight

- CSV serialization and CSV-triggered download are split into two small pure
  functions (`rowsToCsv`, `csvFilename`) plus one thin `downloadCsv(filename,
  csv)` side-effecting function, so the 97-line budget is spent on the parts
  that need dedicated tests, and the Blob-environment gap doesn't block
  testing the serializer.
- No new dependency: native `Blob` + `URL.createObjectURL` + an `<a
  download>` click, matching the ticket's explicit "PapaParse... are not
  added."
