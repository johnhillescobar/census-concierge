# Slices and Jira epics

Which epic carries which slice. Status, numbers and evidence are on each Jira ticket (project
**CC**); what `.claude/PLAN.md` may hold is the rule at its top.

## Board

| epic | slice |
|---|---|
| [CC-8](https://johnhillescobar.atlassian.net/browse/CC-8) | 0 table index + retrieval eval |
| [CC-1](https://johnhillescobar.atlassian.net/browse/CC-1) | 1 `POST /ask` |
| [CC-5](https://johnhillescobar.atlassian.net/browse/CC-5) | 2 chat UI, one pane |
| [CC-2](https://johnhillescobar.atlassian.net/browse/CC-2) | 3 series and comparisons |
| [CC-4](https://johnhillescobar.atlassian.net/browse/CC-4) | agent harness (process, not a product slice) |
| [CC-11](https://johnhillescobar.atlassian.net/browse/CC-11) | 4 living workspace, charts, CSV |
| [CC-91](https://johnhillescobar.atlassian.net/browse/CC-91) | post-slice-3 reliability (did not block CC-11) |
| [CC-9](https://johnhillescobar.atlassian.net/browse/CC-9) | spike: LangGraph checkpointer (direct psycopg, DESIGN §9) |
| [CC-6](https://johnhillescobar.atlassian.net/browse/CC-6) | 5 conversation persistence |
| [CC-3](https://johnhillescobar.atlassian.net/browse/CC-3) | 6 grounded understanding, structured intent + follow-ups |
| [CC-10](https://johnhillescobar.atlassian.net/browse/CC-10) | 7 PDF export |
| [CC-7](https://johnhillescobar.atlassian.net/browse/CC-7) | 8 auth + hosting |
| [CC-77](https://johnhillescobar.atlassian.net/browse/CC-77) | spatial crosswalks + full-table extract (phase 1, intermediary epic) |

## What each shipped product slice delivered

- **Slice 0**: no agent, no HTTP, no UI. Metadata cache, availability matrix, table-family
  index, golden set, `make eval` floors. Retrieval notes: `docs/retrieval.md`.
- **Slice 1**: `POST /ask`, four-tool loop, response contract, five guards from
  `docs/requirements.md` (none block), `make demo`. The selector is `rerank.choose` inside
  `search_tables` ([CC-54](https://johnhillescobar.atlassian.net/browse/CC-54)), not a fifth tool.
- **Slice 2**: Vite chat pane, generated TS client, FastAPI serves `web/dist`.
- **Slice 3**: years and comparison geos as `fetch_data` parameters; `url` → `urls[]`; vintage
  policy; ZCTA / nesting / aggregation / `MOE_diff`. Live behavior: `docs/ask-path.md`.
  [CC-100](https://johnhillescobar.atlassian.net/browse/CC-100) fixed this slice's "and"/comma comparisons dropping every place but the last
  (a bug fix, not a reopening; `docs/ask-path.md`, Finish path).
- **Slice 4**: two-pane workspace, `ResultPlan` + editable plan strip with typed overrides,
  `ChartSpec` rendered as Vega-Lite, GEOID/MOE table, CSV export, plus CC-100/101 fixes.
- **Spike CC-9**: direct psycopg, not the LangGraph checkpointer. DESIGN §9.
- **Slice 5**: Postgres conversation store (CC-40), create / append / read routes (CC-41),
  restore on reload (CC-38). CC-38 added the geography-level scorer; compare later runs only
  against this scorer.

## Decisions (do not implement)

- [CC-55](https://johnhillescobar.atlassian.net/browse/CC-55) — no gazetteer until NAME ranking and the CC-37 plan strip still fail a named golden question.
- [CC-56](https://johnhillescobar.atlassian.net/browse/CC-56) — a fifth tool is earned by a failing golden question, not scheduled. Years are a parameter (CC-28).
- [CC-96](https://johnhillescobar.atlassian.net/browse/CC-96) — informal/alias place language is the agent’s job: existing tools, Census-shaped output. The NAME matcher must not fake a hit ([CC-99](https://johnhillescobar.atlassian.net/browse/CC-99)). A gazetteer *module* is a separate until-clause ([CC-55](https://johnhillescobar.atlassian.net/browse/CC-55)), not a ban on alias questions.
