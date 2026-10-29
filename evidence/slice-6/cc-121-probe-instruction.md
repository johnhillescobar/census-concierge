# CC-121 probe P2: does the model write no figures when told not to? (pre-registered 2026-10-20, before any result)

Claim under test (restored 2026-10-04 text, mechanism step 1): "The model writes only qualitative framing with no digits."

## Setup

* Code under test: this branch's `api/src` unchanged (the model is never shown the fetched figures). Only the system prompt differs, and only in the probe's own process: the sentence block at `prompts.py:40` is replaced by the text in `cc-121-probe-instruction.txt` (a draft, not the production wording). Nothing is written to `api/src`.
* Questions: the 40 visible long_tail questions, `--repeat 1`, answer model `gpt-4o-mini` (the product's), 4 workers. Collector: `scripts/judge_figures.py collect`, label `probe-nodigits`.
* Judge: `gpt-4.1`, the same judge and rule as the other CC-121 runs (`cc-121-judge-rule.md`).
* Comparison: the stored `base-fixed` run, repeat 1 only (40 of its 120 answers): same model, same code, no instruction. Same repeat count, as the repo requires. One run each, so differences of a few answers are noise (the earlier runs of the same code varied by about 2.5 points over 120 answers; over 40 the noise is larger).
* No eval phrasing in the instruction. The instruction was written before the run and is not tuned on its result. If it needs wording changes, that is a new probe with a new label.

## What is read (all from structured fields; nothing parses prose except `float()` on whitespace tokens)

1. Share of answers with a numeric token that is not a year (the digits-only check's "any figure"), and the share the strict check flags against the rows. Under the design, a flagged answer falls back to the code-rendered sentence, so this is the fallback rate.
2. Share of answers with any numeric token at all.
3. Judge: answers with at least one unsupported claim, and answers that state a figure (`states_figures`). On this prose the unsupported claims should be qualitative ones (comparatives, descriptions).
4. Trials that errored, and per-trial latency (p50, max; relative only, 4 workers share the machine).

## Default reading of the result (my default thresholds, not the owner's)

* Strict-check flags at most 4 of 40 (10%): the claim holds; proceed to implement with the instruction.
* 5 to 20 of 40: partly; the fallback would show the code sentence in a quarter to a half of answers; the wording or the design needs the owner's call.
* More than 20 of 40: the claim fails; the instruction does not make the model write no figures.
