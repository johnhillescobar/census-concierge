# CC-104 working state (read this first after any context reset)

Branch `cc-104/structured-geography`, cut from `main`, rebased on 261c18f (2026-11-11). The PR is #131 (draft, head this branch); it is the one to work on. Jira CC-104 is the
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

## 2026-11-22 (end of day): code frozen at 7073bed; closure manifest regenerated for AC1-AC11 / TC1-TC14

Gate 2 ran twice (gate2-final.txt, gate2-final-r2.txt; the playbook's one re-run is spent); every finding fixed with tests and mutation checks except the deferred
ones (T8: a plan with geographies and no dataset binds ACS5, API-only, contract.py has no spare line; T9-T15 notes). Gate 1 transcripts are all in the mutation
index. `closure.py check --pre-merge`: only AC11 and TC14 (the E2E rows) are NOT RUN. Frozen code: 1623 tests pass; api LOC 4998/5100; ask.py AND contract.py
at the 410-line cap; doc lines 1819/1820. NEXT: announce, then the E2E blocks B,P,P,B (owner said run B), each in its own worktree with index_store/, data/raw/ and
.env copied in, NO other agent or git command in either worktree while a block runs, HEAD recorded at start and end; then `metric_compare` once; then fill AC11/TC14.
Comparator FAILs on q42, q43, t01, t14 are the owner's accepted amendment A; any other decrease is not covered. Post-merge E2E precedes Done.

## 2026-11-23: FINAL E2E RAN AND IS RED. Do not merge. AC11/TC14 stay NOT RUN (the run is evidence of a defect, not of closure)

Blocks (sequential, own worktrees, HEAD identical start/end, all steps rc 0 except the floor checks): `e2e-b/` = unchanged main 700d800, `e2e-p/` = branch 4d9445f
(code frozen at 7073bed). `metric_compare` was NOT run on this P: the code must change first, and the compare is run once on the final P.
Aggregates (gated keys; demo.misses ids only). B vs P: long_tail 0.717 / 0.692 (P is under the 0.700 floor); trap 0.907 / 0.741; core 1.0 / 0.917; overall 0.79 / 0.72;
p95 31.5 / 29.9 (both over 20); retrieval@10 0.9 / 0.9; selector@1 0.775 / 0.775; misses 39 / 52; GRID pass 0.986 / 0.781, and the grid at level=tract 1.0 / 0.042.
Misses only in P: q42 x3 and q43 x3 (accepted, amendment A); t01 x3 (accepted); t14 r3 (accepted); NOT covered: t06 x3 (no place named, expects a URL + universe_mismatch:
the same "no place" rule as t01/t14, so it needs the owner to extend amendment A), t10 x3 (P gets acs1 + vintage_gap_2020 instead of overlapping_vintage; B passes: unexplained,
investigate), t13 r1-r2 (wrong table B28011), q04 r3 (core, ambiguous_place + geography_not_nested), q34 r2, q35 r2 (wrong table, probably noise). P fixed 8 B misses (q06, q08, q12 x2, q35 r1, t12 x2, t18).

ROOT CAUSE of the grid collapse (live probe, `e2e-p/live_probe.py`, "All tracts in Cook and DuPage County."): the URLs ARE right (4 and 6 URLs, data returned) but the answer carries
`ambiguous_place` + `state_inferred`. The report lists `states_named` [] (the user wrote none), so geo.py `_written` DROPS the model's "Cook County, Illinois" state, the search runs
across states, and the other same-name counties (Cook GA/MN) stay as extra candidates (`specs[1:]` in `_list`/`_place`), so guards.ambiguous_place fires on a clearly DOMINANT name;
the grid scorer fails every such cell. FIX TO MAKE (code, then Gate 1 for it, then re-run B? no: only P again; compare once): when the dropped state equals the state of the dominant best
match (not `_moved`), keep resolving WITH that state (filter matched to it, so no leftover candidates) and still set state_supplied; apply in `_place` and `_list`. Add tests at the resolver
level (a dominant unwritten name returns ONE state's rows and no extra candidates) and a guard-level test (no ambiguous_place for it), mutation-check them. geo.py has 5 lines left (410 cap).
Then run P once (2.5h block; B stays as measured, same base 700d800), compare once with `register B` in a scratch worktree, and report t10/t13/q04 separately.
OWNER DECISION (2026-11-23, in the ticket's Owner amendments): UNIQUENESS, NOT DOMINANCE. The app never guesses: a place name that matches more than one place and has no state the user wrote is REFUSED
(no selection, URL or fetch) with a message that the question needs more geographic detail, candidates listed. The 4x-population exception (geo_list.dominant(), DOMINANCE=4) is WITHDRAWN. A name matching exactly
one place (DuPage County, Chicago) still resolves. The earlier "keep the dominant name's state" fix is OBSOLETE: do not implement it.
TO IMPLEMENT (next session): (1) in geo.py `_place` and `_list` (and geo_within.tracts_in_place) treat any nationwide match count > 1 as ambiguous (drop the `dominant`/`_moved` tests; `_moved` becomes moot);
applies only when no state was kept (with a written state, keep today's ranking by place class). Keep `state_supplied`/`state_inferred` for a UNIQUE name whose state the model added. (2) deterministic message in finish.unanswered
should say the question needs more geographic detail (no digits). (3) update tests that assume dominance (search: dominant, clear_largest, never_moves, the Wayne/Cook fixtures, test_a_name_with_one_clear_largest_match...),
add: Cook County (3 matches) refused; DuPage (1) resolves; a model-added state never settles a non-unique name. (4) docs: ask-path.md lines on dominance, requirements.md ambiguous_place row, CLAUDE.md untouched.
(5) Gate 1 mutation check, then ONE P block + compare once (B stays 700d800, measured).
GOLDEN HANDLING DECIDED (owner, 2026-11-23, in the ticket as the 'wider amendment', option b): do NOT amend the goldens; every visible golden that names a shared place without a state is an expected, explained miss
(goldens, scorer, hashes unchanged, no bridge); the comparison must name each by id with the reason; the long_tail 0.700 floor is expected to be missed by design on this ticket and is reported, not hidden.
CONSEQUENCE (now decided as above): ~18 visible goldens name a shared place without its state and become expected refusals (core q03 Cook County and q04 Detroit; long_tail q05, q13?, q16, q18, q20, q23, q31, q36, q38, q39, q40;
trap t07, t09, t13, t16, t18, plus the already accepted q42, q43, t01, t06, t14). That drops long_tail answered_rate by roughly 25-30 points (under the 0.700 floor) and the tract grid cells with unqualified counties. Options: (a) amend
those goldens to expect a refusal (dated owner commit; moves cohort/scorer hashes, needs a bridge) - these are "wrong questions" by the owner's own definition; (b) accept them as expected misses by a wider amendment.

OWNER DECISIONS (2026-11-23): t06 IS added to amendment A (expected, explained miss); the T8 deferral is accepted. Both are in the ticket's Owner amendments.

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

## 2026-11-22 (session): uniqueness implemented (53013af); golden curation moves to its own ticket

IMPLEMENTED at 53013af: `dominant()`, `DOMINANCE`, `_moved` and `ResolveGeographyResult.dominant` deleted; geo.py `_place`/`_list` refuse any state-less match count > 1
(`ambiguous_place`, candidates, no selection/URL/fetch); a name matching exactly one place resolves (`state_supplied` -> `state_inferred` when the model added a state).
`finish.unanswered` says the question needs more geographic detail (no digits). ask-path.md updated in place (doc lines 1819/1820). Machines: pytest 1622 passed / 34 skipped,
ruff, mypy clean, invariants ok (regex 18, delta -37), api LOC 4980/5100. Only red budget row: p95 20.714 (inherited from main's committed latest.json).
15 dominance tests rewritten or renamed (Cook/Portland/Wayne/Springfield refused; DuPage and Chicago, one match each, resolve).
NOT DONE: Gate 1 mutation check of these changes (subagent, gate1-uniqueness.txt); requirements.md `ambiguous_place` row needs no change (already says "picks none").

OWNER DECISION (2026-11-22, in chat) -- supersedes "GOLDEN HANDLING DECIDED ... option b" above: the visible goldens that name a shared place without a state are
curated in ANOTHER TICKET (question wording improved so each carries its state), then that work is REBASED into CC-104. So: no accepted-miss list for those goldens,
and the B,P,P,B E2E waits for the curated goldens to land on this branch. No Jira ticket filed yet: a search of project CC found none (CC-134/CC-128 are table-selection stories);
recommend a new story, parent CC-3 only if the owner says so, and ask before filing (epic-scope rule). Owner commits goldens/scorer/hashes (dated commit, needs a bridge).
Amendment A ids (q42, q43, t01, t06, t14) are NOT shared-name cases (no place named); whether they are curated too is for that ticket.

## 2026-11-22: golden curation ticket filed = CC-141 (Bug, Highest, parent CC-3, owner request)

CC-141 curates the visible goldens that name a shared place without a state (and decides the no-place ids q42/q43/t01/t06/t14). CC-104's final E2E (AC11/TC14) waits for CC-141's work to be rebased here.
Gate 1 for the uniqueness rule is done: gate1-uniqueness.txt (20 mutations killed, 2 gaps fixed with tests), HEAD 72ff3af, pytest 1623 passed. NOT yet in `closure-run/mutation-index.txt`
(the manifest pins its sha256 in ~8 fields): regenerate rows and index together after the rebase, since every row is stale at the new head anyway.

## 2026-11-23: rebased onto origin/main c29f22c (CC-141 golden curation and CC-126 deadline are on main); local only, NOT pushed

97 commits replayed with no conflicts (backup `backup/cc-104-pre-rebase4-52ae627`). Pushing needs a force-push (owner's call). Machines after the rebase: ruff/mypy clean on api/src and tests;
invariants ok (regex 18, delta -37); pytest 1738 passed / 34 skipped / 1 failed: `test_census_http.py::test_the_first_response_back_wins` (CC-126, a timing test; fails 1 run in 3 on this tree,
file untouched by this branch; main's own flake, not CC-104).
BUDGET RED: api src LOC 5118 > 5100. origin/main alone is 5045 (CC-126 added to it); CC-104 is +73 over main in api/src. The cap cannot be raised here. Options: (a) trim >= 18 lines from api/src
with tests (each change is new code: Gate 1 mutation check, and the playbook's one Gate 2 re-run is spent), or (b) the owner raises `api_src_loc` in their own commit with a written reason.
p95 20.56 is main's committed latest.json (inherited). Every closure row is stale at the new head; the E2E has not started. The CC-141 goldens are on main now, so nothing else blocks the E2E except the LOC cap.

## 2026-11-23 (later): owner merged #145 (api_src_loc 5200); rebased onto origin/main e96f3a8, local only, NOT pushed

The LOC block is cleared: api src LOC 5118/5200; invariants hold; ruff, mypy clean; the only red budget row is p95 20.56 (main's committed latest.json). Backup `backup/cc-104-pre-rebase5-3848dda`.
Only budgets.toml differs from the previous tree, so the 2026-11-23 pytest run (1738 passed, 1 CC-126 timing flake) still stands. Next: force-push (owner's word), refresh closure rows at the new head, B,P,P,B E2E, metric_compare once, draft PR.

## 2026-11-23 (later): force-pushed (d72434a); closure rows refreshed at d72434a

Pushed with --force-with-lease; PR #131 (draft) updated. All 23 AC/TC command rows were re-run at d72434a (pass counts as before except AC9 22 and TC1 15, which pick up the uniqueness tests);
AC9, AC10 and TC12 `-k` filters were updated for renamed or added tests; gate1-uniqueness.txt added to the mutation index; every pin and `tested_head` rewritten. `closure.py check --pre-merge` now blocks ONLY on
AC11 and TC14 (the E2E). Not Gate 2 read: the uniqueness change (the one re-run is spent); say so in #131's body. NEXT: the B,P,P,B E2E blocks (owner says when), `metric_compare` once,
fill AC11/TC14, update #131's body, mark ready.

## 2026-11-24: E2E in flight; OWNER DECISION on t10 (option C)

Blocks b1, p1, p2 done (HEAD identical start/end: b = 29c0518, p = e86882d); b2 running (expected ~07:45 UTC). Results are in `e2e-r3-{b1,p1,p2}/` (committed with the E2E, not yet).
Preliminary (aggregates only, no metric_compare yet): grid P 1.0/1.0 vs B 0.986; long_tail B .692, P .633/.700; trap B .796, P .704/.722; p95 ~29-30 s everywhere (inherited, load-driven);
selector_at_1 P .425 x2 but b2 (unchanged main) also .425 at 06:21: environmental (Gemini rerank), not this branch; the b1 .75 is the odd one. prompt_hash differs in P (CC-104 rewrote the geography prompt).
OWNER DECISION (2026-11-24, in chat): t10 is an expected, explained miss (option C): no code change, no golden change, no P re-run. Cause: main's overlapping_vintage reads the question; this branch reads fetched
ACS5 vintages only, and a dense series becomes ACS1 annual (valid, no overlap). A golden fix (warning only for ACS5 answers) goes to a separate curation ticket. Recorded as a CC-104 Jira comment.
t09 (wrong table B28010, 2/6 P trials) is NOT excused: probably selection variance under the degraded rerank; report it. NEXT: after b2 ends, quote gated keys and demo.misses for all four blocks, run metric_compare ONCE
(`register B` for the B blocks as needed; refs A,A0), name t10 and each other miss with its reason, fill AC11/TC14, update #131, commit evidence.

## 2026-11-24 (late): FINAL E2E DONE AND RED. AC11/TC14 = FAIL. PR #131 stays draft.

All four blocks (b1 p1 p2 b2) finished, HEAD identical start/end each (orchestrator log). metric_compare ran ONCE per P run (p1, p2) against A, A0, B1, B2 (B1/B2 = the two main blocks, registered in a scratch worktree
so evidence/metrics is untouched; see e2e-r3-compare/): VERDICT FAIL both. Aggregates: long_tail B .692/.675, P .633/.700; trap B .796/.778, P .704/.722; core B .75/.75, P .75/.583; p95 ~29-30 s everywhere;
grid B .986/.986, P 1.0/1.0; selector_at_1 .425 in p1/p2/b2 (rerank environment), .75 in b1. FAIL vs B: trap trial rate (-0.056..-0.093), long_tail empty answers (+0.042..+0.075), rows per family; p1 also long_tail -0.05.
What is explained: t10 (owner option C). What is NOT: trap and core misses beyond t10 (t09 2/3 in p1, t08, t18, q04 3/3 in P vs 2/3 in B), long_tail empty answers (per-id causes not diagnosed), under the degraded rerank that also hit b2.
No rerun, no tuning (protocol). The honest state: CC-104 fixes the grid (1.0) and makes ambiguity/incompleteness fail loudly, but does not improve the demo scoreboard and is red on trap/empty answers vs B.
NEXT (owner decides): diagnose the non-t10 trap/empty-answer deltas from demo.misses (reasons only), or accept with a written waiver per row, or fix and re-run P blocks. Post-merge E2E not applicable until merge.
