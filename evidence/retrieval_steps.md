# Slice 0 — the measured steps

PLAN.md: *"A number before each next step, or you will never know which parts
you can delete."* This is that record. Every number is `@1 / @3 / @5 / MRR` on
the **40-question long-tail tuning set**, `text-embedding-3-large` unless noted.

Not counted against `doc_lines`: this is evidence, not instruction.

## The prescribed ladder

| Step | @1 | @3 | @5 | MRR |
|---|---|---|---|---|
| BM25 only, raw | 12% | 28% | 35% | 0.20 |
| BM25 + corpus stopwords | 18% | 35% | 45% | 0.30 |
| + embeddings, `3-small` | 20% | 52% | 60% | 0.35 |
| + embeddings, `3-large` | 28% | 57% | 68% | 0.43 |
| + synthetic questions | 32% | 50% | 62% | 0.43 |
| **final: families + subject-only, semantic** | **45%** | **68%** | **80%** | **0.56** |
| final + LLM rerank of top 10 | **70%** | 75% | 82% | 0.73 |

Holdout (n=8, run once): `@1` 62%, `@5` 100%. No sign of tuning to the set —
it scores *above* the tuning number, though at n=8 that interval is ±17 points.

## What the plan expected and the data denied

**Embedding models.** `3-large` beat `3-small` by 8 points `@1` and 0.08 MRR.
The plan called `3-small` "the documented default, not a finding"; it was right
to. Cost difference at 756 documents is under a cent. It is now the
default in `embedding.py`, so `make index` reproduces these numbers.

**BM25 fusion hurts.** Equal-weight RRF scored *below* embeddings alone on every
metric (`@1` 40%→28%, `@5` 80%→68%). BM25 at `@1` 18% is not close enough in
strength to earn an equal vote, and the plan forbids weighting for good reason —
any weight is fitted to 40 questions. BM25 stays built and unused by `search()`:
it is what answers a query naming a table ID verbatim, which this set never does.

**Synthetic questions hurt.** The plan said *"expect the largest jump"* here. It
was the largest *drop*: `@1` 40%→25%, MRR 0.55→0.47. One vector per question
with max-pooling was no better (30%), nor was a 50/50 blend (32%). They add
recall (`@10` 88%→90%) and cost precision. The questions are accurate and
generic — six ways of asking about a table describe its topic while blurring
what separates it from its neighbours, and neighbours are the entire problem.
Generation is kept and committed; the embedding no longer reads it.

## What actually moved the number

Both are corpus structure, not ranking:

- **Table families.** 574 race iterations and Puerto Rico variants folded into
  their base table. `B19013A` is `B19013` filtered to Black householders and
  carries a near-identical title, so it crowded out its own parent — "crowded
  housing" ranked `B25014G` first. The members become slice 1's `alternatives[]`.
- **Survey-quality tables.** 114 `B00`/`B98`/`B99` tables dropped. They describe
  how the survey performed, not what it measured. Left in, "how long have
  naturalized citizens held citizenship" answers `B99053`, *Allocation of Year
  of Naturalization*.

- **Iteration-only families.** 14 more dropped. `B28009` is published only
  as `B28009A-I`, and representing that family by its first member put
  "Population in households who are White alone" at rank 1 for a broadband
  question. A race iteration returned as the general table is the exact
  silent wrong answer this product exists to prevent.

- **Identical `B`/`C` twins.** 120 more dropped, 2026-08-15. A `C` table is its
  `B` counterpart with categories collapsed, and the two publish the same title,
  universe and concept — so 120 documents were byte-identical to another
  document and their vectors were equal. Of 600 generated questions, the 97
  asking for such a `C` scored **0%** at rank 1: not hard to rank, impossible.
  Which twin won was decided by float noise, because `text-embedding-3-large`
  returns different vectors for identical text at different batch positions
  (max component difference 1.3e-3), so it could flip on any rebuild — the
  index had `C15003` beating `B15003` for "educational attainment in Cook
  County". `B` has strictly more cells in all 120, so it loses the user nothing,
  and the `C` stays reachable through `members` like a race iteration.

1,458 documents → 636. Worth more than every ranking change combined.

## Where it stands

Slice 0 closed. The gate is retriever `@10` (0.90) and selector `@1` (0.70+);
raw `retrieval_at_1` = **0.475** is diagnostic only.

The shape of the gap is unambiguous and consistent across every configuration:
`@10` is 88–90% while raw `@1` is 45%. The index finds the right table and cannot
put it first, because what separates `B25091` from `B25095` is a universe
string, which is reading, not vector distance. PLAN authorized a reranker under
exactly this condition, and one takes selector `@1` over the floor.

`synthetic_self_retrieval` = **0.45** — diagnostic only. That number assumed
questions would be *in* the embedded document; with them out it duplicates the
golden-set ranking problem on a 600-question sample. The gate is now
**`synthetic_alignment`** (mean cosine from each question to its own
title/universe/concept document): **0.544** against a floor of **0.50** —
catches off-topic generation without requiring rank 1 among 636 siblings.

Dropping the twins moved it from 0.34, and most of that is the benchmark being
wrong rather than retrieval improving: 16% of the sample asked for a table that
no ranker could have returned. On the questions that were always answerable the
change is +0.002.
