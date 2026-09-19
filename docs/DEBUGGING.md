# Debugging census-concierge (without AI help)

This repo is set up so you can step through the core application logic **without
calling OpenAI or the live Census API**. The “offline” debug workflows run a
**scripted model** plus **fake tools** under pytest, so every step is
deterministic and breakpoint-friendly.

## Mental model: the shortest path through the app

**Inputs**

- UI: `web/src/App.tsx` → `web/src/ask.ts` → `POST /ask`
- API: `POST /ask` (`api/src/main.py`) → `run_ask(question)` (`api/src/ask.py`)
- E2E harness: `scripts/run_demo.py` → `POST /ask` (needs live keys)

**Core loop**

`api/src/ask.py:run_ask` runs a “call model → dispatch tool calls” loop:

1. Build `messages[]` (system + user)
2. Call `complete(messages, tools)` (real OpenAI or a scripted fake)
3. For each requested tool call, run `dispatch(tool, call, record)`
4. After the loop, `finish_tools(...)` (fills required fields if the model stopped early)
5. `assemble(answer, record)` produces the `AskResponse`

**Tools (the 4 tool boundary)**

- `search_tables` → `api/src/tools.py` (table retrieval + metadata)
- `resolve_geography` → `api/src/geo.py` (turn a place string into executable `GeoSpec`s)
- `build_url` → `api/src/tools.py` + `api/src/census_url.py` (construct a Census API URL)
- `fetch_data` → `api/src/fetch.py` (HTTP to Census, parse rows, add MOE, series fan-out)

## Entry points (where to put your first breakpoint)

### API / server entry

- `api/src/main.py:create_app` (FastAPI app wiring)
- `api/src/main.py:post_ask` (HTTP boundary: `AskRequest` → `run_ask`)

### Ask loop entry

- `api/src/ask.py:run_ask` (the orchestrating loop)
- `api/src/ask.py:dispatch` (every tool call flows through here)
- `api/src/ask.py:_absorb` (where tool artifacts become `ExecutionRecord` fields)

### Tool entries

- `api/src/tools.py:SearchTablesTool`
- `api/src/geo.py:ResolveGeographyTool`
- `api/src/tools.py:BuildUrlTool`
- `api/src/fetch.py:FetchDataTool`

## Output points (what the app produces)

### HTTP response contract

`POST /ask` returns `AskResponse` from `api/src/contract.py`.

This is the main “output boundary” for debugging correctness:

- `urls[]`: key-redacted Census API URLs (the product)
- `rows[]` + `moe[]`: raw rows + 90% MOE rows (never silently dropped)
- `table_id`, `universe`, `geoid`: the selected table + geography identity
- `warnings[]`: non-blocking guard rails (overlaps, nesting, ACS1 ineligible, etc.)
- `comparisons[]`: paired comparisons and MOE-diff conclusions (slice 3+)

### Demo / evidence output (E2E)

`scripts/run_demo.py` writes metrics to `evidence/latest.json` (requires live keys).

## Debug workflows (pick one)

### 1) Offline API debugging (recommended starting point)

This path uses **no OpenAI key, no Census key, no network**.

- Use the VS Code debug config `api: ask loop (offline, scripted)`
  - It runs `api/tests/test_ask_loop.py::test_scripted_loop_fills_url_rows_geoid_and_universe`
  - The “model” is a scripted queue of tool calls
  - The “tools” are fakes defined in `api/tests/ask_fixtures.py`

Good breakpoints for the first run:

- `api/src/ask.py:run_ask`
- `api/src/ask.py:dispatch`
- `api/src/ask.py:_absorb`
- `api/src/tools.py` (URL build and table selection)
- `api/src/fetch.py` (row parsing and MOE mapping)

More offline use cases (still deterministic):

- “Model stops early but finish still produces a URL/rows”:
  `api/tests/test_ask_loop.py::test_computer_share_finishes_when_the_model_stops`
- “Overlapping ACS 5-year vintages emits a warning”:
  `api/tests/test_ask_loop.py::test_overlapping_income_finishes_when_the_model_stops`
- “Guards + comparisons + aggregation warnings”:
  use the debug config `api: guards + comparisons (offline)` (runs `api/tests/test_guards.py`)

### 2) Offline HTTP surface debugging (FastAPI + schema)

This proves request validation and the OpenAPI schema, with no keys and no network.

- Use the debug config `api: /ask route contract (offline)`
  - Runs `api/tests/test_ask_route.py`
  - Breakpoints to use:
    - `api/src/main.py:post_ask`
    - `api/src/contract.py` validators (`AskRequest.question_is_not_blank`)

### 3) Live API debugging (real OpenAI + real Census)

This is for debugging **integration issues** (provider failures, rate limits,
unexpected Census responses).

Prereqs:

- `.env` has `OPENAI_API_KEY` and `CENSUS_API_KEY`
- `index_store/` exists (build it with `uv run python scripts/build_index.py` if needed)

Run:

- VS Code debug config `api: uvicorn (debug, no reload)` (most reliable breakpoints)
- Or CLI: `uv run uvicorn src.main:app --reload` from `api/`

Manual request:

- Swagger: `http://127.0.0.1:8000/docs`
- PowerShell:
  - `Invoke-RestMethod http://127.0.0.1:8000/ask -Method Post -ContentType application/json -Body '{\"question\":\"population of Harris County, Texas\"}'`
- Curl (Windows): use `curl.exe` to avoid the PowerShell `curl` alias
  - `curl.exe -X POST http://127.0.0.1:8000/ask -H "Content-Type: application/json" -d "{\"question\":\"population of Harris County, Texas\"}"`

### 4) Web UI debugging (React/Vite)

UI entrypoints:

- `web/src/main.tsx` (React mount)
- `web/src/App.tsx` (form submit + rendering)
- `web/src/ask.ts` (HTTP call to `POST /ask`)

Two ways to run the UI:

- Dev server (fast iteration): `npm --prefix web run dev`
  - Vite proxies `/ask` to the API on `:8000` (see `web/vite.config.ts`)
- Same-origin production mode:
  - `npm --prefix web run build`
  - Start the API (`uvicorn src.main:app ...`)
  - Then `GET /` is served from `web/dist` by FastAPI

Offline UI debugging (no API needed):

- `web/src/App.test.tsx` injects `askFn` into `<App>`; set breakpoints in `App.tsx`
  and run `npm --prefix web test`.

## Where data crosses boundaries (useful when debugging “wrong answer”)

- **Tool artifacts → record fields**: `api/src/ask.py:_absorb`
- **Record fields → response**: `api/src/ask.py:assemble`
- **URL redaction**: `api/src/census_url.py` (`CensusURL.__str__`, `redact_text`)
- **Warnings and comparisons**: `api/src/guards.py`, `api/src/compare.py`, and `api/src/finish.py`

## Common breakpoints by symptom

- “Wrong table picked”: `api/src/tools.py` (search/describe/rerank usage) and `api/src/ask.py:_allowed`
- “Wrong geography / ambiguous place”: `api/src/geo.py` (spec construction + ordering)
- “URL looks wrong”: `api/src/tools.py` (BuildUrlTool) + `api/src/census_url.py`
- “Rows empty / missing MOE / GEOID missing”: `api/src/fetch.py` and `api/src/ask.py:_rows_with_geoid`
- “Warnings missing/unexpected”: `api/src/guards.py` and `api/src/finish.py:finish_tools`
