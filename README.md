# census-concierge

Conversational discovery for the Census table ecosystem. Ask in plain language,
get the table you did not know existed, the data, and the API URL to reuse.

## Numbers

`make eval` and `make demo` write `evidence/latest.json`; quote `demo.p95_latency_seconds`, since an
over-ceiling p95 is not promoted to the top-level key. Each ticket's numbers are in its Jira close
comment, not in this file.

## Slices

Each ends in a demo. Nothing in slice N+1 starts until N is demoed.
Each slice's status is in Jira; `docs/slices.md` links its epic.

| # | slice | ships when |
|---|---|---|
| 0 | Table index + retrieval eval | `make eval` clears the long-tail floors |
| 1 | `POST /ask` → answer, URL, rows, MOE, GEOID | you `curl` it and get a working URL |
| 2 | Chat UI, one pane | you type in a browser and get an answer |
| 3 | Series and comparisons | a defensible year series and a cross-geography compare |
| 4 | Canvas: table, ChartSpec, editable plan strip, CSV | two panes, and you can fix a wrong table |
| — | Spike: LangGraph checkpointer | dated decision in DESIGN §9, not merged code |
| 5 | Conversation persistence | restart the server; the canvas is still there |
| 6 | Follow-ups and reference resolution | a three-turn refinement hits the CC-3 floors, on sealed questions too |
| 7 | PDF export as a background job | you download a real document |
| 8 | Auth + hosted | someone else logs in and uses it |

## Layout

```
api/          FastAPI + agent (Python 3.12)
web/          React + TypeScript
packages/client/   generated from the OpenAPI schema; CI fails if stale
evals/        golden_questions.toml — the specification
docs/         ARCHITECTURE.md, requirements, retrieval, slices, ask-path
scripts/      check_budgets.py, eval_retrieval.py, run_demo.py, e2e_capture.py, plot_e2e_latency.py
evidence/     latest.json — what the last run actually measured
budgets.toml  complexity limits, enforced in CI
```

## Working on this

Agent entry point: `AGENTS.md`. Claude Code, Cursor and Codex share the rules
in `CLAUDE.md` and the canonical `docs/playbooks/` workflows. Existing Claude
skills and Cursor commands remain supported; Codex skills live in
`.agents/skills/`. Gate scripts print handoffs for fresh contexts in any host.

```
make check   # budgets, lint, types, tests — under 60s
make eval    # retrieval scoreboard
make demo    # npm ci + build web/dist, then end-to-end against that same process; needs live keys
uv run python scripts/e2e_capture.py --slice 4 --ticket CC-N --phase pre   # eval+demo transcript
uv run python scripts/plot_e2e_latency.py --pre <sha> --post origin/main   # latency histogram + ECDF
uv run uvicorn src.main:app --reload   # POST /ask; GET / is the UI after `npm --prefix web run build`
# Conversation routes (CC-41) and restore-on-reload (CC-38) need Postgres.
# Without it (or if it is unreachable at startup), /ask still works.
docker run -d --name cc-pg -e POSTGRES_PASSWORD=pg -p 5432:5432 postgres:16
export DATABASE_URL=postgresql://postgres:pg@localhost:5432/postgres   # PowerShell: $env:DATABASE_URL=...
# Windows without --reload: psycopg async needs the selector loop
uv run uvicorn src.main:app --loop src.loop:selector_factory
npm --prefix web install && npm --prefix web run dev   # Vite; proxies /ask
uv run python scripts/generate_client.py   # regenerate packages/client; --check in make check
```

Read `CLAUDE.md` first. Canonical: `.claude/DESIGN.md`, `.claude/PLAN.md`,
`docs/ARCHITECTURE.md`, `docs/requirements.md`.

For hands-on debugging, see [docs/DEBUGGING.md](docs/DEBUGGING.md). Retrieval
measurements: [docs/retrieval.md](docs/retrieval.md).
