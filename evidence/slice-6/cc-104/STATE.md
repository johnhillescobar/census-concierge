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

Pre-flight and plan (09469c2, f41873f). Branch rebased on main with #129 and #130. Invariants all ok; budgets: only
`answered_rate` 0.683 < 0.700 red (inherited from CC-114's close, not waivable by the p95 mechanism).

## Open

- No product code changed yet. Next action: step 2(a).
- Baseline lines this change must delete in the same change that removes their code (a stale line fails the build):
  `evals/leakage_baseline.txt` `geo_level.py` x3 (keep one if a single `zcta` constant remains, see plan) and `geo.py`
  `regex2|united states` x2. Keep `contract.py` x2, `geo.py` 'zip code tabulation area' x2, `geo_list.py`, `guards.py`.
- Regex call sites: 55 on main. The story must lower it; report the delta from `check_invariants --base origin/main`.
- Left to CC-129/CC-135, not this story: `wants_acs1`, `requested_years`, `guards.py` question reads. `compare.py:107`
  (`_COMPARE` on the question) is a warning trigger; list it as a finding. The 7 CC-133 xfails owned by CC-104/129:
  the geography ones must flip to passing here; the strict marker forces the removal.
- The ZIP xfail reason string in `test_execution_isolation.py` still says "no PLAN story owns it"; it is CC-135 (change with
  the next edit to that file, then re-run AC4/TC4 of CC-133).
- Context: `.claude/hooks/ctx.py` warns at 80% of the window; when it does, finish the phase, update this file, commit, and
  ask the user to run `/clear`.
