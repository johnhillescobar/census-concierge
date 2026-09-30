# CC-6 pre-flight — claims vs measured

2026-09-29, `main` @ `c176b50`. Jira `CC-6` To Do (Epic). CC-9 Done (`142ea8b`).
Postgres 16 in a throwaway container; scratch scripts were not committed.

| Claim | Measured | Verdict |
| --- | --- | --- |
| CC-9 decided how to persist | Done; DESIGN §9 `142ea8b`: direct psycopg, one state row per thread | **Holds.** (`PLAN.md` said "whichever way CC-9 decided" while it was To Do.) |
| Budget room | `api_src_loc` 4100/4250, `web_src_loc` 3098/3150 after `c176b50`; `check_invariants.py --base origin/main` passes | **Holds.** |
| Routes and dependencies fit | routes 1/10 (+3 = 4); direct deps 7/25 (+psycopg = 8) | **Holds.** |
| psycopg async runs under uvicorn on Windows | uvicorn 0.52.4 default and `--loop none` → `ProactorEventLoop` → `InterfaceError`. `--reload` → Selector, works. `--loop mod:factory` works only with a **no-arg** factory (uvicorn calls it as the loop factory; a `use_subprocess` wrapper fails with `'function' object has no attribute 'create_task'`). Linux is unaffected (Selector default). | **Fails by default on Windows.** `make serve` uses `--reload`, so it works; a non-reload start needs `--loop`. |
| pytest can drive psycopg async | pytest-asyncio 1.4.0, `asyncio_mode=auto`: fails on Windows (Proactor). Passes with a session-scoped `event_loop_policy` fixture returning `WindowsSelectorEventLoopPolicy` on win32. | **Fails by default; fix verified.** |
| Postgres tests run in CI | `.github/workflows/check.yml` runs `pytest -m "not integration"`, has no `services:` block. Locally the docker daemon was down until started. | **Fails.** Needs a decision (below). |
| `AskResponse` survives JSON storage | `model_validate_json(model_dump_json())` equal; equal after a real `jsonb` column. Only the empty fixture (`EMPTY_CONTRACT`) was exercised; populated rows/nested models were not. | **Holds, partly.** Populated case belongs in Gate 1. |
| Inline rows are small enough | Cook County IL tracts (1,332): 3 columns = 200.6 KB, 20 columns = 688.1 KB, rows only (`moe` is separate). Each append rewrites the whole state row. | **Holds** for a 48h thread; unbounded turns would not. |
| The canvas is a conversation | `App.tsx:166` holds one `result`; `/ask` is stateless; no thread concept anywhere in web or api. | **Corrected.** Restore = the latest turn's question, result and plan. All turns are stored; only the latest renders. |
| `user_id` has a source | No auth until slice 8 (Clerk). `AskRequest` has no user field. | **Unresolved** (below). |
| No module-level state | Invariants enforce only sqlite and contextvars; the pool must still live in the app lifespan / `app.state`, not a module global (CLAUDE.md). | **Holds** as a build rule. |
| psycopg in the repo env | Not installed (`api/pyproject.toml` says the driver lands in slice 5). | **Expected.** |
| Client drift gate | `make check` runs `generate_client.py --check`; new routes/models require regenerating the snapshot and `schema.d.ts`. | **Not run** — needs code. Known work. |

## Decisions (owner, 2026-09-29)

1. **Postgres in CI: add a `services: postgres` block to `check.yml`** so the store tests gate. A store that never runs in CI is the "fake that tests nothing" trap.
2. **`user_id` is a client-generated UUID** kept in localStorage and sent as a header. It is a bearer secret until Clerk replaces it in slice 8: unguessable v4, never logged, never returned in a response.
3. **Append is `POST /conversations/{id}/turns`**: takes an `AskRequest`, runs `run_ask` server-side and stores the result, so the client cannot store an answer the server never produced. `POST /ask` stays unchanged.

Not measured: the ~130 api / 35-50 web line estimates. Gate on the real counts.
