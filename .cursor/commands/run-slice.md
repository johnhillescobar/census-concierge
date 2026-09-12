# Run slice

Drive one slice (or a PR within it) through the anti-drift pipeline.

Follow **`docs/playbooks/run-slice.md`** - canonical, kept current, read it rather
than working from memory.

Pipeline: pre-flight claim check -> implement -> Gate 1 (tests + mutation check) ->
Gate 2 (cold review) -> fix -> E2E -> PR -> merge -> post-merge E2E.

## Gate phases run in a fresh subagent

Gate 1, Gate 2 and E2E are token-heavy. **Do not run them in the implementer chat.**
Launch a fresh Task subagent (or New Chat) with the prompt from:

```
scripts/gate.ps1 <phase> <slice>
```

The subagent captures raw output to `evidence/slice-<N>/<phase>.txt`. Start a New
Chat between phases — that is the context boundary.

## State carries through the repo, not the chat

A fresh subagent or New Chat reconstructs state from the current slice in
`.claude/PLAN.md`, the branch, `evidence/slice-<N>/`, the PR body, and
`docs/process-evidence.md`. A phase that has not persisted there has not finished.
