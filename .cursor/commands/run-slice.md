# Run slice

Read `CLAUDE.md` and **`docs/playbooks/run-slice.md`**, the canonical procedure.
Delegate Gate 1, Gate 2 and E2E to a fresh Task subagent or New Chat without
caller history, using `scripts/gate.ps1 <phase> <slice>` or `scripts/gate.sh`.
Use a worktree when needed. Follow the playbook's cold-review ordering,
mutation checks, persisted handoffs and evidence/reporting limits.
The shared plan remains `.claude/PLAN.md`; persist each phase before the next.
