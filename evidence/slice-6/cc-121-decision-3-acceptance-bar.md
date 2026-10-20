# CC-121 decision 3: the acceptance bar for "unsupported figures" (advisor brief, 2026-10-18)

Advisory only; nothing here is decided. Read: CLAUDE.md, run-slice.md, `cc-121-results.md`, `cc-121-judge-rule.md`, `cc-121-gate2-fixes.md`, `cc-121-e2e-base-summary.md`, `scripts/judge_figures.py`, memory files, Jira CC-121/122/82/118/3. Not read: any jsonl, the hand-label key, sealed data, transcripts. No API calls. Arithmetic is Wilson/Clopper-Pearson on the summary-table counts.

## 1. What "unsupported figure" can honestly mean

The ticket says "figure"; the judge counts any quantity, share, ranking, trend or comparison the rows do not support. Three readings, widest last: **R1** a number absent from the rows the model was shown (memory/fabrication); **R2** R1 plus a real number on the wrong variable/place/year; **R3** the current judge (R2 plus words-only rankings, trends, comparisons, computed values, rows not shown, memory facts).

Split derivable from the summary table (gpt-4.1 judge; assumes "fully supported" = ok among figure-stating answers; it reproduces exactly under gpt-5.5, where flagged = stating minus supported in both arms):

| gpt-4.1 judge, of 120 | before | after |
|---|---|---|
| flagged, answer states a figure (82-7 / 36-9) | 75 | 27 |
| flagged, words-only claim (no figure) | 7 | 9 |
| share of figure-stating answers flagged | 75/75 = 100% | 27/81 = 33% |

So the change did its job on figure-stating answers (100% -> 33%) and did nothing for words-only claims (7.5% of all trials, flat). Inside CC-121's mechanism ("the model never saw the figures"): R1, plus the AC "subset asked, only the total fetched, never a subset figure" (a Jira AC of CC-121 itself), plus prompt compliance on memory facts. Owned elsewhere: rankings/computed values/rows beyond the first 20 (CC-122); fetching the right variable (CC-82, CC-118).

Not measured, so the 27 cannot be split into R1/R2/ranking/unshown/memory from the summary tables; the residue list in `cc-121-results.md` is qualitative and from the gpt-4.1 answerer. Two unmeasured terms set a floor for any bar: (a) the share of trials on the finish path (fetch runs after the model stopped, `ask.py:453`; the model never sees figures, so those answers stay near the 68% before-rate; stored trials do not record the path); (b) the judge sees all rows while the model saw 20, so every rate is a lower bound.

Note: CC-82 is whole-table retrieval and CC-118 is the 50-variable URL guard. Neither has an AC about figure support, so "residue moves to CC-82/118" is nominal until the owner gives them one.

## 2. Statistics (n = 120 trials per arm = 40 questions x 3 repeats)

| arm | rate | 95% CI, trials independent | 95% CI, 40 questions as the unit |
|---|---|---|---|
| gpt-4.1 before / after | 68.3% / 30.0% | 59.6-76.0 / 22.5-38.7 | 52-80 / 18-45 |
| gpt-5.5 before / after | 81.7% / 53.3% | 73.8-87.6 / 44.4-62.0 | 68-91 / 37.5-67 |

* Trials are clustered: the same code gave 30.0, 32.5, 30.0 (SD 1.4, three runs, indicative) against a binomial SD of sqrt(.3 x .7 / 120) = 4.2 if independent. Failure is mostly a property of the question (what got fetched), so the effective n lies between 40 and 120. CC-3 already makes the question the unit. More repeats buy little; more questions would (40 visible, 8 holdout, sealed owner-held).
* Before/after: difference 38.3 pts, SE 6.0, +-11.7 (about +-16.5 with a design effect of 2). Relative: ratio 0.44 (0.33-0.59) under 4.1, so a 41-67% reduction; 0.65 (0.54-0.79) under 5.5, so 21-46%. Direction is certain; size is uncertain by 12-17 pts. The same questions in both arms allow a paired test, which is stronger; it needs per-question data I did not read.
* Detectable difference (80% power, alpha .05, two arms of 120): 16.6 pts at a 30% base, 10.9 at 10%; about 23 and 15 with clustering. 30% vs 20% needs about 290 trials per arm and more distinct questions, not more repeats. A bar within about 10 pts of the observed rate cannot be separated from it.
* Zero: 0/120 has a 95% upper bound of 3.0% (0/40: 8.8%). If the true rate is 1%, P(0/120) = 30%; 2%, 9%; 3%, 2.6%. The judge's own false-positive rate is 1/30 (CI 0.6-17%) on the 30-answer sample, so even a perfect product may not read zero. Zero is a design property, not a rate that repeat 3 can confirm.
* Ceiling at 120 trials, P(observed <= bar) by true rate: bar 25% (30/120): 93% at true 20, 55% at 25, 14% at 30. Bar 20%: 55% at 20, 12% at 25, 1% at 30. Bar 35%: current code passes about 97%. To claim "true rate <= 25%" at 95% needs observed <= 20/120 (16.7%); "<= 30%" needs <= 26/120 (21.7%); the current 36/120 has upper bound 38.7%.
* A bar set now is informed by the 30%. Only a fresh run (new `--label`; the script refuses reuse), the 8 holdout questions (24 trials, +-18 pts: too coarse alone) and sealed (no figure-rate runner exists; `judge_figures.py` writes answers to disk) are blind. A replicate of the same 40 questions is blind only in the sense that its result is already known to within about 3 pts.

## 3. Candidate bars

Common to all: the bar goes in a new file `evidence/slice-6/cc-121-bar.md`, committed by the owner before the confirmation run and before `make demo` on the branch (not as another addendum to `cc-121-judge-rule.md`, which already has a duplicated, post-results addendum and a post-hoc judge). It freezes: judge snapshot and prompt hash, the 40-question set hash, answer model, `--repeat 3`, a fresh label, and a tie band (CC-103 precedent: about 5 pts counts as "at the bar", owner decides). Jira: the owner edits the AC line and adds a comment tagged `owner` (session rule 4). PR and Jira close comment: the bar, its commit, the run label, the rate with interval, baseline at the same repeat and judge, the other judge beside it, and the close card.

**A. Zero, as filed** (0 unsupported answers in 120, headline judge). Case: owner-confirmed; it is the "nothing from model memory" yardstick; no ratchet to argue about. Cost: unreachable by measurement (above) and by construction on the finish path. If missed (certain): per run-slice section 6 the PR stays open and red with the scoreboard; CC-121 stays In Progress in Jira (closing it would make Jira wrong); main keeps shipping answers that never see the figures while a 38-point gain sits unmerged. An owner waiver would be new: the only waiver precedent is the p95 `[waiver]` line in `budgets.toml`. Gaming: the only paths to 0/120 are a looser judge or an answer that states no figures.

**B. Absolute ceiling.** Candidate: at most 25% (30/120) under the headline judge, with the stricter judge reported beside it. Reasoning: the lowest ceiling this instrument can tell from the current 30% for a product at 20% (93% vs 14% pass); about a 63% cut from the 68% baseline; above the flat 7.5% words-only floor. A ceiling of 35% only ratifies today's result, and below about 20% needs a stronger answer model (old instrument: gpt-4.1 12.5%, gpt-5.5 5.8%, but gpt-5.5 p95 about 54 s against the 20 s ceiling). Current code fails 25% about 86% of the time, so it needs another measured change. If missed: PR red; further iteration is capped by the 100-iteration rule and confirmed on holdout and the sealed gap (10 pts); or the owner lowers the bar with a written reason. Gaming: tuning prompts on the same 40 questions is exactly "tuning to the instrument".

**C. Relative reduction.** At least 50% fewer answers with an unsupported claim than the same-day `main` arm, same judge, same repeat, with the lower interval bound above 25%. Case: both arms move with the judge, so drift and strictness cancel; the 4.1 headline passes (56%, 41-67%) and 5.5 would not (35%, 21-46%), which is an honest flag. Cost: a high base flatters it (50% off 82% still leaves 41%); needs a baseline re-run each time; says nothing absolute. If missed: PR red, same as B. Gaming: weakest, since a worse baseline passes.

**D. Split metric.** Binding: R1 only (a stated number absent from the shown rows), a ceiling set as a rule before seeing it (for example one third of the baseline R1 rate, or a fixed 5%); reported: wrong-variable, ranking/computed, unshown rows, memory, words-only, each assigned to a named ticket with its own AC. Case: it matches the root cause; CC-121 should not fail for CC-122's work; no regex, since the judge classifies. Cost: no R1 number exists yet; needs a judge change (a `kind` per claim from a closed list), a re-judge of stored answers (no re-collect), hand-labelled kinds on the sample, and is an instrument change reported separately (CC-3 AC10). If missed: PR red on R1 only; residue stays visible under its own tickets. Gaming: classification can launder real failures into "other tickets"; keep the total R3 rate in every comment.

**Modifiers that fit A-D.** **E** a yield floor, so silence cannot pass: figure-stating answers at least the baseline 62.5% (75/120; now 67.5%) and fully supported figure answers at least 40% of trials (now 45%, CI 36-54%). This follows CLAUDE.md "done means a user got an answer". **F** question as the unit, CC-3's convention: a question passes if clean in at least 2 of 3 repeats; the bar counts questions out of 40. It removes the clustering inflation but needs per-question data; the bar must be written before it is looked at.

## 4. Scope

| | files and Jira text | owner required | inside the CC-121 PR | residual ACs needed |
|---|---|---|---|---|
| A | none; PR body, CC-121 comment | decide waiver or red | yes | none required, but nothing owns the gap |
| B | `cc-121-bar.md`, CC-121 AC line; maybe prompt iteration and judge alignment to the shown 20 figures | AC edit, bar commit | yes | optional |
| C | `cc-121-bar.md`, AC line, a same-day baseline arm | AC edit, bar commit | yes | optional |
| D | as B plus `judge_figures.py` `kind` field, labelled kinds in `evidence/`, CC-121 AC rewrite | AC edits on CC-121, CC-122, CC-82 or CC-118 | judge and evidence yes; ACs no | CC-122 (rank/computed over all rows), CC-82/118 (wrong variable: no figure AC today), finish path and unshown rows (no ticket) |

Any new ticket and its epic is the owner's call (CC-3 already large; CC-11 capped). Re-measuring needs OpenAI credits. `review-pr.md:63-64` ("the model must never handle the value") still contradicts the design and blocks Gate 2 independently.

## 5. Questions only the owner can answer

1. Which reading binds: R1 (numbers absent from the rows), R2, or R3 (current judge, including words-only rankings and trends)?
2. Is "zero, as filed" the target (tracked) or the acceptance bar? If the bar, do you accept the PR staying red, or a written merge waiver with CC-121 left open?
3. Which judge governs: gpt-4.1 alone, both, or neither until you adjudicate the 4 items where gpt-5.5 flagged and the model labeller said ok (the labeller was a model, not a person)?
4. May the judge be changed to see only the 20 figures the model saw (removes the lower-bound bias, raises the rate) before the number is fixed, and both arms re-judged?
5. Should the finish-path share be measured first (a trial field, then judge-only reruns)? If large, is the ruling "no end-of-request model call" revisited, or is a floor accepted?
6. Is changing the answer model (the `models` budget, p95) in scope for CC-121 if the bar needs it, or a separate decision?
7. Trial or question as the unit (E, F)? And is a figure-rate sealed run wanted for the 10-pt gap, which needs a new aggregate-only runner?
8. If the bar is anything other than zero, which tickets take the residue, and will you add the figure-support ACs to them yourself?
