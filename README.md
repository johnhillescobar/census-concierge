# census-concierge

Conversational discovery for the Census table ecosystem. Ask in plain language,
get the table you did not know existed, the data, and the API URL to reuse.

## Scoreboard

<!-- Updated by `make eval` and `make demo`. This is the first thing anyone
     working on this repo should see, human or agent. -->

| metric | current | floor |
|---|---|---|
| retriever @10 — long tail | 0.90 | 0.90 |
| selector @1 — long tail | 0.85 | 0.70 |
| synthetic alignment | 0.54 | 0.50 |
| answered rate | 0.80 | 0.70 |
| p95 latency | 31.0s | 20s |
| api src LOC | 0 | 4000 |

## Slices

Each ends in a demo. Nothing in slice N+1 starts until N is demoed.

| # | slice | done when |
|---|---|---|
| 0 | Table index + retrieval eval | `make eval` clears the long-tail floor |
| 1 | `POST /ask` → answer, URL, rows, MOE, GEOID | you `curl` it and get a working URL |
| 2 | Chat UI, one pane | you type in a browser and get an answer |
| 3 | Canvas: table, ChartSpec, editable plan strip, CSV | two panes, and you can fix a wrong table |
| 4 | Memory: thread_id, Postgres checkpointer, follow-ups | "what about Texas?" resolves against the prior turn |
| 5 | PDF export as a background job | you download a real document |
| 6 | Auth + hosted | someone else logs in and uses it |

Slice 0 has no agent, no server and no frontend. If retrieval on long-tail
questions cannot clear the floor, nothing downstream can rescue it — and you
find out in week one instead of month four.

## Layout

```
api/          FastAPI + agent (Python 3.12)
web/          React + TypeScript
packages/client/   generated from the OpenAPI schema; CI fails if stale
evals/        golden_questions.toml — the specification
scripts/      check_budgets.py, eval_retrieval.py, run_demo.py
evidence/     latest.json — what the last run actually measured
budgets.toml  complexity limits, enforced in CI
```

## Working on this

```
make check   # budgets, lint, types, tests — under 60s
make eval    # retrieval scoreboard
make demo    # npm ci + build web/dist, then end-to-end against that same process; needs live keys
uv run uvicorn src.main:app --reload   # POST /ask; GET / is the UI after `npm --prefix web run build`
npm --prefix web install && npm --prefix web run dev   # Vite; proxies /ask
uv run python scripts/generate_client.py   # regenerate packages/client; --check in make check
```

Read `CLAUDE.md` first. It is short, and most of it is prohibitions earned the
hard way.
