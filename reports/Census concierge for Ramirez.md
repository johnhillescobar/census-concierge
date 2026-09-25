# Census Concierge — experimentation and implementation

Briefing for a presentation to Victor Ramirez (ramirezailabs.com). Director, Developer and Platform Experience at Moody's Analytics. He teaches RAG, agents, and evaluation, and he has published the position that a negative eval result is a result: he trained a 7B LoRA for his portfolio assistant, A/B tested it against his own judge, and shipped the base model.

This note is what the repo actually did, mapped onto the questions that record implies. Numbers below are from the repo, dated where the file dates them. His positions are from his site and CV, fetched 2026-09-24. Inference is labeled as such.

Last measured run in `evidence/latest.json` (2026-09-24): long-tail retriever @10 **0.90**, selector @1 **0.875**, synthetic alignment **0.544**, demo answered rate **0.842** on the long tail (repeat 3, n=120), overall answered rate **0.892**, p95 **17.171s**. The README scoreboard is copied by hand and can lag that file.

---

## Who this is for, and why the framing matters

Victor's public work is evaluation-first production AI, not model novelty.

From [ramirezailabs.com](https://ramirezailabs.com/) and [his CV](https://ramirezailabs.com/cv):

- At Moody's he designed the LLM evaluation framework on Databricks, Spark, and MLflow. The metrics he standardized are Recall@k, Precision@k, MRR, and groundedness.
- His RAG Evaluation Lab is an offline lab: keyword and TF-IDF versus embeddings, scored with those retrieval metrics. On his site, Part 2 of that series reports TF-IDF at Recall@3 of 0.833 in under 5 ms, and embeddings at 1.0 at about 50× the latency. Part 3 is a retriever decision framework driven by timeline, budget, and compliance, not a leaderboard.
- His homepage states he has shipped **zero** fine-tunes. He trained a 7B LoRA on AI-Vic's eval data, the adapted model regressed against the un-adapted base under the same judge, and he shipped the base. He also describes a vacuous 5/5 judge bug fixed with hard-case rubrics. The negative result is the point of the write-up.
- Featured agent work ("AI Operating System") is four-domain LangGraph orchestration, a tool-loop safety circuit breaker, a CI-gated eval harness, and deterministic fallbacks.
- Talks in 2025–2026: Building AI Agents for Real-World Workflows (Techqueria, Oct 2025), AI Agents from Scratch (Oakland Tech Week, Nov 2025), RAG Chat + AI Agents (Latino AI Summit, Jan 2026).

A LinkedIn post of his (cited in the research pass, not re-fetched in full) asks, before adding a layer: what failure are we actually trying to fix?

That last sentence is the overlap. This repo's budgets exist because a predecessor reached 38,184 lines across 116 files, a 14-node LangGraph, and 43 files of clarification, and still could not answer "population of New York City" correctly in under 75 seconds. Retrieval in that system was a stub that returned `B01003` for any input. The URL was never shown. The only signal was "tests pass."

Present the negative experiments first. He has already decided that a metric regression is a ship blocker.

---

## Topic 1 — Experimentation

### What the product is being measured against

`evals/golden_questions.toml` was written before the agent existed. It is the specification.

| tier | n | what it proves |
|---|---|---|
| core | 4 | Common tables ("population of Harris County" → B01003). Cheap to pass. The predecessor passed these while retrieval was a stub. |
| long_tail | 40 | The metric. Questions with almost no lexical overlap with the Census title. "How many people bike to work in Portland?" → B08301, *Means of transportation to work*. |
| trap | 18 in the file header; 14 scored in the latest retrieval block | The answer is "no" or "not like that": overlapping ACS vintages, medians that cannot be aggregated, ZIP vs ZCTA, households vs families. |
| holdout | 8 | Run at slice boundaries only, so the tuning set cannot be the only evidence. |

Fixtures were checked with `scripts/verify_golden.py` against cached ACS metadata (ACS5 and ACS1, 2016–2024). That check proves a table ID exists. It does not prove the table is the right answer to the question. A wrong fixture is worse than no fixture.

At n=40, @1 has a standard error of about 7 points. A move from 0.70 to 0.76 is noise. The harness says to chase step-changes and to compare runs at the same `--repeat`, because the pipeline is nondeterministic. Every run records `prompt_hash` and `index_hash` next to the scores.

Gated floors in `budgets.toml` (floors may only be raised, by evidence):

| metric | floor | latest |
|---|---|---|
| long-tail retriever @10 | 0.90 | 0.90 |
| selector @1 | 0.70 | 0.875 |
| synthetic alignment | 0.50 | 0.544 |
| answered rate | 0.70 | 0.842 long-tail / 0.892 overall |
| p95 latency | 20s ceiling | 17.171s |

Raw cosine @1 (0.475 on the long tail) is recorded and not gated. @10 high with selector @1 low would mean the pool is fine and the picker is wrong, which is cheaper to fix than a new encoder. The reverse would mean the index is broken.

`http_ok` and "the question was answered" are separate fields. On the latest demo, long-tail `http_ok_rate` is 1.0 and `answered_rate` is 0.842. A successful Census call that returned the wrong table is a miss.

### Slice 0 ladder — ranking changes that lost

Recorded in `evidence/retrieval_steps.md` on the 40-question long-tail set, before the later encoder sweep. Every step was measured; several prescribed steps were rejected.

| step | @1 | @5 | MRR |
|---|---|---|---|
| BM25 only, raw | 12% | 35% | 0.20 |
| BM25 + corpus stopwords | 18% | 45% | 0.30 |
| embeddings, `text-embedding-3-small` | 20% | 60% | 0.35 |
| embeddings, `text-embedding-3-large` | 28% | 68% | 0.43 |
| synthetic questions in the vector | 32% then a drop to 25% on a later cut | — | 0.43 then 0.47 |
| families + subject-only, semantic | **45%** | **80%** | **0.56** |
| + LLM rerank of top 10 | **70%** | 82% | 0.73 |

Holdout (n=8, once): @1 62%, @5 100%. Small, and the interval is wide. It did not look like the set had been tuned to.

What the plan expected and the data denied:

- **Equal-weight RRF of BM25 and embeddings scored below embeddings alone** (@1 40% → 28%, @5 80% → 68%). BM25 at 18% @1 is not strong enough for an equal vote. Any weight would be fitted to 40 questions, which the protocol forbids. BM25 is still built. `search()` does not consult it while `semantic.npz` exists. The hypothesis that BM25 would win on a verbatim table ID is untested: the golden set never types an ID.
- **Synthetic questions were supposed to be the largest jump. They were the largest drop** (@1 40% → 25%, MRR 0.55 → 0.47). Six generic paraphrases of a table describe the topic and blur the neighbour. Neighbours are the whole problem. Generation is committed in `data/synthetic_questions.json`. The embedding does not read it. The gate became `synthetic_alignment` (mean cosine of each question to its own title/universe/concept document): 0.544 against a floor of 0.50. Rank-1 self-retrieval (~45%) is diagnostic only.

What moved the number was corpus structure, not a ranker. 1,458 table documents became **636 family documents**:

- Race iterations and Puerto Rico variants folded into the parent. `B19013A` is `B19013` for Black householders and carries a near-identical title, so it crowded out the parent. "Crowded housing" was ranking a race iteration first.
- Survey-quality `B00` / `B98` / `B99` tables dropped. Left in, "how long have naturalized citizens held citizenship" answered with an *allocation* table.
- Iteration-only families dropped. `B28009` exists only as `B28009A`–`I`. Representing the family by its first member put "White alone" at rank 1 for a broadband question.
- 120 collapsed `C` tables folded into the identical `B`. A `C` table publishes the same title, universe, and concept as its `B`, with fewer categories. Of 600 generated questions, the 97 that asked for such a `C` scored **0%** at rank 1. They were unanswerable, not hard. `text-embedding-3-large` is not bit-deterministic across batch positions (max component difference 1.3e-3), so which twin won could flip on rebuild. The shipped index had `C15003` above `B15003` for educational attainment in Cook County. Folding them is a benchmark correction as much as a retrieval gain: on the questions that were always answerable, @1 moved by about +0.002.

### The pre-registered model sweep

`experiments/` is quarantined. It does not import into the shipped path, does not touch `budgets.toml` or `evidence/latest.json`, and its dependencies (`torch` and the rest, about 2 GB) live in their own group. `experiments/PROTOCOL.md` was written **2026-08-15, before any arm ran**.

Why the protocol exists: at @1 near 0.5, n=40 has a standard error of about 8 points. Ten arms of equal skill will produce a "winner" about 1.5 SE above the mean by construction. So:

1. The primary set is 600 generated questions (SE about 2 points), not the golden 40. Both are reported. Disagreement is a finding. Bias: the questions were generated by `gpt-4o-mini`, so they may favour models aligned to that phrasing.
2. Comparisons are paired per question, with a 10,000-resample bootstrap on the difference.
3. A difference counts only if the 95% CI excludes zero on the 600-set (encoders) or the arm beats baseline by at least 5 of 40 questions (rerankers). Smaller gaps: "not distinguishable," and the cheaper arm wins.
4. Ties break toward deployment weight: no new dependency, then smaller index, then latency, then cost.
5. Document text was held fixed so the encoder comparison would not be confounded. Instruction prefixes were set per model (E5, BGE, and others fail silently if the prefix is wrong).

Axes A–C were scored on the **pre-fold 756-document** corpus. Re-running encoders today rebuilds the post-fold 636-document corpus and will not reproduce those ranks. The published table was left as the record.

**Axis A — bi-encoders, ranked by recall@10 on the 600-set.**

| arm | @10 | gold @1 | index |
|---|---|---|---|
| gemini-embedding-001 | 92.3% | 57.5% | 9.3 MB |
| voyage-4-large | 92.0% | 40.0% | 3.1 MB |
| openai-3-large (incumbent) | 88.3% | 42.5% | 9.3 MB |
| openai-3-small | 79.8% | 30.0% | 4.6 MB |
| bge-m3 | 66.8% | 17.5% | 3.1 MB |

The two leaders differ by 0.3 points, CI [−1.8, +2.7]. Both beat the incumbent on the 600-set with a CI that excludes zero. The golden-set gap that would pick Gemini over Voyage is the comparison the limits section flags as the most likely false positive: no multiple-comparison correction, and n=40 cannot establish that Gemini beats the incumbent. BGE-M3, a common production default, finished last of eleven. `gemini-embedding-001` beat its successor on every metric. An 8B local encoder was not scored: 18.7 seconds per text on CPU, which already blows the 20-second p95 for a whole answer.

**The live index is still `text-embedding-3-large`.** The sweep did not promote Gemini or Voyage. That is a real open point, not a silent win for the incumbent. State it that way. Corpus structure moved @5 from 68% to 80%, larger than the encoder gaps, and the protocol's own limits section says the golden set cannot crown Gemini. The pre-registered rule would still have treated the @10 gains over OpenAI as real on the 600-set. He will ask why that did not ship. The honest answer is: it has not been promoted; the product decision was "the model is not the bottleneck," and the deployment-weight tie between the two leaders was never closed with a written switch.

**Axis B — rerankers over a frozen top-10 from the incumbent.** Ceiling 90%. No reranking: 42.5% @1.

| arm | @1 | vs no rerank |
|---|---|---|
| gemini generative | **77.5%** | +35 |
| gpt-4o-mini generative | 67.5% | +25 |
| Cohere rerank 3.5 | 40.0% | −2.5 |
| BGE reranker | 35.0% | −7.5 |
| MXBAI rerank | 20.0% | −22.5 |

Every purpose-built cross-encoder was worse than not reranking. They expect a natural-language passage. These documents are short structured records, and the fact that separates siblings is semantic: households are not families. The live selector is generative rerank inside `search_tables` (Gemini), not a fifth tool and not a cross-encoder. Latest selector @1 on the long tail is 0.875.

**Axis C — richer documents.** Four enrichments (everything derived, only discriminating fields, synthetic questions, a targeted cell-count tie-break on twins). All neutral or harmful. Adding cell count only on colliding twins made gemini-embedding-001's @10 worse by 3.5 points, CI excluding zero. The rule that survived: a field earns its place only if it discriminates between siblings, and even then it stays out of the embedded text. Topic words make neighbours more similar.

**Axis D — confidence from the score margin.** Top-1 minus top-2 predicts whether the top hit is right at AUC about 0.73–0.77. A cut at the 70th percentile covers 30% of golden questions where the top hit is right 92% of the time; below the median it is right about 46% of the time. Absolute margins are tiny (50th percentile around 0.0057 cosine), so a threshold is per encoder. This is why the product shows neighbours instead of asking a blocking question. Subject-code agreement in the top 5 was tested as an alternative signal and scored at or below chance.

**Axis E — the ID, not the vector.** Dropping the 120 `C` twins moved @1 from 43.0% to 50.8% on the 600-set, CI excluding zero. Split: the 97 twin-answer questions went from 0% to 47.4%; the 503 untouched questions went from 51.3% to 51.5%. Reordering `B` ahead of `C` changed zero questions. The document had to disappear.

### How an experiment becomes a ship decision

The slice pipeline (`docs/playbooks/run-slice.md`) is the other half of the harness:

1. Pre-flight: every technical claim is run (grep, a library call, metadata) before code depends on it.
2. Gate 1: tests for a short adversarial matrix. Every new test is mutation-checked: revert the behaviour, confirm the test fails, restore. A test that passes against the broken implementation is deleted.
3. Gate 2: a cold read of the diff with no intent, then the project invariants.
4. E2E before the PR and again after merge to `main`. `make demo` is the definition of done. A green pytest run is not.

The adversarial matrix in `docs/process-evidence.md` only contains probes that already caught a real defect (float-noise twins, a race iteration returned as the general table, RRF measured worse, synthetics measured worse). A row that cannot name the defect it would have caught does not belong.

Things deliberately not built, each with an until-clause:

- No clarification subsystem until the demo suite names the questions that need one.
- No gazetteer until NAME ranking and the plan strip still fail a named golden question.
- No fifth tool until a golden question fails because no existing tool can do the thing. Years are a parameter on `fetch_data`, not a tool.
- No graph node for branching. Nodes, if they ever exist, are durable checkpoints.
- No fine-tune. The sweep's "not tested" list includes fine-tuning on purpose, so it would not confound the model comparison.

---

## Topic 2 — Implementation

### Shape

One tool-calling loop. Not a graph, not `create_agent`. `run_ask` calls `_openai_complete`, then `dispatch`, until the model emits text. There is no `finish` tool.

Four tools:

| tool | job |
|---|---|
| `search_tables` | embedding search, top 10, then generative `rerank.choose` |
| `resolve_geography` | ordered `GeoSpec` list from that vintage's geography metadata. Names are not invented. |
| `build_url` | availability matrix; an empty variable list becomes estimate `001E` paired with margin `001M` |
| `fetch_data` | live Census. Fans out years and comparison geographies. Cap 5 in flight, 12 years. |

`assemble()` builds the response from the execution record, not from the model's prose. If the model stops early — no URL, wrong listing level, incomplete comparison, ACS1 request that never built an ACS1 URL — `finish.py` retries those tools. It does not invent a nested `for`/`in` the Census API cannot express.

LangGraph is an open spike (CC-9), not the runtime. The question on the spike is narrow: can the Postgres checkpointer sit under this loop without reintroducing a `StateGraph`? If using it means a graph to hold the loop, the cost is larger than two dependencies, and the fallback is about 30 lines. The predecessor's 14-node graph is the reason routing is not a graph.

No vector database. 636 × 3072 floats in a numpy `.npz`, plus a per-vintage availability matrix. The index is built offline (`scripts/build_index.py`) and loaded read-only. Nothing embeds at request time. The read-only index is the only sanctioned module-level cache. No SQLite, no `contextvars`. A second worker must see the same state.

### What every answer contains

From `docs/requirements.md`. None of these block. A warning still ships the URL.

- Full Census API URL per attempted request: variables, geography, vintage, including when the fetch fails. `&key=` is redacted at the boundary.
- Margin of error beside every estimate. Census sentinels are null, never zero.
- GEOID (AFFGEOID), because names do not join to TIGER shapefiles.
- Published universe. Households, families, population, and housing units are different denominators.
- Related tables, with title, universe, and why they differ.
- A `ResultPlan` assembled from what actually executed (table, estimate IDs, years, geographies). Optional `AskRequest.plan` pins those fields on the next call. Invalid overrides are HTTP 422 before the loop runs. The model cannot undo a pin.
- Optional `ChartSpec` (line or bar roles over the rows). Invalid chart output is discarded. The model does not emit SVG or chart code.

Warning codes a researcher would recognize: overlapping ACS 5-year vintages are not comparable; a difference inside the 90% MOE is not a ranking; ACS1 is only for places of 65,000 or more; there is no standard 2020 ACS1; tract geometry changed in 2020; ZIPs are not ZCTAs; medians cannot be summed across areas; a place and its parent share sample.

### What has shipped

| slice | date | what a user can do | demo at close |
|---|---|---|---|
| 0 index + eval | 2026-09-12 | Nothing conversational. The index and the floors exist. | eval floors |
| 1 `POST /ask` | 2026-09-13 | Curl a question, get a URL, rows, MOE, GEOID. | answered 0.803, p95 14.164s |
| 2 chat UI | 2026-09-14 | Type in a browser. FastAPI serves the built frontend. Generated TypeScript client; CI fails if it drifts. | answered 0.778, p95 24.546s (over the 20s ceiling, recorded, not used to raise the ceiling) |
| 3 series and comparisons | 2026-09-19 | A year series and a cross-geography compare, with vintage policy. | answered 0.825, p95 17.116s |
| post-slice-3 reliability | closed | Ambiguous places, ACS1-ineligible geography, classification, alias places, finish-path pins. | latest demo above |
| 4 canvas | in progress | Two panes. One active dataset. GEOID/MOE table, `ChartSpec`, `ResultPlan`, typed plan overrides. Epic still open. | per-ticket E2E; several p95s over ceiling were recorded and not promoted |

Latency on the latest demo, same run: LLM 4.6s, Census API 2.8s, our code 2.6s, p95 17.2s. The ceiling is 20s. Slice 2's 24.5s was recorded against the ceiling and did not raise it.

Still ahead, and not started as product: conversation persistence (Postgres, slice 5, after the checkpointer spike), follow-ups such as "what about Texas?" (slice 6), PDF as a background job (slice 7), auth and hosting (slice 8). Tracing is planned as Langfuse at the complete/dispatch choke points, not LangSmith.

### Complexity is enforced, not advised

`budgets.toml` is checked in CI. An agent is not allowed to raise a number. A raise is a human commit with a one-line reason. Current caps include 4,000 lines under `api/src`, 40 files, 400 lines in any one file, 6 tools, 8 graph nodes, 10 HTTP routes, 15 domain models, 25 direct dependencies, 1,200 tokens of system prompt. The prompt cap exists because the predecessor spent about 4,000 tokens across seven prompts. One loop has one prompt.

The tool cap is a scope alarm about overlap, not a claim that models can only handle six tools. Two tools that could answer the same question are one tool with a parameter.

### Where this will not match his stack, on purpose

| his production pattern | this repo |
|---|---|
| LangGraph as the agent runtime, checkpointer from early on | Hand-rolled loop. Checkpointer is an unrun spike. Graph for routing is refused. |
| Recall@k, Precision@k, MRR, LLM-as-judge groundedness | @k and MRR on a frozen golden set. Groundedness is structural: the URL, the universe, the MOE. No judge scores the prose. Prompt-wording tests are forbidden because they survive regressions. |
| Databricks / Spark / MLflow | Local JSON scoreboard, hashes, and transcripts under `evidence/`. |
| Vector search as infrastructure | Numpy file. 636 documents. A vector database is not justified at this size. |
| BM25 + vector fusion as a default hybrid | Fusion measured worse. BM25 is built and unused on the live path. |
| Fine-tune when the eval set is large enough | Not tested, and his own LoRA result is the argument for leaving it untested until a metric demands it. |

---

## How to present it

Open with the predecessor: 38k lines, a graph, a fake retriever, no URL, 75 seconds, wrong one run in three. Then the rule that replaced "tests pass": a budget you cannot raise, a golden set written first, and a negative result that stays in the repo.

Spend the experiment half on three negatives he will recognize:

1. Hybrid retrieval lost. Equal-weight fusion was worse than embeddings alone, so it was not shipped.
2. More text in the document lost. Synthetics, rich metadata, and a clever tie-break all made siblings harder to separate.
3. The specialist rerankers lost to no reranker. A generative pass over a frozen top 10 is what moved @1, because the residual error is a universe distinction, not a passage-relevance distinction.

Then the implementation half is short. Four tools. The URL is the product. The plan strip is how a wrong table gets fixed without a clarification dialog. The graph is a spike with a written kill criterion, not an architecture diagram.

Do not claim the encoder sweep picked `text-embedding-3-large`. It did not. Say the live index is still that model, the two leaders were not separable from each other, and promoting one is an open decision with a deployment-weight tie-break already written down.

Close on the scoreboard from `evidence/latest.json`, including the misses. Long-tail answered rate 0.842 at repeat 3 is the number. Core at 1.0 is not.

---

## Questions he is likely to ask

Answer from the repo. Do not invent a subsystem in the room.

**Evaluation design**

1. Why is Recall@10 the retriever gate and @1 the selector gate, instead of one Precision@k?
   The architecture is retrieve-then-select. Gating bi-encoder @1 blocked slice 0 while the pool was already good. If @10 falls, the index is wrong. If @10 holds and selector @1 falls, the picker is wrong.

2. Where is groundedness? You are not running a judge.
   The check is whether the returned table ID matches the fixture and whether the URL, MOE, GEOID, and universe are present. Prose is not scored. A judge that gives 5/5 to vacuous answers is the failure mode his own write-up describes; this harness refuses prompt-wording asserts for the same reason.

3. n=40 is small. How do you know you are not fitting it?
   Standard error is stated as about 7 points at @1. The 600-question set is the discriminator for encoder comparisons. Holdout runs only at slice boundaries. A paired bootstrap CI has to exclude zero before a difference counts. The limits section admits there was no multiple-comparison correction, and names the Gemini-versus-Voyage golden gap as the result most likely to be a false positive.

4. Your synthetic questions are model-generated. Doesn't that favour some encoders?
   Yes. The protocol says so, and requires both sets to be reported. Spearman correlation between the two rankings dropped when Voyage was added. That disagreement is why Voyage was not crowned on the 600-set alone.

5. Why is core not on the scoreboard you lead with?
   Core questions lexical-match titles a specialist already knows. The predecessor passed them with a retriever that returned one table for every query. Long tail is the product.

**Retrieval decisions**

6. Why didn't you ship Gemini or Voyage when their @10 CIs beat OpenAI?
   We have not. The live path is `text-embedding-3-large`. The two leaders are not separable from each other. Corpus folding moved @5 more than any encoder gap. The written tie-break is deployment weight, and that decision was not closed in a dated note. If he pushes, agree it is unfinished, and do not retrofit a reason.

7. Why is BM25 built if fusion lost?
   So a later query class that types a table ID can be measured without rebuilding the lexical index. It is not a live branch. Wiring it needs golden questions that actually contain IDs. Those do not exist yet.

8. TF-IDF was free and close to embeddings in your lab. Did you try it?
   BM25, not TF-IDF. Raw BM25 was 12% @1 and 35% @5 on these questions, because "bike to work" does not share tokens with "means of transportation to work." That is a different corpus from a document collection where the words in the question appear in the passage. His Part 2 tradeoff (embeddings at 50× the latency for a Recall@3 gain) does not transfer here: the lexical baseline is too weak to be the default, and fusion made the semantic ranker worse.

9. Why not a vector database?
   636 documents, 9 MB. Numpy is the index. A database would be a dependency and an operations surface with nothing to operate.

10. Cross-encoders failed. Is that a Census-specific result or a claim about rerankers?
    Specific. The documents are about twelve words of title, universe, and concept. Cross-encoders are trained on query-passage pairs. The error that remains after retrieval is "households versus families," which those models ranked worse than leaving the bi-encoder order alone.

**Agents and complexity**

11. Why a while-loop instead of LangGraph? You know I ship LangGraph.
    The predecessor was a 14-node graph and still failed the easy question. Routing does not need a graph. Persistence might. CC-9 is a half-day spike: if the checkpointer requires a `StateGraph` to hold this loop, we keep about 30 lines and Postgres in slice 5. Interrupts, time-travel, and streaming state are the features to justify, and slices 5–8 do not require them yet. Slices 6's follow-ups are reference resolution, not a new graph.

12. What is your circuit breaker?
    Budgets fail CI. Floors fail CI. A p95 over 20s is recorded and does not raise the ceiling. There is no runtime token breaker in the loop today. Langfuse is slice 8, at the two choke points, not a tracing product wrapped around every call.

13. Four tools seems low. What happens when the question needs something else?
    A fifth tool is earned by a named golden miss, not by a design review. Years, comparison geographies, and the overlapping-vintage override are parameters. The failure mode we are guarding is two tools that both look like they can answer the question.

14. You refuse blocking clarification. What does the user see when the place is ambiguous?
    Ranked `GeoSpec` candidates and a warning. The plan strip is typed fields on the next `POST /ask` (table, variables, years, geographies). It is not a follow-up sentence. Follow-up language is slice 6 and is not built.

15. How do you stop the model from emitting a confident wrong table?
    The URL is built from tool results, not parsed out of the answer. Alternatives ship with the pick. Universe mismatches warn. The margin signal says when the top two are close, show both. We do not hide a low-confidence pick behind prose.

**Process**

16. Mutation testing — what do you actually revert?
    The behaviour the new test claims to cover. One behaviour at a time. If the test still passes, it is not a check. This is not a coverage-guided mutation tool. It is a manual falsification step with a transcript.

17. What would make you raise a budget?
    A human, with a written reason, in a commit that only does that. An agent that cannot fit a change stops and names the limit. The API line cap is 4,000 and the README shows it at the cap, so the next feature that needs lines is a conversation, not a silent overrun.

18. What is still unmeasured that you would want his help designing?
    Promoting an encoder under the existing tie-break. A lexical slice of the golden set so BM25's "verbatim ID" hypothesis can fail in public. Whether an LLM-as-judge for groundedness would catch anything the URL check does not, given his vacuous-5/5 experience. The checkpointer spike, against his "checkpointer from day one" practice, with the kill criterion already written: if it forces a graph, it loses.

---

## Source notes

Repo, primary:

- `.claude/DESIGN.md` — product, the predecessor failure, architecture intent, retrieval decisions, what is not being built.
- `experiments/PROTOCOL.md`, `experiments/FINDINGS.md`, `experiments/README.md` — pre-registered sweep.
- `evidence/retrieval_steps.md`, `docs/retrieval.md`, `docs/process-evidence.md` — ladder and the defects it caught.
- `evidence/latest.json` (generated 2026-09-24) — current scoreboard. README table is a hand copy.
- `docs/ARCHITECTURE.md`, `docs/ask-path.md`, `docs/requirements.md`, `docs/slices.md`, `budgets.toml`, `docs/playbooks/run-slice.md`.

Victor Ramirez, primary pages fetched 2026-09-24:

- https://ramirezailabs.com/ — zero fine-tunes shipped, LoRA lost to the base model, RAG lab metrics, LangGraph operating-system description, talk list.
- https://ramirezailabs.com/cv — Moody's evaluation framework (Databricks, Spark, MLflow; Recall@k, Precision@k, MRR, groundedness), role history, teaching.

The research pass also returned LinkedIn and Medium URLs. Medium returned 403 on direct fetch, so those posts are not quoted beyond what his homepage already states. One research hit attributed LangGraph checkpointer advice to a different person (Eric Ramirez). That is not used here.
