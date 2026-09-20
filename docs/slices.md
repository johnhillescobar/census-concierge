# Slices and Jira epics

Jira project **CC** is the status source of truth. PLAN.md is the order and a
one-line STATUS pointer, not an eval ledger.

## Board

| epic | slice | status |
|---|---|---|
| [CC-8](https://johnhillescobar.atlassian.net/browse/CC-8) | 0 table index + retrieval eval | Done |
| [CC-1](https://johnhillescobar.atlassian.net/browse/CC-1) | 1 `POST /ask` | Done |
| [CC-5](https://johnhillescobar.atlassian.net/browse/CC-5) | 2 chat UI, one pane | Done |
| [CC-2](https://johnhillescobar.atlassian.net/browse/CC-2) | 3 series and comparisons | Done |
| [CC-4](https://johnhillescobar.atlassian.net/browse/CC-4) | agent harness (process, not a product slice) | Done |
| [CC-11](https://johnhillescobar.atlassian.net/browse/CC-11) | 4 living workspace, charts, CSV | **In Progress** |
| [CC-91](https://johnhillescobar.atlassian.net/browse/CC-91) | post-slice-3 reliability (does not block CC-11) | **In Progress** |
| [CC-9](https://johnhillescobar.atlassian.net/browse/CC-9) | spike: LangGraph checkpointer | To Do |
| [CC-6](https://johnhillescobar.atlassian.net/browse/CC-6) | 5 conversation persistence | To Do |
| [CC-3](https://johnhillescobar.atlassian.net/browse/CC-3) | 6 follow-ups | To Do |
| [CC-10](https://johnhillescobar.atlassian.net/browse/CC-10) | 7 PDF export | To Do |
| [CC-7](https://johnhillescobar.atlassian.net/browse/CC-7) | 8 auth + hosting | To Do |
| [CC-77](https://johnhillescobar.atlassian.net/browse/CC-77) | spatial crosswalks + full-table extract | To Do (after CC-11 table/plan-strip foundations) |

## Closed product slices

**Slice 0** (2026-09-12). No agent, no HTTP, no UI. Metadata cache, availability
matrix, 636-family index, golden set, `make eval` floors. Evidence:
`evidence/slice-0/`. Ladder: `evidence/retrieval_steps.md`. Retrieval notes:
`docs/retrieval.md`.

**Slice 1** (2026-09-13). `POST /ask`, four-tool loop, response contract, five
guards from `docs/requirements.md` (none block), `make demo`. answered_rate 0.803, p95 14.164s.
Evidence: `evidence/slice-1/`. Selector is `rerank.choose` inside
`search_tables` ([CC-54](https://johnhillescobar.atlassian.net/browse/CC-54)), not a fifth tool.

**Slice 2** (2026-09-14). Vite chat pane, generated TS client, FastAPI serves
`web/dist`. answered_rate 0.778, p95 24.546s (ceiling 20s, recorded). Evidence:
`evidence/slice-2/`.

**Slice 3** (2026-09-19). Years and comparison geos as `fetch_data` parameters;
`url` → `urls[]`; vintage policy; ZCTA / nesting / aggregation / `MOE_diff`.
answered_rate 0.825, p95 17.116s. Evidence: `evidence/slice-3/`. Live behavior:
`docs/ask-path.md`. Residual misses: CC-91, not a reopening of CC-2.

## Decisions recorded as Done (do not implement)

- [CC-55](https://johnhillescobar.atlassian.net/browse/CC-55) — no gazetteer until NAME ranking and the CC-37 plan strip still fail a named golden question.
- [CC-56](https://johnhillescobar.atlassian.net/browse/CC-56) — a fifth tool is earned by a failing golden question, not scheduled. Years are a parameter (CC-28).
