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
| [CC-11](https://johnhillescobar.atlassian.net/browse/CC-11) | 4 living workspace, charts, CSV | Done |
| [CC-91](https://johnhillescobar.atlassian.net/browse/CC-91) | post-slice-3 reliability (does not block CC-11) | Done |
| [CC-9](https://johnhillescobar.atlassian.net/browse/CC-9) | spike: LangGraph checkpointer | Done (direct psycopg, DESIGN §9) |
| [CC-6](https://johnhillescobar.atlassian.net/browse/CC-6) | 5 conversation persistence | Done |
| [CC-3](https://johnhillescobar.atlassian.net/browse/CC-3) | 6 follow-ups | To Do (current) |
| [CC-10](https://johnhillescobar.atlassian.net/browse/CC-10) | 7 PDF export | To Do |
| [CC-7](https://johnhillescobar.atlassian.net/browse/CC-7) | 8 auth + hosting | To Do |
| [CC-77](https://johnhillescobar.atlassian.net/browse/CC-77) | spatial crosswalks + full-table extract (phase 1, intermediary epic) | To Do (CC-11 foundations shipped; schedule within phase 1) |

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
[CC-100](https://johnhillescobar.atlassian.net/browse/CC-100) fixed a
regression in this slice's own comparisons feature: an "and"/comma-phrased
multi-place question (as opposed to "versus"/"compared to") silently dropped
every place but the last-resolved one, with no warning. Bug fix, not a
reopening — see `docs/ask-path.md`'s Finish path section.

**Slice 4** (2026-09-28). Two-pane workspace, `ResultPlan` + editable plan
strip with typed overrides, `ChartSpec` rendered as Vega-Lite, GEOID/MOE table,
CSV export (CC-34/35/87/88/89/90/49), plus CC-100/101 comparison and wildcard
fixes. Last close: answered_rate long_tail 0.825, p95 over ceiling recorded.
Evidence: `evidence/slice-4/`.

**Spike CC-9** (2026-09-29). Direct psycopg, not the LangGraph checkpointer.
DESIGN §9.

**Slice 5** (2026-10-01). Postgres conversation store (CC-40), create /
append / read routes (CC-41), restore on reload (CC-38). CC-38 added the
geography-level scorer: long_tail answered_rate 0.742 (overall 0.774), p95
21.701s over ceiling recorded. Compare later runs only against this scorer.
Evidence: `evidence/slice-5/`.

## Decisions recorded as Done (do not implement)

- [CC-55](https://johnhillescobar.atlassian.net/browse/CC-55) — no gazetteer until NAME ranking and the CC-37 plan strip still fail a named golden question.
- [CC-56](https://johnhillescobar.atlassian.net/browse/CC-56) — a fifth tool is earned by a failing golden question, not scheduled. Years are a parameter (CC-28).
- [CC-96](https://johnhillescobar.atlassian.net/browse/CC-96) — informal/alias place language is the agent’s job: existing tools, Census-shaped output. The NAME matcher must not fake a hit ([CC-99](https://johnhillescobar.atlassian.net/browse/CC-99) Done). A gazetteer *module* is a separate until-clause ([CC-55](https://johnhillescobar.atlassian.net/browse/CC-55)), not a ban on alias questions.
