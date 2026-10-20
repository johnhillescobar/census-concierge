# CC-121 as rewritten 2026-10-18 (saved 2026-10-20 before the override)

Source: Jira CC-121, description and title as live on 2026-10-20 (Jira history change 11833 holds the same text in wiki markup). Superseded by the owner's override of 2026-10-19; see `cc-121-plan.md`, batch J1.

Title: The model writes the answer without seeing the fetched figures

## Definition

After `fetch_data`, the model is given the first k fetched figures (k = 20): variable label, `E` and `M`, place `NAME`, GEOID, vintage and universe. A sentinel such as `-555555555` is shown as "not available". A line says "k of n shown" when rows were cut. The model writes the answer from those figures and states no figure it was not given. Rows, MOE, GEOID, URLs, universe and alternatives in the response are unchanged.

## Root cause (verified 2026-10-18)

`_tool_content` (`fetch.py:183-205`) returns only a row count, leg counts, failed/omitted years and URLs. The rows exist only in the tool artifact (`fetch.py:47`) and are absorbed into the record (`ask.py:119-120`). Nothing in the loop or in `finish_tools` gives the model the values (`finish_tools` discards every dispatch result). Confirmed two ways: (1) a real run (median household income, Cook County) with a spy on the model call: after `fetch_data` the model's context holds only `1 rows; 1/1 legs; URLs ...`; (2) an independent cold review of `ask.py`, `fetch.py`, `finish.py`, `tools.py` and `geo.py`. So every figure in the prose comes from model memory by construction. The prompt line `prompts.py:40` ("Never invent or retype estimates") asks the model to cite numbers it cannot see.

## Evidence (2026-10-04, measured)

40 visible long_tail questions, `run_ask`, repeat 1, one run, 39 returned rows. A script compared every number of 100 or more in the answer (ignoring years) with the fetched rows, URLs, warnings, plan and alternatives.

* 20 of 39 answers contain such a number; **19 of 39 (49%) contain at least one that is not in the data**. Zero were rounded or scaled versions of a real value.
* Examples (prose vs fetched `E`): q13 78,462 vs 79,423; q14 215,835 vs 255,668; q16 2,282 vs 8,609; q22 32,110 vs 37,756; q28 73,534 vs 728,655; q42 6,893 vs 24,545. The figures change between runs of the same question (q16: 3,061, 2,282 and 2,896 across three runs).
* Related cause, not part of this story: several questions ask about a subset but only the table total (`001E`) was fetched. Variable resolution and whole-table retrieval (CC-82, CC-118) address that.

Correction (comment of 2026-10-04): the 19/39 count and the example figures come from two different runs of the same questions. The q11 "derived average" was not verified. Limits: one run, n=39, visible questions only; the counter ignores numbers under 100 and cannot detect a real number attached to the wrong label. The old counter is superseded as the instrument by the judge below.

## Mechanism (owner decisions 2026-10-18)

1. `_tool_content` appends the figure block for the first 20 fetched rows, in fetched order, then "k of n shown". Labels come from a lookup injected like `table_facts`. Sentinels are shown as "not available" using the existing `CENSUS_MISSING` set.
2. Prompt guidance replaces `prompts.py:40`: use the figures exactly as given, with their margin of error and universe; say plainly when something asked about was not fetched (for example a subset when only the total was fetched); calculate nothing; state no figure beyond those given; the rest are in the rows.
3. **No runtime check and no extra model call.** The model writes the answer itself. An LLM judge in `scripts/` scores stored answers against stored rows, as measurement only.
4. **No regex, keyword list, word list, tokenizer or pattern over the question or the model's prose**, in `api/src` or in `scripts/`. Understanding language is the model's job (CLAUDE.md).

## Out of scope

Calculation and derived values (shares, averages, differences, summaries across all rows): the answer states none. They need deterministic compute tools and are a separate follow-up (see the linked story). Variable selection (CC-82, CC-118). Charts. Raising any budget. A runtime judge or any second validator.

## Dependencies

CC-116 (leakage gate, merged): no eval phrasing in the new prompt text. First in the implementation order (owner decision 2026-10-04).

## Acceptance criteria

* [ ] A seeded-fixture test shows the `fetch_data` tool content carries `E`, `M`, label, GEOID, vintage and universe for distinct rows; a sentinel reads "not available"; a result larger than k reads "k of n shown".
* [ ] The rate of answers containing a figure not supported by the fetched rows or system notes is measured with an LLM judge in `scripts/` on the 40 visible long_tail questions. Baseline (pre-change code) and after use the same judge, the same questions and the same `--repeat`, at least 3. The old number counter is not used for the gate.
* [ ] Target: 0 unsupported figures, as filed. This is a measured result at that repeat, not a per-answer guarantee (no runtime check, by owner decision).
* [ ] Judge agreement with a stored hand-labelled sample of answers and rows (kept in `evidence/`) is reported.
* [ ] A subset question where only the table total was fetched never produces a figure for the subset (measured on the labelled subset questions in the set).
* [ ] Answers for failed fetches and for no-row results contain no figures; a sentinel never appears as a figure.
* [ ] `demo` answered rate, selector@1 and retrieval@10 do not regress against the same-repeat pre-run; `demo.p95_latency_seconds` is reported before and after and stays at or under 20.
* [ ] No test asserts on prompt wording or LLM prose; tests use structured fields and seeded fixtures.
* [ ] No regex or word list anywhere in the change; no budget is raised; `docs/ask-path.md` states what the model sees after `fetch_data`.

## Test cases

* Happy: a single-value question; the figure in the answer equals the fetched `E`.
* Edge: a subset question where only the total was fetched; a result with more than k rows.
* Novel: a table and geography in no eval.
* Regression: charts, alternatives panel and CSV export are unchanged.
* Failure: a failed fetch; the answer carries no figures.

## Evaluation evidence

Judge-measured before and after on the same question set and `--repeat`; held-out and sealed sets reported separately (aggregates only); judge agreement with the hand-labelled sample; `demo` scoreboard and p95 before and after.

## Regression risks

More tokens per fetch result (bounded by k = 20) may raise latency against a p95 of 18.9 s with a 20 s cap; measured, not assumed. Listings cover only the first k rows in prose; the rows and chart carry the rest. Until the compute tools exist, answers will decline to calculate and point to the rows.
