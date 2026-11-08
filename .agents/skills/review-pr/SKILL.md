---
name: review-pr
description: Review a census-concierge PR or branch for project invariants, budgets, scope and evidence. Use for readiness reviews and this repository's Gate 2 invariants pass; generic bug review is a separate cold pass.
---

Read `AGENTS.md`, `CLAUDE.md` and the canonical `docs/playbooks/review-pr.md`
from the repo root. Run its machine checks first; a non-zero exit stops the
invariants review. Preserve raw evidence and use its three-verdict format.
For Gate 2 follow the cold bug pass ordering in `docs/playbooks/run-slice.md`.
