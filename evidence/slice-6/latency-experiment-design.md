# CC-113 latency experiment design

Written and committed **before any experiment run**. Jira: CC-113, epic CC-3.
Only the pre-flight facts in the last section were measured before this file.

## Question

`demo.p95_latency_seconds` is over the 20 s ceiling. Which of three categories
causes it: **LLM**, **Census API**, or **ours**? Each gets one falsifiable
hypothesis, one manipulated variable, a decision rule fixed now.

## Categories (what each span covers)

Leaf spans only, so a nested call is never counted twice. Overlapping spans in a
bucket count once (union of wall-clock intervals), as `scripts/run_demo.py` does.

| category | leaf span | where it is clocked |
| --- | --- | --- |
| LLM | `chat` loop and split-plan call | `openai` `AsyncCompletions.create` |
| LLM | `rerank` | `google.genai` `Models.generate_content` (and the OpenAI rerank arm) |
| LLM | `embed` | `openai` `Embeddings.create` |
| Census | `census` | `httpx.get` (reaches `fetch._census_get` and `geo_list`) |
| ours, named | `retrieval` (BM25 + vector scoring), `url_build`, `rows` (payload to rows), `finish` (`finish_tools` less its leaf spans), `assemble`, `guards` | wrappers on the function |
| unaccounted | total minus the union of everything above | reported, never folded into "ours" |

`t_ours` in `run_demo.py` is a residual. Here it is the sum of **named** spans,
and the residual is its own number, so unmeasured time cannot hide in it.

The probe is `scripts/latency_probe.py`. Nothing under `api/src` changes
(AC "under 90 lines" is met at zero), and no budget moves.

## Workload

- **Probe set (24)**: `q18` (Milwaukee renter vs owner), `q21` (Rio Grande Valley SNAP),
  `q08` (rural Vermont disability), 15 further `long_tail` entries taken at an even
  stride through the file order, 4 `trap`, 2 `core`. Fixed by id in the script.
- **Full baseline**: `make demo` (n=186 at `--repeat 3`) is the scoreboard and the
  source of the p95. The probe set is for arms; it is not a second scoreboard.
- Every arm runs the probe set **3 repeats**, **interleaved** (repeat, then arm, then
  question) so provider drift over the hours cannot line up with one arm.
- **Sealed**: the probe takes `--questions-file`. The owner can point it at the sealed
  set and it prints aggregates only (no question text, no per-trial record). No agent
  reads that file.
- Trials are never dropped. Every statistic is shown with and without trials over 60 s,
  and for `long_tail` alone and `trap` alone.

## Instrument validity (run first, recorded)

Method: the injector logs its own sleep intervals (ground truth `G`). For each trial the
probe reports how much of `G` falls inside each category's spans.

1. 5 s sleep inside every Census request.
2. 5 s sleep inside every LLM call (chat, rerank, embed each get their own run on one question).
3. 5 s sleep inside one named ours span (`assemble`).
4. **Negative control**: 5 s sleep inside an unwrapped function (`guards.evaluate` if it is
   not wrapped for this run). The reconciliation check must **fail** and the gap must land
   in `unaccounted`.

Pass: for runs 1-3 the injected category holds `G` within 0.5 s and every other category
holds under 0.5 s of it. For run 4 the check reports failure.
Reconciliation: `llm + census + named ours + unaccounted == total` by construction, so the
check that matters is `unaccounted <= 0.5 s` on at least 99% of trials of the control arm.
If that is missed, the unaccounted time is itself a finding and spans are added, not the
threshold loosened.

## Hypotheses

### H-LLM: rerank tail latency drives the p95, not the chat loop

Early finding (CC-113 comment, 2026-10-25): q18 rerank took 6.0, 15.9, 32.9 s; chat per call
is steady.

- **Manipulated variable**: the rerank call. Arms: `A0` as shipped (Gemini); `L1` rerank
  through OpenAI `gpt-4o-mini` (provider and model); `L2` Gemini bounded at 3 s, falling
  back to the retrieval top candidate (the code's own fallback).
- **Controls**: same questions, same order, same chat model and prompt, same index, same
  Census key, interleaved arms.
- **Metrics**: calls per question; input and output tokens; per-call latency p50 and p95 by
  tier (`chat`, `rerank`, `embed`); trial total p50 and p95; and for `L1`/`L2` the quality
  cost: answered rate and `table_id == expected` on non-trap questions.
- **Repeats**: 3 per arm.
- **Confirm** if rerank per-call p95 is more than 2x chat per-call p95 in `A0`, **and** `L2`
  lowers trial total p95 by at least 2 s with the table-match rate within 3 points of `A0`.
- **Reject** if `A0` rerank p95 is at most chat p95, or `L2` moves total p95 by under 1 s.
- Otherwise **inconclusive**, with the spread stated.

### H-Census: Census time is request count times serial waves, not per-request latency

Pre-flight (below) shows a first hit and a repeat differ by 0.3 s or less even on 1.2 MB
unique queries, so cold-vs-warm is expected to be a weak lever.

- **Manipulated variable**: concurrency of the fetch fan-out, `fetch.MAX_IN_FLIGHT` in
  {1, 5 (shipped), 12}; and cold vs warm by never-seen variable subset vs repeat.
- **Design**: two parts. (a) `A0` records, per trial, requests, years, geography level,
  per-request seconds, status, retries. (b) A **replay** with no LLM: the exact URL sets
  captured in `A0`, replayed at each `MAX_IN_FLIGHT`, 3 repeats, each URL set run cold
  (variable subset the key has not served) and warm (identical URL again). This isolates
  Census from LLM noise, which would swamp a 1 s effect at /ask level.
- **Controls**: same URL sets, same key, same machine, arms interleaved.
- **Metrics**: requests per question; per-request p50 and p95 by geography level and by
  number of vintages; wall seconds per question per arm; retries and timeouts; and the
  three named questions individually.
- **Repeats**: 3 per arm.
- **Confirm** if, for questions with 3 or more requests, wall seconds at
  `MAX_IN_FLIGHT=1` exceed `MAX_IN_FLIGHT=5` by at least 1 s at the median **and** wall
  seconds are within 20% of (waves x median request), or no more than 0.5 s apart for
  fewer than 3 requests.
- **Reject** if `MAX_IN_FLIGHT=1` and `5` differ by under 0.5 s at the median (fan-out is
  not the lever).
- Cold vs warm: **reject** a cache lever if the cold-warm gap is under 0.5 s at median.

### H-Ours: after the rerank and embed split, our own code is under 1 s per question

Early finding: residual after the split is 0.1 to 0.3 s on q40 and q18.

- **Manipulated variable**: the injected delay of the validity runs doubles as the test
  that a slow named span would be seen. No production variable is changed.
- **Metrics**: p50 and p95 per named span; the largest named contributor to median
  "ours"; `unaccounted`; and every trial where ours exceeds 60 s with its cause.
- **Repeats**: the 3 repeats of `A0`, plus 12 isolated repeats of `q40`
  (the trial that took 47.8 s in the post-merge demo and did not reproduce once before).
- **Confirm** if named ours p95 is under 1 s on `long_tail` and `unaccounted` is at most 0.5 s on
  99% of trials. **Reject** if any named span has p95 over 2 s.
- A trial over 60 s is attributed to a span, or reported as not reproducible with the
  repeat count.

## Decision rules that apply to all three

- A difference smaller than the spread across the 3 repeats (max minus min of the
  per-repeat statistic) is **inconclusive**, whatever its sign.
- Recommendations are ranked by expected seconds saved at p95 per unit of effort, with the
  effort an estimate from the diff size, and each states its cost to MOE, GEOID, universe
  and alternatives.
- No recommendation is implemented in this ticket. `budgets.toml` and `/ask` do not change.

## Pre-flight (run before this file; claims the design rests on)

`scripts/` was not used; one-off requests with the repo's own key, tract queries on
ACS5 2023.

| claim | command | result |
| --- | --- | --- |
| Reordering `get=` is a usable cold-cache trick | 2 tract queries, each URL and its permutation 3 times | no first-hit penalty: 0.85 to 1.27 s first hit, 0.68 to 1.01 s repeats |
| Census cold-vs-warm is a large lever | 3 unique 12-variable state tract queries (0.7 to 1.2 MB), 3 hits each | first hit 1.57 to 2.25 s, repeats 1.31 to 2.03 s; gap under 0.3 s at the median |
| `fetch.MAX_IN_FLIGHT` is read at call time | `grep` | read at `fetch.py:340` inside `run`, so a patch before a request takes effect |
| Census goes through `httpx.get` in `fetch.py` and `geo_list.py` | `grep` | `fetch.py:112` and `geo_list.py:220`; no other network call at request time |
| Fan-out already runs up to 5 requests concurrently | `grep` | `asyncio.Semaphore(MAX_IN_FLIGHT)` with `to_thread`, `MAX_IN_FLIGHT = 5` |

Consequence: "cold" for Census is defined as a URL the server has not been asked before
(a variable subset not used earlier in the run), not as a reordered URL.
