---
name: run-slice
description: Drive one slice (or a PR within it) through this project's anti-drift pipeline - pre-flight claim check, Gate 1 tests + mutation check, Gate 2 cold review, E2E before and after merge - with the token-heavy gate phases delegated to fresh subagents so state carries through the repo, not conversation history. Use when implementing a slice end to end, especially unattended, or when resuming one after a context reset.
---

# Running a slice

Follow **`docs/playbooks/run-slice.md`**. It is canonical and kept current; read it
first, not a summary. This skill only changes *where each phase runs*.

## Delegate the gate phases

Gate 1, Gate 2 and E2E each leave ~25k resident tokens in the caller. Run each in a
**fresh `general-purpose` subagent**, not `fork` (a fork inherits this conversation
and pays exactly the tokens this avoids). Use `isolation: worktree` when the phase
needs a clean checkout.

The subagent prompt, every time:

1. Read `CLAUDE.md`, `docs/playbooks/run-slice.md`, and the current slice in
   `.claude/PLAN.md` first. You have no context from the caller. Gate 1 and
   Gate 2 also read the catalog matching touched paths (`docs/requirements.md`,
   `docs/ask-path.md`, `docs/retrieval.md`).
2. Do exactly this phase, nothing downstream.
3. Capture raw output to `evidence/slice-<N>/<phase>.txt` (no model edits). Gate 1/2
   may tee; E2E redirects to the file so heartbeats never enter the session.
4. Report back only: the path, a one-line verdict, Gate 2 findings, and for E2E the
   DEMO/MISSES scoreboard from `evidence/latest.json` (never the transcript).

## Between phases

The caller keeps the slice number, the branch, and what is now in git +
`evidence/` + the PR body + `.claude/PLAN.md` + `docs/process-evidence.md`. A phase
that has not persisted its output there has not finished. Gate 2 is two passes -
`/code-review` then `docs/playbooks/review-pr.md` - and both findings go in the PR
body, "nothing" included.
