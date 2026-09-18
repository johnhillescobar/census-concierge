# ARCHITECTURE — the system as it IS

**Status: slice 0 is built; slice 1 has `POST /ask`, the four-tool loop, the
five DESIGN §4 guards, and `make demo`; slice 2 has a single-pane Vite chat
UI that POSTs `/ask` through types generated from the OpenAPI schema, served
from the same FastAPI process when `web/dist` exists; slice 3 has started:
`fetch_data` fans `years` and comparison `GeoSpec`s out concurrently (cap 5)
and `AskResponse` carries `urls[]` plus per-leg `for_spec` and unique year
buckets; a year series picks ACS1 when Census publishes every listed member
(200 with rows), else non-overlapping ACS5 end years, omitting unpublished
points (`omission_reasons[]`, `vintage_gap_2020`, `acs1_geography_ineligible`);
`resolve_geography` returns ordered `GeoSpec` values authorized by that
dataset/vintage `geography.json`; a named-county parent becomes `for=tract:*`
without listing tracts; `versus` / `compared to` / `compare … to` emits two
executable specs plus leftovers (`compare` skips `ambiguous_place` only at two); combining
published medians is declined (`median_not_aggregatable`, with `B19001` offered
for B19013) and additive areas combine via `sqrt(sum(MOE_i^2))`, warning past
five (`moe_aggregation_degraded`); ZIP language emits `zcta_not_zip` without
refusing a valid ACS5 ZCTA; a named ACS5 ZCTA is `for=zip code tabulation area:<code>`
with no `in=` and no national listing, ACS1 ZCTA fail-closes from that vintage's
`geography.json` before any listing, and non-expressible containment emits
`geography_not_nested` with no invented fetch.** Retrieval runs
end to end as a two-stage pipeline: `search()` retrieves a top-10 pool;
`rerank.py` selects one table from it. `search_tables` applies that pick;
`index.search()` does not. `budgets.toml` gates retriever `@10` and
selector `@1` on the long-tail tier separately — raw cosine `@1` is diagnostic
only. The ask loop fills `AskResponse` from tool artifacts — URL, paired MOE, GEOID,
universe, structured alternatives, and non-blocking `warnings[]`. `scripts/run_demo.py`
POSTs the golden set at `/ask` and merges `answered_rate`, `p95_latency_seconds`,
timing splits, `prompt_hash`, and `index_hash` into `evidence/latest.json`.

This file is deliberately not a design document. `.claude/DESIGN.md` holds what
we intend and why; `.claude/PLAN.md` holds the order. **This file holds only what
exists and runs.** When the two disagree, this one is right and the others are
out of date.

The rule that keeps it honest: **if a PR changes the shape of the system, it
updates this file in the same commit.** A shape change means a new component, a
new boundary between components, a new external dependency, or a change to how
data crosses one of those boundaries. Renaming a function is not a shape change.

## What exists today

```
budgets.toml                 enforced complexity limits
scripts/check_budgets.py     counts things — exits 1 on violation
scripts/check_invariants.py  named anti-patterns (agent frameworks, sqlite,
                             contextvars, ticket-named tests, prompt
                             assertions, forbidden module suffixes,
                             clarification files or directories, empty secret defaults,
                             `&key=` outside CensusURL, leaked keys in
                             evidence JSON); --base catches a weakened budget
scripts/fetch_metadata.py    caches ACS metadata to data/raw/ (no key)
scripts/verify_golden.py     every expect_table checked against that metadata
scripts/build_index.py       builds index_store/ (needs OPENAI_API_KEY)
scripts/eval_retrieval.py    the scoreboard; --rerank, --holdout
scripts/run_demo.py          POST /ask scoreboard; --repeat, --tier
scripts/e2e_capture.py       eval + demo transcript into evidence/slice-<N>/
scripts/score_synthetic.py   generated-question quality, on a 600 sample
scripts/jira_transition.py   Jira status + comments via REST (needs .env tokens)
scripts/generate_client.py   OpenAPI → packages/client; `--check` is the drift gate
evals/golden_questions.toml  70 scorable: 4 core, 40 long-tail, 18 trap,
                             8 held out. All verified 2026-08-14.
evidence/latest.json         last measured run
evidence/retrieval_steps.md  every step's number, and what the plan got wrong
docs/playbooks/review-pr.md  canonical review procedure
pyproject.toml               uv workspace root; ruff + mypy + pytest config
api/pyproject.toml           the app's dependencies
api/src/main.py              FastAPI app; `POST /ask` → `run_ask`; serves `web/dist`
api/src/ask.py               hand-rolled tool loop (`dispatch`, no graph)
api/src/guards.py            DESIGN §4 guards; evaluated at assemble
api/src/vintages.py          ACS1 vs non-overlapping ACS5 year plan
api/src/tools.py             search_tables, build_url
api/src/fetch.py             fetch_data; years and comparison-geo fan-out, vintage plan, cap 5 in flight
api/src/geo.py               resolve_geography; GeoSpec list, legality per vintage
api/src/geo_list.py          state FIPS lookup and Census NAME listings
api/src/census_url.py        CensusURL — default form never carries `&key=`
api/src/prompts.py           one system prompt; date and vintages injected
.github/workflows/check.yml  the gate, on every PR
.github/workflows/build-index.yml  manual; publishes the index release asset
web/                         Vite + React + TypeScript chat pane
packages/client/             generated from `/openapi.json`; CI fails if stale
```

### Retrieval — `api/src/retrieval/`, 8 modules

```
metadata.py      fetch + cache ACS groups/variables/geography; family_id(),
                 is_subject_table()
availability.py  (dataset, vintage, table) -> universe + variable list.
                 Built for slice 3's guards; slice 0 uses its table union.
text.py          vintage-token stripping, !!-label unpacking, tokenizing
bm25.py          Okapi BM25, no dependency; corpus-derived stopwords
embedding.py     OpenAI embeddings; imports the client INSIDE the functions
synthetic.py     LLM question generation, cached and committed
build.py         assembles the artifact. Reaches OpenAI.
index.py         loads the artifact, search(question, k). Never builds.
rerank.py        LLM picks one of the top k. search_tables calls choose();
                 search() does not.
```

The boundary that matters: **`build.py` reaches OpenAI, `index.py` does not.**
The artifact is produced offline and, in production, downloaded into the image.
Nothing builds an index at import or at request time.

`index.py` caches the loaded index at module scope — the one piece of
module-level state this project allows, sanctioned because it is read-only.

### HTTP — `api/src/main.py`, `ask.py`, `contract.py`

One FastAPI app, one question-answering route: `POST /ask`. `/docs` and
`/openapi.json` come from the framework. When `web/dist` exists, `create_app()`
mounts it at `/` (`StaticFiles`, directory index). There is no CORS middleware.
The route calls `run_ask(question)` and
returns `AskResponse` — `answer`, `urls[]` (one key-redacted Census URL per
attempted request), per-leg `legs[]` (`for_spec` identifies the geography) and
unique year buckets (`requested` / `attempted` / `succeeded` / `failed` /
`omitted`), `rows`, `moe`, `geoid`,
`universe`, `table_id`, `alternatives[]`, `warnings[]`. Rows are dicts, not a
per-row model. Start with `uv run uvicorn src.main:app --reload`.

`run_ask` is a hand-rolled loop (`complete` then `dispatch`), not a graph and
not `create_agent`. Four `BaseTool`s: `search_tables` (Slice 0 index, then `rerank.choose`),
`resolve_geography` (every `geography.json` fips row for the selected dataset
and vintage — `geo_levels()` last-wins is 324 and is the wrong county predicate;
NAME listing includes `B01003_001E` and ranks filtered matches by place class,
population, then GEO_ID — `specs[0]` is selected, the rest stay on `geographies`
so `ambiguous_place` still warns; a `versus` / `compared to` / `compare … to`
split emits one executable spec per side plus leftovers, and `compare` skips
that warning only when there are two; a versus that is not two places keeps
the side that resolved;
a named-county parent of a tract wildcard is resolved from that state's county
listing and emitted as `for=tract:*` without listing tracts; a named ACS5 ZCTA is emitted from the 5-digit
code without listing; ACS1 has no ZCTA row so that path fail-closes before any
GET; emitted `GeoSpec` values are metadata-backed
`for`/`in` clauses, not model prose), `build_url` (availability matrix;
empty `variables` is the table total `001E`, then E paired with M),
`fetch_data` (live Census; `years` fans out under a 5-in-flight / 12-year cap
and the two comparison specs rewrite `for`/`in` on the built URL the same way; a `:*`
wildcard stays one GET; each URL is kept on failure; an ACS1 204/404 on any
comparison leg destaggers every leg to non-overlapping ACS5). `assemble()`
pairs each estimate with its `M`, classifies `alternatives[].reason` (universe,
distribution versus median, collapsed table, race iteration, or related table),
and puts AFFGEOID
`GEO_ID` on every fetched row (empty on a combined total, which is not a
published geography). Top-level `geoid` names one geography or is empty.
`evaluate()` in `guards.py` then attaches DESIGN §4 warnings from the execution
record: overlapping ACS5 vintages, MOE-indistinguishable differences (same-year
geography legs on a versus series, not same-place years), illegal
geography combinations, several matching places, questions that cross
universes, combined published medians, RSS MOE over more than five areas,
ZIP-vs-ZCTA requests, and containment Census `for`/`in` grammar cannot express.
None of them blocks. Additive combine appends one summed row per vintage; a
median combine does not. `CensusURL` redacts `&key=` in `__str__` / the
response; `with_key()` is the httpx site. Missing or empty
`CENSUS_API_KEY` / `OPENAI_API_KEY` raise `ValueError` rather than
calling Census or OpenAI unauthenticated. `langchain_core` supplies schema and
`ainvoke`; control flow is ours. `make demo` is `scripts/run_demo.py --repeat 3`.

### Chat UI — `web/`

Vite + React + TypeScript, one pane. `npm --prefix web run dev` proxies
`POST /ask` to the API on `:8000`. After `npm --prefix web run build`, FastAPI
serves `web/dist` at `GET /` from the same origin as `POST /ask`. The Census URL
is visible and has a copy control; the copied text is the redacted URL.
`web/src/ask.ts` imports `AskResponse`
from `packages/client/schema.d.ts`, which `scripts/generate_client.py`
writes from `app.openapi()` via `openapi-typescript`. `make check` and CI
regenerate and fail on drift. Census-fetch failure is `urls`
set and `rows` empty — there is no `http_ok` on the contract. An empty `urls`
(loop aborted before `build_url`) is a status notice, not a `—` standing in for
the URL. Census missing sentinels (`-555555555` and the rest) render as `—`.
The pane uses `data-state` `idle` / `loading` / `error` / `result`.

### Data and artifacts

```
data/raw/                     14 MB cached ACS metadata. Gitignored.
                              ACS5 2016-2024, ACS1 2016-2024 (no 2020).
data/synthetic_questions.json 8,748 questions, 1 MB, COMMITTED and readable.
                              Currently not fed to the index — see below.
index_store/lexical.json.gz   636 table families: ids, titles, universes,
                              members, BM25 postings. Gitignored.
index_store/semantic.npz       636 x 3072 float32 embeddings.
index_store/availability.json.gz  the vintage matrix.
```

### What the index contains, and what it dropped

1,458 tables in the union across all vintages → **636 documents**:

- **588** race iterations (`B19013A`) and Puerto Rico variants folded into their
  base table. They are the same table filtered, they carry near-identical
  titles, and they crowded out their own parents. Members are retained in the
  artifact and become slice 1's `alternatives[]`.
- **114** `B00`/`B98`/`B99` survey-quality tables dropped — allocation rates and
  sample counts, never the subject of a question.
- **120** collapsed `C` tables folded into the `B` they are identical to.
  `C15003` publishes the same title, universe and concept as `B15003` with
  fewer categories, so the two documents were byte-identical and their vectors
  equal — the winner decided by float noise, and reversible on any rebuild.
  Members like the race iterations.

`search()` ranks on embeddings alone. BM25 is built and unused: equal-weight RRF
measured *worse* than embeddings alone on every metric. It is kept for the query
that names a table ID verbatim, which the eval set does not test.

`check_budgets.py` gates `retrieval_at_10`, `selector_at_1`, and
`synthetic_alignment` from `make eval`. `synthetic_self_retrieval` (@1 rank
against the full index) is recorded as a diagnostic only — questions are not
embedded; see `evidence/retrieval_steps.md`.

## What each slice adds here

Fill these in as they ship. Delete this list when it is no longer a list of
futures.

| slice | adds to this file |
|---|---|
| ~~0~~ | ~~the index~~ — done, above |
| ~~1~~ | ~~`POST /ask`, four-tool loop, `CensusURL`, DESIGN §4 guards, `run_demo.py`~~ — done, above |
| ~~2~~ | ~~`web/` chat pane (CC-24). Generated client (CC-27). FastAPI serves `web/dist` (CC-32)~~ — done, above |
| 3 | fan-out over years (`fetch_data.years`, `urls[]`); `GeoSpec` list from `resolve_geography`; median/MOE aggregation (CC-61); ZCTA/non-nesting (CC-60); named ACS5 ZCTA without listing (CC-71); ACS1 where published else non-overlapping ACS5 (CC-72); wildcard tract parent + versus-split geo fan-out (CC-73); remaining series guards still open |
| 4 | the canvas and its state model |
| *spike* | *nothing — it produces a decision in DESIGN §9, not code* |
| 5 | Postgres, `thread_id`, conversation persistence |
| 6 | follow-up reference resolution |
| 7 | the report worker and object storage |
| 8 | auth, deployment topology, the container and what is baked into it |

## Diagram

None yet. When there is one, it goes here and it shows what runs — not what was
planned.
