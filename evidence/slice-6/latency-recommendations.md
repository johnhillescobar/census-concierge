# CC-113 latency recommendations

Evidence: [`latency-experiment-results.md`](latency-experiment-results.md). Design:
[`latency-experiment-design.md`](latency-experiment-design.md). Nothing here is implemented in
CC-113; no ticket is filed (the owner files, and decides the epic). `budgets.toml` is not
touched and none of these proposes touching it: the p95 gate keeps reading the run-local
`demo.p95_latency_seconds`.

## What the evidence says, in one paragraph

Two different things set the p95, depending on the window. In a clean window (the main run,
2026-10-25) nothing was over 24 s and the p95 of 19.5 s is the LLM: 6.6 chat calls per question
(about 5.7 s of a 10.8 s median) and a rerank whose p95 is 3 to 4x the chat p95. In a hang window
(2026-10-26 and 2026-10-27) 25% of sealed A0 trials are over 60 s and the p95 is 76 s: a Census
request waits out the 60 s client timeout. Our own code is about 0.3 s per question. Expected
savings below are therefore stated per window, and a recommendation that only helps in one window
says so.

## Recommendations

"Saving" is the expected change at p50 / p95 of trial total. "Measured" means an arm in this
ticket produced it; "estimated" means it is arithmetic on measured data and an experiment must
confirm it before the fix ships. Effort is a size estimate from the diff, not a measurement.

### Ranked by saving per effort

| # | category | change | saving, clean window | saving, hang window | effort | basis |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Census | Bound the wait on a Census request and hedge one retry | 0 / 0 | 0 / about 50 s (76 s to about 25 s sealed A0) | S | measured cause, estimated fix |
| 2 | ours | Build the Gemini client once, not per rerank call | about 0.33 s / about 0.33 s | same | S | measured |
| 3 | Census | Do not repeat an identical Census request within one question | about 0.5 s mean / up to 5.7 s | same | M | measured upper bound |
| 4 | LLM | Bound the rerank wait at 3 s with the existing fallback | about 0 / 1 to 2 s | 0 | S | measured on LLM time, confounded on totals |
| 5 | LLM | Cap chat-loop turns | about 1 / 2 to 3 s | same | M | estimated |
| 6 | Census | Keep `MAX_IN_FLIGHT = 5` (no change) | none | none | none | measured |

### 1. Census: bound the wait on a request and hedge one retry

- **Evidence.** `fetch.py:112` and `geo_list.py:220` call `httpx.get(..., timeout=60.0)`. In hang
  windows requests end at 60 to 67 s with status 0: 20 requests in the first 55 rerun trials,
  17 of 257 in the cold replay, and the slow sealed A0 trials hold 61 to 67 s of Census time
  (one timeout plus normal requests; the 194 s trial is about three). Sealed A0 p95 is 76.0 s with
  those trials and 25.1 s without them. Re-fetching the 12 of 13 hung URLs returned in 0.6 to
  4.5 s, so a second identical request would usually have succeeded. A normal request is 0.6 to
  0.7 s at the median and 1.0 to 2.4 s at p95; the slowest legitimate response seen is a 2.2 MB
  `place:*` query at 3.2 s.
- **Expected saving.** Clean window: 0 / 0 (no request is over 5 s). Hang window: the p95 drops
  from about 76 s towards the no-hang 25 s, about 50 s, and the 194 s case falls to about 30 s.
  Estimated, since the hedged retry has not been run.
- **Cost and risk.**
  - *Wrong answers.* A request cut off too early turns a slow valid response into a failed fetch.
    Set the first wait well above the slowest legitimate response (10 s, over 2x the 4.3 s
    daytime maximum) and measure the false-cut rate on a clean window before shipping.
  - *MOE, GEOID, universe, alternatives.* The retry repeats the identical URL, so the `M`
    variables, `GEOID`, universe and related tables are unchanged. If both attempts fail, the
    existing failure path applies and the full URL is still shown.
  - *Load.* At most one extra request, only after a 10 s wait.
  - The sealed rows have no per-request data, so the sealed tail is a supported reading, not a
    proven one; the golden-set records are the direct evidence.
- **Not recommended:** lowering the 60 s without a retry (turns a transient hang into a failure).

### 2. ours: build the Gemini client once

- **Evidence.** Named ours time is 0.33 s at the median under Gemini rerank and 0.01 s under the
  OpenAI rerank (L1). `rerank._choose_gemini` builds `genai.Client(...)` on every call, which
  costs 0.32 to 0.47 s on a quiet machine, outside every LLM span; the first call also pays a 1.7 s
  import.
- **Expected saving.** About 0.33 s at p50 and p95 for every question that reranks (1.04 calls
  per question). Measured directly (client construction timed on its own); the end-to-end effect
  has not been run.
- **Cost and risk.** None to MOE, GEOID, universe or alternatives. The repo forbids module-level
  mutable state, so the client is created once per process and passed in as an argument, not
  cached in a module global; where it is created is for the fix story to decide.

### 3. Census: do not repeat an identical request within one question

- **Evidence.** 295 of 944 requests (31.2%) repeat an earlier request in the same trial, in 83 of
  288 trials; repeat-request seconds per trial are mean 0.99 s, p95 5.7 s, max 29 s; 9 of the 10
  trials over 20 s contain one. q08 repeat 1 made 31 requests, 11 of them distinct.
- **Expected saving.** Up to 0.99 s mean and 5.7 s at p95 of Census time per trial (an upper
  bound: concurrent requests overlap other work, so the wall saving is smaller). Estimated.
- **Cost and risk.** Same URL, same vintage, same variables, so the response is the same: no MOE,
  GEOID or universe cost. The record of requests already made lives on the request record, not
  in module state. The risk is a dedupe key that is too loose (two different requests treated as
  one): key on the full URL without the API key.

### 4. LLM: bound the rerank wait at 3 s, keep the code's own fallback

- **Evidence.** Rerank call p95 is 6.3 s (main run), 6.0 s (rerun) and 5.1 s (sealed), against chat
  p95 of 1.5 to 1.6 s. With a 3 s client-side bound (Gemini rejects a server deadline under 10 s),
  rerank p95 is 3.0 s, LLM-only trial p95 falls 14.3 s to 12.1 s (measured, 2.2 s), and
  table-match is 0.783 against 0.800 (down 1.7 points). Trial-total p95 was not lower in that run
  (it was inside a Census hang window), so the hypothesis is inconclusive at the total.
- **Expected saving.** Clean window: p50 about 0; p95 1 to 2 s on trials where the rerank was the
  long call. Hang window: 0, the Census wait dominates.
- **Cost and risk.** The fallback is the top retrieval candidate, so a cut-off rerank can pick
  the wrong table, and with it the wrong universe (households against families). The measured cost
  was 1.7 points of table-match and 4 points of answered (0.750 to 0.708) on 72 trials per arm,
  inside the noise but not shown to be zero. Alternatives are still listed. Needs a same-repeat
  A/B on a clean window before shipping.
- **Not recommended as-is:** switching the rerank to `gpt-4o-mini` (L1). It cuts p50 by 3.4 s,
  but costs 10 points of table-match (0.850 to 0.750) and 5.6 points of answered. Every one of
  those points is a user handed the wrong table.

### 5. LLM: cap chat-loop turns

- **Evidence.** 6.57 chat calls per question on A0, about 5.7 s of a 10.8 s median; calls
  correlate 0.66 with trial total; 7 of the 10 trials over 20 s made 8 or 9 chat calls.
- **Expected saving.** Each avoided call is about 0.95 s. Cutting the 8 to 9 call trials down to
  6 saves about 2 to 3 s at p95, about 1 s at p50 if the cap trims the median. Estimated from a
  correlation; no arm in CC-113 changes the loop.
- **Cost and risk.** The loop may need those turns to reach an answer, so answered rate can drop.
  The experiment must read answered rate and table-match, not just seconds. The fix is a turn cap
  in the loop, not a new graph node and not a heuristic that pre-empts the model.

### 6. Census: keep `MAX_IN_FLIGHT = 5`

- **Evidence.** Warm replay median wall: 2.92 s at 1 worker, 1.27 s at 5, 1.20 s at 12; q08
  (31 requests) 22.4, 5.3 and 3.6 s. The 5-to-12 gain is 0.07 s at the median, below the 0.5 s
  bar. In the arms, `MAX_IN_FLIGHT=1` raises the p95 from 19.5 to 28.6 s, but the repeat spread
  (17.1 to 39.8) exceeds the effect.
- **Saving.** None. This is a written case for **no change**: do not lower the concurrency, and
  more is not worth it.

## Ranking rationale

1 and 2 are small diffs with the largest, best-evidenced effects (1 on the worst windows, 2 on
every rerank). 3 is a medium diff with a measured upper bound. 4 and 5 trade seconds against
answered rate and table-match, so they come after an experiment. 6 is not a change.

None of these changes the p95 ceiling or how it is measured. If after 1 to 3 the demo still
sits above 20 s in a clean window, the next candidates are 4 and 5, each with its own A/B; the
gate stays as written, and a ceiling is never moved to fit a number.

## Draft fix story (ready to file; not filed)

**Title:** Bound and hedge Census requests, and build the Gemini client once

**Description.** CC-113 found two latency causes that code owns. (1) Census requests can hang
to the 60 s client timeout in bursts (`fetch.py:112`, `geo_list.py:220`); in those windows the
sealed p95 is 76 s against 25 s without the hung trials. (2) `rerank._choose_gemini` builds a
`genai.Client` for every call, 0.32 to 0.47 s outside any LLM span. Evidence:
`evidence/slice-6/latency-experiment-results.md`.

**Acceptance criteria**

1. A Census request that has not returned in 10 s is retried once with the identical URL, and
   the first response to return is used. A request that fails twice follows the existing failure
   path, and the full URL is still in the response.
2. The wait before the retry is justified by a measurement in the PR: the slowest legitimate
   response in a clean window, and the rate at which the 10 s cut would have fired.
3. The Gemini client is created once per process and passed as an argument; no module-level
   mutable state.
4. `MOE` is fetched alongside every estimate, `GEOID` and universe are shown, and alternatives are
   listed, exactly as before; a test fails if a retried or failed request drops any of them.
5. The PR quotes the `make demo` scoreboard at the same `--repeat` as CC-113's, and
   `latency_probe.py compare` for A0 before and after on the same window. If a window has
   Census hangs, the numbers are given with and without trials over 60 s.
6. `budgets.toml` is unchanged and `demo.p95_latency_seconds` is still read from the run.
7. No regex or keyword matching; no new graph node; no module named `*_manager`, `*_service` and
   the like.

**Out of scope:** a rerank bound or a different rerank model (recommendation 4), a chat-turn cap
(5), request dedupe (3, separate story). Each needs its own same-repeat A/B on a clean window.

**Expected effect:** clean window 0.3 s at p50 and p95 (the client); hang window about 50 s at
p95. Estimated; the PR replaces the estimate with its own measurement.

**Companion story, to file after the one above:** "Do not repeat an identical Census request
within a question" (recommendation 3), with the dedupe record on the request record and a test
that two distinct URLs are never merged.
