# DESIGN — census-concierge

The durable "what and why". Reverse a decision here in the same commit and say
why. Order: `.claude/PLAN.md`. What runs: `docs/ARCHITECTURE.md`. Contract and
guards: `docs/requirements.md`.

---

## 1. Product

A conversational concierge for the Census table ecosystem. A user asks in plain
language. The agent finds the right table — **especially one they have never
used** — and returns a natural-language answer, a working table or chart, and
the exact Census API URL. A session exports as a PDF with every URL.

Two panes: chat, and a canvas of tables and charts.

## 2. The failure this project exists to avoid

A predecessor reached 38,184 lines across 116 files, a 14-node LangGraph, 43
files of clarification, and 75–207 seconds to answer *"population of New York
City"*, wrong one run in three. Retrieval was faked with `B01003` for any
input. The API URL was a truncated stub and never shown.

**Root cause: the only signal was "tests pass".** An agent maximizes whatever
signal exists. Section 8 is the replacement signal.

## 3. Users

GIS professionals and non-profit researchers. Expert in a handful of tables,
lost in the other thousand. Consequences:

1. **Discovery is the product.** Effort belongs in the index and its eval.
2. **No blocking clarification.** Candidates are results plus an editable plan strip.
3. **Always show alternatives.** That is the concierge value.
4. **No silent wrong answers.** Universe errors and missing MOEs destroy trust.

## 4. Requirements

Every response ships URL (even on fetch failure), MOE, GEOID, universe, and
alternatives. Guards warn and still ship; none block. Full catalog:
`docs/requirements.md`.

## 5. Architecture (intent)

Monorepo: `api/` (Python 3.12), `web/` (React + TypeScript), generated
`packages/client/` (CI fails on drift). One tool-calling loop, four to six
tools. LangGraph only for durable checkpointing if the CC-9 spike says so —
never for routing.

**Concurrency is law now, not a slice-5 feature.** Even one user today will be
N workers tomorrow. No module-level mutable state; pass context as function
arguments. No `contextvars` set/reset — that pattern leaks across users. The
read-only index is the only exception. Async endpoints. Horizontal scaling is
the test: if a second worker would see different state, the design is wrong.
`check_invariants.py` fails the build on sqlite and contextvars.

Postgres, `thread_id`, and `user_id` ownership land in slice 5 / CC-6.
**Never SQLite** is already decided so that epic cannot undo a local
`checkpoints.db`. CC-6 does not invent the no-globals rule; it stores
conversations under it.

PDF is a background job, never a request handler. The LLM emits a `ChartSpec`;
the frontend renders. Auth is bought (Clerk, slice 8). Tracing is Langfuse at
slice 8 (CC-48), by hand in the complete/dispatch choke points — not LangSmith.

One container: FastAPI serves the API and the built frontend, pinned index
baked in, managed Postgres, object storage for PDFs. The index is a GitHub
Release asset, never built during `docker build`. The container filesystem is
ephemeral.

## 6. Retrieval

Census titles have no overlap with how people ask (`bike to work` → B08301).
Index **universe + title + concept**. Synthetics are generated and committed,
not embedded. `search()` ranks embeddings; BM25 is built, not fused, and is
not a live query path. Variable-level *fetch* is CC-77, not the index.

Two layers: a vintage-agnostic semantic index over the union of table IDs, and
a per-vintage availability matrix (`index_store/availability.json.gz`). No
vector database — numpy `.npz` at this scale.

Measured corrections (ladder + encoder sweep): `docs/retrieval.md`.
What moved `@1` was corpus structure (1,458 → 636 family documents), not RRF
and not synthetic-in-the-vector.

Gate: long-tail retriever `@10` and selector `@1`. `answered_rate` is the
number once an agent exists. `long_tail` is the scoreboard; `core` proves
nothing.

## 7. Deliberately not building

| | until |
|---|---|
| Clarification subsystem | the demo suite names the questions that need it |
| Gazetteer | CC-55: NAME ranking (CC-54) and plan strip (CC-37) still fail a golden question |
| Informal region aliases | CC-96: no gazetteer table; the ask loop maps vernacular to published NAMEs; last-word leaf is CC-99 |
| A fifth tool | CC-56: a golden question fails because no existing tool can do X |
| Graph nodes for branching | never |
| Typed contracts at every boundary | a real bug demands one |
| Caching, queues, a second repo | someone complains / a second team |
| PUMS, LEHD, CBP, decennial | ACS works end to end |

## 8. Anti-drift harness

1. `budgets.toml`, enforced in CI. An agent **never** raises a budget.
2. `make demo` is done. Quote the scoreboard; green tests are not done.
3. Behavior tests only. No prompt-wording asserts, no ticket-named tests, no
   fake that returns one table for every input.
4. `CLAUDE.md` and `.cursor/rules/` stay short, mostly prohibitions.
5. A PR over ~15 files is a redesign wearing a feature's clothes.

## 9. Open decisions

- ~~**Canvas model**~~ — **living workspace** (CC-11), not a card stack.
- ~~**Embedding / vector store**~~ — numpy `.npz`, embeddings-only `search()`.
  `docs/retrieval.md`.
- ~~**StateGraph for the loop**~~ — hand-rolled `_openai_complete` then
  `dispatch`. Still open: CC-9, whether LangGraph's checkpointer can sit under
  that loop without a graph. If not, ~30 lines.
- ~~**ACS vintages**~~ — ACS5 and ACS1, 2016 through latest (no ACS1 2020).
