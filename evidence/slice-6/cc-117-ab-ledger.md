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

## Round 2 E2E: depth 30 + prompt v7, commit 24936d6, run 1 (`cc-117-e2e-d30-run1.txt`, `cc-117-d30-run1-latest.json`)

HEAD 24936d6 at start and end (`cc-117-d30-run1-head.txt`). `--repeat 3`, n=186, isolated worktree.

| | baseline d0d7995 | depth 10 + v5 | **depth 30 + v7** |
|---|---|---|---|
| long_tail answered (floor 0.70) | 0.708 | 0.708 | **0.692 (83/120: one trial under the floor)** |
| core / trap / overall | 0.833 / 0.870 / 0.763 | 0.750 / 0.685 / 0.704 | 0.750 / 0.815 / 0.731 |
| mean t_llm / t_rerank | 6.9 / 85 (hung trial) | 46 / 121 (hung trials) | 6.5 / 5.0 (no hang) |
| demo p95 | 28.4 | 23.8 | 31.1 |

Recovered to baseline: t08, t12, t18 (0 misses each). Changed vs baseline (misses of 3): q21 0->3 (golden under review),
q29 0->1 (no table), q30 0->1 (B05001 for B05011), q41 2->3 (misses on main too), t09 0->3 (not retrievable),
t14 0->2, t07 1->3 (misses 3/3 at every depth in the selector probe), t04 0->1 (unrelated warning), q04 (core) 2->3 (table
returned, other failure). Gains: q07 2->0, q35 1->0, q43 1->0, t15 3->1, t16 3->0.

Latency is not attributable to pool depth: direct rerank timing, sequential, 24 calls per depth
(`cc-117-variants/rerank_latency.py.txt`): median 3.25 s (depth 10), 3.24 s (20), 3.28 s (30), 3.16 s (10 again); tails of
12-40 s appear at every depth including 10. The demo p95 above is Gemini's tail, not the prompt size.

## The gated selector_at_1 now measures a different instrument (re-baseline, owner to acknowledge)

`scripts/eval_retrieval.py --rerank` used to hand the selector `max(k, 10)` = 10 candidates. It now hands it
`POOL_DEPTH` = 30, the same pool the ask loop reads, so the number describes the product. `budgets.toml [quality]`
still reads the same keys (`selector_at_1_min = 0.70`, `check_budgets.py` reads `selector_at_1`); its comment says
"over that pool", which was a 10-table pool when the floor was set. No budget was edited.

Comparable pairs only: **depth 10, Sibling rules (main): 0.85 / 0.85 / 0.825. Depth 10, prompt v5: 0.775 / 0.775 / 0.80.
Depth 30, prompt v5: 0.82 / 0.80 / 0.775 (`cc-117-d30-selector-r*.txt`). Depth 30, prompt v7 (adopted): 0.80 / 0.80 / 0.80
(`cc-117-v7-selector-r*.txt`).** The `cc-117-d30-*` files are the v5 prompt at depth 30; `cc-117-v7-*` is the adopted prompt.
The depth-30 numbers are not directly comparable with main's depth-10 baseline: a deeper pool also makes the selector's job
harder, so the same floor on the new instrument is, if anything, stricter.

## Gate 2 round 2 (commit range d0d7995..24936d6; fixes in 16b148d)

- Invariants pass (`cc-117-gate2-review-pr-round2.txt`): all OK; machine failures identical to clean d0d7995. Prompt n-gram
  check against all 70 golden question texts: 0 shared 3-grams and 4-grams.
- Cold read: no high/medium bug. Fixed: the pick cache ignored `k` (now keyed `(question, k)`, test mutation-checked); stale
  "top ten" help text and a `launch.json` comment. Accepted: a pick beyond rank 10 drops retrieval rank 10 from the response
  (cosmetic; the pick is always first). Kept: `ask_fixtures.py` returns a single hit for device questions, so those ask-loop
  tests exercise fetch and vintages, not selection.
- Open for the owner after both rounds: the long_tail floor (see run 1 and run 2), t09, q21, and the metric redefinition above.

## Raw evidence for the Round 2 depth tables (captured at 16b148d, adopted prompt v7)

`cc-117-depth-ranks.txt` reproduces the ranks and retrieval@K figures exactly (t08 27, t09 none, t12 12, t18 12, q21 4, t14 7;
trap @10/@15/@30/@60 = 0.571/0.786/0.857/0.929). `cc-117-pools-t08-t09-t12-t18-q21.txt` lists the full top-10 pool, the
selector picks and the expected table for the five questions. `cc-117-depth-eval.txt` is the selector by pool depth with the
**adopted v7 prompt** (the earlier table in Round 2 was prompt v5; both are real, different prompts):

| pool depth | long_tail | trap | trap misses (of 3) |
|---|---|---|---|
| 10 | 0.817 | 0.500 | t07, t08, t09, t12, t14, t16, t18 all 3 |
| 15 | 0.792 | 0.762 | t07, t08, t09 all 3; t14 1 |
| 20 | 0.800 | 0.714 | t07, t08, t09, t14 all 3 |
| 30 | 0.800 | 0.810 | t07, t09 all 3; t14 2 |

Across both prompts the pattern holds: depth 30 is the only one that recovers t08 (rank 27); depths 15-20 recover t12 and t18;
t07 and t09 miss at every depth; the long_tail selector is flat within run-to-run spread (0.79-0.82).
This capture ran while the repeat demo was in flight, so that run's latency is not clean (its answered rate is unaffected).

## Round 3: the model supplies the measure as the search query (`topic`)

Why: depth cannot fix a question the retriever embeds badly. "Population of Phoenix in 2024 from the 1-year ACS" puts B01003
at rank **45**; "Total population of Phoenix" puts it at rank **1**. Place, year and dataset words dilute the measure
(`cc-117-variants/t07.py` was a one-off probe; the numbers are in `cc-117-topic-recall.txt`).

Change: `search_tables` gets an optional `topic` argument, composed by the model (no new LLM call, no regex, index and
reranker unchanged). The index is searched with `topic` when given, with the question otherwise (the code-only `finish_tools`
path has no model to write one); the selector still reads the full question. The pick cache is keyed `(question, topic, k)`.
Test `test_search_uses_the_topic_and_the_selector_still_reads_the_question`, mutation-checked three ways (topic ignored,
topic not normalised, cache ignores topic). Tool-description example contains no place or eval phrasing (the leakage
invariant caught an earlier draft naming a state).

Offline, `gpt-4o-mini` at temperature 0 writing a measure-only query per dev question (`cc-117-topics.json`, raw
`cc-117-topic-recall.txt`, `cc-117-topic-selector.txt`; head `cc-117-topic-eval-head.txt`):

| expected table within the pool | question as query | topic as query |
|---|---|---|
| long_tail @10 / @30 (n=40) | 0.900 / 0.925 | 0.875 / 0.950 |
| trap @10 / @30 (n=14) | 0.571 / 0.857 | 0.857 / **1.000** |
| selector@1 at depth 30, v7 prompt, 3 picks: long_tail / trap / core | 0.808 / 0.786 / 1.000 | **0.817 / 0.929 / 1.000** |

Rank moves: t07 45 -> 1, t09 none -> 24, t08 27 -> 18, t12 12 -> 4, t18 12 -> 9; q36 1 -> 13 is the one that got worse (still in
the 30). Only trap miss left offline: t14.

In the real loop (`scripts/ask_one.py`, `gpt-4o-mini` as the agent), `topic` was filled on 6 of 6 questions tried and the
selected table was the expected one for t07, t09, t08, t12 and t18 (B01003, B28001, B19001, B17001, B27001). q11 still selects
"Aggregate Travel Time ... by Sex" (misses on main too). Note the model also shortens the `question` argument ("not just the
median" and "across every tract" were dropped from three of the six); that predates this change.

The `eval_retrieval.py --rerank` instrument still searches with the question (no model in that script), so the gated
`selector_at_1` is a conservative reading of the product; the demo is the end-to-end measure.

## Round 3 E2E: topic search + depth 30 + v7, commit 1f9115b (`cc-117-e2e-topic.txt`, `cc-117-topic-latest.json`)

HEAD 1f9115b at start and end (`cc-117-topic-head.txt`). `--repeat 3`, n=186, isolated worktree. No hung trials
(`t_llm` 5.9 s, `t_rerank` 4.3 s), so this is the first latency reading that is comparable.

A second clean sample of unmodified main exists: the CC-121 session's post-merge run on d0d7995
(commit 72c8a47; copy in `cc-117-main-second-sample-latest.json`). Both main samples are used below.

| long_tail answered (floor 0.70, needs 84/120) | trials | rate |
|---|---|---|
| main sample 1 (this ticket's pre-run) | 85 | 0.708 |
| main sample 2 (CC-121 post-merge, same commit) | 87 | 0.725 |
| depth 10 + v5 | 85 | 0.708 |
| depth 30 + v7, run 1 / run 2 | 83 / 84 | 0.692 / 0.700 |
| **topic + depth 30 + v7** | **81** | **0.675** |

| | main 1 | main 2 | depth 30 run 1 | depth 30 run 2 | **topic + depth 30** |
|---|---|---|---|---|---|
| core | 0.833 | 0.750 | 0.750 | 0.917 | 0.750 |
| trap | 0.870 | 0.926 | 0.815 | 0.741 | **0.870** |
| overall | 0.763 | 0.785 | 0.731 | 0.726 | 0.737 |
| p95 | 28.4 (hung trial) | 22.0 | 31.1 | 50.0 (hung) | **24.5** |

AC (long_tail within 3 points of the pre-run): 0.675 vs 0.708 is -3.3 points, **outside the limit on this run**; vs main
sample 2 it is -5.0. The floor is missed (81 < 84). Runs 1 and 2 at depth 30 were -1.6 and -0.8.

Where the long_tail trials went (misses of 3, main 1 / main 2 -> topic run):
- **q21 0 -> 3**: all three. The selector picks a "Receipt of Food Stamps/SNAP ... for Households" table over golden B19058.
  Without q21 the long_tail count would be 84 (vs 85 / 87).
- **q15 0 / 1 -> 2** (B05012 for B05002), **q38 0 / 1 -> 1** (C02015 for B02015), **q40 0 -> 1** (B25137 for B25041): real selector
  effects; q15 is the one topic search may have caused. q08 0 -> 2 is a geography miss ("wrong geography level county") with
  the right table, not a table choice.
- Gains: q07 2 / 0 -> 0, q35 1 -> 0, q43 1 -> 0.

Trap: t08, t12, t18 at 0 misses (as on main), t07 **0** (main 1 / 2). t09 selects B28001 in 1 of 3 trials (B28010 in the others)
and fails all three on the missing `measure_unavailable` warning, which nothing raises any more. t14 misses 2 of 3 (main 0: the
pin). The trap gap to main sample 2 (0.926 vs 0.870) is t09 and t14.

Net: pin removal is now a wash on t07, t08, t12 and t18 and the cost has narrowed to four golden questions that need an owner
decision (q21, t14, t09-warning) plus selector noise on q15 / q38 / q40. The long_tail floor is not reliably met by this branch
(81, 84, 83 trials) and is only just met by main (85, 87).

## Round 4: q15, q38, q40, and whether a weak topic should be backstopped by the question

Goldens at this point: q21 expects C22001 and t09 has no warning requirement (commit 8cf374f, owner-approved rebaseline;
main is re-run against them, see below).

Real loop, `scripts/ask_one.py`, three runs each on the branch:
- **q38** selected B02015 in 3 of 3 (topic "Asian population"). The demo's single C02015 trial was selector noise.
- **q15** selected **B05012** "Nativity in the United States" in 3 of 3 (topic "foreign-born population"), not golden B05002. B05012
  is the most direct table for foreign-born versus native counts; this is the q21 situation again. Golden not changed without an
  owner decision (changing it would need another run of main).
- **q40**: the model's `topic` decides it. "number of housing units" selected B25137 (Bedrooms by Occupancy Status);
  "number of zero or one-bedroom units" and "...by number of bedrooms" selected B25041. One of four samples dropped the breakdown.

Pool strategies, sampled topics (3 per question at temperature 0.8, `cc-117-topics-sampled.json`; raw `cc-117-pool-strategies.txt`;
script `cc-117-variants/topic_robust.py.txt`), selector@1 with the adopted prompt, 3 picks per question:

| pool built from | long_tail | trap | expected table in pool (long_tail / trap) |
|---|---|---|---|
| question only, depth 30 | 0.800 | 0.786 | 0.925 / 0.857 |
| **topic only (the branch)** | **0.842** | **0.929** | **0.942 / 1.000** |
| topic top 20 + question fill to 30 | 0.842 | 0.905 | 0.925 / 0.929 |
| rank fusion of topic and question | 0.825 | 0.905 | 0.925 / 0.929 |

A question backstop does not beat topic-only: both hybrids lose t09 and gain nothing. Code unchanged. q40's miss is a weak topic
from the model (1 of 4 samples); the tool description already says to keep any breakdown.

## Round 5: the pool offered tables the vintage does not publish (found by tracing q21)

Run on the branch with the rebaselined goldens (`cc-117-final4-latest.json`, HEAD 0bfc9f3): long_tail 0.667 (80/120) against main's
0.700 (84/120). q21 returned **no table** in 3 of 3 trials, not a wrong one. Trace (`scripts/ask_one.py`): the selector picked C22001,
`build_url` answered "C22001 is not in acs5 2024", twice, and the answer ended with no URL.

Ground truth, Census API, `/data/2024/acs/{acs5,acs1}/groups/{table}.json`: C22001 acs5 404 / acs1 200; B24010 acs5 404 / acs1 200;
B22001 and B19058 200 in both. In the availability matrix, **70 of 636 indexed tables (11%) are not in the latest ACS5**, including
34 of 45 C tables. B15010 (what q41's selector picked) is among them. The failures with "wrong table (none)" on main and on the
branch (q17, q21, q34, q41) are this: the selector offers a table the default dataset cannot serve, `build_url` fails, and the user
gets no URL, which the project treats as the worst outcome.

Two golden mistakes follow. The earlier re-baseline of q21 to C22001 (8cf374f) named a table that cannot be fetched in ACS5;
`verify_golden.py` checks the metadata, not the vintage. It is reverted to B19058 (3d30869). q17's golden B24010 is unpublished in
ACS5 2024 (ACS1 only), so q17 cannot pass on the default dataset on any code; that is the owner's call and is not changed here.

Fix (plain set membership against the availability matrix; no regex, no model call): `search_tables` takes an optional `dataset`
(acs5 unless the question asks for 1-year), fetches 20 extra candidates, and keeps only tables, or tables with a family member,
that the dataset's latest vintage publishes. Test `test_the_selector_never_sees_a_table_the_vintage_does_not_publish`,
mutation-checked four ways (no filter, members ignored, dataset ignored, no over-fetch). Largest file 409/410 lines.

Real loop after the fix: q21 selects B22001 and returns data; q41 selects B15012 (its golden); q17 selects B24114; q34 selects B24060.
`eval_retrieval.py --rerank` does not apply this filter, so it still overstates the pool the product uses.

## Round 6: the question the selector reads, prompt v8, and where search_tables spends its time

Harness: `cc-117-variants/pool_capture.py.txt` (captures, per golden question, the exact pool the product hands
the selector: the loop model's own `topic`, depth 30, published filter), `pool_eval.py.txt` (scores a prompt over
those pools), `pools-product.json` (the captured pools). Run from the repo root.

**The model's copy of the question.** `search_tables` took `question` from the model's tool call. The schema said
"verbatim" and nothing enforced it; the model dropped the breakdown or the period in some draws (q15: "by county in
Minnesota"; t14: "changed since 2013"). `dispatch` now supplies `record.question` (`f8356c2`, two mutation-checked
tests). Re-traced q15, t14, q30 twice each: the selector received the full text and the picks did not change
(q15 B05012 x2, t14 B28010 x2, q30 B05011 x2). So the dropped words were not the cause of those two losses.

**Prompt.** The "by ..." rule was the suspect for q15 and was not the cause: B05012 sits at rank 21 of the pool and
is picked 5 of 5 under every variant; B05002 is at rank 9. It is the selector's reading of the titles
("Nativity in the United States" against "Place of Birth by Nativity and Citizenship Status"), and arguably B05012
is the better answer. q15's golden is left as is (owner's call, CC-3 AC10). v8 (cross-tab taken only when the
question also concerns what follows "by") against v7 (shipped in 1be4cc3), 6 repeats over the product pools:

| | long_tail (40) | trap (14) | core (4) | held-out (8) | t14 misses /6 |
|---|---|---|---|---|---|
| v7 | 0.800 | 0.929 | 1.000 | 0.875 | 6 |
| **v8 (adopted)** | **0.817** | **0.976** | 1.000 | 0.875 | 2 |

v9 and v10 (3 repeats) were not better (long_tail 0.808 / 0.792). No table ID, no measure rule, 0 shared 3-grams
with the golden question texts. The held-out miss (h02) is the same on every variant. These are offline selector
numbers; the demo is still the measure.

**Latency of `search_tables`** (66 golden questions, one call each, spans around each step):

| step | median s | p90 s | max s |
|---|---|---|---|
| total | 4.25 | 6.25 | 19.98 |
| index search (embed + fuse) | 0.41 | 0.57 | 2.08 |
| describe (3300 calls) | 0.000 | 0.000 | 0.000 |
| published check (3422 calls) | 0.000 | 0.000 | 0.000 |
| selector (Gemini) | 3.84 | 5.73 | 19.46 |

The selector call is 90% of the time and all of the tail. The tail is random, not per question or per pool size:
the same call repeated 6 times on one question took 3.6, 3.6, 7.5, 10.4, 16.4, 19.2 and 20.8 s, while the question
that took 19.98 s in the sweep took 2.3 to 3.8 s on repeat. Pool size is not the cause (earlier: median 3.2 to
3.3 s at depths 10, 20 and 30). `rerank._choose_gemini` sets no request timeout and no retry.

## Round 7: timeout and one retry on the selector call

`rerank.choose` now gives the Gemini request a 10 s deadline (`TIMEOUT_S`) and makes up to two attempts
(`ATTEMPTS`); two failures still fall back to the retrieval top. Four tests, each mutation-checked
(no retry, no timeout, retry on success).

**A first attempt at 6 s was wrong, and the unit tests could not see it.** Gemini rejects a deadline under 10 s
(`400 INVALID_ARGUMENT: Manually set deadline 6s is too short. Minimum allowed deadline is 10s.`). Every call then
failed and fell back to the top-ranked table, which made `search_tables` look fast (selector median 0.92 s against
3.8 s) and changed the picks (q15 B05011, q12 B27010). The faked `generate_content` in the tests accepts any
deadline. It was caught because 0.9 s was too good to believe and the picks were re-read. 10 s is the floor.

`search_tables` over the 66 golden questions, selector spans, with the 10 s deadline and retry (two sweeps; the
provider's speed drifts between sweeps, so the medians differ):

| sweep | total median s | total p90 s | total max s | selector max s |
|---|---|---|---|---|
| before (no deadline) | 4.25 | 6.25 | 19.98 | 19.46 |
| 1 | 3.08 | 5.37 | 14.90 | 14.58 |
| 2 | 3.13 | 4.41 | 7.60 | 7.34 |

The cap works, but the 10 s floor limits it: a call that hangs costs 10 s plus a normal second attempt, about
13 to 15 s, against up to 21 s before. A hedge (start the second call at about 6 s without cancelling the first) would
cut it further and was not built.

### Correction to Round 6: the selector's slow tail is hidden thinking, not random

Round 6 said the tail is random. Repeated calls on one question showed it is not: q41 took 14 to 19 s in 5 of 6
calls and q34 8 to 17 s in 4 of 6, even with the deadline. Reading `usage_metadata` on those calls
(`cc-117-variants/thinking_usage.py.txt`): the output is 11 tokens every time, and the time follows the thoughts.

| call | seconds | thoughts tokens |
|---|---|---|
| q41 | 15.7 / 9.5 / 4.8 | 1746 / 1225 / 347 |
| q34 | 10.1 / 2.0 / 3.0 | 1242 / none / none |
| q02 | 2.5 / 2.4 / 2.0 | 75 / none / 78 |

`rerank.py` already sends `thinking_budget=0`; `gemini-3.7-flash` does not honour it. `thinking_level=MINIMAL` is
rejected (`400: not supported for this model`) and `LOW` still spends 170 to 1248 thoughts tokens
(`cc-117-variants/thinking_level.py.txt`). So the cap and one retry (Round 7) bound the damage, and the tail itself
needs a different model or setting, which is outside this ticket (no change of reranker model).

## Round 8: the end-to-end at the final code (branch 6c7c512 against main on the same harness and goldens)

Both runs in isolated worktrees, `--repeat 3`, n=186, HEAD logged at start and end (`census-cc-117-pair3.head`).
Branch 6c7c512. Main = origin/main c8ec7f5 + the demo-harness fix (69b09b7) + the branch's golden file (t09 only).
Artifacts: `cc-117-final7-latest.json`, `cc-117-main4-latest.json`, `cc-117-final7-stdout.txt`, `cc-117-main4-stdout.txt`.

| | main (c8ec7f5) | branch (6c7c512) |
|---|---|---|
| long_tail answered (floor 84/120) | **0.767 (92)** | **0.667 (80)** |
| trap | 0.907 | 0.944 |
| core | 0.750 | 0.750 |
| demo.p95_latency_seconds (ceiling 20) | 28.5 | 29.6 |
| trials over 20 s | 46 | 38 |
| rerank per trial: mean / p95 | 4.7 / 10.5 | 4.7 / 13.5 |

The gated criterion "long_tail within 3 points of the pre-run" is NOT met by this run (-10.0 points against main in the
same window; -3.3 to -5.8 against the earlier main samples 0.708, 0.725, 0.700). Main itself spans 0.700 to 0.767 across
five samples, so one pair cannot settle it.

**Latency is the provider's window, not this branch.** Gemini was slow for both runs (p95 28.5 and 29.6; 46 and 38 trials
over 20 s). Earlier runs (p95 20.3 and 21.0) were in a faster window. The p95 is red on both sides and stays a human
decision (waiver) or CC-125/CC-126.

**Where the branch loses to main, per question (misses of 3):**

| question | main | branch | cause |
|---|---|---|---|
| q41 | 0 | 3 | **the 10 s deadline**: rerank was 20.9, 19.7, 20.3 s = two timed-out attempts, then the fallback to the top-ranked table (C15010). Main picks B15012 in 3 to 8 s. |
| q15 | 0 | 3 | B05012 ("Nativity in the United States") beats the golden B05002; it appears only in the 30-deep pool (rank 21) |
| q21 | 0 | 2 | B22001 (SNAP receipt) over the golden B19058 |
| q38 | 0 | 2 | C02015 over B02015 despite the B-over-C sentence |
| q40 | 0 | 2 | B25137 over B25041 |
| t14 | 0 | 2 | B28010 / B28003; main reaches B28001 through its device pin |
| q08 | 0 | 1 | geography-level miss, right table |
| gains: q12 (-1), t07 (-2), t13 (-1), t15 (-1) | | | |

**Deadline and retry, measured against its premise.** In the branch run, long_tail trials with a selector call over 10 s
were answered 3 of 8; on main 3 of 11. The six branch trials with about 20 s of rerank (q41 x3, q26, q34, t06) were
answered 1 of 6. A deadline only pays when the retry is much faster than the call it cut off; questions that trigger long
thinking (q41, q34) are slow again on retry, so the cap costs 10 s and then falls back to the top-ranked table. The pool
for q41 is 1,439 tokens at depth 30; main reads a shorter pool and finishes in 3 to 8 s.

**Pool depth, offline, no deadline (66 pools captured from the loop's own topics, 3 repeats, selector only):**

| depth | long_tail | trap | core | held-out |
|---|---|---|---|---|
| 10 | 0.767 | 0.786 | 1.000 | 0.750 |
| 15 | 0.800 | 0.810 | 1.000 | 0.750 |
| 20 | 0.817 | 0.857 | 1.000 | 0.875 |
| 30 | 0.825 | 0.976 | 1.000 | 0.875 |

Depth 30 is best on every tier, so the demo losses at depth 30 are not a depth effect on average; q15 is the one question
that is missed at depth 20 and 30 only (the competing table is not in a 10-deep pool). The offline numbers do not show
the demo's q38, q40 and q21 misses (the demo composes its own topic each run, so its pool differs from the captured one).
Harness: `cc-117-variants/depth_product.py.txt`.

## Round 9 - the deadline and retry are removed

Round 8 showed the 10 s deadline turning slow-but-correct selections (q41) into fast wrong ones, with no p95 gain over main.
`rerank.py` and `test_rerank.py` are back to main's behaviour apart from `POOL_DEPTH` and the prompt. The bound on the wait is
CC-125's story, which also covers the thinking-token tail (finding posted there). Branch re-run below.

## Round 10 - branch re-run without the deadline (d7464e4, `--repeat 3`, n=186, HEAD d7464e4 at start and end)

| | main (Round 8) | branch with deadline (6c7c512) | branch without (d7464e4) |
|---|---|---|---|
| long_tail answered | 0.767 (92) | 0.667 (80) | **0.683 (82)** |
| trap | 0.907 | 0.944 | 0.926 |
| core | 0.750 | 0.750 | 0.750 |
| demo p95 | 28.5 s | 29.6 s | 20.39 s (ceiling 20) |

Misses of 3 trials, per question (only questions whose count differs between runs):

| question | main | with deadline | without |
|---|---|---|---|
| q15 | 0 | 3 | 3 |
| q21 | 0 | 2 | 3 |
| q41 | 0 | 3 | 3 |
| q38 | 0 | 2 | 1 |
| q40 | 0 | 2 | 1 |
| t14 | 0 | 2 | 1 |
| q12 | 1 | 0 | 0 |

**Correction to Round 8:** q41 was not caused by the deadline. Without it q41 still misses 3 of 3, picking C15010 over
B15012 (rerank 7 to 18 s; main picks B15012). The deadline did not change the long_tail rate beyond the noise in these
samples (0.667 vs 0.683). Remaining gap to main in this window: q15, q21, q41 (9 trials), q38, q40, t14 (3 more).
Floor 84/120 is not met (82).

## Round 11 - rebased onto origin/main c8ec7f5

The branch was rebased onto `c8ec7f5` (PR #118, evidence only); code, tests and docs are byte-identical to the pre-rebase tip
`191bd56` (`git diff` over `api scripts docs evals budgets.toml` is empty). Every commit SHA changed. Commits cited in this
ledger and in the `*-head.txt` files map as follows (old -> new): f4b23d1 -> f9f9a3a (deadline added), 92c2692 -> 13d0d1f,
6c7c512 -> d62b3c3 (code tip of the deadline runs), d7464e4 -> 815de3c (deadline removed; code tip of the final run),
758e284 -> e70cee5, 191bd56 -> 8b805ad. The scoreboards were measured on the old SHAs; the code at the new SHAs is the same.
