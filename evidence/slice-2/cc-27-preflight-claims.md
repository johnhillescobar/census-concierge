# CC-27 pre-flight — claims vs measured

Raw command output: `evidence/slice-2/cc-27-preflight.txt`.

Settled on `origin/main` @ `6eef204` (slice 2 CC-24 merged; generated client not built).

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| FastAPI exposes a schema a TS generator can read | `app.openapi()` / `GET /openapi.json`; OpenAPI 3.1; `operationId` `ask`; components `AskRequest`, `AskResponse`, `Alternative`, `AskWarning` | **Holds.** `AskResponse.required` is the nine contract fields. `url` is a string. `rows`/`moe` items are objects with `additionalProperties` `string \| null`. |
| `openapi-typescript` can consume that schema | `npx openapi-typescript@7.9.1` on a dumped `openapi.json` | **Holds.** Emits `AskResponse` with `rows: { [key: string]: string \| null }[]`, which is the handwritten `Record<string, string \| null>[]`. No machine-specific paths in the output. |
| Frontend currently duplicates the contract | `web/src/ask.ts` | **Holds as the gap.** Local `AskResponse` / `Alternative` / `AskWarning` restated by hand. Comment says CC-27 replaces them. |
| `packages/client/` is the committed generated output | `Path('packages/client').exists()`; `.gitignore` comment; DESIGN §5 | **Fails as implemented.** Directory absent. Git tracks it on purpose so CI can diff. `.cursorignore` already excludes it. Ruff already `extend-exclude`s it. |
| CI / `make check` fail on drift | `.github/workflows/check.yml`; `Makefile` `check` | **Fails as implemented.** No generate or `--check` step. Check job: "no network beyond dependency install" — generator must be a locked `web` devDependency, not `npx --yes` at check time. |
| Regeneration is a documented one-step command | README "Working on this"; Makefile | **Fails as implemented.** No `make client` / `scripts/generate_client.py`. **`doc_lines` 1798/1800** — do not add prescriptive-doc paragraphs. Document in Makefile + README + ARCHITECTURE (none counted except PLAN checkbox). |
| `uv run python` from repo root can dump the schema without the index or keys | `from src.main import app`; `app.openapi()` | **Holds.** Same import as `test_ask_route.py` in CI. |
| Room in the budgets | `check_budgets.py --structural-only` | **Holds.** web src LOC 666/3000. **`doc_lines` 1798/1800**. `direct_dependencies` 7/25 — do not add the generator to `api/pyproject.toml`. `ask.py` 395/400 — do not touch it. |
| FastAPI static serving / copy control | Jira CC-32 | **Out of this ticket.** |

## Decision

Dump the live schema with `app.openapi()`, generate `packages/client/schema.d.ts` with pinned `openapi-typescript@7.9.1` (web devDependency), commit that file plus `packages/client/openapi.json`. `web/src/ask.ts` keeps the fetch helper and imports types from the generated schema — no second `AskResponse` shape. `uv run python scripts/generate_client.py` regenerates; `--check` is part of `make check` and CI after `npm --prefix web ci`.

## Out of this ticket

CC-32 FastAPI static serving, copy control, `make demo` against the served build. Canvas, charts, plan strip (slice 4). `openapi-fetch` / a generated runtime SDK — one route, one fetch helper; a generic client waits for a second caller.
