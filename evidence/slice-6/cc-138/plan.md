# CC-138 model integration

Base `27d4d4711f577cf91bb78890b1dd32ff82c766ed` (`origin/main`). The owner approved implementation and use of the application's existing OpenAI credential. The tested configuration comes from the [CC-137 handoff](https://johnhillescobar.atlassian.net/browse/CC-138?focusedCommentId=10909).

This batch covers repository changes for the Responses transport, regression tests, architecture and rollback notes, and gate evidence. Implementation is on `cc-138/responses-integration`. The baseline checkout stays at the pinned `origin/main` revision. The owner merges after review. The application trial uses the existing Census, retrieval and scoring paths.

| ID | Expected outcome | Verification | Status |
| --- | --- | --- | --- |
| AC1 | `/ask` uses `gpt-6.2-sol` on `POST /v1/responses` with low reasoning, 4,096 output tokens, Standard tier, `store=false`, parallel non-strict calls, 60-second timeout and no SDK retries | SDK and live protocol pre-flight, request-level integration regression, separate live smoke check | Protocol and request-level checks passed. The live `POST /ask` smoke completed six calls that resolved as `gpt-6.2-sol`. |
| TC1 | Stateless continuation retains output items in order, including any reasoning items the provider returns and the IDs that associate tool calls with tool results | SDK wire regression through the normal loop and a targeted mutation | Tests and mutations passed. The live protocol probe confirmed encrypted reasoning replay. |
| TC2 | Existing API contract, deterministic tool guards, and bounded failure and repair continue to apply | Existing contract suite, client drift check and integration tests against malformed output, incomplete responses and provider errors | Base suite passed: 131 passed, 8 expected failures. Final offline and targeted mutation checks passed on `3c6e136`. |
| TC3 | Reverting the integration restores the prior `gpt-4o-mini` Chat Completions path with its previous request and client defaults | Compare the reverted code tree against the pinned base and document rollback | Final Gate 1 inverse-tree check passed on `3c6e136`. |
| TC4 | The diagnostic collector can still override the answer model without sending Sol's reasoning option to that model | Request-level override regression and targeted mutation | Test and mutation passed. |
| AC2 | Baseline and integration use the same repeat-3 scorer and cohorts, meet applicable quality and latency checks, and are reviewed in fresh contexts | Baseline demo, Gate 1 and targeted mutations, cold Gate 2, repeat-3 eval/demo before and after owner merge, and authorized sealed aggregates at closure | The candidate passed the answered-rate floor at 0.775. The owner accepted the measured p95 and assigned latency follow-up to CC-3. The row-GEOID and non-latency regression checks remain red. |
| AC3 | Integrated revision, validation outcomes and rollback are recorded | Evidence linked at the integration head, then refreshed for merged `main` | Local integration evidence and rollback are recorded. Full live validation and post-merge evidence are pending. |

The base is at the API line ceiling of 4,890 and the prescriptive documentation ceiling of 1,820 lines. The integration replaces the prior transport and its Chat Completions history formatting within the existing budget. Retrieval, scoring, unrelated infrastructure, structured intent, and final grading retain their ticket ownership.

The integration replays the SDK's full output items with `store=false`, matching the six-model experiment's request and continuation protocol. A second live probe received an encrypted reasoning item without an explicit `include` option and replayed it with a function result successfully. The figure collector's existing model override still selects the model on the shared application transport. Comparing a prior Chat Completions run against a Responses run requires accounting for the API change.

## Baseline evidence

The prior repeat-3 [CC-133 post-merge scoreboard](../cc-133/e2e-post/latest-after-demo.json) measured 0.675 long-tail answered and 24.001 seconds p95. The application, scorer, cohort, protocol and dependency files match `27d4d47` byte-for-byte. Its prompt hash is `79910a5885fc`, and its index hash is `377cd59fe62a`.

The [repeat-3 baseline](baseline.md) finished all 186 planned trials at `27d4d47`, with 70.0% long-tail answered and 25.960 seconds full-suite p95. On 2026-11-19 the owner accepted the expected inherited latency for this run so work could return to CC-3. Commit `ca50ca7` on `cc-138/baseline-p95-waiver` records the exact UTC run ID and p95. The budget checker passed against the captured baseline with one waiver. An embedding request stalled and resumed during the run. Its diagnostic details are in the baseline evidence.

## Integration revision and rollback

The initial integration is `9b11140865b3bd8210f6fc2a92af15c624b36ad1`. The review fixes are `57ac1f4`, `0ebfb31` and final code head `3c6e136ac65a88a2f73c7fd01ce3e94f61150349`. Roll back with `git revert 3c6e136 0ebfb31 57ac1f4 9b11140`. This restores the prior Chat Completions transport, the original `gpt-4o-mini` alias, and the SDK's previous timeout and retry defaults. If the changes are squash-merged, revert the corresponding squash commit.

Gate 1 verified the entire inverse diff reproduces the pinned base tree. Five new test cases rejected all 16 single-behavior mutations. The offline suite reported 1,402 Python and 110 web tests passed. Types, lint, structural budgets, invariants and generated-client drift checks passed. The full budget command reported 0.683 against the 0.700 floor on the committed historical scoreboard. This measurement is inherited from the base. Its 25.472-second p95 carries an earlier run-specific owner waiver.

The initial cold code review caught default execution after malformed arguments, provider errors bypassing result assembly, and unmarked incomplete responses. The fixes reject invalid payloads before tool execution, including a null field accepted by the SDK's decoder. Tool failures retain the original call ID, and the existing answer assembly path carries an explicit model failure message. The SDK still makes a single attempt per model call.

Gate 1 on `0ebfb31` reproduced the base tree with an inverse patch, ran 1,404 offline Python tests and 90 focused tests successfully, and rejected the additional null-field mutation. The 110 passing web tests were carried forward after verifying input parity. The inherited 0.683 answered rate still prevents the full budget check from passing.

The [repeat cold review](gate2-final.txt) identified that a wire-null argument was omitted from the replay item. Commit `3c6e136` supplies a valid JSON argument field in the replay and retains the tool's validation error and call ID. It keeps the malformed request from executing.

[Gate 1 on the final code head](gate1-replay.txt) confirmed 90 focused tests and 1,404 offline Python tests passed. All three malformed replay cases failed when the final behavior was removed and passed after restoration. The inverse patch reproduced the exact base tree. Invariants and structural budgets passed. Earlier evidence includes [the original mutations](gate1.txt), [initial cold review](gate2.txt), [the first repair mutations](gate1-fixes.txt), and [null-argument coverage](gate1-final.txt).

## Live smoke check

A one-question live `POST /ask` check on `3c6e136` returned HTTP 200, one B01003 row with its margin of error, the expected county GEOID, and the correct Census URL scope for the 2023 ACS five-year release. All six completed model calls resolved as `gpt-6.2-sol`. The optional Postgres pool was unavailable at startup under the Windows test client's event loop. The standalone route completed successfully. Its elapsed time includes startup and is excluded from the benchmark.

## Readiness

Gate 2's initial mechanical budget prerequisite stopped on the checked-in historical answered rate of 0.683 against the 0.700 floor. The subsequent candidate passed that floor. The [dedicated waiver branch](https://github.com/johnhillescobar/census-concierge/tree/cc-138/baseline-p95-waiver) carries the owner-approved p95 waivers separately from the code.

Pre-PR live validation on the [integration branch](https://github.com/johnhillescobar/census-concierge/tree/cc-138/responses-integration) at `653a5ab659358b3adb38028870e8a5d0ae97874a` ran from 02:08:52 to 03:18:20 UTC on 2026-11-20. [Command exits](e2e-pre-commands.txt) record all seven Makefile recipe commands. The [closure manifest](../../closure/CC-138.toml) records the remaining checks.

Both branches were published. [CC-138](https://johnhillescobar.atlassian.net/browse/CC-138) moved to In Progress during validation.

## Candidate demo

The pinned candidate completed all 186 repeat-3 trials at `2026-11-20T03:04:38+00:00`. The scorer, cohorts, protocol, prompt and retrieval index match the baseline. The two live runs occurred sequentially. The repeat-3 geography grid passed 210 of 210 trials across 70 cells. The retrieval evaluations and web build passed. [Candidate scoreboard](e2e-pre-scoreboard.json) · [Transcript](e2e-pre.txt)

The aggregate records the original Windows snapshot hashes. Git-normalized SHA-256 values are `cf25e2b81982f75fc1dea40c5f78107d520da293f3e9cd6fbdb8c6cf17de68f3` for `evidence/latest.json` and `283bdf3c5c0b40b359b4fecaf72aea3dc1fda254ab1337738f61f101638239a8` for [the grid snapshot](e2e-pre-grid-after.json).

The [resumed Gate 2 budget check](gate2-candidate.txt) recorded the candidate's 32.215 s p95 against the 20-second ceiling before the candidate waiver was entered.

| Measure | GPT-4o mini baseline | GPT-6.2 Sol candidate |
| --- | ---: | ---: |
| Long-tail answered | 70.0% (84/120) | 77.5% (93/120) |
| Overall answered | 80.1% | 83.9% |
| Core answered | 100.0% (12/12) | 91.7% (11/12) |
| Trap answered | 98.1% (53/54) | 96.3% (52/54) |
| Full demo p95 | 25.960 s | 32.215 s |
| Retriever@10 | 0.900 | 0.900 |
| Selector@1 | 0.825 | 0.825 |
| Synthetic alignment | 0.544 | 0.544 |

The response-contract check flagged missing row GEOIDs in three trials with data. The exact same three trials have missing row GEOIDs in the baseline. The comparison also reports fewer rows in four baseline families, more empty long-tail responses, and an unbridged scorer mismatch for A0. L is absent from the registered references. [Metric comparison](metric-compare-pre.txt)

| Timing bucket p95 | Baseline | Candidate |
| --- | ---: | ---: |
| Model completion | 10.819 s | 14.377 s |
| Gemini reranking | 8.711 s | 12.325 s |
| Census tool dispatch | 9.525 s | 4.915 s |
| Query embedding | 0.610 s | 0.590 s |
| Remaining application time | 0.663 s | 0.429 s |

The timing buckets can overlap. On the candidate's ten slowest requests, reranking averaged 21.980 s and model completion averaged 13.939 s. An optimistic simulation that caps all reranking within a request at 3 seconds yields 21.085 s p95. It assumes the removed time was on the critical path and all other behavior stays fixed. [CC-125](https://johnhillescobar.atlassian.net/browse/CC-125) caps individual calls and requires an A/B accuracy check.

## Owner latency decision

On 2026-11-19 the owner clarified that the CC-138 waiver accepts the measured latency of the integration trial, including the increase over the baseline. The open [CC-3 tickets](https://johnhillescobar.atlassian.net/browse/CC-3) carry the p95 follow-up.

- Baseline `2026-11-20T01:02:40+00:00`, 25.960 s p95, recorded in `ca50ca7`.
- Candidate `2026-11-20T03:04:38+00:00`, 32.215 s p95, recorded in `948c107`.

The budget checker recognized both exact-run waivers when applied to the captured scoreboards. The independent contract and non-latency regression findings remain open in the [closure manifest](../../closure/CC-138.toml).
