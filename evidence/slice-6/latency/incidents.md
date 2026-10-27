# CC-113 run incidents

## Concurrent sealed run overlapped the main arm run (2026-10-25)

The owner started a sealed-set probe run while `arms.jsonl` was running (same machine,
same network, same API keys). Facts from file metadata only; no sealed content was read:

- `evidence/latency-sealed-cc113.jsonl` (gitignored): created 21:43:53, last write 21:45:09,
  no probe process left by 21:46.
- `arms.jsonl` started 21:31:00, 84 trials at 21:46:16, so about 11 s per trial. The overlap
  falls on trials roughly 72 to 87, which is repeat 1 of arm `C1` (trials 73 to 96, in
  question order). Interleaving is repeat, arm, question, so an arm is one contiguous block
  and the overlap hits `C1` repeat 1 alone, not every arm equally.

Treatment, decided before looking at any result:

1. Exclude all 24 `C1` repeat-1 trials from `arms.jsonl` in every statistic.
2. After the main run ends, rerun `C1` repeat 1 alone into `arms-c1-r1-rerun.jsonl` and use
   that block in its place. It runs hours later than the other arms, which the results
   file states.
3. The sealed run's own timings for those 76 s are contaminated the same way. The owner
   decides whether to rerun it.

## Injector patched the wrong HTTP client (found in validity runs)

The OpenAI SDK sends through a vendored `httpx2`, so the first chat and embed injections
never fired. The injector now patches `httpx` and `httpx2`. The failed runs are kept as
`injector-bug-chat.jsonl` and `injector-bug-embed.jsonl`.

## First cold replay was invalid (2026-10-26)

`cold_variant` invented a variable ID, so 846 of 846 cold requests returned HTTP 400. It now
picks a real sibling variable from `data/raw/<dataset>/<year>/variables.json.gz`. The cold
arm is rerun after the fix; the first cold numbers are not used.

## First L2 arm was invalid: Gemini rejects a deadline under 10 s (2026-10-26)

`L2` set `HttpOptions(timeout=3000)`. One direct call returned
`400 INVALID_ARGUMENT: Manually set deadline 3s is too short. Minimum allowed deadline is 10s.`
(the same call with no timeout, and with 30 s, succeeded in 1.7 s). `rerank.choose` swallows
every exception and returns the top candidate, so the arm silently skipped the reranker
(rerank median 0.18 s, answered 0.542, table-match 0.533). None of the first `L2` numbers
are used. `L2` now bounds the wait client-side at 3 s (a thread future with a 3 s wait that
raises `TimeoutError`, which `choose` treats as a failure). This is a different mechanism
from the design doc's wording ("bounded at 3 s"); the bound and the fallback are the same.
`L2` and `A0` were rerun together, interleaved, into `arms-l2-rerun.jsonl`.

## Census requests hung to the 60 s timeout (2026-10-26 and 2026-10-27)

Both Census call sites use `httpx.get(..., timeout=60.0)` (`fetch.py:112`, `geo_list.py:220`).

- `arms-clean.jsonl` (288 trials), `q40-x12.jsonl` and `arms-c1-r1-rerun.jsonl`: no Census
  request over 55 s.
- The sealed run (2026-10-26 20:57 to 22:55), `arms-l2-rerun.jsonl` (from 23:00) and the cold
  replay (2026-10-27 about 06:10): many requests
  end at 60 to 67 s with status 0. In the first 55 rerun trials, 20 requests and 15 trials.
- Re-fetching the 13 distinct URLs that hung in the rerun, once each at about 23:30: 12 returned
  in 0.6 to 4.5 s (HTTP 200, one 204, one 400), 1 hung again to 75.9 s. The hangs are mostly
  transient and not tied to a URL.
- Consequence: totals in those runs carry Census timeout time. They are kept, never
  dropped, and every statistic is shown with and without trials over 60 s. LLM per-call times
  are not affected. The `make demo` p95 is exposed to the same episodes, and its run time is
  stated next to its number.
