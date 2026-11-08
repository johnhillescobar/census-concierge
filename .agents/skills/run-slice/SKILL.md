---
name: run-slice
description: Run or resume a census-concierge slice or PR through pre-flight, mutation-tested Gate 1, cold Gate 2, and E2E before and after merge. Use for this repository's implementation workflow and gate handoffs.
---

Read `AGENTS.md`, `CLAUDE.md` and the canonical `docs/playbooks/run-slice.md`
from the repo root. Use its phase prompts from `scripts/gate.ps1` or
`scripts/gate.sh`. In Codex, use `fork_context: false` when supported, otherwise
a fresh session. Follow the playbook's isolation, mutation checks, cold-review
ordering, persisted handoffs and evidence/reporting limits.
