# Host-neutral workflow update

Owner request: make the gates, rules, workflow and skills usable by Codex while
preserving Claude Code and Cursor support.

Authorized repo writes: this plan; root AGENTS.md; repo-local skill pointers;
shared workflow/review documentation; gate prompt scripts and Makefile help;
process pointer tests; evidence for checks and cold review. No external writes,
commits, merges, budget changes or application changes are planned.

Default implementation: retain the existing shared CLAUDE.md and .claude/PLAN.md
paths, add discovery adapters, and use the same canonical playbooks in all hosts.
Keep existing Claude skills, Cursor commands, rules and safety settings usable.

Validation: process tests and mutation checks for expanded pointer coverage;
PowerShell/Bash prompt smoke checks; offline repository checks; fresh-context
Gate 2 review. Record failures and limitations. Live Census/LLM E2E is not a
measurement of these instruction-only changes and will not be claimed as run.

Existing unrelated working-tree changes are outside this update.

Gate 1 passed for the discovery adapters. First Gate 2 found no generic defects,
but stopped at doc_lines 1842/1820 and the pre-existing recorded p95 23.344/20s.
Default follow-up: condense duplicated host adapters, count AGENTS.md and
.agents/skills in the existing doc budget, and extend/mutation-check the budget
test. Additional authorized writes: scripts/check_budgets.py,
api/tests/test_budgets.py, the existing review-pr adapters, and follow-up evidence.
Do not change budgets.toml or the recorded product scoreboard.

Result: adapters, shared playbooks and budget counting updated. Targeted budget
and process tests: 41 passed. Both new discovery-pointer mutations and both
budget-glob mutations failed as required, then passed with behavior restored.
All four skill frontmatters validate; PowerShell and Git Bash phase/alias smoke
checks pass. Changed Python files pass ruff lint/format; git diff --check passes.
Structural budgets pass, including 1813/1820 documentation lines.

Final cold re-review found no concrete bugs. Full Gate 2 remains NOT YET: the
unchanged HEAD scoreboard records demo.p95_latency_seconds=23.344 above 20.
The invariants pass stopped at that prerequisite, per the existing rule. No live
E2E, merge, commit, Jira write, waiver or product scoreboard update was performed.
Evidence: workflow-host-neutral-gate1.txt, workflow-host-neutral-budget-gate1.txt,
workflow-host-neutral-smoke.txt, workflow-host-neutral-gate2.txt and
workflow-host-neutral-gate2-rerun.txt alongside this plan.
