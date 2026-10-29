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
| **v5 (adopted)** | **0.800** | **0** | shorter; names no measure and no table |

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
- Demo on the adopted prompt v5: pending (final E2E on the last commit).
