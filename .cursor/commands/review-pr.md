# Review PR

Review the current branch against this project's invariants.

Follow **`docs/playbooks/review-pr.md`**. It is canonical and kept current —
read it, do not work from memory or from a summary.

Start by running the gates and pasting their real output:

```
uv run python scripts/check_budgets.py
uv run python scripts/check_invariants.py --base origin/main
uv run ruff check . && uv run ruff format --check .
uv run mypy api/src
uv run pytest -q -m "not integration"
```

A non-zero exit ends the review. `check_invariants --base` is the load-bearing
check: it catches a budget widened to make the change fit.

Then work through the playbook's sections — the claim, scope, silent-wrong-
answer review, shape, tests — and finish with one of its three verdicts, most
important reason first.
