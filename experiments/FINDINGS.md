# What the sweep found

Protocol in `PROTOCOL.md`, written before any arm ran. How to reproduce:
`README.md`. Raw per-question ranks: `results/*.json`.

Corpus 756 table families. Primary set 600 generated questions; secondary set 40
human-written long-tail questions. Every comparison paired per question,
bootstrapped 10,000 times. `*` marks a CI excluding zero.

---

## Axis A — bi-encoders

Ranked by `recall@10`, the pre-registered rule.

| arm | @10 | @5 | @1 | gold@1 | Δ@10 vs incumbent | dims | MB |
|---|---|---|---|---|---|---|---|
| gemini-embedding-001 | **92.3%** | 85.3% | 42.2% | 57.5% | +4.0 [+1.7,+6.5] * | 3072 | 9.3 |
| voyage-4-large | **92.0%** | 81.8% | 41.5% | 40.0% | +3.7 [+1.3,+6.0] * | 1024 | 3.1 |
| gemini-embedding-2 | 90.3% | 78.8% | 36.2% | 47.5% | +2.0 [−0.5,+4.7] | 3072 | 9.3 |
| openai-3-large *(incumbent)* | 88.3% | 77.5% | 35.5% | 42.5% | — | 3072 | 9.3 |
| cohere-embed-v4 | 87.8% | 75.7% | 37.8% | 32.5% | −0.5 [−3.3,+2.2] | 1536 | 4.6 |
| openai-3-small | 79.8% | 69.2% | 34.8% | 30.0% | −8.5 * | 1536 | 4.6 |
| embeddinggemma-300m | 77.7% | 65.5% | 28.5% | 25.0% | −10.7 * | 768 | 2.3 |
| mxbai-embed-large-v1 | 77.3% | 64.7% | 31.8% | 37.5% | −11.0 * | 1024 | 3.1 |
| bge-large-en-v1.5 | 76.2% | 64.3% | 32.5% | 37.5% | −12.2 * | 1024 | 3.1 |
| e5-large-v2 | 72.8% | 58.8% | 25.5% | 32.5% | −15.5 * | 1024 | 3.1 |
| bge-m3 | 66.8% | 55.0% | 22.7% | 17.5% | −21.5 * | 1024 | 3.1 |

**The two leaders are not separable.** `gemini − voyage` on the deciding metric
is +0.3 points, CI [−1.8, +2.7]. Voyage produces a 3.1 MB index against 9.3 MB.
On the 40 human questions Gemini leads by 17.5 points with a CI that technically
excludes zero — see the limits section before believing it.

---

## Axis B — rerankers

Frozen top-10 from the incumbent encoder, so rerankers are compared to each
other rather than to their retriever. Ceiling 90%; no reranking scores 42.5%.

| arm | kind | @1 | MRR | vs no reranking |
|---|---|---|---|---|
| gemini-3.7-flash | generative | **77.5%** | 0.81 | +35.0 |
| gpt-4o-mini | generative | 67.5% | 0.74 | +25.0 |
| *no reranking* | — | *42.5%* | — | — |
| cohere-rerank-3.5 | cross-encoder, hosted | 40.0% | 0.53 | −2.5 |
| bge-reranker-v2-m3 | cross-encoder, local | 35.0% | 0.48 | −7.5 |
| mxbai-rerank-base-v1 | cross-encoder, local | 20.0% | 0.38 | −22.5 |

Zero failed calls on all five, so these are scores rather than silent fallbacks.

**Every purpose-built cross-encoder was worse than not reranking.** They are
trained on (query, natural-language passage) pairs; our documents are twelve-word
structured records with no passage to score, and the discriminating fact is
semantic — households are not families. Generative models reason about that.

---

## Axis C — metadata design

Does a richer document help? Derived from variable labels, never authored.
Three variants, tested on both the reranker path and the embedding path.

**Reranker path** (no re-embedding needed):

| listing | mean chars | gemini-3.7-flash | gpt-4o-mini |
|---|---|---|---|
| plain | 131 | 77.5% | 67.5% |
| rich — everything derived | 213 | 75.0% | 60.0% |
| lean — only discriminating | 140 | 77.5% | 65.0% |

Zero questions gained across both models, four lost. The derived statistic type
is generic for 56% of the corpus, so `rich` added 63% more text of which over
half separates nothing.

**Embedding path** (a different mechanism — an embedder cannot reason):

| encoder | plain @10 | lean @10 | paired |
|---|---|---|---|
| gemini-embedding-001 | 92.3% | 92.8% | +0.005 [−0.008,+0.018] |
| voyage-4-large | 92.0% | 91.5% | −0.005 [−0.018,+0.008] |

Symmetric around zero. **Derived metadata enrichment is neutral at best and
harmful at worst, on both paths.**

The rule that survives all three tests: **a field earns its place only if it
discriminates between sibling tables.** Text that describes the topic makes
every sibling more similar. That is why synthetic questions were slice 0's
largest regression, why `rich` lost four questions, and why keywords like
"income, salary, wealth" would apply equally to B19013, B19113, B19001 and
B19025.

**Not tested:** a genuine natural-language statement of what a table is *for*,
as opposed to a restatement of its title. That cannot be derived, and generation
is what failed before.

---

## What actually moved the number

Neither models nor metadata. **Corpus structure**, before this sweep began:

- 588 race iterations and Puerto Rico variants folded into their parent tables.
  `B19013A` was outranking `B19013`; a broadband question answered with
  "population in households who are White alone".
- 115 `B00`/`B98`/`B99` survey-quality tables dropped — allocation rates and
  sample counts, never the subject of a question.

1,458 documents → 756, and `@5` moved 68% → 80%. Larger than every model
difference measured here.

---

## Limits

- **No multiple-comparison correction.** Dozens of paired tests were run against
  a protocol that pre-registered none. The single "significant" golden-set result
  — Gemini over Voyage — is the one most likely to be a false positive, and it is
  the one that would otherwise pick a winner. The same 40 questions cannot
  establish that Gemini beats the incumbent.
- **The primary set is machine-generated** and may reward models sharing
  `gpt-4o-mini`'s phrasing. Spearman rho between the two sets fell from +0.82 to
  +0.73 when Voyage joined; Voyage is where they disagree most.
- **Forty human questions** cannot resolve anything smaller than ~5 questions.
  Growing that set is the cheapest remaining harness investment.
- **The 8B class was measured infeasible, not scored.** `Nemotron-3-Embed-8B`
  downloads and loads correctly, then embeds at **18.7 s/text** on 12 CPU cores
  — about 4x worse than scaling linearly from the 335M models, because CPU bf16
  kernels upcast. That is 5 hours to screen one arm and 7.3 hours to run it in
  full.

  The cost is not the reason to stop. **18.7 s/text is also the query embedding
  cost**, against a 20-second p95 budget for a whole answer. An 8B local encoder
  cannot ship in this product on CPU whatever it scores, so measuring it would
  inform nothing. The top of both MTEB and RTEB is 7B+ and stays out of reach
  until there is a GPU or a hosted endpoint for that class.
