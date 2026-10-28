# CC-123 memory experiment results

Design: `memory-experiment-design.md` (committed before any run). Raw data, logs and every
incident: `evidence/slice-6/memory/` (`incidents.md`). Probe: `scripts/memory_probe.py`.
Jira: CC-123, epic CC-3. No `api/src` change, no budget change, no new dependency, sealed set not read.

## Verdict

**The ~5 GB growth did not reproduce.** In 7 complete full-workload runs (62 questions each,
real APIs, fresh process) on three source trees, peak private memory was 582 to 642 MB and
settled near 580 to 600 MB. The incident's rate (about 100 MB per question) is more than 150
times what any run showed. AC6 outcome: **not reproducible after 7 complete attempts** (target
was 3 per tree; M 3, C 2, B 2, plus one partial, see "Attempts").

One small, real, repeatable growth was found and attributed: **one asyncio event loop is left
alive per `/ask` request in the demo, because `scripts/run_demo.py` uses `TestClient(app)`
without `with`.** It is a demo-harness artifact (`scripts/`), not `api/src`, and it costs about
0.2 to 0.6 MB per question. It does not explain the 5 GB.

## Per-run results (arm P: private bytes after `gc.collect()`)

Slope = OLS slope over trials 11 to 62, 95% CI. Retained-growth bar: CI lower bound > 5 MB per trial.

| run | tree | n | peak private MB | last post-GC MB | slope MB/trial (95% CI) | verdict | resource |
| --- | --- | --- | --- | --- | --- | --- | --- |
| w1-M-P-r1 | main 635449d | 62 | 641.5 | 585.0 | 0.641 (0.531 to 0.751) | resource growth | asyncio.loop |
| w1-M-P-r2 | main | 62 | 590.5 | 580.3 | 0.210 (0.137 to 0.284) | resource growth | asyncio.loop |
| w1-M-P-r3 | main | 62 | 583.9 | 579.2 | 0.290 (0.253 to 0.327) | resource growth | asyncio.loop |
| w1-C-P-r1 | CC-121 f901c73 | 62 | 600.0 | 583.5 | 0.405 (0.355 to 0.455) | resource growth | asyncio.loop |
| w1-C-P-r2 | CC-121 | 62 | 618.8 | 604.4 | 0.324 (0.178 to 0.470) | resource growth | asyncio.loop |
| w1-C-P-r3 | CC-121 | 44 of 62 | 615 | 609.6 | partial, not analysed | killed by host (incident 3) | asyncio.loop 44 |
| w1-B-P-r1 | merge-base 1160bde | 62 | 583.9 | 581.7 | 0.326 (0.283 to 0.368) | resource growth | asyncio.loop |
| w1-B-P-r2 | merge-base | 62 | 582.2 | 579.3 | 0.286 (0.238 to 0.334) | resource growth | asyncio.loop |

"Resource growth" in every row is the same single signal: live `asyncio` loop count rises by 1
per question and survives GC. Handles (~396 to 406) and threads (2) are flat; no client, socket
or OpenAI/genai object accumulates. No run is "retained growth" and none is near 2 GB.

## Hypotheses

- **H-main** (growth is on `origin/main`): **not confirmed.** 0 of 3 M runs show retained growth
  or reproduce; 0 of 2 complete C runs either, so the "rejected" branch is not met either.
  Result: not reproducible on either tree.
- **H-base** (growth predates CC-121 and main's drift): **not confirmed.** 0 of 2 B runs.
- **H-CC121** (CC-121 adds or enlarges it): **rejected.** C slope CIs (0.355 to 0.455;
  0.178 to 0.470) overlap B's (0.283 to 0.368; 0.238 to 0.334). M, C and B all show the loop
  signal. M run 1 is the highest slope (0.64) and C is not above B.
- **H-lifecycle** (a named path owns the growth): see leaf arms. Only the event-loop path is
  attributed; the memory-slope ownership rule (>= 50% of the W1 slope) could not be applied to the
  metadata paths (below).

## Leaf arms (AC5)

Slopes in the report script are labelled "MB/trial" but for leaf arms are **per sample = per 10
iterations**; the table converts to KB per iteration. "No growth" = CI wholly below 20 KB per iteration (design).

| arm | path | iterations | KB per iteration (CI) | live loops | reading |
| --- | --- | --- | --- | --- | --- |
| L1 | `AsyncOpenAI()` built and dropped per call | 300 | 0 (0 to 0) | 0 | no growth |
| L2 | `OpenAI()`, `genai.Client()` per call | 300 | -0.2 (-0.6 to 0.2) | 0 | no growth |
| L3 | Census `httpx.get` | 200 | flat (69 to 72 MB) | 0 | no growth (curve; 20 samples, not classified by the window rule) |
| L4 | `availability.load()` | 300 | 57.5 (48.2 to 66.7) | 0 | **grows, linearly, 68 to 94 MB over 300 calls** |
| L5 | `metadata.variables("acs5", 2023)` | 300 | 54.9 (48.1 to 61.7) | 0 | **grows, linearly, 68 to 85 MB over 300 calls** |
| L5c | `figures._labels` (tree C) | 300 | 6.8 (2.2 to 11.4) | 0 | no growth (rose 68 to 80 MB then flat) |
| L6a | bare `TestClient(app)`, 300 requests | 300 | 9.4 (7.1 to 11.7) | **300** | **one loop left alive per request** |
| L6b | `with TestClient(app)`, 300 requests | 300 | 0 (0 to 0) | 1 | no growth |

- **Event loop (proven).** Bare `TestClient` leaves one loop per request (300 loops after 300
  requests, handles and threads flat). Used as a context manager the loop count is constant at 1
  and memory flat. `run_demo.py:513` is the bare form.
- **`availability.load()` and `metadata.variables()` (open).** Both decompress and parse a file
  on every call (`availability.py:80`, `metadata.py:87`), and `ask.py:319` and `vintages.py:237`
  call `availability.load()`. Repeated calls keep raising post-GC private bytes by about 55 KB
  per call with no plateau in 300 calls. Not attributed: arm T (tracemalloc) did not run, so
  Python retention versus allocator fragmentation is unknown, and the number of loads per question
  in W1 was not recorded, so the ownership rule cannot be evaluated. At one load per question this
  would be about 0.06 MB per question, 10 to 25% of the 0.2 to 0.64 MB W1 slope, below the 50% bar.
  W1 shows memory settling near 580 to 600 MB, which an unbounded 55 KB per call would not
  produce at that call count, so it is more likely warm-up than a leak. This is an inference.

## What is not established

- **Why the original run reached ~5 GB.** Nothing here reproduces it. Candidates the probe
  cannot see: the eval steps that ran in the same shell session before the demo, a different
  question mix, or another process mistaken for the demo. Incident 3 adds one data point:
  when the host reaped our driver for low memory, our process held only 610 MB, so the machine
  was short of memory for a reason not measured here.
- **Arm T (tracemalloc) was not run**, so Python-heap versus native ownership is not measured.
  It would only matter if a retained growth were found; none was.
- **Fewer attempts than the plan.** M 3, C 2, B 2 complete (plan: 3 each), one partial.

## Consequences (no fix in this phase)

- AC7: nothing to fix for the 5 GB. The only attributed cause (bare `TestClient`) is in the demo
  harness; `with TestClient(app)` is a one-line change in `scripts/run_demo.py` that removes the
  loop leak (L6b). It is not made here, since it would not change the E2E behavior and the owner
  has not asked for it.
- AC8 (two complete `--repeat 3` runs with a plateau) is not evaluated: no fix exists. The 62-trial
  evidence is a plateau near 580 to 600 MB, but `--repeat 3` (186 trials) was not run.
- AC9: not applicable, no behavior changed.
- AC10: no new behavioral test (script only); `make check` was not changed by this work.

## Reproduce

```
uv run python scripts/memory_probe.py validity            # 5 injection cases, all pass
uv run python evidence/slice-6/memory/run_all.py          # full sequence, resumable
uv run python scripts/memory_probe.py report evidence/slice-6/memory/*.jsonl
```

Commits on `feat/cc-123-demo-memory`: design 7a1a0e1, 4390c2b; probe and validity a80db3a;
driver 0153202; raw runs 31dd867; this file in the commit after.
