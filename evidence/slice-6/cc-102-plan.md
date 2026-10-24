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
(`plan_split`) now also reports `level` and `named` (the places the question itself names). After the
loop's first model turn and before any tool runs, code checks:
- `level` via `geo.detect_level`; `needs` = the level's smallest `requires` in `geography.json`;
- each `named` place must be a run of the question's own words (so a place the model remembers and the
  user never wrote does not count), or `find_state(question)` finds a state;
- a listing the model reports is fine if `legal_predicate(level, {state}, wildcard=True)` allows it
  (all counties list under `state:*`; all tracts do not).

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

## Not verified: needs a live key and API spend

- Whether the real model fills `level` and `named` correctly. The risk is a false trap: the model omits a
  place the question names, so a valid question is refused. Code limits it (a written state always counts,
  garbled replies fail open) but cannot remove it. Measure `answered_rate` and the golden set at the same
  `--repeat`, and p95 against the 20 s ceiling (PLAN.md records 18.9-21.7 s).
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
