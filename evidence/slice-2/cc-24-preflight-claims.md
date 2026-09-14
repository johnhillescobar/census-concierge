# CC-24 pre-flight — claims vs measured

Raw command output: `evidence/slice-2/cc-24-preflight.txt`.

Settled on `origin/main` @ `e805357` (slice 1 closed; answered_rate 0.803, p95 14.164s).

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| Slice 2 may start; slice 1 is demoed | PLAN STATUS 2026-09-13; `evidence/latest.json` answered_rate 0.803 / p95 14.164s | **Holds.** |
| A user types a question in a single-pane browser UI | `web/` does not exist | **Fails as implemented.** This ticket creates it. |
| Answer area renders URL, estimate+MOE, GEOID, universe, ≥1 alternative from the existing contract | `AskResponse` required fields; OpenAPI `/ask` POST; `test_scripted_loop_fills_url_rows_geoid_and_universe` | **Holds as a backend contract.** `rows[*]_*E` pair with `moe[*]_*M`; `geoid` is AFFGEOID; `alternatives[]` is `{table_id, reason}`. No `http_ok` field. Frontend reads these names as spelled. |
| Census fetch failure still returns URL and table metadata | `test_failed_fetch_still_returns_the_built_url` (HTTP 400, `rows==[]`, URL kept, `geoid` from resolved geography); `test_fetch_with_no_rows_still_returns_the_url` | **Holds.** Detect as nonempty `url` + empty `rows`. Do not add a new response field. |
| Loading and error states are distinct from the empty initial state | nothing in `web/` | **Fails as implemented.** UI must set distinct `data-state` values: `idle` / `loading` / `error` / `result`. Census-fetch failure is a `result` with a notice, not `error`. |
| React + TypeScript, single pane | PLAN slice 2; DESIGN §5 `web/` | **Holds as intent.** No component library, router, or state-management library (`.cursor/rules/20-web-typescript.mdc`). |
| Generated TS client / CI drift check | Jira CC-27 | **Out of this ticket.** Local types in `web/src/ask.ts` duplicate the nine contract fields until CC-27. Do not create `packages/client/`. |
| FastAPI serves the Vite build; copy control; `make demo` against the served build | Jira CC-32; PLAN "FastAPI serves the Vite build output"; DESIGN §5 no CORS | **Out of this ticket.** No static-file route, no CORS middleware (measured: `app.user_middleware == []`). Local Vite proxies `POST /ask` to `127.0.0.1:8000`. URL is visible and selectable; a copy button is CC-32. |
| No new agent tool, graph node, or blocking clarification | PLAN Not in this slice; DESIGN §4 | **Holds if this PR does not touch `api/src` tools or add a route.** |
| Room in the budgets | `check_budgets.py --structural-only` | **Holds.** web src LOC 0/3000. **`doc_lines` 1798/1800** — do not add prescriptive-doc paragraphs. PLAN checkbox `[ ]`→`[x]` is fine. `ARCHITECTURE.md` is not counted and must record `web/`. `ask.py` 395/400 — do not grow it. |

## Decision

Build `web/` as Vite + React + TypeScript: one question form, one answer pane, `POST /ask` through a Vite proxy. Render the nine contract fields. Infer Census-fetch failure from `url && rows.length === 0`. Do not generate a client, do not serve dist from FastAPI, do not add CORS, do not add a copy button.

## Out of this ticket

CC-27 generated client + CI staleness. CC-32 FastAPI static serving, copy control, `make demo` against the served build. Canvas, charts, plan strip (slice 4).
