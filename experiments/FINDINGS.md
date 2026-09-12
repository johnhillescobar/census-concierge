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

**A fourth variant, targeted rather than blanket, also failed.** 32% of the
corpus (242 of 756 tables) embeds to byte-IDENTICAL text: a `C` collapsed table
carries the same title and universe as the `B` detailed table it came from, and
the embedded document is title + universe. Identical text means identical
vectors, so which twin ranks first is decided by array order — an exact tie on
7 of 40 golden questions. Cell count separates them perfectly (`B02003` 71
categories, `C02003` 21). Adding it *only* where a twin exists:

| encoder | plain @10 | twin-aware @10 | paired |
|---|---|---|---|
| gemini-embedding-001 | 92.3% | 88.8% | −0.035 [−0.055,−0.015] * |
| voyage-4-large | 92.0% | 91.3% | −0.007 [−0.022,+0.008] |

Worse, significantly so on the better encoder. Four enrichments tested — generated
questions, all derived facts, only-discriminating facts, and a targeted
tie-break — and every one is neutral or harmful. **The embedded document should
be as short and as purely topical as possible.** Words that discriminate for a
human still dilute the topical signal a vector is carrying.

The tie is real, and Axis E below found where it should be fixed: not in the
document and not in the ranking, but by not having two documents. `C02003` is
`B02003` with fewer categories, so one of them should never have been a
retrieval target. Where two tables genuinely *are* different and still
indistinguishable — `B05013` and `B05014` publish the same title and universe —
the user should see both, which is what the margin signal is for.

**Not tested:** a genuine natural-language statement of what a table is *for*,
as opposed to a restatement of its title. That cannot be derived, and generation
is what failed before.

---

## Axis D — is low confidence detectable?

If the gap between the top two candidates predicts whether the top one is right,
the product gets a confidence signal for free, from vectors it already has,
before spending an LLM call. `python experiments/run_margin.py`.

| signal | AUC, n=600 | AUC, n=40 |
|---|---|---|
| top1 − mean(top10) | 0.748 → 0.730 | 0.680 → 0.654 |
| top1 − top5 | 0.730 → 0.719 | 0.682 → 0.656 |
| top1 − top2 | 0.707 → **0.734** | 0.758 → **0.768** |
| top1 score alone | 0.660 → 0.600 | 0.570 → 0.570 |

Re-run 2026-09-11 against cached embeddings with mid-rank `auc()` (CC-51). Figures
before the arrow are the published ordinal-rank rows. `top1 − top2` is now the
best signal on both sets; the qualitative range is unchanged.

AUC 0.5 is a coin flip. **The gap works** — around 0.73–0.77, which is a usable
signal rather than a strong one. What a threshold buys, on the golden set:

| cut at | covers | top-1 right above | top-1 right below |
|---|---|---|---|
| 50th pct | 50% | 80% | 40% |
| 70th pct | 30% | 92% | 46% |

So the top 30% of questions by margin are answered correctly 92% of the time,
and the bottom half barely better than chance. That is exactly the split the
product needs: answer confidently when the gap is wide, and when it is narrow,
show the neighbours with the reason they differ — never a blocking question.

Two caveats. The absolute margins are tiny (a 50th-percentile cut sits at 0.0057
cosine, was 0.0036 when first published — the cut is a quantile of the margins,
not of `auc()`), so the threshold must be calibrated per encoder and
re-calibrated when the encoder changes. And 32% of documents are exact twins,
which puts a floor under how often the margin can be wide.

---

## Axis E — the table ID itself

The ID is already this corpus's best feature: `family_id` strips the `A`–`I`
race iteration and `PR` suffix, `is_subject_table` reads the 2-digit subject as
`00`/`98`/`99`. What is left is the type prefix and the subject code.
`python experiments/run_codes.py`. None of it goes into the embedded document.

**The `B`/`C` prefix, as a reason to drop a document.** A `C` table is its `B`
counterpart with categories collapsed, and the two publish the same title,
universe and concept — so 120 of 756 documents are byte-identical to another
document. `B` carries strictly more cells in all 120.

| arm | @10 | @5 | @1 | Δ@1 vs plain |
|---|---|---|---|---|
| plain (756 documents) | 92.3% | 85.3% | 43.0% | — |
| tie-break `B` over `C` | 92.3% | 85.3% | 43.0% | +0.000 |
| drop the 120 `C` twins | 94.2% | 89.2% | 50.8% | +0.078 [+0.057,+0.100] * |

Split by whether the question's answer was one of the dropped twins, because
only the untouched questions measure "120 fewer distractors" on its own:

| | n | @1 before | @1 after |
|---|---|---|---|
| answer was a twin | 97 | **0.0%** | 47.4% |
| answer untouched | 503 | 51.3% | 51.5% |

**That is not a retrieval gain, it is a benchmark correction.** Those 97
questions asked for a table whose vector is identical to another table's. No
ranker could ever put it first; they were scored as failures and were
unanswerable. `@1` on this set was never 43% — it was 51% on the questions that
could be answered, dragged down by 16% that could not. Voyage agrees (5.1% →
33.0%), so this is a property of the corpus, not of a model.

Two consequences beyond the score:

- **The winner was not stable.** `text-embedding-3-large` returns *different*
  vectors for identical text depending on batch position — measured max
  component difference 1.3e-3, enough to move a cosine by 6e-4, which is the
  size of a real margin here. So the twin that won was decided by float noise
  and could flip on any rebuild. The shipped index had `C15003` above `B15003`
  for "Educational attainment in Cook County"; the experiment's stable sort
  had it the other way.
- **The tie-break is worth nothing** once the fold is in, and was worth nothing
  before it: `B` already sorts ahead of `C`, so it changed zero questions.
  Dropping the document is the fix; reordering it is not.

**The 2-digit subject code, as a confidence signal.** 29 subject codes, and
grouping the corpus by them produces coherent topics without any authored
mapping (`25` housing n=150, `19` income n=54, `08` commuting n=88). The
hypothesis was that a top-5 spanning several subjects means the index has not
found the topic. It does not hold:

| signal | AUC n=600 | AUC n=40 |
|---|---|---|
| subject agreement in top-5 | 0.411 → 0.494 | 0.125 → 0.422 |
| margin (top1 − top2) | 0.707 → 0.703 | 0.758 → 0.760 |

Re-run 2026-09-11, same as Axis D. Subject agreement stays at or below 0.5 — the
n=40 figure moved a lot and is still not a usable signal. The relationship still
runs the *other* way: when all five candidates share a subject they are siblings
and harder to order, not easier. And 70% of questions sit at the maximum value,
so there is almost no range to threshold on. Margin remains the only confidence
signal measured here.

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
