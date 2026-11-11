# CC-104 working state (read this first after any context reset)

Branch `cc-104/structured-geography`, cut from `main`, rebased on 261c18f (2026-11-11). No PR yet. Jira CC-104 is the
status source of truth. Rules: `CLAUDE.md`, `docs/playbooks/run-slice.md` (re-read both). Plan and design:
`evidence/slice-6/cc-104-plan.md` (pre-flight table, owner answers, design refinement, AC/TC matrix).

## The order, and the tools (no improvising)

1. Work from the AC/TC rows (AC1-5, TC1-5 are the Jira ticket's own IDs, plus MET and INH in the plan). Each row gets a test
   that runs the REAL chain (scripted model, real resolver), not stubs. Record rows in `evidence/closure/CC-104.toml`.
2. Build order, `uv run pytest api/tests` after each step (3 min; baseline 1397 passed, 34 skipped, 8 xfailed):
   (a) `geo_list.py` + `tools.py` schema, (b) `geo.py` resolver, (c) `finish.py` redo + frame + `incomplete()`,
   (d) fixtures and tests. Net-negative in api LOC at every commit (budgets have ZERO headroom).
3. Gate 1 in a subagent (owner standing decision 2026-11-10): it commits first, writes `gate1-*.txt`, returns a one-line verdict.
   Every new test is mutation-checked. Commit BEFORE mutating.
4. Gate 2: `/code-review` (Skill `code-review`) on the diff against main, THEN `review-pr` (Skill). Fresh context, code only.
5. E2E exactly once on frozen code, in an isolated worktree, HEAD recorded at start and end. Quote gated keys and
   `demo.misses` only, never `demo.trials`. `metric_compare.py compare ... --refs A,A0`. Then post-merge E2E on main.
6. PR stays draft until every row is verified PASS. The owner merges. Close with `jira_transition.py CC-104 --done`.

## Owner decisions (2026-11-11)

- Tool shape: structured fields. `places` / `parents` as "Name, ST", `level`/`levels` required, `query` dropped from execution.
  Default refinement (mine): `parents` non-empty means listing (no separate `listing` flag), plus a `parent_level` field.
- Leakage baseline landed (#129). p95 waived for the 2026-11-09 run only (#130). Neither covers CC-104's own run.
- Cohort: the owner commits `[cohorts.geography]` to `evals/metric_protocol.toml` (default: `long_tail` + the 8 `trap` goldens
  with `expect_geo_level`). NOT yet confirmed landed. Do not measure P before it does.
- Never raise a budget. Never read sealed sets, E2E transcripts or `demo.trials`. No oracle review, no signing.

## Done

Pre-flight and plan (09469c2, f41873f). Branch rebased on main with #129 and #130 (waiver and baseline both landed).
Steps 2(a)-(c) built in 8e31a5c: `geo_list.py` (`state_of`, `name_token`), `tools.py` schema (`places`, `parents`,
`parent_level`, `level`, `levels`; `query` gone), `geo.py` (`_place`, `_list`, `_stated`), `finish.py` (frame carries
`parent_level`, `numbered` levels, `pointing` bool, `places`; `_split_parents` also checks the unit; no word rescans, no
`query="nationwide"` repair), `ask.py` `_absorb` tracks `places`, `geo_level.ZCTA`. ruff, mypy clean; invariants all ok.
Measured: api LOC 4890 -> 4679, regex call sites 55 -> 28 (delta -27), largest file 408/410, prompt tokens untouched (1095).
Leakage baseline lines deleted with their code: tools.py oregon, geo_list.py x2, geo.py zip x2 and united states x2,
geo_level.py zip x2 (one stays: the `ZCTA` constant).

## Open

- 2026-11-11: owner asked how a famous city without its state is handled. Fixed in the next commit: `incomplete()` counts a
  reported name (letters, no digit) as giving the state; a digit entry must ground itself; `_list` searches a state-less
  county or place parent across states. Gate 1 was started on 0f9841f and stopped by the owner before any transcript was
  written; the tree was restored. Re-run Gate 1 on the commit after this one.

- **Tests are red: step 2(d).** `pytest api/tests` errors at import in `test_ask_tools.py`, `test_finish.py`,
  `test_geography_completeness.py` (they import `find_state`, `place_token`, `split_comparison`, etc., which are deleted) and
  many tests pass `query=`. Migration rules: a test of a deleted prose reader is deleted (never ported); a test of behavior
  (comparison, wildcard parents, ambiguous names, incomplete chains, level fidelity) is kept with the same assertion and
  structured args (`query="Harris County, Texas"` -> `places=["Harris County, TX"]`; `all counties in X` -> `parents=[X]`,
  `level="county"`; a tract in a county -> `parents=["Dane County, WI"]`, `parent_level="county"`).
  Files with `query`: test_ask_tools (68), test_level_fidelity (51), test_ask_loop (16), test_guards (13), test_finish,
  test_tracts_in_place, test_execution_isolation, ask_fixtures, and six others (grep `"query"`).
- Not yet done in the prompt: `prompts.py` GEOGRAPHY paragraph still describes `query`/phrases. Rewrite shorter (budget 1095/1200).
- Docs: `docs/ask-path.md` geography section and `docs/ARCHITECTURE.md` still describe the old resolver; update in the same PR
  (doc_lines is at 1820/1820: net-negative edit only). Fix the stale comment at `evals/leakage_baseline.txt` lines 18-22.
- New fixed-intent tests for AC1-5/TC1-5 on the real chain, then flip the `CC104` xfails in `test_execution_isolation.py`.
- Then: `evidence/closure/CC-104.toml`, Gate 1 (subagent), Gate 2, cohort check, E2E, draft PR.
- Behavior changes to watch in E2E (defaults I took): a listing whose parent is a place or county needs `parent_level`
  (else refused for repair); DC as a state parent must be written "DC" or the full name alone, never "Washington, DC"; `level=null` listing is refused.
- Left to CC-129/CC-135: `wants_acs1`, `requested_years`, `guards.py` question reads. `compare.py:107` is a finding.
- Context: `.claude/hooks/ctx.py` warns at 80% of the window; then finish the phase, update this file, commit, ask for `/clear`.
