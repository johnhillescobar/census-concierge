# CC-121 probe P2 results (2026-10-20)

Setup, instruction and readings were fixed before the run: `cc-121-probe-instruction.md` / `.txt` (commit `fbff733`). Run: this branch's `api/src`, only the prompt block at `prompts.py:40` replaced in the probe's own process; `gpt-4o-mini`; 40 visible long_tail questions, repeat 1; judge `gpt-4.1`. Files: `cc-121-answers-probe-nodigits.jsonl`, `cc-121-collect-probe-nodigits.log`, `cc-121-judged-probe-nodigits-gpt-4.1.jsonl`. Reproduce the table: `uv run python -I evidence/slice-6/cc-121-preflight-check.py probe-nodigits`.

| | probe (told to write no figures) | stored base-fixed, repeat 1 only (not told) |
|---|---|---|
| trials, errored | 40, 0 | 40, 0 |
| strict flags (a numeric token matching no row cell, universe, label or note) | **13** | 30 |
| numeric token that is not a year | 20 | 32 |
| any numeric token | 34 | 34 |
| judge: answers with an unsupported claim | **2** | 28 |
| judge: answers that state a figure | 1 | 27 |
| latency p50 / max, seconds (shared machine, relative only) | 9.5 / 48.7 | 9.9 / 22.0 |

One run each, n = 40: a difference of a few answers is noise.

## Against the pre-registered bands

13 of 40 strict flags falls in "5 to 20 of 40: partly; the wording or the design needs the owner's call". It is not in the "proceed" band (at most 4) and not in the "fails" band (more than 20).

## What the 13 flags are

24 unmatched tokens: 23 are below 100 and one is a year (2008). **None is 100 or more.** No estimate, margin of error, count or share from the data appears in any of the 40 answers.

* "5" from "ACS 5-year": 8 answers (the only unmatched token in 6 of them).
* Table wording: "past 12 months" (3), "over 14" (1), "more than 30%" (1).
* FIPS parts, "county code 087, state code 06" (1).
* Numbered-list markers 1 to 5 and "the 2008 financial crisis" (1 answer, explanations from model memory; the judge marked it ok because it states no quantity).

The stored records carry no table title and no plan, so the real check, which has both, would match some of these. How many is not measurable here.

## Verdict on the claim

* "The model writes no digits": **fails as stated.** 34 of 40 answers contain a digit, 20 of 40 one that is not a year.
* "The model writes no figures from the data": **holds in this run.** 0 of 40 answers contain a number of 100 or more; the judge finds an unsupported claim in 2 of 40 (70% before) and a stated figure in 1 of 40 (27 of 40 before).
* Not settled: how the final answer reads (this prose plus code-rendered sentences); a real number on the wrong variable (the rendering step is not built); explanations from model memory and comparatives pass a digits check, and the judge missed the q39 explanation too.

## Options for the owner

1. **Proceed (my recommendation).** Build the allowed set from structured response fields only: years, the dataset's digits (`acs5` gives 5), table title, universe, variable labels, GEOID parts. No regex, no word list. Measure the fallback rate at E2E and report it. Allowing the "5" alone clears 6 of the 13 flagged answers (13 to 7 of 40).
2. **Refine the instruction first** (plain sentences, no numbered lists, no explanations beyond the data) and re-probe under a new label before implementing. Costs another run.
3. **Loosen the check to numbers of 100 or more.** Rejected: on unconstrained prose it missed 21 answers the judge flags, and the ticket says no model-written digit survives the check.
