---
name: review-pr
description: Review a pull request or the current branch against this project's own invariants — budgets, guards, scope, and evidence. Use before merging anything, when asked "is this ready", "review this branch", "check this PR", or after a Cursor session claims a slice is done. Not a substitute for /code-review, which finds generic bugs; this checks that the change did not weaken the harness or ship a silent wrong answer.
---

# Review a PR

Read `CLAUDE.md` and **`docs/playbooks/review-pr.md`**, the canonical procedure.
Run its machine checks first; a non-zero exit stops the invariants review.
Preserve raw evidence and use the playbook's three-verdict format.
For generic bug-hunting use `/code-review`. For Gate 2, follow the two-pass
ordering in `docs/playbooks/run-slice.md`; this skill is the invariants pass.
