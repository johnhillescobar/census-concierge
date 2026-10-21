# CC-121 pre-flight (2026-10-20): the restored 2026-10-04 mechanism

Claims are from the Jira description as restored on 2026-10-20. Each was run against the thing it names. Population for the numeric check: 120 stored answers from the unmodified code (the model is never shown the figures), gpt-4o-mini, 40 visible long_tail questions x 3 repeats (`cc-121-answers-base-fixed.jsonl`), with the judge verdicts beside them (`cc-121-judged-base-fixed-gpt-4.1.jsonl`, `...-gpt-5.5.jsonl`). Command: `uv run python -I evidence/slice-6/cc-121-preflight-check.py` (plain code: whitespace tokens, `str.strip`, `float()`; no regex, no model call; no word sets).

## Claims that held

| claim | settled by | result |
|---|---|---|
| `contract.py` `take_chart` lines 389-390 pass the model's `answer` through unchanged | read `contract.py:384-394` | holds: `cleaned = str(body.get("answer") or "")`; no code compares its numbers to the rows |
| `prompts.py:40` carries "Never invent or retype estimates" | grep | holds, line 40 |
| the sentinel set exists | grep | `CENSUS_MISSING`, `vintages.py:40` |
| root-sum-of-squares code exists for computed values | grep | `compare.moe_diff` (`compare.py:57`), `guards.py:322` |
| the check adds no model call and no latency | timed the prototype, three runs | 12 to 16 ms for 120 answers |
| the 49% baseline | counted unmatched numbers of 100 or more, years ignored, against the rows | 61 of 120 = 50.8% (filed: 19 of 39 = 48.7%). Not the same counter: this one allows row cells only |
| `float()` handles commas, `$`, `%` | prototype | holds (`str.strip` and `str.replace`, no regex) |
| number words ("two million") need a parser | **Withdrawn, then decided by the owner.** An earlier count used a throwaway word set (1 of 120 answers); the owner does not want word sets, so the set and the count are removed. Decision (owner, 2026-10-20): no sets of number words and no parser, in the product or in `scripts/`. The check reads digits only; a number written in words is not a number to it. Telling the model how to write figures is the model's job, by instruction |

## Claims that failed or are unsettled

| claim | result |
|---|---|
| `prose_check.py` and `prose_results2.json` exist in a session scratchpad "to be moved into `evidence/`" | **Failed.** Searched every session scratchpad under the Claude temp directory: not found. The old counter must be rebuilt in `scripts/` for the first acceptance criterion ("same counter"). The prototype above is the starting point |
| the allowed set includes years, table IDs and GEOIDs "from the plan and URLs" | Stored answers carry rows, labels, universe and notes but no plan or URLs, so the prototype allowed row cells (including `GEO_ID` suffix and `year`) and numbers in the universe, notes and labels. The real check has the plan |
| code renders "every figure sentence" | **Needs a cap.** 90 of 117 answers have one row, but 12 answers (4 questions) have more than 20 estimate cells, maximum 100. The ticket has no "k of n shown" rule for rendered sentences. Owner decision |
| the model, told to write no digits, writes none | **Unsettled.** The stored prose was written without that instruction. Needs a live probe with credits |
| `answer_figures_unverified` | Not in the repo (grep). Warning codes are a function in `guards.py` plus a row in `docs/requirements.md`; guards never change the answer, so the replacement belongs at `assemble()`, not in a guard |

## Checker against the judge and the hand labels

Strict mode: every numeric token must match a row cell, at the precision written; list numbering is not exempt.

| | judge unsupported | checker flags | both | judge only | checker only |
|---|---|---|---|---|---|
| gpt-4.1 judge | 82 | 89 | 78 | 4 | 11 |
| gpt-5.5 judge | 98 | 89 | 86 | 12 | 3 |

With numbered-list markers exempt (a plain string test): 86 flags; vs gpt-4.1, both 77, judge only 5, checker only 9. The checker-only cases are small numbers (list numbering, "5-year", similar). The old rule (numbers of 100 or more, no years) flags 61 and misses 21 that the judge flags, which are small numbers and percentages.

Hand-labelled sample (30 answers, labelled by a model, not a person): the strict checker agrees on 26 of 30 (9 flagged and unsupported, 17 passed and ok, 3 missed, 1 flagged but ok).

## What the design would still let through

If a flagged answer is replaced by the code-rendered sentence (which is supported by construction) and unflagged answers keep their prose, the answers that remain unsupported are the ones the checker passes and the judge flags: 4 of 120 = 3.3% (gpt-4.1 judge), 12 of 120 = 10% (gpt-5.5 judge; it includes the 4). Read from the 12 claims (printed by the script): comparatives ("significantly lower"), a time of day ("7:15 AM"; `float()` cannot read it), statements about what the table contains, a claim that no data was found, and one fraction written in words ("more than a third"). None is a digit string the check could compare. Digit-bearing tokens `float()` cannot read: table IDs (allowed), decades like "1950s" (4), a time (1). Zero is not shown reachable by the check alone; comparatives are the ticket's own residual gap.

## Cost to the reader

On this prose the strict check flags 89 of 120 answers (74%), so 74% would show the deterministic sentence instead of the model's prose. That figure is for prose written without the no-digits instruction. The real rate is unknown until the probe.

## Budgets and files

* `api_src_loc` 4452 of 4600 with `figures.py` (56 lines) restored; headroom 148. The 4400 to 4600 raise is already on `origin/main` (PR #110, `3b785a4`, merged 2026-10-18). This PR raises nothing, so "no budget is raised" holds for it.
* `ask.py` and `geo.py` are both at the file ceiling, 410 of 410. The hook is `ask.py:252`, `**take_chart(answer, rows, warnings)`; it can change in place with zero net lines. `contract.py` (368) and `guards.py` (374) have room.
* `doc_lines` 1753 of 1800; prompt tokens 977 of 1200.

## Branch state

`origin/main` is 15 commits ahead of this branch (PR #110 and PR #111, merged 2026-10-18 and 2026-10-19). `api/src` is unchanged on `main`: no CC-121 code reached it. Local `7aebf3a` duplicates `3b785a4` with different changelog text ("forwrites"); `main` holds the clean text. Reconcile before a PR.

## Open for the owner

1. Cap for rendered sentences (default: the first 20 figures, then "k of n shown", as in `figures.py`).
2. Comparatives: bar by instruction, or have code supply them as facts (default: bar by instruction; measure the residual).
3. A live probe to settle the no-digits claim: 40 visible questions, repeat 1, `run_ask` with a draft instruction, needs OPENAI and CENSUS credits.
4. "The LLM should understand the difference in numbers" (owner, 2026-10-20). Reading A, the default: the model is told to write figures as digits exactly as rendered, and the check stays a digits-only comparison with no number-word logic. Reading B: a model call at runtime decides whether prose numbers are supported (rounding, scale, words). B was dropped on 2026-10-18 for the ask-path rule ("the end of the request never calls the model", `docs/ask-path.md`) and for latency (p95 18.9 s of 20 s), and it is not in the restored 2026-10-04 text. **Decided (owner, 2026-10-20): A.** No runtime model call.
