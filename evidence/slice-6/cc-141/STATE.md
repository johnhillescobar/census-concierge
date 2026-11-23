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

## Next (in order)

1. Full machines at the frozen head (pytest, ruff, mypy, invariants), then a NEW isolated worktree detached at that head with index_store/,
   data/raw/ and .env copied in, and `bash evidence/slice-6/cc-141/e2e/driver.sh` (verify, eval, demo, grid, budgets, invariants). HEAD must be
   identical at start and end (log.txt). No git, edit or live API job in that worktree or beside it until DONE. `make e2e` / e2e_capture.py
   do NOT run the live place check: the driver does (step v).
2. Copy artifacts into this branch's `evidence/slice-6/cc-141/e2e/`; quote gated keys + `demo.misses` only; never `demo.trials`.
3. AC3/TC3: `metric_compare.py freeze` (new cohort hashes; scorer hash unchanged); `evidence/metrics/bridges.json` (ref A; relabel; note says the
   old trials answered the old wording); ONE `metric_compare compare ... --refs A,A0`; FAIL verdicts are the product's result.
4. `evidence/closure/CC-141.toml` (AC1-AC4, TC1-TC3; AC4 stays NOT RUN until after merge), `closure.py check --pre-merge`.
5. Draft PR; owner merges; post-merge E2E on main; rebase CC-104 onto main with a backup branch (AC4); `jira_transition.py CC-141 --done`.

## Owner items to surface in every status message

- Defaults taken (revertible): the three places for t01/t06/t14; q42/q43 curated here; holdouts curated; the bridge is a relabel of A, so CC-104's
  B block must run on the curated goldens and grid.
- Inherited red on origin/main: doc_lines 1822/1820, p95 20.714. A waiver or raise is an owner commit.
