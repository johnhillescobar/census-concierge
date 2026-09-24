# census-concierge

Conversational discovery for the Census table ecosystem. Ask in plain language,
get the table you did not know existed, the data, and the API URL to reuse.

## Scoreboard

<!-- Copied from evidence/latest.json after `make eval` / `make demo`.
     Those commands write the JSON; this table is not auto-updated. -->

| metric | current | floor |
|---|---|---|
| retriever @10 — long tail | 0.90 | 0.90 |
| selector @1 — long tail | 0.88 | 0.70 |
| synthetic alignment | 0.54 | 0.50 |
| answered rate | 0.81 | 0.70 |
| p95 latency | 16.7s | 20s |
| api src LOC | 4000 | 4000 |

## Slices

Each ends in a demo. Nothing in slice N+1 starts until N is demoed.
Closed vs open: `docs/slices.md`. Jira is the status source of truth.

| # | slice | done when |
|---|---|---|
| ~~0~~ | Table index + retrieval eval | `make eval` clears the long-tail floors |
| ~~1~~ | `POST /ask` → answer, URL, rows, MOE, GEOID | you `curl` it and get a working URL |
| ~~2~~ | Chat UI, one pane | you type in a browser and get an answer |
| ~~3~~ | Series and comparisons | a defensible year series and a cross-geography compare |
| 4 | Canvas: table, ChartSpec, editable plan strip, CSV | two panes, and you can fix a wrong table |
| — | Spike: LangGraph checkpointer | dated decision in DESIGN §9, not merged code |
| 5 | Conversation persistence | restart the server; the canvas is still there |
| 6 | Follow-ups and reference resolution | "what about Texas?" resolves against the prior turn |
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

```
make check   # budgets, lint, types, tests — under 60s
make eval    # retrieval scoreboard
make demo    # npm ci + build web/dist, then end-to-end against that same process; needs live keys
uv run python scripts/e2e_capture.py --slice 4 --ticket CC-N --phase pre   # eval+demo transcript
uv run python scripts/plot_e2e_latency.py --pre <sha> --post origin/main   # latency histogram + ECDF
uv run uvicorn src.main:app --reload   # POST /ask; GET / is the UI after `npm --prefix web run build`
npm --prefix web install && npm --prefix web run dev   # Vite; proxies /ask
uv run python scripts/generate_client.py   # regenerate packages/client; --check in make check
```

Read `CLAUDE.md` first. Canonical: `.claude/DESIGN.md`, `.claude/PLAN.md`,
`docs/ARCHITECTURE.md`, `docs/requirements.md`.

For hands-on debugging, see [docs/DEBUGGING.md](docs/DEBUGGING.md). Retrieval
measurements: [docs/retrieval.md](docs/retrieval.md).
