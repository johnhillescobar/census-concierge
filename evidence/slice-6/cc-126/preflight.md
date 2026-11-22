# CC-126 preflight

Head this note was checked against: `origin/main` `700d800`.

## Claims

| Claim | Result |
| --- | --- |
| `fetch.py` calls `httpx.get(..., timeout=60.0)` | True at `api/src/fetch.py:114` on `700d800`. The ticket's line 112 is that call before later edits. |
| `geo_list.py:220` does the same | True. |
| `httpx`'s numeric timeout is per phase | `httpx.Timeout(60.0)` sets connect, read, write and pool each to 60 (`httpx` 0.28.1). |
| `latency_probe.py compare` exists | True (`cmd_compare`). |
| Clean-window maximum and the 10s cut | `evidence/slice-6/latency/arms-clean.jsonl`: 944 Census requests, slowest HTTP 200 is 4.311s, 0 requests over 10s. |

The 10s hedge is a bit over twice that 4.311s maximum. The wall-clock budget stays 60s for the original call and its one retry together. A per-phase 60s is what ran to 62.8s and 75.9s in the CC-113 notes.

`scripts/url_grid.py`, `scripts/memory_probe.py` and `latency_probe.py`'s replay GET are not the ask-path calls the ticket names. They still pass `timeout=60.0`.
