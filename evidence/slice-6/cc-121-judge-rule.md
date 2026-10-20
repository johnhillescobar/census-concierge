# CC-121 judge selection rule (written 2026-10-18, before any baseline or after results)

* Instrument: `scripts/judge_figures.py`, 40 visible long_tail questions, `--repeat 3`, 4 workers.
* Arms: `baseline` = HEAD a3f0930 (model never sees the figures); `after` = this branch.
* Two candidate judges run on both arms: `gpt-4o` and `gpt-4.1`.
* A fresh subagent labels a random sample of stored answers blind (it sees answer, rows, labels, universe, notes; never a judge verdict). Sample: 30 answers, drawn with a fixed seed from the union of both arms.
* The headline judge is whichever agrees more with the hand labels on the sample (agreement = same ok/unsupported call). A tie goes to gpt-4o. The other judge's rate is reported beside it.
* The labelling rubric is the judge prompt's own definition (quantity, share, ranking, trend or comparison in any form that the rows do not support; computed values are unsupported unless the facts state them; years, table IDs and statements with no quantity are fine).
* Target (owner, 2026-10-18): 0 unsupported answers in the `after` arm at repeat 3, as a measured result; baseline reported with the same judge.
* Nothing is tuned on the sample or on question phrasing; no eval phrasing goes into prompts or `api/src`.

## Addendum, 2026-10-18 (written after the first results were seen)

* Results seen before this addendum: baseline 72/120 (gpt-4.1), after-v1 32/120, after-v2 39/120; gpt-4.1 agreed with the 30 blind labels on 29/30, gpt-4o on 23/30, so gpt-4.1 was the headline judge under the rule above.
* Owner request: also judge with `gpt-5.5` (resolves to `gpt-5.5-2026-04-23`) and run `gpt-5.5`, `gpt-4.1` and `gpt-4o-mini` as the model that writes the answers, to see how the product performs per model. `gpt-4o-mini` is the product's current model; the other two are measurement runs only (`--answer-model` changes the constant in the script's own process, never in `api/src`).
* `gpt-5.5` joins the judge candidates after the fact. The same selection rule applies: the judge with the higher agreement on the same 30 labels is the headline; a tie goes to the cheaper/earlier model (gpt-4.1). Every judge's numbers are reported side by side.
* The answer-model runs use the current branch code (table title in the closing line, tightened subset guidance = "v2"). Latencies from these parallel runs are contended and relative only; p95 is measured with `make demo`.

## Addendum, 2026-10-18 (written after the first results were seen)

* Results seen before this addendum: baseline 72/120 (gpt-4.1), after-v1 32/120, after-v2 39/120; gpt-4.1 agreed with the 30 blind labels on 29/30, gpt-4o on 23/30, so gpt-4.1 was the headline judge under the rule above.
* Owner request: also judge with `gpt-5.5` (resolves to `gpt-5.5-2026-04-23`) and run `gpt-5.5`, `gpt-4.1` and `gpt-4o-mini` as the model that writes the answers, to see how the product performs per model. `gpt-4o-mini` is the product's current model; the other two are measurement runs only (`--answer-model` changes the constant in the script's own process, never in `api/src`).
* `gpt-5.5` joins the judge candidates after the fact. The same selection rule applies: the judge with the higher agreement on the same 30 labels is the headline; a tie goes to the earlier model (gpt-4.1). Every judge's numbers are reported side by side.
* The answer-model runs use the current branch code (table title in the closing line, tightened subset guidance = "v2"). Latencies from these parallel runs are contended and relative only; p95 is measured with `make demo`.
