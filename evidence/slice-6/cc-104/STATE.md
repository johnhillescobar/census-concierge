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

## Done (2026-11-11, HEAD 473628a)

Pre-flight/plan; source rewrite; test migration (subagents for the large files, diff reviewed); prompt and docs;
isolation harness findings flipped. Gate 1 (gate1.txt: 63 GOOD, 9 BAD each followed by a strengthened or restored
test). Gate 2 round 1 NOT YET with F1-F8 (gate2.txt), all fixed (gate1-gate2-fixes.txt). Gate 2 round 2, the one
allowed re-run, R1-R8 (gate2-r2.txt), fixed except R1 (owner decision) and the noted follow-ups
(gate1-rerun-fixes.txt). Owner decisions after that: a famous city needs no state (a reported name gives it);
an unqualified listing parent is taken only if its best match has 4x the people of the next, else
`ambiguous_place` candidates and no selection (gate1-dominance.txt). Direct single places keep largest-wins.
Machines at HEAD: pytest 1412 passed / 34 skipped / 5 strict xfail (4 CC-129, 1 ZIP CC-135); ruff, mypy clean;
check_invariants exit 0, regex call sites 28 (delta -27); api LOC 4771/4890, largest file 409/410, prompt tokens
1033/1200, doc lines 1806/1820; p95 row waive (2026-11-09 run only); answered_rate 0.683 FAIL (inherited).

## Cycle 3 (owner request 2026-11-11: "solve the Gate 2 issues and run another cycle")

Ticket: Jira CC-104 moved To Do -> In Progress with a status comment (2026-11-11). Workflow: `evidence/closure/CC-104.toml`
exists, all 10 rows NOT RUN on purpose (well-formed; `closure.py check` blocks until rows are PASS). Fixed for the cycle: R1
via the `given` report (a unit identified by its number needs parents the question states; mutation transcript
gate1-given.txt). Cycle order: Gate 1 subagent on the new HEAD (gate1-c3.txt) -> fix -> Gate 2: /code-review then review-pr
(gate2-c3.txt) -> fix each finding with tests + mutation. After that the E2E waits on the owner's cohort commit.

Cycle 3 progress: Gate 1 c3 (gate1-c3.txt, 117 mutation runs) -> one finding fixed (gate1-c3-fixes.txt) -> Gate 2 c3
NOT YET with C1-C10 (gate2-c3.txt) -> all fixed with tests (gate1-c3-gate2-fixes.txt, 10 GOOD). C10: the manifest `head`
is refreshed with every commit that changes code; keep it equal to the head the rows were last run at. The one allowed Gate 2
re-run for this cycle ran (gate2-c3-r2.txt, D1-D10): D2, D4, D7 fixed with tests (gate1-c3-r2-fixes.txt, GOOD), D6 not
reachable, D1/D3/D5/D8-D10 kept with reasons. Owner: stop re-running Gate 2 -- no further round.

## Open

- **Owner decision needed (cohort):** the protocol loads cohorts by `tier` only, so `[cohorts.geography]` as first described
  (goldens that carry expect_geo_level) cannot be loaded. Recommended: use the existing frozen `long_tail` cohort (48 families,
  all carry expect_geo_level; the metro golden counts as a miss until CC-106, 47/48 = 97.9%). Option 2: add a field filter to
  metric_compare.py (instrument change). Correct plan D8 and the Jira comment once chosen. Do not measure P before it.
- **E2E, once, on frozen code**, in an isolated worktree, HEAD identical at start and end:
  `bash evidence/slice-6/cc-133/e2e-r4/driver.sh` pattern (copy it to `evidence/slice-6/cc-104/e2e/`). Quote gated keys
  and `demo.misses` only; `metric_compare compare ... --refs A,A0`; then `git checkout -- evidence/latest.json` and delete
  root `evidence/grid-latest.json` / `grid-trials.jsonl`. Watch: repair turns from refusals (parent_level, state-less
  parents, mixed fields), `ambiguous_place` on listings, p95 against A (25.472) and the 20s ceiling (unwaived for this run).
- **Closure:** write `evidence/closure/CC-104.toml` (AC1-5, TC1-5; evidence hashes, mutation index = the gate1*.txt files,
  reviewer = gate2.txt / gate2-r2.txt); `uv run python scripts/closure.py check evidence/closure/CC-104.toml --pre-merge`.
- **PR:** draft until every row is PASS; body states each gate's findings (including R1 and the follow-ups), the numbers,
  and the behaviour changes below. Owner merges. Then post-merge E2E on main, then `jira_transition.py CC-104 --done`.
- **Follow-ups to list in the PR, not fix here:** `compare.py:107` reads the question (warning trigger); `wants_acs1` and
  `requested_years` read words (CC-129); a partial comparison returns only the legs that resolved (old behaviour);
  `geography_level_unverified` treats `asked_levels == [None]` as stated (CC-114); R1 (a named county without its state
  gives the state, so "tract 12 in Cook County" is not refused).
- **Behaviour changes to name in the PR:** listing parents need `parent_level` unless a bare state; `level=null` listing
  refused; `parents` with other places/levels refused (same names again are redundant); several county/place parents
  must each carry their state; an unqualified listing parent that no match dominates returns candidates.
- Context: `.claude/hooks/ctx.py` warns at 80%; then update this file, commit, ask for `/clear`.
