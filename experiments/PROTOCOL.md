# Retrieval model sweep — pre-registered protocol

**Written 2026-08-15, before any arm was run.** The point of writing it first is
that "which model won" cannot then be decided by looking at the table.

Nothing here is a product decision. `experiments/` is throwaway: it does not
import from a shipped path, it writes only to `experiments/results/`, and it
never touches `budgets.toml`, `evidence/latest.json`, or `api/src/`. The budget
is **recorded per arm as a benchmark**, not enforced.

## The problem this design exists to solve

The golden tuning set is 40 questions. At `@1` near 0.5 that is a standard error
of ~8 points and a 95% interval near ±16. Running ten arms against it and
picking the highest number would select noise with near-certainty: with ten arms
of equal true skill, the best observed will sit ~1.5 SE above the mean by
construction.

So the sweep does three things:

1. **Primary discriminator is the 600-question self-retrieval set** (SE ≈ 2
   points), not the golden 40. Justification: it measures the same failure —
   ranking among sibling tables — at 15× the sample. Baseline evidence that it
   tracks: self-retrieval 34% against golden `@1` 45% on the same index.
   **Its bias:** the questions are `gpt-4o-mini`-generated, so it may favour
   models aligned to that phrasing. Mitigation is not to correct it but to
   *report both* and publish the rank correlation between the two orderings.
   Disagreement between them is a finding, not a nuisance.
2. **Paired statistics.** Every arm sees identical inputs, so arms are compared
   per question — win/loss/tie — with a paired bootstrap over questions (10,000
   resamples) giving a CI on the *difference*. Comparing two independent point
   estimates throws away the pairing and is far less sensitive.
3. **This decision rule, fixed in advance.**

## Decision rule

**Axis A — bi-encoders.** Ranked by `recall@10` on the self-retrieval set.
Rationale: in this architecture the agent selects from a candidate list, so a
first-stage retriever's job is to *contain* the answer, not to order it. `@1` is
reported but does not decide Axis A.

**Axis B — rerankers.** Ranked by `@1` on the golden set over a **frozen**
candidate list — the top 10 from the current `3-large` baseline, identical for
every reranker. Freezing the candidates is what makes rerankers comparable to
each other rather than to whatever retriever they were paired with.

**A difference counts as real only if** the paired bootstrap 95% CI on the
difference excludes zero *on the self-retrieval set* (Axis A) or the arm beats
baseline by ≥ 5 questions of 40 (Axis B). Anything smaller is reported as
"not distinguishable" and the cheaper arm wins.

**Ties break toward deployment weight**, in this order: no new dependency >
smaller index > lower per-query latency > lower cost.

## Fairness constraints

- Identical document text for every arm, regenerated from metadata rather than
  read from a built index, so no arm inherits a different corpus.
- Identical query text. No per-model query rewriting in this sweep.
- **Correct instruction prefixes per model.** E5 wants `query:`/`passage:`, BGE
  wants a query instruction, Nomic wants `search_query:`/`search_document:`,
  Gemini and Cohere take a task/input type. Getting these wrong silently
  degrades a model by several points and is the most common way a sweep like
  this produces a false ranking. Each arm records the prefixes it used.
- Every embedding cached on `(model, hash of the exact text list)`, so a re-run
  is free and cannot accidentally mix a stale matrix with new text.

## Recorded per arm, whether or not it wins

Parameters, embedding dimensions, index size in MB, `corpus_n` and `corpus_hash`
(table-id fingerprint), corpus embed time, per-query latency, cost per million
queries, and whether it needs `trust_remote_code`.
The report is quality *per unit of weight*; a two-point gain that costs a 2 GB
container is a different answer from a two-point gain that costs nothing.

## What this sweep deliberately does not test

Query rewriting/HyDE, document-text changes (statistic type, breakdown
dimensions), and fine-tuning. All three are live options and all three would
confound a model comparison if varied at the same time. They come after, against
whichever encoder wins.
