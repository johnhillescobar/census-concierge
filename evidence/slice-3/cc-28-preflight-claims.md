# CC-28 pre-flight — claims vs measured

Raw command output: `evidence/slice-3/cc-28-preflight.txt`.

Settled on `origin/main` @ `7bee525` (slice 2 closed; `url` still singular).

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| `fetch_data` accepts `years: list[int]` on the existing tool; no fifth tool or new route | `FetchDataInput.model_fields == []`; `_arun(self)` takes no args; `convert_to_openai_tool` parameters are `{}`; `agent tools` 4/6; `api routes` 1/10 (`paths == ['/ask']`) | **Holds as a gap.** Add `years` to `FetchDataInput`. Do not add a tool or route. |
| Duplicate years de-duplicated in first-requested order | no helper exists | **Holds as a gap.** Implement `unique_years` in the fetch module. |
| Available years execute concurrently, at most five in flight | `asyncio.Semaphore(5)`: 3 tasks peak=3 in 0.082s (one hold); 8 tasks peak=5 in 0.164s (two holds). `httpx.get` today is one `asyncio.to_thread` call | **Holds.** Cap with `Semaphore(5)` around each `to_thread`. A behavior test must observe peak>1 for 3 legs and peak==5 for 8. |
| `build_url` produces one complete key-redacted URL per attempted year (dataset, vintage, E/M, legal geography) | `CensusURL` path is `/data/2024/acs/acs5`; `has with_year: False`. `pair_margins` already on the built query. Key is absent from `str(CensusURL)` | **Holds as a gap.** Add `CensusURL.with_year`. Do not re-run `build_url` per year; rewrite the vintage on the already-paired URL. |
| `urls[]` and per-leg results follow requested-year order | `AskResponse.url` is `str`; OpenAPI `"type": "string"` with no `items`; description still says "Singular; slice 3 grows urls[]" | **Holds as a gap.** Replace `url` with `urls[]`. `asyncio.gather` preserves input order. |
| Failed/timed-out leg keeps URL, year, status, redacted reason; successes still return | `TimeoutException` MRO includes `HTTPError` (already caught). Today a failed fetch is one `FetchDataResult` with `ok=False` and empty `rows` | **Holds as a gap.** Per-leg catch. Partial success must set tool `ok=True` if any leg succeeded so `consecutive_failures` does not abort the series. |
| Requested / attempted / succeeded / failed / omitted years represented separately; CC-31 owns omission reasons | no such fields | **Holds as a gap.** Add the five lists now. This ticket omits only when `years` was passed and no URL has been built. Vintage policy stays CC-31. |
| `url` → `urls[]` in OpenAPI, generated client, and frontend in the same change; stale-client check fails against the old schema | `web/src/App.tsx` and `display.ts` read `response.url`; `ask.ts` consumes `packages/client/schema`; `generate_client.py --check` already exists; `test_generated_client.py` pins `url` | **Holds as a gap.** Same commit: contract, client regen, `App`/`display`, `run_demo.py` scoring. |
| Room in the budgets | `check_budgets.py --structural-only` | **Holds with a constraint.** `ask.py` **395/400** — fan-out must not live there; extract `api/src/fetch.py` (`api src files` 19/40). `doc_lines` **1800/1800** — do not edit PLAN/DESIGN/playbooks. `tool_schemas` 8/12; `domain_models` 4/15 (`RequestLeg` is a domain model). `direct_dependencies` 7/25 — stdlib semaphore, no new dep. |

## Decision

`fetch_data` gains `years: list[int]`. Empty `years` fetches the URL `build_url` already produced. Non-empty years are de-duplicated in order, each URL is `CensusURL.with_year`, and HTTP runs under `asyncio.Semaphore(5)`. `AskResponse.url` becomes `urls[]` plus the five year lists and `legs[]`. CC-31 still owns why a year was omitted.

## Out of this ticket

Vintage policy, ACS1 eligibility, 2020 gap copy (CC-31). Series/comparison guards (CC-29). Geography lists (CC-30). Charts and plan strip (slice 4). A fifth tool.
