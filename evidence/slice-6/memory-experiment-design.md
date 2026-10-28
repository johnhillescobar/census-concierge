# CC-123 memory experiment design

Written and committed **before any experiment run**. Jira: CC-123, epic CC-3.
Only the pre-flight facts in the last section were established before this file.

## Question

During the CC-121 E2E, `run_demo --repeat 3` reached trial 44 of 186 when the harness
reaped the shell for low memory; the orphaned Python process held about 5 GB. Is that
growth (a) already on `origin/main`, (b) added by CC-121, and (c) retained Python heap,
native allocation, or per-request client/loop/handle growth, or only an allocator
high-water mark that would have plateaued?

## What is measured (all script-only; nothing under `api/src` changes)

`scripts/memory_probe.py`. Windows API through `ctypes` (no new dependency; `psutil` is not
installed and `direct_dependencies` is a budget). No module-level mutable state: a `Sampler`
object is passed as an argument.

Per trial, in this order:

1. **Pre-GC sample**: `PrivateUsage`, `WorkingSetSize`, `PeakWorkingSetSize`
   (`GetProcessMemoryInfo`), process handle count (`GetProcessHandleCount`),
   `threading.active_count()`.
2. `gc.collect()` (all generations).
3. **Post-GC sample**: the same fields, plus counts by type of `httpx.Client`,
   `httpx.AsyncClient`, `openai.AsyncOpenAI`, `openai.OpenAI`, `genai.Client`,
   `asyncio.AbstractEventLoop`, `socket.socket`, `threading.Thread` (`gc.get_objects()` filtered
   by `isinstance`, counted not stored).
4. Per-trial call counts at the SDK / httpx boundary (chat, embed, rerank, Census) so a
   per-call leak can be scaled to per-trial growth.

Arm **P** is those samples only. Arm **T** adds `tracemalloc` (1 frame) and records
`traced_current` after the collect, plus a snapshot diff between trial 10 and the last trial
(top 15 by size, file:line). Arms are separate processes, so tracing overhead cannot
perturb the P numbers.

## Workload

- **W1**: `scripts/run_demo.py`'s own question order and `_ask` path (the tree's own copy,
  loaded by path), **one repeat over all in-scope questions (62 trials)**. The incident was
  reaped at trial 44 of repeat 1, so W1 contains the point of failure. Real APIs, real keys.
- Same questions, same order, same repeat count, fresh process, in every run.
- Trees: **M** = `origin/main` 635449d; **C** = CC-121 branch `feat/cc-121-answer-figures`
  at f901c73 (committed state; its uncommitted evidence files are irrelevant to `api/src`);
  **B** = their merge-base 1160bde. C is 42 commits behind M and `api/src` differs between
  M and B in 6 files, so C against M mixes CC-121 with main's drift. B isolates it: **C
  against B is CC-121's effect; M against B is main's drift.** (Added before any run.)
- Run order interleaved `M, C, B, M, C, B, M, C, B` for arm P (3 complete attempts per
  tree), then one arm-T run per tree. A Census hang window or provider drift cannot line up with one tree.
- **Containment**: each run is detached from the harness, and a watchdog in the probe kills
  its own process above 9 GB private bytes. A kill is data (`killed at trial k, N GB`), not a
  failure to report.
- Sealed set: not used and not read. This experiment measures memory, not answer quality.

## Decision rules (fixed now)

Let `x_i` = post-GC private bytes after trial `i`. Warm-up = first 10 trials, excluded from
the slope. `slope` = OLS slope of `x_i` over trials 11 to 62, with a 95% confidence interval
(OLS standard error, t distribution).

| verdict | rule |
| --- | --- |
| **retained growth** | lower CI bound of slope > 5 MB per trial |
| **plateau** | upper CI bound of slope <= 5 MB per trial **and** max of `x_i` over the last 20 trials <= 1.15 x median of `x_i` over trials 11 to 30 |
| **inconclusive** | neither; the arm is extended to `--repeat 3` (186 trials) before a verdict |
| **reproduced (incident)** | peak private bytes in a run > 2 GB (the incident was about 5 GB at trial 44, roughly 100 MB per trial) |
| **high-water, not growth** | pre-GC peak is high but the plateau rule passes |

Attribution of a retained-growth run (arm T and arm P together; the growth magnitudes must
agree within a factor of 2, otherwise tracing perturbed it and the arm-T attribution is
reported as unreliable):

| owner | rule |
| --- | --- |
| **Python retention** | slope of `traced_current` >= 70% of the post-GC private slope |
| **native allocation** | slope of `traced_current` <= 30% of the post-GC private slope |
| **client / loop / handle growth** | slope of handle count > 0.5 per trial, or of any counted client / loop / thread type > 0.5 per trial |
| **mixed** | none of the above holds alone; reported with all three slopes |

## Hypotheses (one falsifiable statement each)

- **H-main**: the growth is on `origin/main`. *Confirmed* if >= 2 of 3 M runs show retained
  growth or reproduce the incident. *Rejected* if 0 of 3 M runs do while >= 2 of 3 C runs do.
  Otherwise inconclusive (both trees alike, or neither reproduces; see "not reproducible").
- **H-base**: the growth predates CC-121 and main's recent changes. *Confirmed* if >= 2 of 3 B
  runs show retained growth or reproduce the incident.
- **H-CC121**: CC-121 adds or enlarges it. *Confirmed* if the C post-GC slope exceeds the B
  slope and the two 95% CIs do not overlap. *Rejected* if the CIs overlap. (M is reported
  beside them; a C-over-M difference alone is not attributed to CC-121.)
- **H-lifecycle**: a named request-lifecycle path owns the growth. Decided by the leaf arms
  below: a path owns it if its per-call slope times its calls per trial (from arm P counters)
  is >= 50% of the W1 post-GC slope.

## Leaf arms (request-lifecycle paths named in AC5)

Each is a loop of 300 iterations (100 for the heavy loads) in a fresh process, no
`run_demo`, sampled every 10 iterations with the same post-GC sampler. The slope rule is the
one above, per iteration, in KB.

| arm | path | network |
| --- | --- | --- |
| L1 | `AsyncOpenAI()` constructed and dropped inside a fresh event loop per iteration (the `ask._openai_complete` shape) | none |
| L2 | `OpenAI()` and `genai.Client(...)` constructed and dropped (`embedding.py`, `rerank.py` shape) | none |
| L3 | one tiny Census request with `httpx.get` (`fetch.py` shape) | Census, same URL |
| L4 | availability map load as `/ask` does it | none |
| L5 | variable-label metadata load (`metadata.variables`; on tree C also `figures._labels`) | none |
| L6 | the app's cheapest route through `TestClient`: bare `TestClient(app)` (as `run_demo`), and `with TestClient(app)` (lifespan shutdown), 300 requests each | none |

## Instrument validity (run first, recorded)

Offline harness, 30 trials per run, no API keys. Each run injects a known per-trial
allocation; the classifier must name the owner and the plateau rule must fail, and the
controls must pass.

1. **Python retention**: append 20 MB of `bytearray` to a list per trial. Expected: retained
   growth, slope 20 MB +/- 20%, owner Python (arm T), plateau fails.
2. **Native allocation**: `ctypes` `malloc` of 20 MB per trial, never freed (invisible to
   `tracemalloc`). Expected: retained growth, owner native, plateau fails.
3. **Resource growth**: open and hold 20 sockets per trial. Expected: handle-count slope
   about 20 per trial, owner client / loop / handle, plateau fails.
4. **Negative control**: constant workload, no injection. Expected: plateau passes.
5. **High-water control**: allocate 500 MB at trial 5, free it at trial 8. Expected: plateau
   passes (pre-GC peak high, post-GC flat) and verdict "high-water, not growth".

Pass: all five classified as expected. If any fails, the probe is fixed and the five re-run
before any W1 run.

## Reporting

- Per run: peak private bytes, post-GC retained bytes at the last trial, slope with CI, the
  verdict, and the owner when retained. Every run is listed, none dropped; killed and
  incomplete runs are shown as such.
- If no run on either tree exceeds 2 GB or shows retained growth, the result is **not
  reproducible**, with the count of complete attempts (target >= 3 per tree, plus the
  arm-T runs) and the incident's own record as the only evidence.
- AC8 (two complete `--repeat 3` demos with a plateau) is checked only after a measured fix
  exists. No fix is made in this file's phase.

## Pre-flight facts (established before this file)

- The demo drives the app in-process with `fastapi.testclient.TestClient(app)` and one request
  at a time (`scripts/run_demo.py`, `main()`); a request does not overlap another.
- Per-call construction in `api/src`: `AsyncOpenAI()` in `ask.py:293`, `OpenAI()` in
  `retrieval/embedding.py:36` and `retrieval/rerank.py:82`, `genai.Client(...)` in
  `retrieval/rerank.py:67`; `httpx.get` (closes its client) in `fetch.py:112` and
  `geo_list.py:220`. The only module-level mutable cache found by search is
  `retrieval/index.py:44` (`_loaded`, keyed by store path, so bounded).
- `psutil` is not installed; the probe uses `ctypes`.
- CC-121's own label lookup was measured separately at about 340 MB peak for 36 parallel
  lookups settling near 136 MB (`evidence/slice-6/cc-121-plan.md`); it is not the 5 GB.
- Machine: Windows 11, 32 GB RAM, about 11 GB free when this file was written.
