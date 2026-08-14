---
name: review-pr
description: Review a pull request or the current branch against this project's own invariants — budgets, guards, scope, and evidence. Use before merging anything, when asked "is this ready", "review this branch", "check this PR", or after a Cursor session claims a slice is done. Not a substitute for /code-review, which finds generic bugs; this checks that the change did not weaken the harness or ship a silent wrong answer.
---

# Review a PR

Follow **`docs/playbooks/review-pr.md`** in this repository. It is the canonical
version and it is kept current; do not work from a summary of it.

Read it first, then work through it in order. Two things it insists on that are
easy to skip:

1. **Run the gates before reading any code.** `check_budgets.py`,
   `check_invariants.py --base origin/main`, ruff, mypy, pytest. Paste the real
   output. A non-zero exit ends the review.
2. **`check_invariants --base` is the load-bearing one.** It catches a budget
   widened to make the change fit, which is the failure mode this whole
   repository is built to prevent.

Report findings in the playbook's three-verdict form: ship it, ship it with
follow-ups, or not yet — with the single most important reason first.

If the user asked for generic bug-hunting rather than an invariants review,
`/code-review` is the better tool. Say so instead of doing a worse version.
