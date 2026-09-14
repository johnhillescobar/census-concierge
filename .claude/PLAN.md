# PLAN — census-concierge

Execution order. `DESIGN.md` holds the what and why.

## Rules for using this document

1. **Slices ship in order. Nothing in slice N+1 starts until N is demoed.**
   Every slice ends in something a person can watch you use.
2. Each slice has a **Not in this slice** list. That list is the point. When a
   coding agent proposes something on it, the answer is "not yet" — say which
   slice it belongs to.
3. **Done means a user got an answer.** Paste `make demo` output. A passing
   pytest run is not done. A new test file is not done. A closed ticket is not
   done.
4. If a slice needs a budget raised, stop and ask. That is a separate human
   commit with a reason logged in `budgets.toml`.
5. **A spike is not a slice.** It is timeboxed, runs on a throwaway branch, and
   ships a written decision rather than code — so rules 1 and 3 do not apply to
   it. Overrunning the timebox is not a reason to extend it; it is the answer,
   and the answer is the simpler option. Spikes exist to stop a framework
   decision from being made halfway through the slice that depends on it.

---

## Slice 0 — Table index + retrieval evaluation

**No agent. No FastAPI. No frontend. No database.** If long-tail retrieval
cannot clear the floor, nothing downstream rescues it, and you learn that in
week one instead of month four.

### Metadata first

- [x] Pull `groups.json`, `variables.json` and `geography.json` for **every
      vintage in scope — ACS5 and ACS1, 2016 through latest.** Cache to disk.
      No LLM, no cost, and everything below is a join over it.
- [x] **Verify `evals/golden_questions.toml` programmatically** against the
      metadata you just pulled — ten lines, not an hour in a browser. Delete the
      warning at the top of the file. *A wrong fixture is worse than none.*
- [x] Build the **availability matrix**: `(dataset, vintage, table_id,
      variable_id) -> exists`, plus the universe string per vintage. A lookup,
      not a search; a few MB as parquet. Nothing consumes it until slice 1, but
      the index needs the union of table IDs anyway — and it is what lets the
      slice 3 guards join on facts instead of guessing.
- [x] `geography.json` is the authority on which `for`/`in` combinations are
      legal. The agent looks it up, never reasons about nesting from memory: an
      invented `for=zcta:*&in=county:X` returns a 400 that the model will then
      "fix" by inventing a different wrong call.

### The question set

- [x] Grow to **~40 `long_tail` questions**. That tier alone is the target —
      `core` and `trap` sit on top of it and **do not count toward it.** The
      scoreboard is `retrieval@1` on long-tail, so a file that grows by adding
      traps looks fuller while the metric stays half-built. *Currently 20.*
- [x] Source them without leaning on memory — hand-picking biases toward tables
      you already know, which is the bias the product exists to fix. Ask real
      census nerds for the last ten questions they struggled with; sample
      programmatically across topic prefixes.
- [x] Hold ~8 **long-tail** questions back. **Protocol:** iterate against the
      tuning set; that is what lands in `evidence/latest.json` and gates the
      budget. Run the holdout at slice boundaries only, recorded separately as
      `retrieval_at_1_holdout`. A sharp divergence means you tuned to the set
      rather than to the problem — a live risk at this n, not a theoretical one.

### The index

**No vector database.** ~1,300 table groups is ~8 MB of embeddings; brute-force
cosine over 30k vectors is single-digit milliseconds. numpy `.npz` + BM25,
loaded at startup. Revisit only if decennial or PUMS are added.

- [x] **Semantic layer: vintage-agnostic, built once**, over the *union* of
      table IDs across all vintages — discontinued tables must stay findable —
      using metadata from the most recent vintage each appears in.
- [x] **Normalize vintage tokens out of indexed text.** `(IN 2023
      INFLATION-ADJUSTED DOLLARS)` is noise: it pollutes the embedding and gives
      BM25 a year to match on.
- [x] Generate 5–10 synthetic questions per table with an LLM. **From table
      metadata only — never from the golden set**; that is leakage, and it would
      make the scoreboard lie convincingly. Cache on `(table_id, vintage,
      metadata_hash, model, prompt_hash)`. **Commit the output to git** — ~600 KB,
      and being able to read what the LLM wrote for `B28002` is how you catch
      garbage. (`.cursorignore` excludes `data/` from the coding agent's reach;
      that is not `.gitignore`.)
- [x] **Score the generated questions mechanically.** `scripts/score_synthetic.py`
      writes `synthetic_alignment` (mean cosine from each question to its table's
      semantic document) and `synthetic_self_retrieval` (@1 rank) into
      `evidence/latest.json`. The floor is **`synthetic_alignment >= 0.50`** —
      questions are not in the embedded document (folding them in hurt golden
      `@1`), so rank-1 self-retrieval (~45%) duplicates the golden-set ranking
      problem and is diagnostic only. Low alignment catches off-topic generation
      without requiring a question to beat 636 siblings at rank 1.
- [x] **Split the two indexes by strength, do not feed both everything:**
      BM25 gets title + universe + concept + *all* variable labels — length
      normalization handles long documents, and this carries jargon and exact
      IDs. Embeddings get title + universe + concept + synthetic questions —
      short and dense; a 500-label blob makes everything weakly similar to
      everything.
- [x] Fuse with **reciprocal rank fusion**, not weighted scores. The two score
      scales are incompatible and any weight you pick is tuned against 40
      questions.
- [x] Expose `search(question, k) -> [table_id, ...]` at
      `api/src/retrieval/index.py`. `scripts/eval_retrieval.py` picks it up
      automatically.
- [x] **The build script writes a file; nothing builds the index at import or at
      request time.** In production it is a pinned artifact downloaded into the
      image (DESIGN §5). Keep build and load in separate modules so the loader
      never pulls in the OpenAI client.

### Build in measured steps

A number before each next step, or you will never know which parts you can
delete:

```
BM25 only  ->  + embeddings  ->  + synthetic questions  ->  RRF  ->  reranker?
```

Expect the largest jump at synthetic questions. Add a reranker **only if `@5` is
high and `@1` is low** — the diagnostic already tells you.

- [x] At the embeddings step, **compare at least two embedding models** before
      settling. `text-embedding-3-small` is the documented default, not a
      finding: swapping the model and re-running the eval is an afternoon, and
      Census jargon is unusual enough that the ranking may not match the general
      benchmarks. Record which models were compared and their `@1` — otherwise
      the next person re-litigates it from scratch.

**Done when:** `make eval` clears the long-tail floors — retriever `@10 >= 0.90`,
selector `@1 >= 0.70`, `synthetic_alignment >= 0.50` — and
`python scripts/check_budgets.py` exits 0.

Two prescriptions were measured wrong and reversed: RRF fusion and synthetic
questions both *lowered* `@1`. Corpus fold (1,458 → 756) plus a generative
selector cleared the gate. Ladder: `evidence/retrieval_steps.md`.

> **STATUS 2026-09-12.** Slice 0 closed. Floors met. Evidence: `evidence/slice-0/`. Epic: https://johnhillescobar.atlassian.net/browse/CC-8.

**Read the number honestly.** At n=40, `@1` near 0.70 carries a standard error
of ~7 points — a 95% interval of roughly ±14. A move from 0.70 to 0.76 is noise,
and clearing the gate is consistent with a true rate near 0.60. Chase
step-changes, not deltas. Growing the long-tail tier toward 100 tightens the
interval to about ±9 and is the best harness investment after this slice ships.

**Not in this slice:** the agent, tool calling, any HTTP endpoint, geography
resolution, MOE handling, the UI.

---

## Slice 1 — `POST /ask`

- [x] FastAPI app with Swagger. One endpoint.

> **STATUS 2026-09-13.** Slice 1 closed. Floors met: answered_rate 0.803, p95 14.164s. Evidence: `evidence/slice-1/`. Epic: https://johnhillescobar.atlassian.net/browse/CC-1.
- [x] Tool-calling loop, 4 tools: `search_tables`, `resolve_geography`,
      `build_url`, `fetch_data`. **Not a graph.**
- [x] `build_url` returns the complete URL — variables, geography, vintage — and
      its output is returned to the caller **even when `fetch_data` fails.**
- [x] Response contract includes: `answer`, `url`, `rows`, `moe`, `geoid`,
      `universe`, `table_id`, `alternatives[]`, `warnings[]`.
- [x] `&key=` redacted at the boundary, everywhere.
- [x] The five slice-1 guards from DESIGN §4: `overlapping_vintage`,
      `moe_not_significant`, `geography_unsupported`, `ambiguous_place`,
      `universe_mismatch`. **None of them blocks** — warn and ship the answer.
- [x] `scripts/run_demo.py --repeat 3` → writes `answered_rate` and
      `p95_latency_seconds` into `evidence/latest.json`, plus a breakdown:
      `t_llm`, `t_census_api`, `t_ours`. **Gate on the total only** — the split
      is diagnosis, the same way `@5` diagnoses `@1`. Without it, a slowdown in
      our code is indistinguishable from a slow model day.
- [x] Same run records `prompt_hash` and `index_hash`. Without them a prompt
      change and an index change look identical in the evidence, and
      `answered_rate` is the noisier of the two numbers. Every score in the
      record should be attributable to a specific prompt and a specific index.

**Done when:** you `curl` it, paste a working Census URL into a browser, and get
the data back. `make demo` clears both floors.

**Not in this slice:** conversation memory, auth, database, frontend, charts,
PDF, clarification, series and cross-geography comparison (slice 3 — keep `url`
singular for now, but do not hard-code a shape that fights `urls[]`).
Within-level wildcards (`all counties in Oregon`) **are** in this slice: q02 is
a core question.

---

## Slice 2 — Chat UI, one pane

- [x] React + TypeScript, minimal.
- [x] TS client generated from the OpenAPI schema; CI fails if the committed
      copy is stale.
- [x] Chat: question in, answer + URL out. The URL is visible and copyable.
- [x] **FastAPI serves the Vite build output** as static files. One container,
      one domain, no CORS (DESIGN §5). The build output path is a deployment
      detail, not a local convenience — set it now, not at slice 8.

**Done when:** you type in a browser and get an answer with a usable URL.

**Not in this slice:** the canvas, charts, series and comparisons, memory, auth.

> **STATUS 2026-09-14.** Slice 2 closed. answered_rate 0.778; p95 24.546s (ceiling 20s, recorded). Evidence: `evidence/slice-2/`. Epic: https://johnhillescobar.atlassian.net/browse/CC-5.

---

## Slice 3 — Series and comparisons

*"…since 2017"* and *"…compared to…"* are **standard** questions for this
audience, not advanced ones. Both are one mechanism — fan `fetch_data` over a
list, then guard the comparison — so they are one slice. **Every failure mode
here is silent:** a wrong series or a wrong cross-geography comparison looks
exactly like a right one.

Backend only. It lands before the canvas so the chart pane is built once,
against the final shape.

### Years

- [ ] `fetch_data` accepts `years: list[int]` and fans out concurrently, bounded.
      **A parameter, not a fifth tool.** The Census API takes one vintage per
      request; N years is N calls, and sequential calls blow the p95 budget.
- [ ] `build_url` returns one URL per year. Contract `url` → `urls[]` — breaking,
      so regenerate the TS client in the same commit. That is slice 2 earning its
      keep.
- [ ] Vintage policy, stated in every series response: ACS1 where the geography
      qualifies, otherwise **non-overlapping** ACS5 end years. Never consecutive
      ACS5 — 2017 means 2013–2017 and 2018 means 2014–2018, four of five sample
      years shared.
- [ ] **Say what is not available, and why.** ACS1 is published only for places
      of 65,000+, and the standard 2020 release was never issued. A missing year
      is a sentence in the answer and a gap in the data — never interpolated,
      never bridged, never silently dropped. A silently short series is the same
      failure as a wrong one.
- [ ] Per-year variable existence check against that vintage's `variables.json`.
      A variable absent or redefined mid-range is a warning, not a silent join.
- [ ] Year-over-year significance: `MOE_diff = sqrt(m₁² + m₂²)`. Differences that
      do not clear it are reported as **not distinguishable**, not as change.
- [ ] Tract and block-group series crossing 2020 carry a boundary-change warning:
      the geometry was redrawn, so the polygons differ.
- [ ] Plan strip carries vintage and year list. Overriding to a consecutive ACS5
      series is **allowed** — some users have a reason and know the caveat. The
      warning stays attached.

### Geographies

- [ ] `resolve_geography` returns a **list of specs** — level, codes, and the
      legal `for`/`in` form for that dataset and vintage. Legality comes from
      the indexed `geography.json`, never from the model.
- [ ] `fetch_data` takes the list and fans out. A wildcard
      (`for=tract:*&in=state:26 county:163`) stays **one** call — within-level
      comparison is not N calls.
- [ ] **ZCTAs.** Not ZIP codes: ZIPs are USPS delivery routes, ZCTAs are
      block-built approximations. Roughly a tenth of ZIPs have no ZCTA. They
      nest in nothing. **No ACS1**, so no annual ZCTA series exists. 2020
      definitions differ from 2010.
- [ ] **Aggregation.** Estimates sum; MOEs do not. `MOE_total = sqrt(Σ MOEᵢ²)`,
      and the approximation degrades past a handful of areas — warn when it
      does. **Medians cannot be aggregated at all**; decline the computation and
      say why rather than producing a plausible wrong number.
- [ ] Non-nesting containment — *"the part of ZIP 80202 inside Denver"* — is not
      computable from published ACS. It needs block-level areal allocation. Say
      so; do not approximate.
- [ ] Place-vs-parent comparisons (Denver against Colorado) share samples, so
      the independent difference-of-MOE formula overstates variance. Note it.
- [ ] Trap questions `t09`–`t18`, and long-tail `q23`–`q24` for the comparisons
      that must **succeed** — a guard-only eval measures refusals, not capability.

**Done when:** *"number of cell phones in Denver since 2017"* returns the
universe correction (households with a smartphone — the Census counts no
devices), a defensible series, every URL, and a plain statement of which years
are unavailable and why. The overlapping-ACS5 override returns the data with the
warning intact. And *"median gross rent in Austin vs the Texas average"* returns
both levels with a significance test on the difference.

**Not in this slice:** charts, memory, PDF, auth. No new tool, no new route, no
graph node.

---

## Slice 4 — Canvas

Decide the canvas model first (DESIGN §9): card stack or living workspace.

- [ ] Second pane: data table with GEOID, estimate, and MOE columns.
- [ ] `ChartSpec` from the agent (type, x, y, series, title); frontend renders.
      **The LLM never emits chart code or SVG.**
- [ ] Editable plan strip — `ACS5 2019–2023 · B01003 · county · Texas [edit]` —
      with re-run on override.
- [ ] Alternatives panel: related tables and why they differ.
- [ ] CSV export.

**Done when:** you ask a question, get a wrong-ish table, fix it in one click,
and download the CSV.

**Not in this slice:** memory, auth, PDF.

---

## Spike — does LangGraph earn its place?

**Half a day, timeboxed. A throwaway branch and a written decision — not merged
code.** Run it before slice 5 starts, because the answer changes what slice 5
builds and it is the wrong thing to be deciding halfway through.

The question: does LangGraph's Postgres checkpointer justify two dependencies,
against ~30 lines that append messages to a table keyed by `thread_id` and load
them on the next turn?

Evaluate on:

- [ ] Lines of code each way, and the delta to `direct_dependencies`.
- [ ] What LangGraph gives *beyond* persistence — interrupts, time-travel,
      streaming state. Does anything in slices 5–8 need them? If nothing does,
      the checkpointer is the only thing being bought.
- [ ] How well the checkpointer sits under a **hand-rolled loop** rather than a
      graph. This is the crux: it was designed for `StateGraph`, and if using it
      means reintroducing a graph to hold the loop, the cost is much larger than
      two dependencies.
- [ ] Cost of switching later, in each direction.

**Done when:** a dated decision with its reason is in DESIGN §9, the branch is
deleted, and `budgets.toml` is untouched.

**Do not** let this become slice 5. If the spike overruns the timebox, that is
itself the answer: pick the 30 lines and move on.

---

## Slice 5 — Conversation persistence

Storage only. A conversation survives a restart; it does not yet understand
"what about Texas?".

- [ ] Postgres. **Never SQLite.**
- [ ] `thread_id` per conversation, **owned by a `user_id`** — take it from day
      one even though there is only one user until slice 8, where it arrives as
      a JWT claim. Retrofitting ownership onto existing rows is the expensive
      version of this.
- [ ] Message arrays as JSONB. Postgres gives the document flexibility without
      giving up transactions for the report job's state machine.
- [ ] `POST /conversations`, `POST /conversations/{id}/messages`,
      `GET /conversations/{id}`. That last one is not optional: without it a
      page refresh loses the canvas.
- [ ] Implement whichever way the spike decided.

**Done when:** you hold a conversation, restart the server, reload the page, and
the canvas is still there.

**Not in this slice:** reference resolution, auth, PDF.

---

## Slice 6 — Follow-ups and reference resolution

The conversational half, on top of storage that already works. Split from slice
5 because these fail differently: persistence either survives a restart or does
not, while reference resolution is a nondeterministic quality problem measured
across repeats.

- [ ] Resolve *"what about Texas?"*, *"add median income"*, *"go back to the
      second one"* against prior turns.
- [ ] Multi-turn cases in the golden set, scored across `--repeat`.
- [ ] A reference the agent cannot resolve becomes a **warning with the
      candidates shown**, never a blocking question.

**Done when:** a three-turn refinement conversation produces the right final
dataset, at a pass rate you measured rather than saw once.

**Not in this slice:** auth, PDF.

---

## Slice 7 — PDF export

- [ ] `POST /reports` → job id. Background worker. **Never a request handler.**
- [ ] **The container filesystem is ephemeral.** The worker writes the PDF to
      object storage and `GET /reports/{id}` returns a signed URL. Writing to
      local disk and serving it later works on your laptop and fails in
      production — this is the constraint that quietly breaks a naive
      implementation.
- [ ] Poll or SSE for status; download when ready.
- [ ] Contents: table of contents, summary section, every question, every
      answer, summary tables where applicable, visualizations where applicable,
      and **the API URL for every call made.**

**Done when:** you run a real session and download a document you would attach
to a grant report.

---

## Slice 8 — Auth and hosting

The shape was settled in DESIGN §5 so that slices 0–6 do not build against
assumptions this slice has to undo. Do not build any of it before here.

- [ ] **Clerk.** Email allowlist is fine at 10 users. Chosen over an edge
      allowlist because it survives the move to public signup.
- [ ] The JWT's user id keys thread ownership and the spend cap — both already
      wired since slice 5.
- [ ] **One container on Render** (Fly.io equal substitute): FastAPI serving the
      API and the static frontend, plus that provider's managed Postgres. No
      k8s, no queues, no second host.
- [ ] Dockerfile downloads the **pinned index release asset**. Never builds the
      index — that would need an API key at build time.
- [ ] `build-index` GitHub Actions workflow: manual trigger, publishes a
      versioned Release asset. Runs about once a year, on the ACS release.
- [ ] Stateless workers; no module-level mutable state. The read-only index is
      the sanctioned exception.
- [ ] Per-user spend cap enforced in `call_model()`, plus a cost dashboard.
- [ ] Langfuse tracing live in production.

**Done when:** someone who is not you logs in and answers a real question.

---

## After slice 8

Do not plan this yet. Revisit with real usage data. Candidates in rough order:
clarification *only where the demo suite proves it is needed*, saved sessions,
more datasets (decennial, PUMS, CBP), shapefile/GeoJSON export, scheduled
refreshes.

## Standing checklist for every PR

- One sentence on what a user can now do that they could not before.
- `make check` green, **no budget raised**.
- Long-tail retrieval and answered rate did not regress.
- p95 latency did not regress.
- URL, MOE, GEOID and universe still present in every response path.
- No new blocking clarification prompt.
- `docs/ARCHITECTURE.md` updated if the shape changed.
- Under ~15 files touched, or an explanation why not.
