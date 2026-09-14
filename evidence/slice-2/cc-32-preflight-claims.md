# CC-32 pre-flight — claims vs measured

Raw command output: `evidence/slice-2/cc-32-preflight.txt`.

Settled on `origin/main` @ `e04c445` (slice 2 CC-27 merged; FastAPI does not serve `web/dist`).

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| FastAPI serves the Vite build at the app boundary, same-origin, no CORS shim | `app.user_middleware == []`; live `GET /` is 404; `StaticFiles` is already in Starlette (FastAPI 0.141.1). Mounting a real `web/dist` at `/` with `html=True`: `GET /` 200 HTML titled census-concierge, `/assets/*.js` 200, `POST /ask` 200, no `Access-Control-Allow-Origin` | **Holds as a gap.** Do not add `CORSMiddleware`. Keep Vite's `/ask` proxy for `npm run dev` only. |
| One process/container serves API and static assets | `run_demo.py` already uses `TestClient(app)`. `make demo` can build `web/dist` then hit that same app. No Dockerfile this slice (slice 8). | **Holds if** `create_app` mounts `web/dist` when the directory exists. |
| Mount must not change the generated client contract | OpenAPI with and without the mount is **byte-identical**; paths stay `['/ask']`. `generate_client.py --check` does not depend on whether dist exists. | **Holds.** Use `app.mount`, not `@app.get("/")` — a new route decorator would appear in OpenAPI and count against `api_routes`. |
| Missing dist must not crash import / `POST /ask` | `StaticFiles(directory=...)` raises `RuntimeError` when the dir is absent (`check_dir=True`). | **Holds as a constraint.** Mount only when `dist.is_dir()`. CI pytest does not build dist. |
| `html=True` is directory index, not history fallback | Starlette `get_response`: directory → `index.html`; unknown path → 404. Slice 2 has no client router. | **Holds.** `GET /` is enough. |
| Vite asset URLs work from FastAPI `/` | `npm --prefix web run build` emits `/assets/index-*.js` (root-absolute). Measured 200 through TestClient. | **Holds.** Do not set a Vite `base`. |
| Census URL is visible and copyable | `<pre class="census-url">` exists; no copy button, no `clipboard` | **Holds as a gap.** Copy the already-redacted visible URL. Do not copy `key=`. |
| Serving path reuses the generated client | `web/src/ask.ts` already imports `packages/client/schema`. `fetch("/ask")` is relative. | **Holds.** Do not add a second client or an absolute API origin. |
| `make demo` against the served build | Demo is TestClient against `src.main:app`, not a second host. Today `GET /` 404. | **Holds as a gap.** Build dist in `make demo`, then refuse to score if `GET /` is not the UI. |
| Room in the budgets | `check_budgets.py --structural-only` | **Holds.** `doc_lines` 1798/1800 — no prescriptive-doc paragraphs. `ask.py` 395/400 — do not touch it. `api routes` 1/10 — mount, do not decorate. `direct_dependencies` 7/25 — StaticFiles needs no new dep. `api src files` 19/40 — keep the mount in `main.py`. |

## Decision

`create_app()` in `api/src/main.py` keeps `POST /ask` and mounts `web/dist` with `StaticFiles(html=True)` when that directory exists. No CORS. Copy control on the redacted Census URL. `make demo` runs `npm --prefix web run build` then `run_demo.py`, which checks `GET /` before scoring `/ask`.

## Out of this ticket

Canvas, charts, plan strip (slice 4). Dockerfile / one-container hosting (slice 8). Client-side routing. `openapi-fetch` / a generated runtime SDK.
