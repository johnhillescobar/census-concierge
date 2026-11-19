# CC-137 controlled six-model comparison

The run recorded 540/540 planned trials, including 540 completed continuations. All six models used the same 90 frozen post-retrieval checkpoints in one experiment.

**Recommend `gpt-6.2-sol` for the CC-138 integration trial.** The tested configuration used POST `/v1/responses`, `low` reasoning, and a 4,096-token output ceiling. It verified the required facts on **24/63 (38.1%)** and had a continuation p95 of **15.19 s**.

## All models compared

Accuracy measures verified required facts and the existing structural grade. The three HTTP columns show means across continuations, in seconds. The same continuation wall-time measurement supplies every p95.

| Model ID | Reasoning | Verified facts | Structural passes | OpenAI HTTP | Census data HTTP | Census geography HTTP | Continuation p95 | Estimated cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-4o-mini-2024-07-18` | native | 3/63 (4.8%) | 53/90 | 5.26 | 0.62 | 0.59 | 12.72 | $0.129 |
| `gpt-5-mini-2025-08-07` | low | 6/63 (9.5%) | 60/90 | 16.70 | 0.59 | 0.44 | 27.45 | $0.399 |
| `gpt-6-luna` | low | 5/63 (7.9%) | 63/90 | 7.10 | 0.57 | 0.42 | 14.90 | $0.101 |
| `gpt-6-sol` | low | 13/63 (20.6%) | 62/90 | 6.51 | 0.53 | 0.40 | 11.18 | $2.088 |
| `gpt-6.1-sol` | low | 5/63 (7.9%) | 62/90 | 11.05 | 0.61 | 0.43 | 17.09 | $1.982 |
| `gpt-6.2-sol` | low | 24/63 (38.1%) | 61/90 | 9.08 | 0.71 | 0.41 | 15.19 | $1.940 |

Verified-fact accuracy covers 63 trials per arm from 21 question families with exact or statewide county scope. A pass requires the correct Census entities, period, dataset, universe, requested estimates, margins of error, and values. The grader checks 1,030 independent official values keyed by geography and variable in the expected period and dataset.

The structural score covers all 90 trials per arm, including nine additional families whose intended scope requires interpretation. It checks the expected table and geography level where specified, URL, and rows. Prose claims and derived calculations remain unverified.

### Paired accuracy and the decision

`gpt-6.2-sol` led observed verified-fact accuracy at 24/63 (38.1%). Each interval resamples the same 21 families with all three repeats together. The point estimate and intervals below give the candidate's percentage-point difference from that accuracy leader. Intervals are exploratory and unadjusted.

| Candidate versus accuracy leader | Accuracy difference | Paired 95% interval |
| --- | ---: | ---: |
| `gpt-4o-mini-2024-07-18` | -33.33 pp | [-50.79, -17.46] pp |
| `gpt-5-mini-2025-08-07` | -28.57 pp | [-44.44, -14.29] pp |
| `gpt-6-luna` | -30.16 pp | [-47.62, -14.29] pp |
| `gpt-6-sol` | -17.46 pp | [-33.37, -1.59] pp |
| `gpt-6.1-sol` | -30.16 pp | [-49.21, -12.70] pp |

Compared with GPT-6 Sol, the next-highest arm on verified facts, GPT-6.2 Sol
passed 11 more trials. The gain was 17.46 percentage points (paired 95%
interval 1.59 to 33.37). Its continuation p95 was 4.01 seconds higher
(15.19 versus 11.18 seconds).

The frozen rule retains the observed leader and allows a faster candidate when the lower confidence bound is at least −2 percentage points. It then uses continuation p95 and estimated cost to choose among eligible arms. The eligible arms were `gpt-6.2-sol`.

## Latency by step

Columns through other local time are disjoint means in seconds. Their sum matches the continuation mean before rounding. HTTP spans include elapsed provider and network time. Shared retrieval ran before these checkpoints were frozen.

| Model ID | OpenAI HTTP | SDK local | Census data HTTP | Census geography HTTP | Census tool local | Search replay | Other local | Mean | p50 | p95 | Structural-pass p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-4o-mini-2024-07-18` | 5.26 | 0.05 | 0.62 | 0.59 | 0.97 | 0.00 | 0.16 | 7.64 | 7.02 | 12.72 | 11.79 |
| `gpt-5-mini-2025-08-07` | 16.70 | 0.05 | 0.59 | 0.44 | 0.91 | 0.00 | 0.17 | 18.85 | 17.99 | 27.45 | 26.96 |
| `gpt-6-luna` | 7.10 | 0.04 | 0.57 | 0.42 | 0.86 | 0.00 | 0.17 | 9.16 | 8.45 | 14.90 | 12.21 |
| `gpt-6-sol` | 6.51 | 0.04 | 0.53 | 0.40 | 0.85 | 0.00 | 0.17 | 8.51 | 8.28 | 11.18 | 10.94 |
| `gpt-6.1-sol` | 11.05 | 0.04 | 0.61 | 0.43 | 0.83 | 0.01 | 0.16 | 13.12 | 12.74 | 17.09 | 16.91 |
| `gpt-6.2-sol` | 9.08 | 0.03 | 0.71 | 0.41 | 0.90 | 0.00 | 0.15 | 11.29 | 11.04 | 15.19 | 14.55 |

### HTTP requests

| Model ID | OpenAI n / p50 / p95 | Census data n / p50 / p95 | Census geography n / p50 / p95 |
| --- | ---: | ---: | ---: |
| `gpt-4o-mini-2024-07-18` | 362 / 1.13 / 2.37 | 142 / 0.45 / 0.93 | 148 / 0.47 / 1.00 |
| `gpt-5-mini-2025-08-07` | 362 / 2.90 / 10.69 | 115 / 0.46 / 0.92 | 88 / 0.44 / 0.89 |
| `gpt-6-luna` | 383 / 1.44 / 3.29 | 100 / 0.45 / 0.87 | 79 / 0.45 / 0.82 |
| `gpt-6-sol` | 398 / 1.36 / 2.51 | 107 / 0.44 / 0.76 | 81 / 0.45 / 0.88 |
| `gpt-6.1-sol` | 392 / 2.24 / 4.49 | 109 / 0.46 / 0.91 | 85 / 0.45 / 0.76 |
| `gpt-6.2-sol` | 374 / 1.76 / 4.17 | 126 / 0.45 / 0.84 | 81 / 0.45 / 0.70 |

The shared retrieval preparation averaged 5.83 s, including 3.67 s for the Gemini selector. The same historical preparation applies to every arm. The table measures live continuation latency with up to 12 concurrent checkpoints. Component percentiles cannot be added.

## Spend and execution coverage

Conservative incremental OpenAI spend was **$6.6393** under the $12.00 stop. Input spend is estimated at 125% of uncached Standard rates. Calls with missing usage keep the request reservation.

| Model ID | Recorded outcomes | Input tokens | Output tokens | Reasoning tokens |
| --- | ---: | ---: | ---: | ---: |
| `gpt-4o-mini-2024-07-18` | 90 completed | 639,814 | 14,726 | 0 |
| `gpt-5-mini-2025-08-07` | 90 completed | 723,899 | 86,389 | 46,848 |
| `gpt-6-luna` | 90 completed | 699,506 | 26,780 | 9,160 |
| `gpt-6-sol` | 90 completed | 734,591 | 25,136 | 7,727 |
| `gpt-6.1-sol` | 90 completed | 708,566 | 21,096 | 3,860 |
| `gpt-6.2-sol` | 90 completed | 689,884 | 21,574 | 1,954 |

## Protocol and evidence

Each model saw the same frozen messages, retrieved evidence, auxiliary intent, tool schemas, and remaining turn and tool budgets. Every arm used POST `/v1/responses`, Standard service, 4,096 maximum output tokens, non-strict parallel function calls, `store=false`, a 60-second model timeout, and zero SDK retries. The five reasoning models used low effort. GPT-4o mini used its native generation mode.

The 90 checkpoint blocks cover 30 question families with three repeats each. The order was balanced so each model appeared 15 times at each position and each ordered pair was adjacent 15 times. The same live Census client and timing instrumentation handled every arm.

Raw artifacts and the frozen ad-hoc runner are retained in `20261115_census_questions/cc137_common_responses_20261119`. The portable files include grade and timing data for every trial. [Machine summary](model-comparison-summary.json) · [Per-trial results](model-comparison-trials.csv)

| Artifact | Commit or SHA-256 |
| --- | ---: |
| Pinned app source | `f6fa608827acb117f016d404d1ea72aa1d422af7` |
| Frozen retrieval continuation inputs | `ca62df77107e20569ffa4c39950c4a5ce4f4f6ea0548a56c40edac1195b8684f` |
| Run manifest | `84905dfe3c861b936b201fdcb086617b675015529b729e0fc93205ea2332ac2b` |
| Trial journal | `dadba4275c51d3cff51c826e673810cc2ea3ce4697528256536bc08dafda2893` |
| Request ledger | `0ccb1fbfeb6abafd8b5a0ebed51d987ccc25fb1b202dc9eae88a84488b00ed5d` |
| Six-model runner | `9be95c0ba0e9494688057d65b6d456e331a98767c161c014918e61dbf5e939f0` |

[CC-137](https://johnhillescobar.atlassian.net/browse/CC-137) · [CC-138](https://johnhillescobar.atlassian.net/browse/CC-138) · [Earlier experiments](sol-full-comparison.md)
