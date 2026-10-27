# CC-113 latency experiment results

Design (committed before any run): [`latency-experiment-design.md`](latency-experiment-design.md).
Recommendations: [`latency-recommendations.md`](latency-recommendations.md).
Raw data, reports and incidents: [`latency/`](latency/). No fix is made in this ticket;
`api/src`, `/ask` and `budgets.toml` are unchanged.

All runs used `api/src` at `origin/main` b9a5ca5 (PR #114's `t_rerank`/`t_embed` split is in).
The probe is `scripts/latency_probe.py` (final commit on this branch). Times are seconds.
"Pre-registered" statistics are the ones the design doc fixed before any run; "post hoc"
ones were found afterwards and are labelled so.

## Read this first

1. **Census requests hang to the 60 s client timeout, in bursts.** `fetch.py:112` and
   `geo_list.py:220` use `httpx.get(..., timeout=60.0)`. The first main run
   (2026-10-25 evening, 288 trials, 944 requests) had none over 55 s. On 2026-10-26 and
   2026-10-27 the sealed run, the L2/A0 rerun and the cold replay all had them (status 0,
   60 to 67 s each). Re-fetching 12 of the 13 distinct URLs that hung in the rerun returned
   in 0.6 to 4.5 s, so the hang is mostly transient, not tied to a URL (`incidents.md`).
   Every statistic below is shown **with and without trials over 60 s**, and no trial is
   dropped.
2. In clean windows the p95 is driven by **the LLM**: the chat loop makes 6.6 calls per
   question (about 5.7 s of a 10.8 s median) and the rerank has a 4x heavier tail than chat.
   In hang windows the p95 is driven by **Census timeouts**. Our own code is about 0.3 s.
3. Three runs were invalid or contaminated and are excluded or rerun; see "Incidents".

## Reconciliation and instrument validity (pre-registered)

Validity (`latency/validity.txt`): an injected delay lands in the right bucket to within
0.001 s for Census, chat, rerank, embed and assemble; the unwrapped negative control lands
in `unaccounted` (10.2 to 10.3 s for 10 s injected), so the instrument fails when it should.
An earlier chat/embed injection never fired (the OpenAI SDK sends through a vendored
`httpx2`); fixed and kept as `injector-bug-*.jsonl`.

Reconciliation, `unaccounted <= 0.5 s`:

| set | trials within 0.5 s |
| --- | --- |
| main run, control arm A0 | 72 / 72 (100%) |
| all golden-set A0 (main + rerun) | 142 / 144 (98.6%) |
| sealed A0 | 91.7% (max 0.61 s) |
| sealed C1 | 87.5% (max 0.84 s) |

**The 99% target is met on the main control arm and missed pooled and on the sealed set.**
The design said a miss is itself a finding and spans are added, not the threshold loosened.
The overshoot is at most 0.84 s on trials of 8 to 194 s, so no conclusion below depends on it;
adding spans needs a rerun and is not done here.

## H-LLM: rerank tail drives the p95, not the chat loop (pre-registered)

Arms: A0 as shipped, L1 rerank through `gpt-4o-mini`, L2 Gemini rerank bounded at 3 s with the
code's own fallback to the top candidate. Main run, 24 questions x 3 repeats x arm
(`latency/arms-clean.jsonl`, `arms-report.txt`, `arms-compare.txt`).

Per-call latency, A0, p50 / p95:

| data | chat | rerank | embed | rerank p95 / chat p95 |
| --- | --- | --- | --- | --- |
| main run (n=72) | 0.87 / 1.53 | 1.90 / 6.31 | 0.29 / 0.42 | 4.1x |
| L2 rerun A0 (n=72) | 0.95 / 1.60 | 1.90 / 6.02 | | 3.8x |
| sealed A0 (n=120) | 0.97 / 1.62 | 1.89 / 5.09 | 0.33 / 0.54 | 3.1x |

**First half of the confirm rule holds on all three data sets** (rerank p95 above 2x chat p95).

Trial total p50 / p95, main run (daytime, no trial over 60 s, so "with" and "without" are the
same); per-repeat p95 in brackets:

| arm | all tiers | long_tail | trap | answered | table-match |
| --- | --- | --- | --- | --- | --- |
| A0 | 10.79 / 19.54 [16.6, 19.5, 23.7] | 10.81 / 22.62 | 13.88 / 17.45 | 0.764 | 0.850 |
| L1 | 7.40 / 13.63 [13.6, 12.8, 13.1] | 7.39 / 13.63 | 10.20 / 16.40 | 0.708 | 0.750 |
| C1 | 9.74 / 28.64 [25.6, 39.8, 17.1] | 9.74 / 38.72 | 13.66 / 22.85 | 0.806 | 0.867 |

Second half (L2), from the valid rerun `arms-l2-rerun.jsonl` (A0 and L2 interleaved, 3
repeats). The rerun ran inside a Census hang window, so totals are shown both ways:

| arm | rerank call p95 | trials over 60 s | total p50 / p95, all | total p50 / p95, <= 60 s | LLM-only p95 | table-match |
| --- | --- | --- | --- | --- | --- | --- |
| A0 | 5.97 (max 9.2) | 10 of 72 | 11.62 / 78.15 | 11.18 / 21.53 | 14.28 | 0.800 |
| L2 | 3.00 (max 3.0) | 24 of 72 | 12.90 / 130.65 | 10.31 / 25.68 | 12.09 | 0.783 |

By tier, without trials over 60 s (p50 / p95): long_tail A0 11.07 / 18.17, L2 10.44 / 26.06;
trap A0 14.09 / 21.53, L2 12.28 / 15.17. With them: long_tail A0 11.62 / 85.02, L2 12.54 /
130.65; trap A0 14.09 / 21.53, L2 13.86 / 135.58. Per-repeat total p95, all trials: A0 77.1,
78.1, 74.9; L2 130.6, 91.2, 129.7.

**Result: inconclusive.** The bound works as designed (rerank p95 6.0 to 3.0 s; LLM-only p95
down 2.2 s; table-match down 1.7 points, inside the 3-point limit). But the pre-registered test
is on trial-total p95, and there L2 is not lower by 2 s: it is 4.2 s higher without trials
over 60 s and 52 s higher with them, and the difference is smaller than the spread across
repeats. L2 drew 24 hang trials against A0's 10, so the totals are confounded by Census, not
by the rerank. The reject rule ("L2 moves total p95 by under 1 s") is not met either.

L1 (post hoc reading, not a registered confirm arm): p50 falls 3.4 s with per-repeat p50
spread of 1.1 s, a clear effect; p95 falls 5.9 s but the A0 per-repeat p95 spread is 7.1 s, so
the p95 effect is **inconclusive** by the design's rule. L1 costs 10 points of table-match
(0.850 to 0.750) and 5.6 points of answered, so it is not a free win.

The first L2 arm (`arms.jsonl`) is **invalid**: Gemini rejects a server deadline under 10 s,
the call failed instantly and fell back to the top candidate (rerank median 0.18 s, answered
0.542, table-match 0.533). Its numbers are not used.

## H-Census: Census time is request count times serial waves (pre-registered)

Replay with no LLM: the exact URL sets of A0 repeat 1 replayed at `MAX_IN_FLIGHT` 1, 5 and
12, 3 repeats (`latency/replay.jsonl`, `replay-report.txt`; cold arm
`replay-cold.jsonl`, `replay-cold-report.txt`). Warm, questions with 3 or more requests,
median wall seconds (per repeat in brackets):

| workers | wall | q18 (6 req) | q21 (10 req) | q08 (31 req) |
| --- | --- | --- | --- | --- |
| 1 | 2.92 [2.69, 2.61, 2.92] | 8.23 | 9.53 | 22.44 |
| 5 (shipped) | 1.27 [1.14, 1.27, 1.12] | 2.74 | 2.84 | 5.27 |
| 12 | 1.20 [1.12, 1.36, 1.06] | 2.98 | 3.03 | 3.59 |

Per request, warm: county p50 0.63 s (p95 1.05), place p50 0.71 (p95 2.45), state p50 0.59,
ZCTA p50 0.32. Requests per question in the arms: 3.4 mean.

**Result: not confirmed as registered; the fan-out lever is real.** The first clause holds
(1 worker is 1.65 s slower than 5 at the median, above the 1 s bar, and 22.4 against 5.3 s on
q08). The second clause (wall within 20% of waves x median request) does not hold across the
questions, so the pre-registered conjunction fails. The reject rule does not fire either
(the 1-vs-5 gap is over 0.5 s). Going from 5 to 12 workers saves 0.07 s, below the 0.5 s bar,
so more concurrency is not a lever. In the arms, C1 (`MAX_IN_FLIGHT=1`) raises p95 from 19.5
to 28.6 s, but the spread across repeats (17.1 to 39.8) is larger than the effect, so that
arm alone is inconclusive.

Named questions, as asked in the ticket: q21 (Rio Grande Valley SNAP) 10 requests, warm replay 9.53 / 2.84 / 3.03 s at 1 / 5 / 12
workers. q18 (Milwaukee renter vs owner) 6 requests, 8.23 / 2.74 / 2.98 s; its rerank tail is
the larger problem (rerank calls up to 15.5 s in the C1 arm). q08 (rural Vermont disability)
31 requests, 11 distinct, 22.44 / 5.27 / 3.59 s, and its repeat-1 URLs fetch B01003 rather
than B18101.

**Cold versus warm: inconclusive.** The first cold replay was invalid (846 of 846 requests
returned HTTP 400, the variable ID was invented; fixed to pick a real sibling variable, which
covers about 25 to 33 of the 61 distinct URLs). The rerun hit a hang window in repeat 2
(17 of 257 requests returned status 0; repeat-2 medians are 61 to 72 s). In the two unaffected
repeats, cold at 5 workers is 1.57 and 2.46 s against warm 1.14 and 1.12: cold is slower by
0.4 to 1.3 s, but the cold query carries one extra variable, so it is not a paired
comparison, and the gap is not larger than the spread. The pre-flight (design doc) measured
first hit against repeat at 0.3 s or less on 0.7 to 1.2 MB queries. No cache lever is
supported by this evidence, and a Census-side cache is not ours to control.

**Post hoc, Census timeouts.** In the sealed A0 arm Census exclusive time is p50 2.5 s and p95
64.3 s (max 184.9 s); LLM is p95 15.2 s. The slow A0 trials have 61 to 67 s of Census time,
one 60 s timeout plus ordinary requests, and the 194 s trial is about three stacked timeouts.
Only 4 of 40 sealed questions were over 60 s in 2 or more of their 3 A0 repeats, so the cause is
the window, not the question. Per-request data is removed from sealed output by design, so
this reading rests on the golden-set records of the rerun (20 requests at 60 s or more in the
first 55 trials, all status 0), not on the sealed set.

## H-Ours: our own code is under 1 s per question (pre-registered)

Named "ours" spans (retrieval, guards, assemble, `tool:*`, finish), main run A0:

| set | named ours p50 | p95 | max |
| --- | --- | --- | --- |
| A0 all (n=72) | 0.33 | 1.21 | 2.58 |
| A0 long_tail (n=54) | 0.34 | 1.24 | 2.58 |
| A0 trap (n=12) | 0.30 | 0.38 | 0.41 |
| sealed A0 (n=120) | 0.73 | 1.54 | 2.77 |

Largest span: `tool:search_tables`, p95 1.21 s on long_tail; every other named span p95 is under
0.26 s. **Result: not confirmed and not rejected.** The confirm rule (named ours p95 under 1 s
on long_tail) misses at 1.24 s; the reject rule (any named span p95 over 2 s) does not fire. Our
code is 3% of the median trial, so the conclusion "ours is not the cause" stands whichever
side of 1 s it is on. Reconciliation is above.

**Post hoc, where the 0.3 s is.** Under L1, where the rerank goes through OpenAI, named ours is
0.01 s at the median. Under Gemini it is 0.33 s. `rerank._choose_gemini` builds a new
`genai.Client` for every call, and building one costs 0.32 to 0.47 s when the machine is quiet
(measured directly, no API call), plus a one-time 1.7 s import on the first call. That time sits
outside every LLM span.

**The 47.8 s q40 repeat-3 trial: not reproducible.** 30 q40 trials in this ticket (12 isolated
in `q40-x12.jsonl`, 12 in the main arms, 6 in the rerun), plus 12 isolated runs earlier in the
ticket's own findings: the slowest is 23.9 s and none is over 25 s. A hang does not explain
47.8 s (a timeout is 60 s or more). A 30 s rerank tail would (q18 has shown rerank calls of
15.5 s here and 32.9 s earlier), but that is unverified for q40. It is reported as not
reproducible with this repeat count, with the rerank tail as the candidate cause.

## Duplicate Census requests (post hoc, not pre-registered)

295 of 944 Census requests (31.2%) in the main run are exact repeats of an earlier request in
the same trial, in 83 of 288 trials; repeat-request seconds per trial are mean 0.99 s, p95 5.7 s,
max 29 s. 9 of the 10 trials over 20 s contain one. q08 repeat 1 made 31 requests, 11 of them
distinct (`duplicates.txt`).

## Chat loop (post hoc, not pre-registered)

6.57 chat calls per question on A0 (about 5.7 s of a 10.8 s median trial); the number of chat
calls correlates 0.66 with trial total, and 7 of the 10 trials over 20 s had 8 or 9 chat calls.
That is a correlation, not an experiment: no arm in this ticket changes the loop.

## Sealed set (aggregates only)

240 trials, 40 questions, A0 and C1, 3 repeats, run by the owner with `--aggregate-only`
(sealed outputs stay gitignored under `evidence/*sealed*`; no question, id or per-request data
is in this repo). Trial total p50 / p95, seconds:

| arm | tier | all trials | without trials over 60 s |
| --- | --- | --- | --- |
| A0 | all (n=120) | 12.62 / 76.02 | 11.36 / 25.10 (n=99) |
| A0 | long_tail (n=84) | 12.34 / 76.20 | 11.02 / 22.05 (n=70) |
| A0 | trap (n=24) | 15.39 / 76.02 | 14.58 / 42.05 (n=17) |
| C1 | all (n=120) | 13.50 / 125.67 | 12.19 / 27.96 (n=88) |
| C1 | long_tail (n=84) | 12.73 / 99.00 | 11.99 / 19.75 (n=63) |
| C1 | trap (n=24) | 17.12 / 133.28 | 12.72 / 27.96 (n=16) |

Per-repeat A0 p95, all trials: 74.6, 75.6, 77.4. The regression-minus-sealed gap in quality
is a CC-3 AC6 to 12 item and is not measured here: expected tables are removed from sealed
rows, so table-match is not computed. 21 of 120 A0 trials and 32 of 120 C1 trials are over
60 s, and they are what moves the sealed p95. The sealed run overlapped my main run once
(about 76 s), and my API steps were held while the owner's sealed run was in progress.

## Scoreboard (`make demo`, same `--repeat 3`)

SCOREBOARD_PLACEHOLDER

## Incidents

Details and timestamps in [`latency/incidents.md`](latency/incidents.md).

1. Chat/embed injection never fired (OpenAI SDK uses `httpx2`); injector fixed.
2. The owner's sealed run overlapped C1 repeat 1 of the main run; those 24 trials are excluded
   and were rerun hours later (`arms-c1-r1-rerun.jsonl`), which is a different time window.
3. The first cold replay was invalid (HTTP 400 on every request); rerun with real sibling variables.
   A later restart crashed on a dropped connection and now records status 0 instead.
4. The first L2 arm was invalid (Gemini deadline under 10 s); L2 now bounds the wait client-side.
5. Census requests hung to the 60 s timeout on 2026-10-26 and 2026-10-27.
6. The session ended at about 00:35 on 2026-10-27, which stopped the cold replay at 18 of 207
   records; the partial file is kept as `replay-cold-partial-interrupted.jsonl` and not used.

## Reproduce

```text
uv run python scripts/latency_probe.py validity
uv run python scripts/latency_probe.py run --arms A0,L1,L2,C1 --repeat 3 --out evidence/slice-6/latency/arms.jsonl
uv run python scripts/latency_probe.py run --arms A0,L2 --repeat 3 --out evidence/slice-6/latency/arms-l2-rerun.jsonl
uv run python scripts/latency_probe.py report evidence/slice-6/latency/arms-clean.jsonl
uv run python scripts/latency_probe.py compare evidence/slice-6/latency/arms-clean.jsonl
uv run python scripts/latency_probe.py duplicates evidence/slice-6/latency/arms-clean.jsonl
uv run python scripts/latency_probe.py replay --source evidence/slice-6/latency/arms-clean.jsonl --out evidence/slice-6/latency/replay.jsonl
uv run python scripts/latency_probe.py replay --source evidence/slice-6/latency/arms-clean.jsonl --temperatures cold --out evidence/slice-6/latency/replay-cold.jsonl
uv run python scripts/latency_probe.py replay-report evidence/slice-6/latency/replay-cold.jsonl
# owner only, sealed set, aggregates only:
uv run python scripts/latency_probe.py run --arms A0,C1 --repeat 3 --questions-file <sealed file> --aggregate-only --out evidence/latency-sealed-cc113.jsonl
```

`arms-clean.jsonl` is `arms.jsonl` minus the contaminated C1 repeat 1, plus
`arms-c1-r1-rerun.jsonl`. It still holds the invalid first L2 arm; do not use its L2 rows.
