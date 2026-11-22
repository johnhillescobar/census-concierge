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

## Cycle 4 (owner request 2026-11-12: "ALL AC AND TC fully met")

Audit found AC3 NOT met (Gate 2 round 1 had called it weak; carried unfixed). Fixed in 52662e7: one `GeoIntent` on
`record.intent` (loop group + report group + `adopt`, `intent_of`); `plan_split` returns it; loose fields
(`asked_levels`, `geo_queries`, `unmet_levels`, `tables_only`) gone. Gate 1 (gate1-ac3.txt, 75 mutations, 9 BAD each followed by
a stronger test) -> Gate 2 once (gate2-ac3.txt, READY, E1-E7 NOTE) -> E1 (listing flag must be `is True`), E2/E6 (docstring)
fixed with a test and mutation (gate1-ac3-gate2-fixes.txt). E3 unreachable, E4 benign, E5/E7 known. Stale item removed: R1 is
fixed (probe: county given without state is refused). Do not run Gate 2 again.
Owner decision 2026-11-12: "Fix them inside CC-104" (the 5 isolation xfails). Done in 76d20f9: `wants_acs1`, `requested_years`,
`question_years`, `year_span` and their regexes deleted; plan path and `overlapping_vintage` no longer read the question;
`zcta_not_zip` fires on a ZCTA geography / `860` rows; recovery takes `dataset` and `years` from the split report (validated by
type and 2000-2100); the fetch tool's asked-years hook falls back to the report's years (a pinned plan outranks it). Gate 1
gate1-timeprod.txt (36 mutations, 13 BAD each strengthened) -> Gate 2 once gate2-timeprod.txt (NOT YET: G1, G2, G8 SHOULD) ->
fixed with tests and mutation (gate1-timeprod-gate2-fixes.txt). Known and kept: G3 (overlap warning no longer fires when ACS5 thins
a series to non-overlapping years), G6 (a missing report gives ACS5 for a 1-year ask; a plan with no dataset is the user's plan),
G9 (guards.py still reads the question for universe/combine/derived/median warnings: CC-122). Do not run Gate 2 again.
Manifest `evidence/closure/CC-104.toml`: all ten rows PASS at the code head; `closure.py check --pre-merge` prints CLOSURE OK.
Machines at that head: pytest 1505 passed / 34 skipped / 0 xfailed; ruff, mypy clean; invariants ok (regex 18, delta -37); api LOC
4801/4890; prompt 1050/1200. RISK for the E2E: time and product are no longer backstopped by code reading the question; a model
that omits years or the 1-year product now gets the latest ACS5 unless the report supplies them. Watch time questions in demo.misses.
Any later change to api/src or api/tests makes every row stale: re-run the row commands, refresh closure-run/.

## Rebase onto origin/main 7239f32 (2026-11-21, owner request) -- supersedes the Open items below where they conflict

Main moved 47 commits: GPT-6.2 Sol on the Responses API (CC-138, #134/#135), `api_src_loc` 5100 (#136). Rebased 57 commits (backup branch
`backup/cc-104-pre-rebase-f6fa608`); two conflicts (docs/ask-path.md, ask.py `ExecutionRecord` fields: kept main's `retained_legs`,
dropped `geo_queries`/`tables_only`). main's CC-138 tests called `resolve_geography` with `query`; moved to `places` (69ad347, no source change).
plan_split goes through the same `_openai_complete`, so the report call is already on gpt-6.2-sol. Machines at 69ad347: pytest 1547 passed / 34
skipped; ruff, mypy clean; invariants ok (regex 18, delta -37); api LOC 4800/5100; all ten rows re-run at 69ad347, `closure.py check --pre-merge`
CLOSURE OK. The 2026-11-12 E2E (long_tail 0.467, RED) was the old model and is void.

E2E r2 (`evidence/slice-6/cc-104/e2e-r2/`, frozen code 69ad347, driver head 486ff12 identical start/end, all steps rc=0): long_tail 0.775 (93/120),
trap 0.889, core 1.0, overall 0.823; p95 19.949s (slowest 26.666s), under the 20s ceiling, so no waiver is needed or recorded; retrieval@10 0.9,
selector@1 0.825; grid 210/210; check_budgets and invariants rc=0 (regex 18, delta -37; api LOC 4800/5100). metric_compare (once, vs A,A0,
`compare.txt`): VERDICT FAIL. PASS: all floors, long_tail trial rate +0.092 (lower +0.017), case rate +0.100. FAIL: trap trial rate -0.074 (18
families), rows per family (3 families), long_tail empty answers +0.025, A0 (no bridge, inherited from CC-133). INCONCLUSIVE: trap case, core (under 30
families). A is the 2026-11-09 old-model run, so the comparison mixes the model change (CC-138) with CC-104; there is NO same-day control of origin/main
7239f32 yet. Next default: run it (same driver, e2e-main-r2/, in its own worktree) before drawing any conclusion. Trap misses t05/t10 (3/3 each, missing
`ambiguous_place` / `overlapping_vintage`) match the earlier diagnosis items 3 and 4 in PR #131; not re-diagnosed on this model. Worktree E2E prerequisites
(this cost an invalid attempt twice): copy gitignored `index_store/`, `data/raw/` and `.env` from the main checkout before the driver.

## 2026-11-22: rebased onto main 989f2b4 (CC-125 promoted); the ticket now has AC1-AC11 and TC1-TC14

Rebased 73 commits onto origin/main 989f2b4, no conflicts (backup `backup/cc-104-pre-rebase2-ee4eab3`); pytest 1564 passed / 34 skipped, ruff, mypy,
invariants clean; the only red budget row is p95 26.391 from main's committed CC-125 `evidence/latest.json`. CLAUDE.md "URL is the product" now says
"too incomplete or ambiguous to search" (owner instruction; R1 closed by classification, no second exception). The same-day control of main was stopped by
the owner; `e2e-main-r2/` holds a replicate of the CC-104 code (NOT a control) and the aborted log.

The owner rewrote the Jira description (read 2026-11-22): the manifest `required` list (AC1-5, TC1-5) is incomplete. Status of the new ones:
AC6/TC6/TC7 same-state single-parent precedence: implemented + mutation-checked (gate1-e2e-single-parent.txt, gate1-rebase-r2-fixes.txt); rows to write.
AC7/TC8/TC9 a corrected call supersedes a refused invalid-level call: NOT implemented (`intent.unmet` in geo_level.py keeps a refused level).
AC8/TC10/TC11 report years/dataset never change a built fetch, mismatch warns: dataset done (no redo of a built URL, `dataset_mismatch`); YEARS NOT done
(`question_years` in ask.py:377 still lets `intent.years` steer a fetch_data call that stated none, so the rendered URL's vintage can differ from the year fetched).
AC9/TC12 a model-supplied state is recorded inferred and cannot suppress ambiguity: NOT done in code (only the prompt/tool text tells the model not to supply a state for a single place).
AC10/TC13 no national fallback: tests exist (test_level_fidelity, test_geography_intent); map and confirm TC13 specifically.
AC11/TC14 evidence: E2E vs B, A and L on frozen code, then post-merge. B (same-window pre-change main) is REQUIRED by the ticket text but the owner stopped the control: ask which governs.
Do not start the final E2E until AC7, AC8-years and AC9 are implemented, mutation-checked and Gate 2 read; the E2E must run on frozen final code.

## OWNER DECISIONS PENDING / MADE (2026-11-22) -- remind the owner of the pending one in every status message

DECIDED 2026-11-22 -- B: the owner said YES, run it. B (unchanged origin/main at the time) runs in the same window as the candidate in alternating blocks
(protocol `B,P,P,B`), never at the same moment (shared API load distorts p95), after the code is frozen. Each block ~1.2h (demo + grid) in its own worktree
with index_store/, data/raw/ and .env copied in; no subagent or git command in either worktree while a block runs; record HEAD at start and end.
MADE: (1) the dedicated geography cohort is deprecated; measure on long_tail/trap/core plus fixtures (recorded in the ticket, "Owner amendments").
(2) Ambiguity fails loudly everywhere: a name with no dominant match is refused (no selection, URL or fetch) with candidates and a message, for
direct places, comparisons and listings (CLAUDE.md now says "too incomplete or ambiguous to search"). (3) AC10/TC13 are NOT met: a silent "done"
with nothing rendered and a partial comparison must fail loudly. (4) AC8 approved: report years stop feeding fetch_data, `year_mismatch` warns,
unpublished-vintage warns. (5) A multi-year question that names no years is ambiguous and is refused. (6) AC9: independent report supplies
`states_named`; a state not in it is dropped and the bare name is checked for dominance; unknown provenance is untrusted (fail loud).
AC7: probe first (a refused level counts as unmet only if it equals the level the report states).

## 2026-11-22 (later): implementation of the owner decisions is done; Gate 1 done; Gate 2 next

Implemented and pushed: AC7 (`GeoIntent.unserved`), AC8 (report years never steer a fetch, `year_mismatch`, `unpublished_vintage`), the multi-year-with-no-years
refusal, the no-place refusal, ambiguity refused for direct places and comparisons (all-or-nothing), `unanswered` (a loud end, never a silent "done"),
AC9 (`states_named` from the independent report; unknown is not written; `state_supplied`). Gate 1: gate1-ac7-ac10.txt (50 mutations killed, 8 gaps found and
strengthened, 1 equivalent mutant: `len(matched) > 1`, removed). Golden flips (owner amendment A, 2026-11-22, in the ticket): q42, q43, t01, t14 (and q13 only if
its name proves non-dominant on live populations) are expected, explained misses; goldens, scorer and hashes unchanged. Budgets: api LOC ~4968/5100; ask.py and
contract.py sit AT the 410-line cap, so any fix there must be net-zero. NEXT: Gate 2 (cold; /code-review then review-pr; one re-run only), then closure rows AC6-AC11 and
TC6-TC14 (the manifest still lists AC1-5/TC1-5 and is stale), then B,P,P,B E2E blocks (owner: run B) in separate worktrees, no other activity during a block.
The post-rebase ledger/latest.json on main come from CC-125's post-merge run (main 989f2b4: long_tail 0.733, p95 20.714).

## Open

- **Cohort (owner decision 2026-11-12): the owner commits the cohort first** (any `metric_compare.py` loader change it needs
  included), in their own commit on `main`. I offered three options: existing `long_tail` (recommended, 47/48 ceiling), a field
  filter (instrument change + bridge), or the owner commits. The owner chose the last. WAIT for it: `git fetch; git grep
  cohorts.geography origin/main -- evals/metric_protocol.toml`. Then rebase this branch on that `main`, re-run the machines,
  correct plan D8 and the Jira comment, and only then run the E2E. Do not measure P before it lands.
- **Owner instruction 2026-11-12: every `budgets.toml` floor must be green except p95.** Only `answered_rate` is red (0.683,
  inherited: the 2026-11-09 run on main, long_tail 82/120; 0.700 needs 84/120). It can only be cleared by this branch's own E2E
  (`run_demo.py --repeat 3`), never by editing the budget, the instrument or the prompt against known misses. Of the
  2026-11-09 long_tail misses, q06 (1 trial) and q08 (2 trials) are this story's level misses; fixing them would give 85/120
  = 0.708, but that is a hypothesis until measured. If the run is still below 0.700 the scoreboard is red and the PR stays
  open; report it, do not tune. p95 on this run is unwaived: a waiver is the owner's `[waiver]` commit, if they want one.
- Machines re-run 2026-11-12 at HEAD 6c9eeff: pytest 1446 passed / 34 skipped / 5 xfailed; ruff clean; invariants exit 0
  (regex 28, delta -27); budgets: only `answered_rate` 0.683 red (inherited), p95 row waived for the 2026-11-09 run only.
  `make` is not installed on this machine: run the Makefile recipe lines directly.
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
  `geography_level_unverified` treats `asked_levels == [None]` as stated (CC-114).
- **Behaviour changes to name in the PR:** listing parents need `parent_level` unless a bare state; `level=null` listing
  refused; `parents` with other places/levels refused (same names again are redundant); several county/place parents
  must each carry their state; an unqualified listing parent that no match dominates returns candidates.
- Context: `.claude/hooks/ctx.py` warns at 80%; then update this file, commit, ask for `/clear`.
