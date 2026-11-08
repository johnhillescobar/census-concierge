---
name: run-slice
description: Drive one slice (or a PR within it) through this project's anti-drift pipeline - pre-flight claim check, Gate 1 tests + mutation check, Gate 2 cold review, E2E before and after merge - with the token-heavy gate phases delegated to fresh subagents so state carries through the repo, not conversation history. Use when implementing a slice end to end, especially unattended, or when resuming one after a context reset.
---

# Running a slice

Read `CLAUDE.md` and **`docs/playbooks/run-slice.md`**, the canonical procedure.
Use the phase-specific prompt from `scripts/gate.ps1` or `scripts/gate.sh`.
In Claude Code, delegate each gate to a fresh `general-purpose` subagent, not
`fork`; use `isolation: worktree` when needed. Follow the playbook's cold-review
ordering, mutation checks, persisted handoffs and evidence/reporting limits.
Use `/code-review` for the generic bug pass, then the canonical invariants pass.
