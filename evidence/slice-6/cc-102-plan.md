# CC-102 plan

Ticket: CC-102 (bug, epic CC-3). Branch `fix/cc-102-original-question-parent-guard`, built on
`origin/main` 1160bde in its own worktree. The CC-121 branch and its dirty files are untouched.
Yardstick (phase 1): a sound URL, nothing from model memory. Jira holds status; this file holds the plan.
Everything below is uncommitted.

## Owner decisions (2026-10-24)

| Decision | Tag |
| --- | --- |
| A question must carry what `geography.json` `requires` for its GEOGRAPHY LEVEL; if not, there is nothing to look for | `owner` |
| A trap (no geography named) cannot be answered: say so at once, **no URL**, no search, no fetch, no candidates | `owner` |
| t03 golden expectation becomes "the warning, and no URL"; the scorer checks exactly that | `owner` (approved by "we MUST expect" no URLs) |
| Detection is model-composed, validated by code; never a word or token scan | `owner` (CLAUDE.md) and "go ahead with the model-composed detector" |
| Defense in depth: a work bound on pair materialization ships too (amendment 2026-10-22) | `owner` |
| CC-121 stays open until CC-102 and CC-120 are both complete; no Jira write made | `owner` |
| Answer text is written by code (the model supplies the missing state, so it cannot write the explanation) | `default` |
| Trap = no geography named at all. Partial cases (state only for tracts, a county without a state, "tract in a city") keep their existing warnings | `default`, **strict vs lenient still open** |
| Work bound `MAX_COMPARISON_WORK = 50_000` and warning code `comparison_too_large` | `default` |
| Wait up to `FRAME_WAIT_SECONDS = 3.0` for the model's report before the first tool runs; past it, treat the question as complete | `default` |

## Built

**1. Level-completeness check (`finish.incomplete`).** The split call that already runs beside the loop
(`plan_split`) now also reports `level`, `named` (places identified by a name or by a code that
identifies them on its own) and `numbered` (places identified only by a number inside another place).
After the loop's first model turn and before any tool runs, code checks:
- `level` via `geo.detect_level`; `needs` = the level's smallest `requires` in `geography.json`;
- each `named` place must be a run of the question's own words (so a place the model remembers and the
  user never wrote does not count), or a state the model spelled out whose abbreviation was written, or
  `find_state(question)` finds a state; a `named` entry that is also `numbered` is dropped;
- with nothing named: if the question has `numbered` places it is incomplete; otherwise it follows the
  metadata: a level that lists under `state:*` (`legal_predicate`, all counties) goes on, one that does
  not (all tracts) is incomplete. The model's own `listing` flag is not used: it varied run to run.

If the level needs parents and none are met, `run_ask` returns at once through `assemble`:
`geography_unsupported`, a code-written answer naming the level and what it needs, empty `urls[]`,
`rows`, `alternatives`; no search, fetch, URL or candidates. No verdict from the model, no metadata, or a
timeout fails open and the loop runs as before. Complete questions pay no extra call: the split call
already existed. Code: `finish.py` (`incomplete`, `_stated`, `_words`, `plan_split` returns `frame`).

**2. Work bound (`compare.py`, `guards.py`).** `comparison_rows` returns `[]` before any pair is built when
row pairs x estimate columns exceeds 50,000, and `finish_aggregation` adds a visible
`comparison_too_large` warning. It never limits the fetch, rows, URL, MOE, GEOID or universe.

**3. Instrument.** `evals/golden_questions.toml` t03 gains `expect_no_url = true` and a new note;
`scripts/run_demo.py` scores such an entry answered only with the warning and no URL. Stricter than
before, so no loosening. PLAN.md requires re-baselining and reporting it apart from code gains.

**4. Removed.** The token scanner, the tool-level guard, `FetchDataTool.refuse`, the `needs_parent`
plumbing, the old `parentless_tracts` regex pair. Regex call sites 64 -> 62.

**5. Docs and rules.** `CLAUDE.md` "Geography is level-complete"; `docs/requirements.md` "Geography
completeness" and a `comparison_too_large` row; `docs/ask-path.md`; `.cursor/rules/00-guardrails.mdc`
(URL carve-out) and `40-census-domain.mdc` (pointer). Cursor reads `CLAUDE.md` and rules.

## Verified without a live key

`make check` equivalents: ruff and format clean, mypy clean, 672 passed / 34 skipped, invariants held,
client up to date, web 110 passed. Budgets, no raise: `api_src_loc` 4445/4600 (base 4396), largest file
406/410, `doc_lines` 1796/1800, `web_src_loc` 3349/3350.

New tests (`test_geography_completeness.py`, 13 cases, scripted model): no geography named at every level
that needs parents; a remembered-but-unwritten place does not count; a written state counts even if the
model omits it; a named place lets the loop run; "all counties" is fine and "all tracts" is not; levels
needing no parent; garbled model reply fails open. Scorer test added to `test_demo_harness.py`.
**Not yet mutation-checked (Gate 1) and not yet cold-reviewed (Gate 2).**

Post-fix `comparison_rows`, `evidence/slice-6/cc-102-measure.py`: 6,896 rows x 1 or 2 columns: 0.0 s,
~31 MB, 0 comparisons; 200 x 25: 0.0 s; 60 x 25 (largest legitimate fan-out, 44,250): 0.27 s, 95 MB.
Pre-fix, measured: 400 rows x 2 cols 1.10 s / 269 MB; 150 x 25 1.77 s / 450 MB (~6.5 us and 1.5 KB per
comparison). The full 6,896-row shape was never run pre-fix; extrapolation does not reconcile with the
recorded 697 s / ~5 GB, so no extrapolated figure is quoted.

## Live probe of the model's report (credits approved 2026-10-24)

Model calls only (gpt-4o-mini, the loop's model), 30 to 41 hand-written questions, no Census calls.
`false trap` = a valid question refused (the costly error). `miss` = a trap let through, which fails
open, so it is no worse than before. Scripts live in the session scratchpad, not the repo.

| Iteration | Change | False traps | Misses |
| --- | --- | --- | --- |
| 1 | `named` only; "a bare number is not a name" | 0 of 20 | 6 of 10 (model files "tract 1201" under `named`) |
| 2 | add a `numbered` slot; code ignores a `named` entry that is also `numbered` | 2 of 20 | 4 of 10 |
| 3 | code: a spelled-out state counts if its abbreviation was written; ignore the model's `listing` flag, follow `legal_predicate` | 1 of 20 (a FIPS question) | 1 of 10 |
| 3b | 5 repeats, 26 valid + 15 trap cases | 11 of 130, all FIPS/GEOID codes | 6 of 75 |
| 4 | prompt: a code that identifies a place on its own goes in `named`, never translated | 1 of 130 | 10 of 75 (a lone "tract 88 ..." now filed as named) |
| 5 | prompt: a tract, block group or county number alone is not such a code | 0 of 130 | 11 of 75 |
| 6 | prompt: numbered "wherever it sits, even as the first words" | **0 of 130** | **5 of 75, all one phrasing ("my county", a deictic the model will not drop)** |

Caveat: I tuned against these very phrasings, so iteration 6 is optimistic. The unbiased tests are the
golden set (not tuned against) and the owner's sealed set. Split-call latency in these runs: p50 ~1.1 s,
max ~2.6 s, beside the loop.

## Not verified: needs the full E2E

- `answered_rate`, the golden set and p95 against the 20 s ceiling (PLAN.md records 18.9-21.7 s) with the
  detector in place, at the same `--repeat`; and the regression-minus-sealed gap.
- t03 under `make demo` with the new scorer.
- The pre-flight claim of 6,896 tract rows for Texas (recorded in the ticket, not re-run).

## Known limits

- The check covers the narrow case: no geography named at all. Partial cases are unchanged.
- A model that lists a level word as a named place would hide a trap (fails open, same as today).
- CC-123 (demo process memory, reaped before E2E completes) is still To Do and may affect E2E.
- Docs and `.cursor/rules` now describe this behavior as required.

## Outward writes

None. No commit, push, PR or Jira write. Close comment only after the owner merges, via
`scripts/jira_transition.py`.

## Gates (not run)

Gate 1 (tests + mutation checks), Gate 2 (cold review), E2E `make eval` and `make demo` run in fresh
subagents from a commit, writing `evidence/slice-6/cc-102-gate1.txt`, `cc-102-gate2.txt`,
`cc-102-e2e-pre.txt`. Gate 1 mutations: level check ignores `requires`; grounding removed so a
remembered place counts; `find_state` fallback removed; listing exemption removed; early return removed
(loop runs); fail-open removed; work-bound check removed; bound set to 0; scorer ignores `expect_no_url`.

## Gate rounds (owner asked for four, 2026-10-24; round 1 counts the first Gate 1 and Gate 2)

Each round is a Gate 1 (tests, mutation-checked) and a cold Gate 2, then the fixes. Lenses for the
cold reviewers: round 2 async and fail-open correctness; round 3 behavior against `CLAUDE.md`,
`docs/requirements.md` and the scorer and golden changes; round 4 red team (force false traps and
misses). The E2E runs once after the rounds, and once more after the merge.

**Round 1.** Gate 1 (`cc-102-gate1.txt`): 51 mutations, 49 killed, 1 equivalent, 0 survivors; two real
gaps in its own tests found and fixed. Gate 2 (`cc-102-gate2.txt`): not ready, 8 findings.

| Finding | Disposition |
| --- | --- |
| 1. A tract question refused when the model reports a canonical name ("NYC" -> New York City) | Fixed: only a state must be a word the question wrote; other names count. Live: 0 of 160 false traps. |
| 2. A late report stops the loop after tools ran | Fixed: checked on the first turn only (`ask.py`). |
| 3. A non-list `parents` crashes the request | Fixed: only lists are used. |
| 4. "in" counts as Indiana | Fixed: an upper-case token only. |
| 5. No tests for the cap or the slow-split path | Gate 1 wrote the cap tests; slow-split tests added in `test_geography_report.py`. |
| 6. t17 and t03 criteria | t17: owner chose to fix the question (names Cook County, Illinois). t03 criterion is meaningful only with a live model, so it is judged in the E2E. |
| 7. Stale docs | Fixed (`ask-path.md`, `ARCHITECTURE.md`, `DEBUGGING.md`). |
| 8. `CLAUDE.md` carve-out, bundled scope | Owner decision, still open (below). |

Also found by measuring: a parenthetical mid-sentence in the prompt made 7 of 60 number-leading
reports wrong; moved to its own closing sentence (0 of 60). The probe's timeouts were not model errors:
with a 30 s wait the split call is p50 1.0 s, p95 1.5 s, max 3.3 s, and 2 of 245 exceeded 3 s.
Live probe now: 0 of 160 false traps; 5 of 85 fail-open misses (one deictic phrasing, "my county").
Round 1 end state: 770 passed, ruff and mypy clean, `api_src_loc` 4473/4600, `doc_lines` 1796/1800.

**Open for the owner.** (a) `CLAUDE.md` still says MOE, GEOID, universe and alternatives are "in every
response" and excepts only the URL; a refusal has none of them. (b) The diff bundles the comparison
cap and touches many files; the PR must explain both.
