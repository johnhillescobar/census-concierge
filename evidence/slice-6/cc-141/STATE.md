# CC-141 working state (read this first after any context reset)

Branch `cc-141/golden-state` (worktree `.worktrees/cc-141`), cut from origin/main 9a36dff. No PR yet. Jira CC-141 is In Progress
(status source of truth). Rules: `CLAUDE.md`, `docs/playbooks/run-slice.md`. Plan, pre-flight and decisions: `plan.md` here.

## Done (2026-11-22/23)

- Pre-flight (`preflight.py`, `preflight.txt`): 26 visible goldens name a shared place with no state; ticket corrected (q42/q43 are
  shared-name cases; scorer hash does not move). Jira comment posted.
- Curation (c31feb2): 26 `text` edits, state inserted right after the place. `scripts/verify_golden_places.py` proves AC1 against live
  listings and, with `--base origin/main`, AC2. `verify-before.txt` (25 problems at origin/main; q23 already wrote "Texas"),
  `verify-after.txt` (OK).
- Gate 1 (`gate1.txt`, subagent): 44 mutations, 43 killed first pass, 1 strengthened. Fix `gate1-fixes.txt`: diff check needs
  "<place>, <State>" directly after the place and absent from the old text (one test survived its mutation, strengthened, rerun).
- Gate 2 (`gate2.txt`, subagent, /code-review high then review-pr): NOT YET only for the pending steps R1-R3 (bridge, manifest,
  post-merge). Fixed: R4/R5 (`_carries` scan replaced by the literal `_written`, `gate2-fixes.txt`, 3 mutations killed).
  Kept, not fixed: R6 (the state-qualified name is proven to exist, not to be unique inside the state; the resolver ranks by class
  when a state is written), R7 (the live check is not in `make check`; follow-up), R8 (refresh matrix heads in the manifest).
  Decision (default): no second Gate 2 round; the fixes remove a heuristic from a script outside api/src, with tests and mutation.
- Machines at 9998aac: pytest green, ruff/mypy clean, invariants exit 0, no new regex. `check_budgets` red on doc lines 1822/1820 and
  p95 20.714: BOTH ALREADY ON origin/main (confirmed on a clean archive), this branch changes neither. Not raised, not mine.

## In flight: the E2E

Frozen code = HEAD 5e463bf (driver committed). Isolated worktree `.worktrees/cc-141-e2e`, detached at 5e463bf, with index_store/,
data/raw/ and .env copied in. Driver `evidence/slice-6/cc-141/e2e/driver.sh` (eval_retrieval x3, run_demo --repeat 3, run_grid --repeat 3,
check_budgets, check_invariants); log at `evidence/slice-6/cc-141/e2e/log.txt` IN THAT WORKTREE. Do not run git, edit, or start any live
API job in it or beside it until `DONE` is in the log. HEAD must be 5e463bf at start and end. Never read the .out transcripts or demo.trials.

## Next

1. After DONE: copy `e2e/` artifacts (latest-after-demo.json, grid files, log, .out/.err) into `.worktrees/cc-141/evidence/slice-6/cc-141/e2e/`.
   Quote gated keys + `demo.misses` only. `git checkout -- evidence/latest.json`; delete root `evidence/grid-latest.json` / `grid-trials.jsonl`
   in the E2E worktree (they were tracked there? check `git status` only after DONE).
2. AC3/TC3: `uv run python scripts/metric_compare.py freeze` (new cohort hashes long_tail ab5c9c2ffa0bbb1c, trap 27ef452a0959cfe6,
   core 622f5f5937db5bac; scorer 6054312479188110 unchanged; old: 3357c07b051d8f28 / 86599fef7d3afc08 / 3f0faaf0e5df706b). Write
   `evidence/metrics/bridges.json` (ref A; from/to scorer equal; from/to cohorts as above; `rescored_run` = A's run file, `rescored_sha256`;
   note: text-only curation, the trials answered the old wording, so a comparison against it mixes curation with code). Then ONE
   `metric_compare compare <candidate latest-after-demo.json> --refs A,A0`; a FAIL verdict is the product's result, report it. TC3 = it completes
   under the bridge (A0 has no bridge: say so). Per the protocol never rerun until green.
3. `evidence/closure/CC-141.toml` (AC1-AC4, TC1-TC3; rows with command, observed, evidence+sha256, tested_head, mutation index = gate1*/gate2-fixes,
   reviewer = gate2.txt). AC4 (CC-104 rebase and its rows re-run) can only be PASS after merge: leave NOT RUN until then, never PASS early.
   `uv run python scripts/closure.py check evidence/closure/CC-141.toml --pre-merge`.
4. Draft PR (body: each gate's findings, the numbers, the ticket corrections, defaults, the two inherited red budget rows). Owner merges.
   Post-merge E2E on main, then rebase CC-104 onto main (AC4), then `jira_transition.py CC-141 --done`.

## Owner items to surface in every status message

- Defaults taken (revertible): q42/q43 curated here; t01/t06/t14 left to CC-104 amendment A; holdouts curated; grid files out of scope
  (they carry unqualified counties too: CC-104 follow-up); bridge is a relabel of A, so CC-104's B block must run on the curated goldens.
- Inherited red on origin/main: doc_lines 1822/1820 and p95 20.714. A waiver or raise is an owner commit.
