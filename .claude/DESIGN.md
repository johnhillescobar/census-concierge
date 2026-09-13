# DESIGN — census-concierge

The durable "what and why". If a decision here is reversed, edit this file in
the same commit and say why. `PLAN.md` holds the "when and in what order".

---

## 1. Product

A conversational concierge for the Census table ecosystem.

A user asks in plain language. The agent finds the right table — **especially
one the user has never used** — pulls the data, and returns three things
together: a natural-language answer, a working table or chart, and the exact
Census API URL that produced it. At the end of a session the whole conversation
exports as a PDF with a table of contents, a summary, the tables, the
visualizations, and every API URL.

Two panes: chat on one side, a canvas of tables and charts on the other.

## 2. The failure this project is designed to avoid

A predecessor (`census_tool`) reached:

- 38,184 lines of Python across 116 source files
- ~100 test files, a 14-node LangGraph with 10 conditional-edge blocks
- 43 of 125 source files touching a clarification subsystem
- 8 separate validation modules that nobody decided to build
- 75–207 seconds to answer *"What's the population of New York City?"*, wrong
  one run in three

Its retrieval was faked in tests by a stub returning `B01003` for any input, so
a broken retriever stayed hidden for months. The API URL — the headline feature
— was built as a truncated stub missing variables and geography, and never
rendered anywhere a user could see it.

**Root cause: the only feedback signal was "tests pass", so that is what got
optimized.** An AI coding agent maximizes whatever signal exists. Everything in
section 8 follows from this.

## 3. Users, and what follows

GIS professionals, non-profit researchers, and others who work with Census data
regularly. Initially ~10 known users; more if it proves out.

They are **expert in a narrow subset of tables and lost in the other thousand.**
Someone who knows income tables cold may never have touched housing, commuting,
or disability tables, and may not know the subject tables exist.

Four consequences:

1. **Discovery is the product.** Retrieval quality is not a supporting concern;
   it is the thing being sold. Engineering effort belongs in index construction
   and retrieval evaluation, not orchestration.
2. **No blocking clarification questions.** A user who does not know the
   ecosystem *cannot answer* "which table did you mean?" Show candidates as
   results with an editable plan strip instead.
3. **Show alternatives, always.** Related and adjacent tables are the concierge
   value, and they teach the ecosystem one answer at a time.
4. **They will not tolerate silent wrong answers.** Universe errors and missing
   margins of error destroy trust permanently with this audience.

## 4. Non-negotiables in every response

| | why |
|---|---|
| **Full API URL** | The product. Variables, geography, vintage. Rendered even when the fetch fails or the agent is unsure — a wrong URL is fixable in ten seconds, wrong prose is not. |
| **Margins of error** | Fetch `M` beside every `E`. ACS estimates without MOE are professionally useless to a researcher; small-geography MOEs routinely swamp the differences people want to compare. |
| **GEOID** | They join to TIGER shapefiles. Place names do not join. |
| **Universe** | "Households" vs "families" vs "population" vs "housing units" is the most common silent wrong answer in Census work. |
| **Alternatives** | Related tables, with the reason they differ. |

### Guards

Conditions the agent must **raise rather than answer through**. Every one of
them fails silently by default: the answer looks right, charts cleanly, and is
wrong. Each has a warning code, each has a trap question in
`evals/golden_questions.toml`, and **none of them blocks** — the answer still
ships, with the warning attached and the user free to override.

Shipping in **slice 1**:

| code | condition |
|---|---|
| `overlapping_vintage` | ACS5 periods sharing sample years (2015–2019 vs 2018–2022) are not comparable. Warn; never silently chart. |
| `moe_not_significant` | Differences inside the margin of error are reported as indistinguishable, not ranked. |
| `geography_unsupported` | A table not published at the requested level is said plainly, never silently substituted. |
| `ambiguous_place` | "Springfield" returns the candidates **as results**. Never a blocking question — a user who does not know the ecosystem cannot answer one. |
| `universe_mismatch` | A question crossing households × families × population × housing units surfaces the conflict instead of picking one. |

Added in **slice 3** (series and comparisons). These are standard questions for
this audience, and every failure in them is silent.

Across years:

| code | condition |
|---|---|
| `measure_unavailable` | The Census does not measure it at all. Say so, then offer the nearest real thing and name its universe. |
| `acs1_geography_ineligible` | ACS1 is published only for places of 65,000+, so no annual series exists for smaller geographies. |
| `vintage_gap_2020` | The standard 2020 ACS1 release was never issued. Show a gap; never interpolate or bridge. |
| `boundary_change_2020` | Tract and block-group geometry was redrawn; a series crossing 2020 compares different polygons. |
| `variable_not_in_vintage` | A variable absent — or present but redefined — in part of the requested range. The redefined case is the dangerous one. |

Across geographies:

| code | condition |
|---|---|
| `zcta_not_zip` | ZIP codes are USPS delivery routes; ZCTAs are block-built approximations. ~10% of ZIPs have no ZCTA, ZCTAs nest in nothing, and ACS1 does not publish them. |
| `geography_not_nested` | The requested containment is not expressible — tracts nest in counties, not places; a ZIP overlaps a city rather than sitting inside it. Splitting one needs block-level areal allocation, which is out of scope. |
| `median_not_aggregatable` | Medians cannot be combined across areas by any weighting. Decline the computation rather than produce a plausible wrong number. |
| `moe_aggregation_degraded` | Estimates sum; MOEs do not. `sqrt(Σ MOEᵢ²)` is an approximation that degrades past a handful of areas. |

**A silently short series is the same failure as a wrong one.** When years,
geographies, or variables are dropped, the response says which and why.

## 5. Architecture

**Monorepo.** Two repos for one developer buys nothing and costs version skew,
two CI configs, and contract drift.

```
api/                FastAPI + agent (Python 3.12)
web/                React + TypeScript
packages/client/    generated from the OpenAPI schema
evals/              golden_questions.toml — the specification
scripts/            check_budgets.py, eval_retrieval.py, run_demo.py
evidence/           latest.json — what the last run measured
docs/ARCHITECTURE.md   one page, the system as it IS
budgets.toml        enforced complexity limits
```

CI regenerates the TypeScript client from FastAPI's OpenAPI schema and **fails
if it differs from the committed copy.** A breaking API change therefore cannot
merge without its frontend change in the same commit.

**Agent shape: one tool-calling loop, four to six tools.** LangGraph only where
durable checkpointing and multi-user resumption genuinely require it — never for
routing. Routing branches are the mechanism by which the predecessor grew to 14
nodes.

**Concurrency.** Postgres from day one, never SQLite. `thread_id` per
conversation. No module-level mutable state; context is passed as arguments so
workers scale horizontally. Per-user spend cap from the first deployed slice.

**PDF is a background job.** `POST /reports` → job id → poll or SSE. Never a
request handler; generation takes tens of seconds and blocks a worker.

**Charts: the LLM emits a `ChartSpec`, the frontend renders it.** Never chart
code, never SVG — unreviewable, unverifiable, and a security problem once hosted.

**Auth is bought, not built.** Clerk / Auth0 / Supabase. At ~10 users this is an
afternoon.

**Observability: Langfuse.** *(Changed 2026-08-13 — this said LangSmith, whose
only stated advantage was being "an env var away with LangChain/LangGraph." That
argument died when we chose to own the loop.)* With manual instrumentation as
the baseline either way, Langfuse's SDK is the nicer one to write by hand, and
it links traces to prompt versions — which pairs directly with `prompt_hash`.
About twenty lines, inside `call_model()` and `dispatch()`, which are already
the choke points.

**Deployment: one container.** FastAPI serves the API *and* the built frontend
as static files, on Render (Fly.io is an equal substitute), with that provider's
managed Postgres. One deployable, one domain, no CORS, no second host — at ten
users a separate CDN for the frontend buys nothing and costs a pipeline. Auth is
Clerk: unlike an edge allowlist it survives the move to public signup. Running
cost ~$25–40/month plus model usage.

```
                     ┌── Clerk (JWT) ──┐
  browser ── TLS ──▶ one container ─────▶ managed Postgres
                     FastAPI
                     + static frontend
                     + baked index
                          ├──▶ object storage (PDFs)
                          └──▶ api.census.gov · OpenAI
```

**The index ships as a pinned artifact.** A manually-triggered GitHub Actions
workflow builds it and publishes a versioned Release asset; the Dockerfile
downloads that exact version. It is never built during `docker build` — that
would need an API key at build time and make images nondeterministic. This is
what makes `index_hash` operationally real: the hash in `evidence/latest.json`
corresponds to a release tag you can point at.

**The container filesystem is ephemeral.** Nothing durable is written to disk at
runtime. Generated PDFs go to object storage and come back as signed URLs.

## 6. Retrieval design — the core

Semantic search over table titles alone will not work. Census titles are terse
jargon (`MEDIAN HOUSEHOLD INCOME IN THE PAST 12 MONTHS (IN 2023
INFLATION-ADJUSTED DOLLARS)`) and nobody types that. The gap is real:

```
"how many people bike to work"  ->  B08301  MEANS OF TRANSPORTATION TO WORK
"worst broadband access"        ->  B28002  PRESENCE AND TYPES OF INTERNET
                                            SUBSCRIPTIONS IN HOUSEHOLD
```

Zero lexical overlap in either case. Four requirements:

1. **Index the universe**, not just the title. It is both a retrieval signal and
   a required display field.
2. **Index at variable level as well as table level.** Users want one line
   inside a large cross-tab they would never find by table name.
3. **Generate synthetic questions at index time.** For each table, have an LLM
   write 5–10 questions it answers, and embed those alongside the metadata.
   Matching a user question against *other natural questions* works far better
   than matching against Census title-case. Highest-leverage item in the stack.
4. **Hybrid search.** Lexical (BM25) for exact IDs and jargon, embeddings for
   semantics. Users will type both `B19013` and "gross rent as a percentage of
   income". Fuse with reciprocal rank fusion — the score scales are
   incompatible, and any weight is tuned against 40 questions.

### Two layers, because questions span 2016 → latest

A table's *meaning* is stable across vintages; its *availability and definition*
are not. Those are different data structures, and conflating them means either
one index per vintage (nine times the embedding and LLM cost) or silently wrong
answers about what existed when.

- **Semantic layer — vintage-agnostic, built once**, over the union of table IDs
  across all vintages so discontinued tables stay findable. Vintage tokens are
  normalized out of the indexed text: `(IN 2023 INFLATION-ADJUSTED DOLLARS)` is
  noise that pollutes embeddings and gives BM25 a year to match on.
- **Availability matrix — per vintage.** `(dataset, vintage, table_id,
  variable_id) -> exists`, plus universe. A lookup, not a search. This is what
  lets `variable_not_in_vintage` and `acs1_geography_ineligible` join on facts
  rather than expecting the model to remember when the computer tables were
  reworked.

### No vector database

~1,300 table groups is ~8 MB of embeddings; brute-force cosine over 30k vectors
runs in single-digit milliseconds. numpy `.npz` + BM25, loaded at startup. Chroma,
FAISS and pgvector are all a service, a dependency and a class of bugs bought for
nothing at this scale. Revisit if decennial or PUMS land.

**The index is a build artifact, not runtime state** — built offline by a script
that needs an API key and ~1,300 LLM calls, then served read-only and baked into
the container image. Not object storage, not a shared database. The operational
argument is that ACS refreshes annually and deploys are more frequent; the
decisive argument is that `evidence/latest.json` records a score for a *specific*
index, so an index that can change under a running deployment makes the
scoreboard describe something that is no longer running.

### Corrections, measured 2026-08-14 (slice 0)

Full ladder in `evidence/retrieval_steps.md`. Three claims above did not survive
contact with the corpus:

- **~~Fuse BM25 and embeddings with RRF~~.** Equal-weight RRF scored below
  embeddings alone on every metric. `search()` ranks on embeddings; BM25 is
  built and unused, kept for verbatim table-ID queries.
- **~~Synthetic questions are the largest jump~~.** They were the largest drop
  (`@1` 40%→25%). Generated and committed; not fed to the embedding.
- **What worked was corpus structure, not ranking.** One document per table
  family, no survey-quality tables, and no `C` table identical to its `B`:
  1,458 documents → 636. Every step reads the table ID, which is the most
  informative field in this corpus.

### The metric

`retrieval@1` — the fraction of eval questions where the correct table is ranked
**first**. The agent acts on the top hit; a right answer at rank 4 is a wrong
answer to the user.

**`@1` is a proxy, and should be treated as one.** The number that matters is
`answered_rate`, which cannot be measured until an agent exists in slice 1. `@1`
is the best stand-in available before then — but it assumes the agent takes the
top hit rather than weighing two or three candidates on universe and vintage. If
it turns out to do the latter, `@3` is the honest gate and `@1` is needlessly
punishing. So `@3` is recorded from the first eval run onward, ungated, and the
choice gets revisited on that data rather than on argument. Do not over-optimize
a proxy without knowing it is one.

`@5` and MRR are diagnostics, and the gap between them is informative:

- **@5 low** → the index is broken; the table is not findable at all.
- **@5 high, @1 low** → ranking problem; a reranker fixes it. Much cheaper.

### Why the eval set is deliberately long-tail

> A question belongs in the eval set if **the user could not already answer it
> themselves.** If they know the table is B19013, they do not need this product.

Easy questions score well and measure nothing — a retriever that nails
"population of Harris County" and misses the two examples above would score 100%
on a core-only set and be useless. That is the `B01003`-stub failure with extra
steps.

`evals/golden_questions.toml` is tiered `core` / `long_tail` / `trap`.
**`long_tail` is the number on the scoreboard.** Building the set, in order of
value: ask real census nerds for the last ten questions they struggled with;
sample programmatically across topic prefixes; and use the heuristic *if you had
to look up the table ID, it belongs in the long tail.*

## 7. Deliberately not building

| | until |
|---|---|
| Clarification subsystem | the demo suite proves specific questions need it |
| Gazetteer / geocoder module | ranked NAME listing (CC-54) and plan-strip override (CC-37) still fail a golden question. Census `onelineaddress` matches zero county names (CC-23). |
| A fifth agent tool | a question in `golden_questions.toml` fails because no existing tool can do X. Years are a parameter (slice 3 / CC-28), not a tool. |
| Graph nodes for branching | never |
| Typed contracts at every boundary | a real bug demands one |
| Caching, queues, horizontal scaling | someone complains |
| Multi-repo split | a second team exists |
| PUMS, LEHD, CBP, decennial beyond basics | ACS works end to end |

## 8. Anti-drift harness

Because the signal is what gets optimized, the signal is a user-value number.

1. **`budgets.toml`, enforced by `scripts/check_budgets.py` in CI.** Caps lines,
   files, graph nodes, tools, models, dependencies, latency, and floors on
   retrieval and answered rate. **A coding agent may never raise a budget.**
   Raising one is a standalone human commit with a written reason in the log at
   the bottom of that file. This turns invisible growth across fifty PRs into
   about ten decisions a human made and can read back.
2. **`make demo` is the definition of done.** Real questions, real APIs, pass
   rate and p95 latency. The PR template requires pasting the output. Green
   tests are not done; a closed ticket is not done.
3. **Behavior tests only.** Question in, table and URL out. No assertions on
   prompt wording or LLM prose. No test named after a ticket. No fake that
   returns the same table for every input.
4. **`CLAUDE.md` and `.cursor/rules/` are short and mostly prohibitions**, each
   one earned by a specific predecessor failure.
5. **Diff-size tripwire.** A PR touching more than ~15 files is a redesign
   wearing a feature's clothes. CI says so loudly.

The scaffold starts **red**: with nothing built, every structural budget passes
and `retrieval_at_1` fails. You cannot reach green by writing code, only by
making retrieval work.

## 9. Open decisions

- **Canvas model: card stack or living workspace?** Experts refine rather than
  ask independent questions — *"population by county in Texas"* → *"add median
  income"* → *"only counties over 100k"*. That is one dataset being iterated,
  not four cards. Leaning workspace. Affects the state model, so decide before
  slice 4.
- **Table IDs in `evals/golden_questions.toml` are unverified.** Written from
  memory as a starting point; each must be checked against the live groups
  endpoint before it is trusted. A wrong fixture trains you to "fix" correct
  behavior.
- ~~**Embedding model and vector store**~~ — **decided 2026-08-13.** No vector
  store: numpy `.npz` + BM25, fused with RRF, baked into the image. See §6.
  Embedding model **provisionally** `text-embedding-3-small`; at least two
  models get compared at slice 0's embedding step, since Census jargon is
  unusual enough that general benchmarks may not carry over.
- ~~**StateGraph for the agent loop**~~ — **decided 2026-09-12.** The agent is
  a hand-rolled loop (`call_model()` then `dispatch(tool_call)`), not
  `create_agent` and not a `StateGraph`. Graph nodes for routing stay banned
  (§5, §7). Still open, spiked before slice 5 (PLAN): whether LangGraph's
  Postgres checkpointer can sit under that loop without reintroducing a graph.
  If it cannot, persist with ~30 lines.
- **Which ACS vintages and datasets** ship first (acs5 only? acs1 too?).
