# CC-141 working state (read this first after any context reset)

Branch `cc-141/golden-state` (worktree `.worktrees/cc-141`), cut from origin/main 9a36dff. No PR yet. Jira CC-141 is In Progress
(status source of truth). Rules: `CLAUDE.md`, `docs/playbooks/run-slice.md`. Plan, pre-flight, scope change and decisions: `plan.md`.

## Scope (owner, 2026-11-23, in chat; recorded in plan.md)

26 visible goldens get their state; the 16 phrasing-grid tract cells g054-g069 get a state and a `parent_state` field (the grid scorer
requires that state's counties); t01, t06, t14 each gain a county (Fulton GA, LA CA, King WA: MY defaults, revertible); the live check
`scripts/verify_golden_places.py` is the first line of `make demo`. I once widened scope without asking and was told so: ask before
adding scope, and say what is a default.

## Done

- Pre-flight (`preflight.py/.txt`), curation, `scripts/verify_golden_places.py` (AC1 live, AC2 with `--base`), `verify-before*.txt`,
  `verify-after.txt` (re-capture at the E2E head), `url-grid-scan.txt` (the generated grid needs no change).
- Gate 1: `gate1.txt` + `gate1-fixes.txt` (goldens + checker), `gate1-grid.txt` (grid check, parent_state scorer, ADDED path; 46 mutations, no
  GOOD baseline lines in that file, the subagent's own).
- Gate 2: `gate2.txt` (round 1) -> `gate2-fixes.txt`; round 2 `gate2-r2.txt` (NOT YET only for pending evidence: manifest, E2E, bridge) ->
  `gate2-r2-fixes.txt` (word edge, county-cell parent_state, empty parents; 5 mutations killed). The one allowed re-run is SPENT.
  Kept, not fixed, to disclose in the PR: nit 1 (hand annotation can be mislabelled), nit 2 (url_grid_scan.py scans wording, a one-off
  fixture lint outside api/src), nit 7 (the live fetch has no retry; a blip aborts the demo loudly), nit 4 (the instrument moved: cohort
  hashes change and retrieval@10 sits exactly at its 0.90 floor, so report it, never tune).
- Red on origin/main, NOT from this branch: `check_budgets` doc lines 1822/1820 and p95 20.714. Never raised.
- The first E2E (HEAD 5e463bf) was stopped and its processes killed; void.

## E2E done (2026-11-23) at frozen code 133b3bc, HEAD identical start and end, isolated worktree (removed after copy)

`e2e/` holds the artifacts (transcripts never read). Gated keys, repeat 3: long_tail 0.725 (floor 0.70 met), overall 0.79, core 0.917, trap 0.907;
retrieval_at_10 0.90 (AT the floor), selector_at_1 0.75, p95 23.758 (ceiling 20, FAIL; red on origin/main too); grid 210/210 trials, pass rate 0.986,
tract level 1.0 (the 16 curated cells pass), only g028 misses (3/3, untouched). demo and check_budgets exit 1 for p95 (+ doc lines 1822, both inherited).
Comparator (`compare.txt`, ONE run, scratch checkout holding `bridge-entry.json`): VERDICT FAIL = the measured result; TC3 completes under the bridge.
It cannot isolate the curation (A is an older run on an older model; api/src is byte-identical to main). Per-id: 29 curated ids 13 misses in A, 10 now.

## Manifest `evidence/closure/CC-141.toml`: AC1 AC2 TC1 TC2 TC3 PASS; AC3 and AC4 NOT RUN on purpose

`closure.py check --pre-merge` blocks only on AC3 and AC4. Any later change under scripts/, evals/, api/tests, Makefile makes the PASS rows stale.

## Next

1. OWNER, own commit on main: land `evidence/slice-6/cc-141/bridge-entry.json` as `evidence/metrics/bridges.json` (check_invariants forbids a bridge added on a
   branch). Then rebase this branch on that main, re-run AC3 (freeze + compare) and mark it.
2. Push, DRAFT PR (not yet pushed: ask first), body per gate, the numbers above, the ticket corrections, the defaults, the disclosed nits (1, 2, 4, 7), and the
   two inherited red budget rows. Jira comment with the scoreboard once the PR exists.
3. Owner merges. Post-merge E2E on main. Rebase CC-104 onto main with a backup branch (AC4), re-run its rows. `jira_transition.py CC-141 --done`.

## Owner items to surface in every status message

- Defaults (revertible): the three counties for t01/t06/t14; q42/q43 and holdouts curated; the bridge is a relabel of A. CC-104's B block must run on the
  curated goldens and grid. Amendment A in CC-104 is fully covered by this ticket (q42, q43, t01, t06, t14), so it can be withdrawn.
- retrieval_at_10 sits exactly on its 0.90 floor after the wording change; a future dip is a floor failure to report, never to tune against.
- Inherited red on origin/main: doc_lines 1822/1820, p95 20.714 (23.758 in this run). A waiver or raise is an owner commit.

## Post-merge (main c29f22c: #142 and #144 merged)

E2E on main in an isolated worktree, HEAD identical at start and end (`e2e-post/`, transcripts unread). Gated keys, repeat 3: long_tail 0.717 (floor 0.70 met),
overall 0.78, core 0.833, trap 0.907; retrieval_at_10 0.90 (at floor), selector_at_1 0.75, p95 27.021 (ceiling 20: FAIL, tracked on CC-142; red on main before this ticket);
grid 210/210, pass rate 0.986, tract level 1.0, only g028 misses (untouched). check_budgets red on doc lines 1822/1820 and p95; invariants held; live place check OK.
Comparator (`e2e-post/compare.txt`, one run, real bridge on main): A reads as bridged, no hash FAIL for A; VERDICT FAIL (p95, selector_at_1 vs A, trap, core; A0 unbridged).
AC3 PASS. AC4 NOT RUN: the owner runs the CC-104 rebase and rows in another agent; link its evidence here, then close with jira_transition.py.

## AC4 (2026-11-24)

AC4 PASS: CC-104 is rebased onto main e96f3a8 (CC-141 goldens, bridge, budget raise are ancestors of its tip e86882d) and its AC1-AC10, TC1-TC13 are PASS at d72434a
(`ac4-cc104-rebase.txt`). Its AC11 and TC14 (E2E) stay NOT RUN on CC-104's own closure. Its uniqueness change had no Gate 2 read. `closure.py check --ref origin/main` exits 0.
Next: owner merges this evidence PR, then `jira_transition.py CC-141 --done` from main.
