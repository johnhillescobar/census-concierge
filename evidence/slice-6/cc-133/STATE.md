# CC-133 working state (read this first after any context reset)

Branch `cc-133/instrument`, draft PR #127. Jira CC-133 is the status source of truth.
Rules live in `CLAUDE.md` and `docs/playbooks/run-slice.md`; re-read both, they are short.

## The order, and the tools (no improvising)

1. Work from the AC/TC rows in `evidence/closure/CC-133.toml`, not from the last message. For every
   row there is a test that runs the REAL chain (real hashes, real git, real guard), not stubs.
2. Gate 1: tests for the adversarial matrix, then a mutation check of every new test. Commit
   BEFORE mutating (the script restores with `git checkout`). Transcript: `gate1-*.txt`.
3. Gate 2: `/code-review` (Skill `code-review`) on the branch diff against main, THEN
   `docs/playbooks/review-pr.md` (Skill `review-pr`). Fresh context; code only, no intent. Never a
   hand-written subagent prompt in place of these. Transcript: `gate2-r*.txt`. Fix every finding
   with tests + mutation check; re-run Gate 2 once on the fix; then stop.
4. E2E exactly once, after the code is frozen: `bash evidence/slice-6/cc-133/e2e-r4/driver.sh`.
   HEAD must be identical at start and end; do not edit or commit while it runs. Then:
   quote gated keys + demo.misses only (never demo.trials), `metric_compare compare ... --refs A,A0`,
   `git checkout -- evidence/latest.json`, delete root `evidence/grid-latest.json`/`grid-trials.jsonl`.
5. Only then: manifest observed text, PR body, Jira comment, push. PR stays draft until every
   row is verified PASS. Owner merges. Post-merge E2E on main precedes Done.

## Standing decisions (owner)

- No oracle review and no signing, ever (2026-11-10). Removed in aa1feb1. Do not raise it.
- Never raise a budget. Never read sealed sets or `demo.trials`.
- Do not press the owner for decisions that have a default; state the default and proceed.

## Done

Instrument built (metric_compare, closure, jira gate, invariants, isolation harness); Gate 1 x7;
Gate 2 x5, the last the prescribed way (/code-review then review-pr, gate2-r5.txt, verdict NOT YET,
findings fixed except the two documented); Copilot comments fixed and resolved; oracle removed;
real-chain tests added; context hooks (.claude/hooks/ctx.py, .claude/settings.json) added.

## Open

- E2E at the final head: `bash evidence/slice-6/cc-133/e2e-r4/driver.sh` (an earlier partial run was
  discarded). After it: compare, restore latest.json, manifest, PR body, Jira comment, push.
- Retrieval scalars (`retrieval_at_10`, `selector_at_1`) are not stamped with a head.
- `has_moe` etc. are outside the scorer hash (`evals/metric_protocol.toml` symbols: owner commit).
- Trap (18) and core (4) cohorts are under the 30-family minimum, so the real protocol cannot
  reach PASS on them (ticket wording: insufficient precision is inconclusive). Default taken: leave
  as written and report it; do not weaken.
- A0->A bridge needs a live re-score. p95 and 6 leakage entries are inherited red from main.
- All 13 AC/TC rows stay UNKNOWN/NOT RUN until verified PASS with a tested head.
