# ARCHITECTURE — the system as it IS

**Status (2026-09-25).** Slices 0–3 are built and their epics are Done
(`docs/slices.md`). Post-slice-3 reliability (CC-91) is Done. Slice 4 (CC-11)
is in progress: `AskResponse.chart` is a validated `ChartSpec` (CC-34 Done);
the canvas translates that spec into Vega-Lite SVG over the normalized table
(CC-87 Done); the result pane renders one normalized GEOID/MOE table (CC-35 Done);
`AskResponse.plan` is a `ResultPlan` assembled from executed artifacts (CC-90 Done);
optional `AskRequest.plan` overrides are validated and pinned on `POST /ask` (CC-89 Done);
the UI is a two-pane living workspace (chat + one active canvas dataset) (CC-88 Done);
the canvas plan strip edits that `ResultPlan` and reruns `POST /ask` (CC-37).

This file is not a design document. Intent: `.claude/DESIGN.md`. Order:
`.claude/PLAN.md`. **When they disagree, this file is right.** A shape-changing
PR updates it in the same commit.

Live ask-path behavior: `docs/ask-path.md`. Retrieval measurements:
`docs/retrieval.md`. Contract and guards: `docs/requirements.md`.

## What exists today

```
budgets.toml                 enforced complexity limits
scripts/check_budgets.py     exits 1 on violation
scripts/check_invariants.py  named anti-patterns; --base catches a weakened budget
scripts/fetch_metadata.py    ACS metadata → data/raw/ (no key)
scripts/verify_golden.py     golden fixtures vs that metadata
scripts/build_index.py       builds index_store/ (needs OPENAI_API_KEY)
scripts/eval_retrieval.py    retrieval scoreboard; --rerank, --holdout
scripts/run_demo.py          POST /ask scoreboard; --repeat, --tier
scripts/e2e_capture.py       eval + demo transcript → evidence/slice-<N>/
scripts/plot_e2e_latency.py  pre vs post demo latency histogram + ECDF
scripts/score_synthetic.py   generated-question quality
scripts/jira_fetch.py        read-only Jira (needs .env tokens)
scripts/jira_transition.py   Jira status + comments
scripts/generate_client.py   OpenAPI → packages/client; --check is the drift gate
scripts/diagnose.py          BM25 vs semantic vs fused (not the live path)
evals/golden_questions.toml  4 core, 40 long-tail, 18 trap, 8 holdout
evidence/latest.json         last measured run
evidence/retrieval_steps.md  slice-0 ladder
api/src/main.py              FastAPI; POST /ask; serves web/dist
api/src/ask.py               hand-rolled loop (_openai_complete, dispatch)
api/src/finish.py            fills required fields if the model stops early
api/src/guards.py            warning codes; evaluated at assemble
api/src/compare.py           comparisons[]
api/src/vintages.py          ACS1 vs non-overlapping ACS5
api/src/tools.py             search_tables, build_url
api/src/fetch.py             fetch_data; year/geo fan-out, cap 5
api/src/geo.py               resolve_geography → GeoSpec list
api/src/geo_list.py          state FIPS + NAME listings
api/src/census_url.py        CensusURL; default form never carries &key=
api/src/prompts.py           one system prompt
api/src/contract.py          AskRequest.plan; AskResponse; ResultPlan; ChartSpec; GeoSpec
web/                         Vite + React two-pane workspace
packages/client/             generated; CI fails if stale
```

## Retrieval — `api/src/retrieval/`, 9 modules

`metadata.py` `availability.py` `text.py` `bm25.py` `embedding.py`
`synthetic.py` `build.py` `index.py` `rerank.py`.

**`build.py` reaches OpenAI; `index.py` does not.** Nothing builds an index at
import or request time. The loaded index is the one sanctioned module-level
cache (read-only).

`search()` ranks embeddings. BM25 is in `lexical.json.gz` and unused while
`semantic.npz` exists. `search_tables` calls `rerank.choose()`; `search()`
does not. Detail: `docs/retrieval.md`.

636 family documents (from 1,458). Synthetics committed, not embedded.
Availability: `index_store/availability.json.gz` (not parquet).

## HTTP

One route: `POST /ask` → `run_ask`. Four tools. `AskResponse` fields and the
series/geo/comparison rules: `docs/ask-path.md`. `plan` is the executed table,
estimate variables, years, and `GeoSpec`s — not parsed from answer prose.
An optional `AskRequest.plan` pins those fields on the next `POST /ask`; the
four-tool loop still runs, and model args cannot undo the pin.
`Alternative` carries title and universe. Optional `chart` is a `ChartSpec` (line/bar roles over
`rows`); invalid model chart output is discarded (`chart_unavailable`).
`ambiguous_place` carries ranked `GeoSpec` candidates. Start:
`uv run uvicorn src.main:app --reload` (from `api/`, or with `PYTHONPATH=api`).

`make demo` is `scripts/run_demo.py --repeat 3` (golden set except holdout).

## Chat UI

Two panes. Chat keeps the question form and the natural-language answer.
The canvas is one active `AskResponse`: idle / loading / result / error.
A new submit leaves the current dataset visible until a successful response
replaces it; a failed request keeps that dataset and surfaces the failure
in chat. Refresh is not persistence. Narrow viewports stack chat above
canvas (`overflow-x: hidden` on the workspace); from `48rem` the panes sit
side by side. Dev server proxies `/ask` to `:8000`. Built `web/dist` is
served at `GET /` from the same origin.

The canvas renders one frontend-normalized table from `AskResponse`
(`normalizeActiveDataset` in `web/src/display.ts`): one visible row per
geography × year/period × estimate variable, with GEOID, dataset, vintage,
period, table, variable, raw estimate, and matching 90% MOE. Scalar and
multi-row answers share that model. Census sentinels and missing MOE are
unavailable (`—`), never zero. A `ChartSpec` on that response is translated
into Vega-Lite SVG (`web/src/chart.ts`) over the same rows, with one shared x
domain so comparison series overlay (lines) or cluster (bars); `chart_unavailable`
or an over-limit series count or embed failure shows a notice and keeps the table.
Homonymous Census NAMEs stay separate series (GEOID in the label); a `ChartSpec`
that omits `series_by` is inferred from the rows or declined if both geography
and variable vary. The plan
strip reads `AskResponse.plan` and
related `alternatives` / `ambiguous_place` candidates; apply POSTs the original
question plus that `ResultPlan`. CSV consumes that same `AskResponse`;
it must not keep a second copy.

## Data

```
data/raw/                      ACS5/ACS1 2016–2024 (no ACS1 2020). Gitignored.
data/synthetic_questions.json  committed; not fed to the embedding.
index_store/lexical.json.gz    636 families + BM25 postings. Gitignored.
index_store/semantic.npz       636 × 3072.
index_store/availability.json.gz
```

## What each open slice adds here

| slice | adds |
|---|---|
| 4 (CC-11) | canvas, ChartSpec, plan strip, CSV |
| CC-91 | residual warning/URL determinism — not a new component |
| *CC-9 spike* | a decision in DESIGN §9, not code |
| 5 | Postgres, thread_id |
| 6 | follow-up resolution |
| 7 | report worker + object storage |
| 8 | auth, container, baked index |
| CC-77 | after CC-11 foundations; not yet |
