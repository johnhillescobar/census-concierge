# CC-117 A/B ledger: pins and Sibling rules removed

Baseline = main `d0d7995`, run in its own worktree. Branch = `feat/cc-117-no-table-pins`.
All demo numbers `--repeat 3`, n=186, same index (`377cd59fe62a`) and same Census/model keys.
Raw: `cc-117-baseline-*.{txt,json}`, `cc-117-branch-latest.json`, `cc-117-selector-*`, `cc-117-holdout-*`.

## Demo, selector prompt v1 (first general principle), commit bf44ecd

| | baseline | branch | delta |
|---|---|---|---|
| long_tail answered (gated, floor 0.70) | 0.708 | 0.683 | -2.5 pts (AC: within 3) |
| core / trap / overall | 0.833 / 0.870 / 0.763 | 0.750 / 0.704 / 0.694 | |
| miss trials | 44 | 57 | +13 |
| p95 | 28.4 s | 25.7 s | not comparable, see below |

Latency caveat: the baseline contains one trial of **6,502 s** (an unbounded rerank call), which is why its
mean `t_rerank` is 85 s against 4.3 s on the branch. Both p95s are over the 20 s ceiling, as on main.
Searches per question were not instrumented in this run.

## Every question whose outcome changed (misses out of 3 repeats)

| id | tier | expected | base -> branch | got on branch | cause |
|---|---|---|---|---|---|
| t08 | trap | B19001 | 0 -> 3 | B19082 | expected table **not in the retrieved top-10**; the pin injected it |
| t09 | trap | B28001 | 0 -> 3 | B28010 | not in pool; also the `measure_unavailable` warning is gone |
| t12 | trap | B17001 | 0 -> 1 | B17020 | not in pool; the pin injected it |
| t18 | trap | B27001 | 0 -> 3 | B27010 | not in pool; the pin injected it |
| t14 | trap | B28001 | 0 -> 3 | B28003/B28010 | in pool at rank 7; selector picks a sibling |
| q21 | long_tail | B19058 | 0 -> 3 | (C22001) | in pool at rank 4; see Losses |
| q08, q09, q15 | long_tail | | 0 -> 1 each | | single-repeat misses, no pin involved (noise) |
| t16 | trap | B17001 | 3 -> 0 | | gained, no pin involved (unexplained; treat as noise) |
| q07, q35, q43 | long_tail | | 2->0, 1->0, 1->0 | | gained (noise) |
| t15, q04, q41, t07 | | | +-1..2 | | noise-level moves, table unchanged |

## Selector only (`eval_retrieval.py --tier long_tail --rerank`, n=40, three runs each)

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| baseline (Sibling rules) | 0.850 | 0.850 | 0.825 |
| branch, prompt v1 | 0.775 | 0.775 | 0.800 |

Changed selector outcomes: **q11** (commute; chose "Aggregate Travel Time ... in Minutes"), **q21** (SNAP), q12 (noisy in both).
q10, q17, q18, q20, q34, q41 miss in both arms. Floor 0.70 met. Historical 0.875 baseline is diagnostic only.

## Prompt iterations (dev set only, 3 picks per question; held-out untouched until the end)

| variant | long_tail selector@1 | q11 misses/3 | note |
|---|---|---|---|
| v0 = v1 prompt | 0.783 | 3 | reproduces the branch run |
| v2 | 0.783 | 3 | |
| v3 | 0.800 | 1 | |
| v4 | 0.783 | 2 | |
| **v5 (adopted)** | **0.800** | **0** | shorter; no table ID and no measure rule; its Aggregate example (minutes, dollars) is generic title vocabulary |

Five variants, no table ID or measure name in any. Texts and harness: `cc-117-variants/`.

## Held-out (h01-h08), selector with rerank, three runs each

Baseline 7/8, adopted v5 7/8, every run. Same single miss (h02) in both arms.

## Losses needing an owner decision (AC5)

1. **t08, t09, t12, t18: the pins hid retrieval@10 misses.** The table was never returned by the index, so no
   selector change can recover it and the alternatives panel cannot list it. Out of scope here (retrieval stack).
   These are trap-tier, not gated.
2. **t09 `measure_unavailable`:** the warning had a phrase trigger; it is not raised now. Golden t09 still expects it.
3. **q21:** the selector picks "Receipt of Food Stamps/SNAP ... for Households", the plainest title for
   "households receiving SNAP". Golden B19058 ("Public Assistance Income or Food Stamps/SNAP") is arguably the weaker
   match; the removed rule existed to prefer it. No general principle recovers it without encoding that preference.
4. **t14:** B28001 is rank 7; sibling choice is a judgement the golden settles one way.

## Not measured

- Sealed set and regression-minus-sealed gap: owner-held, not run.
- Retrieval@10 not re-measured by the capture on the branch (block stale); the index is unchanged (`index_hash` equal).
- Grid (visible / held-out) and `searches per question`: not run or instrumented for this ticket.
- Latency: see the final section; the p95 is not comparable.

## Final E2E: adopted prompt v5, commit 9b39eef, isolated worktree, `--repeat 3`, n=186

HEAD was 9b39eef at start, at the resume and at the end (`cc-117-final-head.txt`). The first attempt died with
the session before any scoreboard; the demo was re-run with `--from demo` (eval, rerank, synthetic, build had
completed). Raw: `cc-117-e2e-final.txt`, `cc-117-final-latest.json`; the earlier v1-prompt run is `cc-117-e2e-v1-prompt.txt`.

| | baseline d0d7995 | v1 prompt bf44ecd | **final 9b39eef** |
|---|---|---|---|
| long_tail answered (gated, floor 0.70) | 0.708 | 0.683 | **0.708 (delta 0.0)** |
| core / trap / overall | 0.833 / 0.870 / 0.763 | 0.750 / 0.704 / 0.694 | 0.750 / 0.685 / 0.704 |
| miss trials | 44 | 57 | 55 |
| selector@1 long_tail (`--rerank`, n=40) | 0.85/0.85/0.825 | 0.775/0.775/0.80 | 0.80 (one run in the capture) |
| held-out h01-h08 selector@1 | 7/8 x3 | | 7/8 x3 |
| retrieval@10 long_tail | 0.90 | 0.90 (stale block) | 0.90 |
| demo p95 | 28.4 s | 25.7 s | 23.8 s |

**p95 is not usable as a comparison.** The final run's mean `t_llm` is 46 s and mean `t_rerank` 121 s (a normal
run is about 6.8 s and 4 s), the run spanned a long idle gap, and the baseline held a 6,502 s trial. All three
p95s are over the 20 s ceiling, as on main. Nothing here shows this change moved latency.

Outcomes that differ from baseline (misses of 3): the pin-served trap questions t08, t09, t14, t18 (0 to 3 each;
t12 recovered to 0); q21 (0 to 3, see Losses); q18 3 to 1, q12 2 to 1, t15 3 to 0, q07 2 to 0 (gains, not
pin-related); q38 0 to 1 (got C02015 for B02015), t04 0 to 1, t16 3 to 1, q04 2 to 3 (core, expected table
returned, other trial failure) are single-trial moves without a table change attributable to this PR.
q11 (commute) misses 3 of 3 in the demo in both arms, so the selector fix measured in the harness did not
change the demo outcome.

## Round 2: the trap-tier loss is a pool-depth problem (solved in this ticket)

Jira check (live, read-only): no ticket in CC-3 owns retriever recall of plain base tables. CC-117 excludes
"the retrieval stack or reranker model" but says the fix is "in retrieval or the selector, measured and general".
Pool depth `k` is a tool parameter, not the retrieval stack, so it is changed here.

Where the pin-served tables rank in the retriever (`cc-117-variants/depth.py.txt`):
t12 rank 12, t18 rank 12, t08 rank 27, t09 not in the top 60, t14 rank 7, q21 rank 4. The retriever puts the plain
base table of a family below its narrower cross-tabs. Trap retrieval@K (n=14): @10 0.571, @15 0.786, @30 0.857, @60 0.929;
long_tail dev (n=40): @10 0.90, @15 0.925, @60 0.95.

Selector over a deeper pool, prompt v5, 3 picks per question (`cc-117-variants/depth_eval.py.txt`):

| pool depth | long_tail selector@1 | trap selector@1 | trap questions recovered |
|---|---|---|---|
| 10 | 0.808 / 0.817 | 0.500 | |
| 15 | 0.800 | 0.714 | t12, t18, t16 |
| 20 | 0.800 | 0.714 | same (t08 is rank 27) |
| 30 | 0.800 | 0.833 | t08, t12, t18, t16; t14 1/3 |

Change: `POOL_DEPTH = 30` in `rerank.py`, shared by the search tool and `eval_retrieval.py --rerank`. The selector reads 30
candidates; the tool returns the pick plus the best-ranked rest, capped at 10 (`SHOWN`), so alternatives, the allowed-table
set and the response size are unchanged. Test: `test_selector_reads_the_deep_pool_and_the_answer_stays_ten_wide`,
mutation-checked both ways (no cap; depth back to 10).

At depth 30 the pool holds seven "Aggregate Travel Time" tables and the v5 prompt stopped following its own rule (q11 flipped
to 3/3). Prompt rewrites at depth 30 (`variant_depth.py.txt`, long_tail + trap, 3 picks):

| variant | long_tail | trap | misses outside the 7 persistent |
|---|---|---|---|
| v5 (previous) | 0.792 | 0.857 | q11 2/3, q12 2/3 |
| v6 | 0.808 | 0.810 | q11 1/3, q12 1/3, t14 1/3, t17 1/3 |
| **v7 (adopted)** | **0.825** | **0.833** | t14 1/3 |

Through the real eval path (`--rerank`, depth 30, v7, three runs): long_tail selector@1 0.80 / 0.80 / 0.80; held-out
h01-h08 7/8 / 7/8 / 7/8 (same single miss, h02). Persistent long_tail misses, identical on main: q10, q17, q18, q20, q34, q41;
plus q21 (see Losses) and one of q11 / q12 per run.

Still open after round 2: **t09** is never retrieved (B28001 "Types of Computers in Household" shares no words with
"cell phones") and its `measure_unavailable` warning is gone; **q21** is a golden question where the selector's pick is arguably
the better table; **t07** misses 3/3 at every depth.
