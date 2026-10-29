# CC-121 results (2026-10-18)

Instrument: `scripts/judge_figures.py` over the 40 visible long_tail questions, `--repeat 3` (120 trials per cell, 0 errored in every cell). Before = unmodified `main` (the model is never shown the fetched figures). After = this branch (first 20 fetched figures, each with its own vintage's label, E, M, place, GEOID, dataset and year, plus a closing "Table ...: ... Universe: ..." line; guidance in `prompts.py`). Judge rule and its addendum: `cc-121-judge-rule.md`. Raw answers, verdicts and logs sit beside this file.

## Headline: re-measured with the corrected instrument (gpt-4o-mini, the product's model)

Gate 2 found the first instrument built labels from the newest year only (CC-121 Gate 2 finding 4) and the code under test labelled every year with the newest year's label (finding 1). Both are fixed (`cc-121-gate2-fixes.md`); these two arms are the re-run: `base-fixed` and `after-fixed`.

| judge | answers with at least one unsupported claim, before | after | answers that state a figure, before -> after | figure-stating answers fully supported, before -> after |
|---|---|---|---|---|
| gpt-4.1 (headline) | 82/120 = 68.3% | 36/120 = 30.0% | 75 -> 81 | 0 -> 54 |
| gpt-5.5 (stricter) | 98/120 = 81.7% | 64/120 = 53.3% | 100 -> 99 | 2 -> 35 |

Zero was not reached under either judge. The target as filed ("0 unsupported figures") is not met; the PR reports it red.

Latency per trial, seconds, measured while other runs shared the machine, so relative only: before p50 9.4 / p95 19.8 / max 25.1; after p50 10.5 / p95 22.2 / max 32.9. The authoritative p95 is `make demo` (`demo.p95_latency_seconds`), reported in the PR. Label lookups cost about 0.1 s per distinct year shown.

Caveats:

* The judge sees every fetched row while the model saw only the first 20 figures. A matching figure for an unshown place scores "supported", so the rates are a lower bound.
* The 30-answer judge validation below was labelled on the first instrument's answers. The judge prompt changed by one phrase (labels are given per year); the validation was not re-run.
* Run-to-run noise on this model is about 2.5 points (the first measurement of the same code gave 30.0%, 32.5% and 30.0%).
* The labeller was a model, not a person; a spot check by the owner would strengthen this.

## Judge validation (30 answers, drawn with a fixed seed from both arms, labelled blind by an independent model, never by the product's models)

| judge | agreement with the labels | judge flagged, label ok | judge ok, label flagged |
|---|---|---|---|
| gpt-4.1 (headline) | 29/30 | 1 | 0 |
| gpt-5.5 | 26/30 | 4 | 0 |
| gpt-4o | 23/30 | 2 | 5 |

## Superseded: other answer models, first instrument

Measured before the per-year fix, with labels from the newest year only. Kept for the per-model picture; not re-run. Treat the "after" column as indicative only.

| answer model | before | after | answers that state a figure (before -> after) | figure-stating answers fully supported (before -> after) |
|---|---|---|---|---|
| gpt-4o-mini (first run) | 74/120 = 61.7% [90/120] | 36/120 = 30.0% [65/120] | 71 -> 70 | 1 -> 44 |
| gpt-4.1 | 11/120 = 9.2% [64/120] | 15/120 = 12.5% [41/120] | 9 -> 68 | 1 -> 55 |
| gpt-5.5 | 22/120 = 18.3% [54/120] | 7/120 = 5.8% [18/120] | 21 -> 54 | 1 -> 48 |

(gpt-4.1 judge; gpt-5.5 judge in brackets.) gpt-4.1 and gpt-5.5 mostly avoided figures before the change and state them after. gpt-5.5 p95 was about 54 s, so it cannot meet the 20 s ceiling.

## What remains unsupported after the change (gpt-4.1 as answerer, read from the flagged claims)

* A real figure for the wrong variable (only the table total, or a different row, was fetched). Out of scope here: CC-82, CC-118.
* Rankings and superlatives stated from the first 20 figures when the result had more rows ("oldest county"). Needs the compute tools: CC-122.
* Figures for listing rows that were not shown.
* Facts from the model's memory (a city's historical peak population).
* The finish path: when the model stops without fetching, `fetch_data` runs afterwards and the model never sees its figures (documented in `docs/ask-path.md`).

## Not done yet

`make demo` on the branch (answered rate, selector@1, retrieval@10, p95), compared with the baseline run on `main`; held-out and sealed reporting (owner-held); PR.
