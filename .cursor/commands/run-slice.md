# Run slice

Drive one slice (or a PR within it) through the anti-drift pipeline.

Follow **`docs/playbooks/run-slice.md`** - canonical, kept current, read it rather
than working from memory.

Pipeline: pre-flight claim check -> implement -> Gate 1 (tests + mutation check) ->
Gate 2 (cold review) -> fix -> E2E -> PR -> merge -> post-merge E2E.

## Gate phases run in a fresh context

Gate 1, Gate 2 and E2E are token-heavy. Run each headless, capturing the transcript
with shell redirection:

```
agent -p "run Gate 1 for the current slice per docs/playbooks/run-slice.md" \
  > evidence/slice-<N>/gate1.txt 2>&1
agent -p --mode ask "review this diff for bugs, code only, no intent" \
  > evidence/slice-<N>/gate2.txt 2>&1
```

Add `-w gate-<N> --worktree-base <branch>` for an isolated checkout. Start a New
Chat between phases - that is the context boundary.

## State carries through the repo, not the chat

A fresh `agent` run or New Chat reconstructs state from the current slice in
`.claude/PLAN.md`, the branch, `evidence/slice-<N>/`, the PR body, and
`docs/process-evidence.md`. A phase that has not persisted there has not finished.

`scripts/gate.ps1` wraps the calls above: `gate <phase> <slice> cursor`.
