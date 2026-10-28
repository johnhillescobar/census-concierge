# CC-123 plan

The one plan file for this ticket. Every outward write is listed before it happens.
Branch `feat/cc-123-demo-memory` from `origin/main` 635449d, worktree `C:\Users\johnh\worktrees\census-cc-123`.
Yardstick: the product is a sound URL, nothing from model memory. CC-123 is research plus a measured
fix for a reliability blocker; it does not change what `/ask` answers.

## Phases

1. **Design** (this commit): `memory-experiment-design.md`. No run before it is committed. Done when committed.
2. **Probe**: `scripts/memory_probe.py` (script only, zero `api/src` lines). Instrument validity (five
   offline injections) must pass before any W1 run.
3. **Runs**: leaf arms L1-L6, W1 on trees M and C (6 arm-P runs interleaved, 2 arm-T runs). Raw output to
   `evidence/slice-6/memory/`. Detached, 9 GB watchdog.
4. **Results**: `memory-experiment-results.md` (verdict per hypothesis, numbers, commands, commit).
5. **Fix**, only for the measured cause (AC7). Tests mutation-checked. Gate 1, Gate 2, E2E twice (AC8).
6. PR, merge by the owner, E2E post, Jira close comment by the owner.

## Outward writes (batched; one "yes" per batch)

- Local commits on `feat/cc-123-demo-memory`: design now; probe and results later. Not pushed.
- Jira CC-123: one comment when the design is committed, one with the results, one at close.
- Push and PR: after Gate 2 and a measured fix, or after results if the cause is not reproducible.
- Memory files: none expected.
- No `budgets.toml` change, no `api/src` change before a measured cause exists.

## Decisions

- `default`: trees M = `origin/main` 635449d and C = CC-121 `f901c73`. Revertible.
- `default`: W1 is one repeat (62 trials), not `--repeat 3`, because the incident died at trial 44 of repeat 1.
  Extended to 186 only for an inconclusive verdict.
- `default`: thresholds in the design (5 MB per trial, 2 GB reproduction, 9 GB kill). Revertible before the first run.

## Open

- CC-121 is Blocked on this ticket; its E2E resumes after a measured fix or a documented non-reproduction.
