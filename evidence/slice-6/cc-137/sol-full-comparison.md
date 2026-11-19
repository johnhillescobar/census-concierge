# CC-137 model accuracy and step latency

The fresh controlled run supplies the six-model comparison and the CC-138
test recommendation. [Controlled six-model results](model-comparison.md)

The experiment recorded 540/540 planned outcomes, with 539 completed continuations. Both Sol models used low, medium, and high reasoning on the same 90 frozen post-retrieval checkpoints.

In the new Responses run, the highest structural score was **61/90**, recorded by `gpt-6.2-sol` low, `gpt-6.1-sol` medium, and `gpt-6.1-sol` high. `gpt-6.1-sol` low had the lowest p95 in that run at **17.29 s**.

**CC-138 test selection is inconclusive.** The paired structural and latency results did not meet the predeclared selection rule.

## All models compared

| Model ID | Run | Reasoning | Structural passes | All three repeats | Required-cell passes | OpenAI HTTP mean | Census data / geography HTTP mean | Wall-time p95 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-4o-mini-2024-07-18` | V3 whole app | Provider default | 80/186 (43.0%) | 21/62 | — | — | — | 18.65 s |
| `gpt-4o-mini-2024-07-18` | V6 continuation | Provider default | 56/90 (62.2%) | 16/30 | 9/90 | 6.78 s | 0.93 / 0.69 s | 13.80 s |
| `gpt-5-mini-2025-08-07` | V3 whole app | Provider default | 107/186 (57.5%) | 31/62 | — | — | — | 70.63 s |
| `gpt-6-luna` | V3 whole app | None | 104/186 (55.9%) | 32/62 | — | — | — | 15.03 s |
| `gpt-6-sol` | V3 whole app | None | 111/186 (59.7%) | 34/62 | — | — | — | 11.06 s |
| `gpt-6-sol` | V6 continuation | None | 62/90 (68.9%) | 19/30 | 42/90 | 5.76 s | 0.88 / 0.61 s | 11.27 s |
| `gpt-6.1-sol` | Responses continuation | Low | 60/90 (66.7%) | 19/30 | 18/90 | 11.43 s | 0.69 / 0.48 s | 17.29 s |
| `gpt-6.1-sol` | Responses continuation | Medium | 61/90 (67.8%) | 19/30 | 22/90 | 13.06 s | 0.79 / 0.41 s | 21.73 s |
| `gpt-6.1-sol` | Responses continuation | High | 61/90 (67.8%) | 19/30 | 30/90 | 19.57 s | 0.83 / 0.76 s | 30.78 s |
| `gpt-6.2-sol` | Responses continuation | Low | 61/90 (67.8%) | 19/30 | 51/90 | 8.71 s | 0.93 / 0.61 s | 17.57 s |
| `gpt-6.2-sol` | Responses continuation | Medium | 59/90 (65.6%) | 18/30 | 52/90 | 11.56 s | 0.77 / 0.58 s | 23.27 s |
| `gpt-6.2-sol` | Responses continuation | High | 60/90 (66.7%) | 18/30 | 50/90 | 17.09 s | 0.77 / 0.50 s | 38.63 s |

V3 p95 covers the whole application, including live retrieval. V6 and
Responses p95 cover the continuation after frozen retrieval. Those two runs
share the same 90 checkpoints and differ in API, reasoning, and concurrency.
A dash marks unavailable or differently scoped evidence. See the earlier
run notes for source hashes and the V3 cohort.

## Responses accuracy

The V6 score checks the expected table, requested geography level where specified, Census URL, and returned rows. The full structural contract also requires margins of error, GEOIDs, universe, and alternatives. The expected table was already admitted in 82/90 shared checkpoints.

Every structural pass in the Responses run also passed the full structural contract.

| Model and effort | Correct table | Required cells | Required MOE cells | Factual geography | Expected period | All necessary checks | Values checked / mismatched |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-6.1-sol` low | 69 | 18 | 18 | 53 | 66 | 3 | 40 / 0 |
| `gpt-6.2-sol` low | 69 | 51 | 51 | 50 | 65 | 25 | 3374 / 0 |
| `gpt-6.1-sol` medium | 69 | 22 | 22 | 54 | 65 | 9 | 636 / 0 |
| `gpt-6.2-sol` medium | 67 | 52 | 52 | 50 | 66 | 25 | 3216 / 0 |
| `gpt-6.1-sol` high | 69 | 30 | 30 | 52 | 65 | 12 | 1456 / 0 |
| `gpt-6.2-sol` high | 68 | 50 | 50 | 49 | 63 | 25 | 3356 / 0 |

Factual columns count PASS over 90 planned trials per arm. Required cells reflect the annotated Census method. Values were compared where the executed URL, geography, and vintage match an independent frozen public snapshot. Unchecked cells, prose claims, and calculations remain unknown.

### Paired factual differences

| GPT-6.2 Sol minus GPT-6.1 Sol | Required cells difference (95% interval) | All necessary checks difference (95% interval) |
| --- | ---: | ---: |
| low | +36.67 pp [+21.11, +52.22] | +24.44 pp [+12.22, +38.89] |
| medium | +33.33 pp [+20.00, +46.67] | +17.78 pp [+7.78, +28.89] |
| high | +22.22 pp [+10.00, +34.44] | +14.44 pp [+5.56, +24.44] |

These secondary contrasts compare the share of planned trials passing each check. The intervals retain all three repeats within each paired family.

### Paired differences

| Comparison minus reference | Structural difference | 95% interval |
| --- | ---: | ---: |
| `gpt-6.2-sol` low minus `gpt-6.1-sol` low | +1.11 pp | [+0.00, +3.33] pp |
| `gpt-6.1-sol` medium minus `gpt-6.1-sol` low | +1.11 pp | [+0.00, +3.33] pp |
| `gpt-6.1-sol` high minus `gpt-6.1-sol` low | +1.11 pp | [+0.00, +3.33] pp |
| `gpt-6.2-sol` medium minus `gpt-6.2-sol` low | -2.22 pp | [-6.67, +0.00] pp |
| `gpt-6.2-sol` high minus `gpt-6.2-sol` low | -1.11 pp | [-3.33, +0.00] pp |
| `gpt-6.2-sol` medium minus `gpt-6.1-sol` medium | -2.22 pp | [-6.67, +0.00] pp |
| `gpt-6.2-sol` high minus `gpt-6.1-sol` high | -1.11 pp | [-3.33, +0.00] pp |

Intervals resample the 30 paired question families, keeping three repeats together. The comparisons are exploratory and intervals are unadjusted for multiple contrasts.

## Continuation latency by step

Times are seconds. Component columns are disjoint means per measured continuation, with zero contribution when a step was unused. Their sum matches mean wall time before rounding. HTTP time includes client-observed provider and transport time.

| Model and effort | OpenAI HTTP | OpenAI SDK local | Census data HTTP | Census geography / metadata HTTP | Census tool local | Frozen search replay | Other local | Total mean | Total p50 | Total p95 | Passing p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-6.1-sol` low | 11.43 | 0.05 | 0.69 | 0.48 | 0.73 | 0.01 | 0.18 | 13.58 | 13.68 | 17.29 | 17.20 |
| `gpt-6.2-sol` low | 8.71 | 0.05 | 0.93 | 0.61 | 0.85 | 0.00 | 0.17 | 11.32 | 10.65 | 17.57 | 17.79 |
| `gpt-6.1-sol` medium | 13.06 | 0.05 | 0.79 | 0.41 | 0.73 | 0.00 | 0.18 | 15.22 | 14.89 | 21.73 | 21.76 |
| `gpt-6.2-sol` medium | 11.56 | 0.04 | 0.77 | 0.58 | 0.82 | 0.00 | 0.18 | 13.95 | 12.44 | 23.27 | 19.95 |
| `gpt-6.1-sol` high | 19.57 | 0.04 | 0.83 | 0.76 | 0.87 | 0.00 | 0.19 | 22.26 | 21.39 | 30.78 | 30.25 |
| `gpt-6.2-sol` high | 17.09 | 0.04 | 0.77 | 0.50 | 0.87 | 0.00 | 0.19 | 19.45 | 15.76 | 38.63 | 29.43 |

### Per HTTP request

| Model and effort | OpenAI n / p50 / p95 | Census data n / p50 / p95 | Census geography and metadata n / p50 / p95 |
| --- | ---: | ---: | ---: |
| `gpt-6.1-sol` low | 398 / 2.26 / 4.63 | 109 / 0.49 / 0.87 | 88 / 0.45 / 0.86 |
| `gpt-6.2-sol` low | 385 / 1.70 / 3.70 | 132 / 0.53 / 2.06 | 87 / 0.46 / 3.24 |
| `gpt-6.1-sol` medium | 411 / 2.44 / 5.93 | 114 / 0.53 / 2.86 | 85 / 0.44 / 0.79 |
| `gpt-6.2-sol` medium | 399 / 1.92 / 5.49 | 141 / 0.48 / 1.84 | 87 / 0.47 / 1.14 |
| `gpt-6.1-sol` high | 430 / 2.93 / 10.19 | 130 / 0.50 / 0.89 | 94 / 0.48 / 2.24 |
| `gpt-6.2-sol` high | 401 / 2.38 / 11.81 | 135 / 0.49 / 0.89 | 87 / 0.47 / 0.88 |

Continuation timings include live Census calls and application work under up to 12 concurrent checkpoints. They describe observed latency in this run. Calls within a checkpoint ran sequentially. Percentiles use linear interpolation. Per-step percentiles cannot be added.

### Shared upstream retrieval

| Historical V6 step | Mean | p50 | p95 |
| --- | ---: | ---: | ---: |
| OpenAI retrieval controller HTTP | 1.37 | 1.29 | 1.79 |
| Auxiliary intent | 0.35 | 0.34 | 0.81 |
| Semantic embedding | 0.37 | 0.34 | 0.65 |
| Local semantic search | 0.00 | 0.00 | 0.00 |
| Gemini selector | 3.67 | 2.79 | 9.02 |
| Census HTTP | 0.00 | 0.00 | 0.00 |
| Other preparation work | 0.08 | 0.07 | 0.08 |
| Total preparation | 5.83 | 4.86 | 11.24 |

These 90 historical preparation measurements are shared by every arm. No new embedding or Gemini requests occurred during the candidate continuations.

## Cost and coverage

| Model and effort | Measured input tokens | Output tokens | Reasoning tokens | Estimated cost | Attempt outcomes |
| --- | ---: | ---: | ---: | ---: | --- |
| `gpt-6.1-sol` low | 721,369 | 21,561 | 3,872 | $2.0190 | 90 completed |
| `gpt-6.2-sol` low | 711,340 | 22,558 | 2,286 | $2.0039 | 90 completed |
| `gpt-6.1-sol` medium | 760,225 | 28,996 | 9,841 | $2.1905 | 90 completed |
| `gpt-6.2-sol` medium | 769,884 | 35,877 | 13,415 | $2.2835 | 90 completed |
| `gpt-6.1-sol` high | 849,827 | 60,425 | 40,159 | $2.7288 | 90 completed |
| `gpt-6.2-sol` high | 830,822 | 66,422 | 43,208 | $2.8701 | 89 completed, 1 failed |

Incremental conservative OpenAI accounting was **$14.0959**, under the $15 stop. Input was charged at 125% of the uncached Standard rate for the estimate. Unknown usage retains the request reservation. Failed and unrun outcomes remain in their planned denominators.

Recorded execution failures and stops were `gpt-6.2-sol` high · APIConnectionError (1).

## Earlier model versions tested

### V6 post-retrieval comparison

These two models ran on the same 90 frozen checkpoints as the later
Responses experiment. V6 ran sequentially through Chat Completions, with
reasoning `none` for GPT-6 Sol and provider defaults for GPT-4o mini.
The observed scores and timings describe those V6 configurations. The
later results use Responses, different reasoning settings, and up to 12
concurrent checkpoints.

V6 source is `evidence/slice-6/cc-137/v6-analysis.json`, SHA-256
`2d76d31e5f5feafdd1108392d4e423cd5531a6b768ceebaeacfd5fd16d378e6`.
Required-cell counts come from `evidence/slice-6/cc-137/factual-audit.json`,
SHA-256 `c476430932d7f0913a2adac4bcc70f3f397eb1595c48d926916796359cff575a`.
The V6 audit and the Responses run used the same required-cell oracle and
scorer.
[V6 results in CC-137](https://johnhillescobar.atlassian.net/browse/CC-137?focusedCommentId=10881)

### V3 whole-application comparison

V3 tested four models through Chat Completions, with reasoning `none` for
the GPT-6 versions and provider defaults for the other versions. Each arm
had 186 regression trials, including 120 long-tail trials. The model ran
the full workflow including retrieval. The cohort and measured latency
scope differ from the later post-retrieval runs.

On the 120 long-tail trials per model, structural passes were 48 for
GPT-4o mini, 65 for GPT-5 mini, 64 for GPT-6 Luna, and 67 for GPT-6 Sol.

V3 source is `cc137_run_v3/learnings-aggregate.json` in the owner's Ad-hoc
folder, SHA-256 `1063fe91c2bad90f9d88588f29080a03ccf0bd827ca635a9b9ab00427baec57a`.
The three runs support comparisons within their respective protocols.

## Reproduction

The run used POST `/v1/responses` with Standard service, 4,096 maximum output tokens, low/medium/high effort, `store=false`, non-strict parallel function calls, 60-second per-call timeout, and zero SDK retries. Each of 30 visible question families has three checkpoints. Arm order rotates on each checkpoint. V6 Chat Completions is historical context for an earlier configuration.

The registration, per-trial evidence, raw traces, and request ledger are retained in the owner's Ad-hoc folder under `20261115_census_questions/cc137_sol_full_20261119`. Public source pins, paired diagnostics, and detailed latency distributions are in [the machine summary](sol-full-summary.json). [Per-trial grades and step timings](sol-full-trials.csv) are also available.

| Artifact | Commit or SHA-256 |
| --- | --- |
| Pinned app source | `f6fa608827acb117f016d404d1ea72aa1d422af7` |
| V6 preparation manifest | `2c43395de46b14ee43ae5e3888f1d7a661135e42c8b7ad2a5ea4996e15499799` |
| V6 continuation manifest | `ca62df77107e20569ffa4c39950c4a5ce4f4f6ea0548a56c40edac1195b8684f` |
| Full experiment manifest | `401d142973cbe7b43ffee4fe03817ac94979cd0371e8a1c06c378d375a9a637f` |
| Trial journal | `00cd8c7a84d3544d4c3cca3ad1daaadbbe9cf216791b92636875ce6df8853782` |
| Request ledger | `bfa009a7977b3daea05b5a8e047443347dd91d3d2e8b6014ec9d4480b30084d4` |
| Temporary runner | `735d19753d99c9faeb974520c70ee70ed11abfc3ef47ecaa3bd98cb17af6ccef` |
| Offline analysis | `2f34916a31478ec9dc0506bb76cd66a65144b4b4606ebfdc8b70fb0182a88441` |

[CC-137](https://johnhillescobar.atlassian.net/browse/CC-137) · [CC-138](https://johnhillescobar.atlassian.net/browse/CC-138)
