# CC-121 decision 2: which model writes the answer (advisor brief, 2026-10-18)

Advice only. Nothing decided, no repo file but this one touched, no API call made (the OpenAI account has had no credit since about 17:20, `cc-121-e2e-base-summary.md:28`). I read the summary documents only, no `.jsonl` and no transcript. Dollar figures are estimates from stated assumptions; the repo logs no token usage.

## 0. What the code says (changes the shape of the question)

* **No budget caps the number of LLM models.** "models" in CLAUDE.md is `domain_models`, Pydantic classes, 11 of 15 (`budgets.toml:54`, `check_budgets.py:326-328`). Model names on the request path today: gpt-4o-mini (`api/src/ask.py:40`), gemini-3.7-flash selector (`retrieval/rerank.py:22`), text-embedding-3-large (`retrieval/embedding.py:21`) = 3. gpt-4o-mini also builds synthetic questions offline (`retrieval/synthetic.py:13`).
* **There is no separate answer-writing call.** The answer is the text of the loop's last turn (`ask.py:417-422`), from the same `complete` that plans the tools; `_openai_complete` passes `model=MODEL` with no temperature or reasoning setting and drops `response.usage` (`ask.py:295-318`). The CC-103 parent-splitting call uses the same `complete` (`finish.py:129`), so changing `MODEL` also moves it.
* **The model name lives in one place**, `ask.py:40`. Not in env, docs or tests. `scripts/judge_figures.py:56` overrides it in-process. `run_demo.py` records `prompt_hash` and `index_hash` (`:191,:315`) but not the answer model, so a demo run cannot later be attributed to a model.
* **`ask.py` is at 410 of the 410-line `max_file_loc` cap** (repo counter; `geo.py` too). A one-line constant change is neutral; any in-file routing fails `make check`, and the rule is never to raise it. api_src_loc 4454/4600; system prompt 1097/1200 tokens.
* **Owner rule:** the end of a request never calls the model (`docs/ask-path.md:49`; `cc-121-gate2-fixes.md` finding 2). So "re-call a stronger model after the loop" is out. The only fit for "stronger writer only" is choosing the model for the turn that follows a fetch (a gate on the loop's own state, no regex, no extra call). The finish path (model stops without fetching) is not covered either way (`ask-path.md:29-32`).

## 1. Fair reading of the evidence

* **gpt-4o-mini, corrected instrument** (`cc-121-results.md:9-12`): 68.3% -> 30.0% (gpt-4.1 judge), 81.7% -> 53.3% (gpt-5.5 judge). Per-cell SE is about 4 points (n=120, and the 3 repeats share 40 questions, so independence is weaker than 120); the 38-point drop is about 6 SE. Solid. It supports "showing figures helps this model", not "30% is acceptable".
* **Other models, first instrument** (labels from the newest year only; the code under test also mislabelled older years; superseded, not re-run). Use the within-instrument order only; absolute numbers are indicative. After the change, unsupported rate (gpt-4.1 judge / gpt-5.5 judge): mini 30.0 / 54.2, gpt-4.1 12.5 / 34.2, gpt-5.5 5.8 / 15.0. The order is the same under both judges. mini versus 4.1 is clear (3+ SE); 4.1 versus 5.5 under the gpt-4.1 judge (6.7 points, about 1.8 SE) is not separable. Mini's own first-instrument "after" (30.0) equals its corrected one, which weakly suggests the shift is small, but nothing proves it for 4.1.
* **gpt-4.1's "got slightly worse" (9.2 -> 12.5) is a judge artifact.** Under the gpt-5.5 judge the same answers go 53.3 -> 34.2 (better). Before the change 4.1 mostly stayed silent (9 answers with figures), so a low rate there meant "said nothing". After: 68 answers with figures, 55 fully supported, versus mini 70 and 44 (first instrument). Mini corrected is 54 fully supported, close to 4.1's 55 on the old instrument. The useful number is figure-stating answers fully supported, not the bare rate.
* **Judge validity:** n=30, labelled by a model, on first-instrument answers; judge prompt changed afterwards and was not revalidated. gpt-4.1 29/30 (95% interval roughly 83-99%), gpt-5.5 26/30 (over-flags 4, misses 0), gpt-4o 23/30 (misses 5). Using gpt-4.1 as both answerer and judge reintroduces the overlap Gate 2 removed (finding 4); report both judges.
* **Lower bound and an unseen bias:** the judge sees every row while the model saw 20 figures. A figure for an unshown place that matches a row scores "supported", and a stronger model with better memory is more likely to land one. This inflates the better models' scores by an unknown amount.
* **What a better writer cannot fix** (`cc-121-results.md:45-51`, read from gpt-4.1's own flagged claims): wrong variable fetched (CC-82, CC-118), rankings over partial rows (CC-122), unshown rows, facts from memory, finish-path fetches. Even the best model keeps a floor from those.
* **Latency is the missing number.** Reported: mini per trial p95 19.8 s before, 22.2 s after (shared machine, relative only); gpt-5.5 about 54 s. **gpt-4.1's latency is not in the results file.** `latency_s` sits in its answers file; a one-line aggregate (p95 only, no reading of answers) answers it for free.
* Baseline on main: long_tail 0.725, `demo.p95_latency_seconds` 16.664 s. The same code has measured 18.9 and 21.7 s on two runs (`README.md:17-26`). The CC-121 branch `make demo` is not run yet; the headroom under 20 s is unknown until it is.

## 2. Why gpt-5.5 is so slow (the owner asked)

* gpt-5.5 is a reasoning model (general knowledge, not measured here): before every reply, including a tool call, it writes hidden reasoning tokens. They are generated one after another like visible text, cost output-token rates, and their number grows with the "reasoning effort" setting. mini and gpt-4.1 do not do this.
* The loop pays that per turn: search, resolve, build, fetch, answer is about 5-6 sequential calls per question, plus the splitter. `_openai_complete` sets no effort (`ask.py:302-306`), so the default applies.
* The arithmetic from repo numbers: 54 s p95 minus about 4.5 s of Census and our own time (`cc-121-e2e-base-summary.md:15`) leaves about 50 s of model time over about 6 calls, near 8 s per call, against near 1 s for mini (5.3 s mean over the same calls). That is an inference, not a per-call measurement.
* What I could not check: reasoning-token counts (the loop discards `usage`), rate-limit retries, shared-machine load. A 5-trial smoke run logging `usage.completion_tokens_details.reasoning_tokens` and per-call seconds would confirm it; whether a lower effort setting is accepted by gpt-5.5 must be read from OpenAI's docs. Even then a final-turn-only gpt-5.5 likely adds about 8 s, which on a 17-22 s baseline leaves no room.

## 3. Constraints a switch must respect

* p95 ceiling 20 s from `demo.p95_latency_seconds` (`budgets.toml:63`); over it passes only with an owner `[waiver]` line, one run, its own commit (`check_budgets.py:232-250,395-399`; `run-slice.md:100-101`).
* `max_file_loc` and `api_src_loc`: no raise (CLAUDE.md "Never raise a budget"; `check_invariants --base`). Routing code must live outside `ask.py` or net out to zero lines there.
* Test fakes call `complete(messages, tools)` (about 30 across `test_ask_loop.py`, `test_finish.py`, `test_plan_override.py`); keep that signature. Tests must not assert prompt wording.
* No tuning to the instrument: no eval phrasing in prompts; sealed set owner-held, report the regression-minus-sealed gap at close (CLAUDE.md Traps). A model switch changes tool-calling for the whole loop, so `answered_rate` and the grid (tuned on mini) must be re-measured at the same `--repeat 3`.
* Cost: 4.1 is about 13x mini per token at list price (my recollection of $2/$8 versus $0.15/$0.60 per million tokens in/out; verify; I do not know gpt-5.5 pricing).

Assumptions for the estimates: about 18k input and 1k output tokens per trial (static prompt plus tool schemas about 1.8k tokens per call, measured locally as chars/4; 5-6 calls with growing history); one judge call about 5k in, 250 out. Per 120-trial cell: mini about $0.4, 4.1 whole loop about $5.3, post-fetch turn only about $2.3, one judge pass about $1.5. Calls per cell: about 720-840 chat calls plus 120 Gemini and 120 embedding calls, and 120 per judge pass. `make demo` (186 + 210 grid trials, held-out extra) is about $1.6 on mini, about $9 post-fetch-only, about $18 whole-loop 4.1.

## 4. Options

**A. Stay on gpt-4o-mini; ship CC-121.** Strongest case: the measured gain is large and attributable (same model, same repeat); no latency, cost or loop-behavior risk beyond CC-121 itself; the PR stays small and reports 30% / 53% honestly as red against "0". Measure first: the branch `make demo` and grid at repeat 3 (about $2, about 1,100 chat calls), the p95, the sealed gap (owner). Risks: mini's after-arm p95 rose 2.4 s under load, so CC-121 alone may reach 20 s; residual stays 30%+. Rollback: revert the feature commits (prompt, `fetch.py`, `figures.py`, docs); the merged budget raise stays.

**B. Switch the whole loop to gpt-4.1 (`ask.py:40`) as its own measured change.** Strongest case: best-evidenced upgrade (30.0 -> 12.5, or 54.2 -> 34.2 under the stricter judge), no extra code, no budget touched, no new provider, same API shape. Measure first: (1) free: p95 of the existing 4.1 arm's `latency_s`; (2) corrected-instrument 4.1 collect, `--repeat 3`, 40 questions, judged by 4.1 and 5.5 (about $7, 960 calls); (3) `make demo` plus visible grid (about $18), `answer_model` added to the demo evidence; (4) owner: held-out and sealed gap. Risks: p95 over 20 s (a waiver is not a fix); 13x cost on every request including the splitter; answers become figure-heavy and expose the 20-figure/unshown-row gap; tool-calling behavior shifts. Rollback: one-line revert, clean given `answer_model` is recorded.

**C. Loop stays on mini; gpt-4.1 only for the turn after a successful fetch.** Strongest case: keeps tool-calling, answered_rate and the splitter as tuned; pays 4.1 for about one call; adds a second request-path model name (3 -> 4), which no budget caps. Structure allows it: `run_ask` takes an injectable `complete` (`ask.py:394,412`), so a wrapper that picks the model from the last message (a tool result for `fetch_data`) keeps the fake signature and needs no end-of-request call. It must live outside `ask.py`. Measure first: prototype in `scripts/judge_figures.py` by passing the wrapper to `run_ask` (zero `api/src` change), 120 trials (about $2.3 plus $1.5 judge); then demo and grid (about $9). Unknown: 4.1's gain may come partly from its earlier turns, so the final-turn-only effect is unmeasured; the finish path stays uncovered. Risks: mid-conversation switch on tool-call history written by mini; a post-fetch tool call also runs on 4.1; p95 up by one slower turn (assume +1-3 s, unmeasured). Rollback: remove the wrapper or point both at one model.

**D. Measure other candidates first, ship nothing model-related yet.** Strongest case: the switch has no 4.1 latency, no corrected-instrument data and no cost log; the cheapest-first ladder is free p95 aggregate -> 5-trial usage log -> corrected 4.1 arms (B and C) -> untested candidates (gpt-4.1-mini, gpt-4o, gpt-5.5 at reduced reasoning effort if supported; Gemini needs a different completion adapter, `ask.py` has no room, so it is not cheap). Combines with A. Risk: indefinite delay; every extra arm adds noise-chasing at a 2.5-point noise floor. Rollback: nothing shipped.

## 5. Scope and ticket (path to consider: A now, B/C/D as one separate ticket)

CC-121 PR: stays on mini (prompt, `fetch.py`, `figures.py`, tests, `ask-path.md`), plus its own `make demo` scoreboard, Gate 2, sealed gap. Folding a model switch in would confound the before/after, widen the blast radius to the loop and splitter, and need the owner-held sets before it can merge.

Draft (not created; unscheduled, no epic like CC-122; per memory, ask the owner before attaching to CC-11 or any epic):
* Title: "Answer-model selection: measure gpt-4.1 whole-loop and post-fetch-only against the corrected CC-121 instrument and the 20 s ceiling".
* AC1: a decision rule committed before any result (eligibility `demo.p95_latency_seconds` <= 20 s and long_tail answered_rate >= the main baseline within a stated band; then figure-stating answers fully supported and the unsupported rate under both judges; tie band stated), as CC-103 did.
* AC2: arms mini (existing `base-fixed`/`after-fixed`), 4.1 whole-loop, 4.1 post-fetch-only, corrected instrument, `--repeat 3`, 40 visible long_tail, judged by gpt-4.1 and gpt-5.5; latency from `latency_s` aggregated, token usage from a 10-trial smoke log.
* AC3: `make demo` (long_tail answered_rate, p95, grid) for each eligible arm at `--repeat 3`; `answer_model` recorded in `evidence/latest.json`; owner reports held-out and sealed gap (<= 10 points).
* AC4: no budget raised; rollback is one constant or one wrapper removal.
* Files: `scripts/judge_figures.py` (wrapper arm), `scripts/run_demo.py` (record `answer_model`), `evidence/slice-6/` results, one mutation-checked test for the model-choice wrapper if it ships (not before), `ask.py:40` or a small wrapper outside `ask.py` only after the rule picks a winner.
* Who: the agent writes scripts, tests and evidence on a branch and commits only when you ask; you create the ticket, top up credit, run held-out and sealed, and make any `[waiver]` commit separately.

## 6. Open questions only the owner can answer

1. Is a per-request cost increase of roughly 5-13x acceptable at all, and what ceiling? (Memory: through slice 8 the yardstick is URL generation, not prose figures; does prose correctness justify it?)
2. Is 20 s absolute, or is a one-run `[waiver]` acceptable for a model switch? The same code measured 16.7 to 21.7 s on different days.
3. Is "0 unsupported" still the CC-121 bar, or do you accept 30% / 53% and move the residual to CC-82/118/122?
4. Which judge is authoritative, gpt-4.1 or the stricter gpt-5.5; and will you spot-check some labels (the labeller was a model)?
5. Should the splitter follow the loop model (B) or stay on mini?
6. May I draft the ticket as unscheduled (no epic), and when will credit be topped up (nothing here can run before)?
7. Separate open item: amend `review-pr.md:63-64` ("the model must never handle the value"); a figure-heavy model makes the conflict more visible.
