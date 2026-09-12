# CC-19 pre-flight — claims vs measured

Raw classifier output: `evidence/slice-1/cc-19-preflight.txt`.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| Slice 1 may start (slice 0 demoed) | `.claude/PLAN.md` STATUS 2026-09-11 | **Holds.** |
| FastAPI is not in the app yet | `api/pyproject.toml` dependencies | **Holds.** four deps, no FastAPI. Comment says it lands in slice 1. |
| `POST /ask` does not exist | grep under `api/` for `/ask` and `FastAPI(` | **Holds.** 0 matches. |
| `api_routes` / `domain_models` have room | `check_budgets.py --structural-only` | **Holds.** routes 0/10, models 0/15, deps 4/25, files 11/40, LOC 849/4000. |
| Import path is `src.*` | hatchling `packages = ["src"]`; existing tests `from src.retrieval import …` | **Holds.** Documented command is `uv run uvicorn src.main:app --reload`. |
| FastAPI serves Swagger at `/docs` and OpenAPI at `/openapi.json` | `uv run --with fastapi` TestClient | **Holds.** both 200. FastAPI 0.141.1. |
| A typed `AskRequest`/`AskResponse` produces `$ref` schemas a TS generator can read | same run, `/openapi.json` | **Holds.** components: AskRequest, AskResponse, Alternative, AskWarning. `AskResponse.required` is the PLAN §slice-1 field list. |
| Empty / blank / missing body is HTTP 422, not 200 | same run | **Holds.** `question: ""` 422; `"   "` 422 with a strip validator; `{}` 422. |
| A valid body reaches the ask function | same run, counter on `run_ask` | **Holds.** HTTP 200, `reached=1`. |
| Four-tool loop is a later story | Jira CC-23 | **Holds.** This PR stops at the thin route + stub `run_ask`. |
| Full populated contract is a later story | Jira CC-25 | **Holds.** This PR *declares* the fields so OpenAPI is explicit; it does not fetch Census data. |
| `scripts/run_demo.py` is a later story | glob | **Holds.** missing; CC-26. |

## Decision

Ship the HTTP surface only. Declare the slice-1 response shape in OpenAPI now (CC-19 AC: explicit schema for the later TS client). Leave `run_ask` a stub. Do not add tools, guards, or `run_demo.py`.
