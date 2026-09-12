# evidence/slice-N/

One directory per slice. Each gate phase of `docs/playbooks/run-slice.md` writes
its transcript here, captured by the shell (`scripts/gate.sh` / `scripts/gate.ps1`)
and never edited by a model:

| file | phase |
| --- | --- |
| `gate1.txt` | Gate 1 - tests and the mutation check |
| `gate2.txt` | Gate 2 - cold-context review (`/code-review` + `review-pr.md`) |
| `e2e-pre.txt` | E2E against the real system, before the PR |
| `e2e-post.txt` | E2E against merged `main`, after the merge |

These are the durable handoff between phases: a fresh context reconstructs slice
state from here plus `.claude/PLAN.md`, the branch, the PR body, and
`docs/process-evidence.md`. Not counted against `doc_lines` - evidence, not
instruction.

Slice 0 shipped before this workflow existed; its measured record is
`evidence/retrieval_steps.md`.
