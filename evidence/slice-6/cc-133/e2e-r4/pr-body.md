**What a user can now do:** nothing new. This is the instrument CC-133 asks for: a frozen metric protocol and comparator, an AC/TC closure gate on every Jira move to Done, and an execution-isolation harness. No `api/src` change, no budget change, no product-gain claim.

## What it adds
- `evals/metric_protocol.toml` + `scripts/metric_compare.py`: B/P/A/L comparison by paired family bootstrap (fewer than 30 families or a possible loss over 2 points is INCONCLUSIVE; any observed decrease fails), scorer/cohort/protocol hashes (a change needs a pinned bridge), L moves only on a pass against A and L. A (main 69d7364) and A0 (4b24f77) are registered from existing evidence as `legacy-unfrozen-protocol`, floors unmet recorded as blockers.
- `scripts/closure.py` + `jira_transition.py`: both Done paths (and any Done-category status) run the manifest check; a Story/Bug with no AC/TC ids is refused. `check_invariants.py` checks manifest form, that the protocol is never loosened, and that references and the ledger are not rewritten.
- `api/tests/test_execution_isolation.py`: scripts the model, proves with mutants that code reading the question's wording is caught, and records today's wording dependence as 8 strict xfails (CC-104, CC-129, one unplaced).
- `run_demo.py` records the response-contract fields per trial.

## Gates (transcripts in `evidence/slice-6/cc-133/`)
- Gate 1 (mutation check of every new test): seven passes; each found survivors that became tests or corrected patterns (latest: 25, 17, 9 of 10, 23 of 24 and 14 of 14 caught; the survivors left are documented equivalents).
- Gate 2 ran five times; the fifth the prescribed way (`/code-review` then `review-pr`, `gate2-r5.txt`). Each said "Not yet". The fifth's ten findings are fixed (dirty-tree stamp, pinned PASS evidence, declared `required` ids, dependency pins in the measured code, cancellations, dotted and ranged ids, records guard for a new store, decennial `has_moe`) except two documented below. **Those fixes have no cold review of their own**; the playbook stops at one re-run.
- Oracle review and sign-off: removed (owner decision 2026-11-10).
- Machines at 0853a63: ruff, format and mypy clean; budgets.toml untouched, doc lines 1820; 1382 passed, 1 failed (inherited from main).

## Copilot review (fixed, threads resolved)
- The response contract is checked on every trial that returned rows, in any tier, answered or not.
- A run must hold exactly the frozen (tier, id, repeat) trials: extra, missing and duplicated ones fail.
- A run records the head and the scorer, cohort and protocol hashes it was scored under; the comparison judges it by those, checks them against the head and the measured code, and treats a run with none as UNKNOWN. Promotion labels L with the producing head, which must be reachable from origin/main.
- `has_moe` means every returned estimate had its M variable fetched, per row; a fetched but suppressed M counts. This reading is the owner's to confirm.

## E2E at the final head (0853a63 at start and end, repeat 3; `e2e-r4/`)
long_tail answered 0.700 (floor 0.700) | overall 0.801 | demo.p95 31.236s (ceiling 20; main 25.472; api/src unchanged here, one Census call took 88.5s) | retriever@10 0.900 | selector@1 0.825 | synthetic_alignment 0.544 | geography grid 0.995 | 37 demo misses.
`metric_compare compare --refs A,A0`: **VERDICT FAIL**. long_tail trial rate vs A PASS (diff +0.017, lower -0.017); long_tail case rate, trap (18 families) and core (4) INCONCLUSIVE. FAIL: p95 ceiling and p95 vs A; rows per family (3 families returned fewer rows); response contract (3 of 179 trials that returned rows lack a contract field; trials not read, so the field and question are unknown here); A0 (scorer changed, no bridge). The same capability as main, measured by a stricter instrument; nothing here claims a product gain. The p95 and rows verdicts are on unchanged product code, i.e. run noise.

## Matrix
`evidence/closure/CC-133.toml`: every row UNKNOWN or NOT RUN on purpose; `uv run python scripts/closure.py check evidence/closure/CC-133.toml --pre-merge` exits 1. Not ready to close.

## Owner items (defaults taken; nothing blocks on them being answered now)
1. Trap (18) and core (4) cohorts are under the 30-family minimum, so the comparator can never PASS them as written. Default: left as written and reported INCONCLUSIVE. Options: grow them, or rule observed-only for them.
2. Strict "no observed worsening" on p95 and rows per family fails an identical candidate on noise. Default: strict, per the ticket. Option: a tolerance.
3. `has_moe` (fetched M counts, suppressed or not) and `has_geoid` sit outside the scorer hash; moving them into `evals/metric_protocol.toml` is an owner commit.
4. `retrieval_at_10` and `selector_at_1` are not stamped with a head.
5. A0-to-A bridge needs a live re-score.
6. p95, answered_rate floor, 6 leakage entries and one invariants test are red on main as well.
7. PLAN lines 41-42 and 46 still describe a rollback that did not happen; D1 here takes A = 69d7364.
8. Rows PASS at tested head 0853a63: AC1, AC4, AC5, TC1, TC2, TC4, TC5, TC7 (`evidence/slice-6/cc-133/closure-run/`). Open: AC2, AC3, TC3, TC6 (cohort size, A0 bridge) and AC6. AC4/TC4 rest on the harness; the 8 strict xfails are today's wording dependence owned by CC-104/CC-129, plus one ZIP case in guards.py, now CC-135. Post-merge E2E on main is still to run; `closure.py check --pre-merge` exits 1 with 5 problems.

~25 files touched against the ~15 guideline: the story is three tools, their tests and their evidence. Doc lines 1822 -> 1820.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


