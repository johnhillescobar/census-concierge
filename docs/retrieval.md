# Retrieval: what was measured, what runs

DESIGN §6 is the intent. This file is the measured record and the live path.

## Two experiment logs

They are not the same sweep.

| log | what it varied | BM25? |
|---|---|---|
| `evidence/retrieval_steps.md` | slice-0 ladder: BM25 → embeddings → synthetics → RRF → rerank, then corpus folds | yes |
| `experiments/FINDINGS.md` | encoder, reranker, document text, confidence margin, table-ID *structure* | no |

`experiments/PROTOCOL.md` held document text and ranker mix fixed so the
encoder comparison would not be confounded. Re-run BM25 vs semantic vs fused
with `uv run python scripts/diagnose.py rankers`. Rebuild BM25-only with
`uv run python scripts/build_index.py --bm25-only`.

## Slice-0 ladder (long-tail n=40)

| step | @1 | @5 |
|---|---|---|
| BM25 only, raw | 12% | 35% |
| BM25 + corpus stopwords | 18% | 45% |
| + embeddings `3-large` | 28% | 68% |
| equal-weight RRF | *below* embeddings alone (40%→28% @1, 80%→68% @5) | |
| families + subject-only, semantic | 45% | 80% |
| + generative rerank of top 10 | 70% | 82% |

BM25-only is weak on these questions because they have almost no lexical overlap
(`bike to work` vs `MEANS OF TRANSPORTATION TO WORK`). Fusion lost because BM25
at 18% `@1` is not strong enough for an equal vote, and any weight would be
fitted to 40 questions.

## What actually moved `@1`

Corpus structure, not ranking (`experiments/FINDINGS.md` Axis E, same result as
the ladder). 1,458 tables → **636 documents**:

- 588 race iterations and PR variants folded into the parent (`B19013A` → `B19013`)
- 114 `B00`/`B98`/`B99` survey-quality tables dropped
- 120 collapsed `C` tables folded into the identical `B`

Members stay in the artifact and become `alternatives[]`. Synthetic questions
are generated and committed; folding them into the embedding *lowered* `@1`.
Richer documents (FINDINGS Axis C) were neutral or harmful.

## What `search()` does today

With `semantic.npz` present, ranking is **embeddings only**
(`text-embedding-3-large`). BM25 postings are loaded and not consulted.
BM25 runs only if the semantic file is missing (a `--bm25-only` index).

`search_tables` then calls `rerank.choose()` (Gemini) over the top-10 pool.
`index.search()` does not. That split is [CC-54](https://johnhillescobar.atlassian.net/browse/CC-54).

Gated metrics: long-tail retriever `@10`, selector `@1`, `synthetic_alignment`.
Raw cosine `@1` is diagnostic.

## The unused-BM25 reservation

Lexical documents still carry title + universe + concept + **all variable
labels**, including table IDs and labels that never appear in a title
(`3-person carpool`). Embeddings stay short (title + universe + concept).
That split is still right.

The golden set never types a table ID. “BM25 would answer `B19013` or rare
jargon” is an **untested hypothesis**, not a finding. It is not a live
`search()` branch. Wiring it needs a query-class branch plus golden questions
that actually type IDs.

## Not in the index

Variable-level *documents* were a DESIGN guess. The index is table families.
Fetching every published cell of a selected table is [CC-77](https://johnhillescobar.atlassian.net/browse/CC-77) / CC-82, not retrieval.
