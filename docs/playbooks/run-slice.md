# Playbook: running a slice

Canonical. `.claude/skills/run-slice/SKILL.md` and `.cursor/commands/run-slice.md`
are thin pointers - edit here, not there. Worked examples and the adversarial
matrix are in `docs/process-evidence.md`, read at audit time, not every turn.

A slice (`.claude/PLAN.md`) ships as one or more PRs, each through this pipeline. A
PR that has not been demonstrated is not finished, however good the diff looks.

## The pipeline

```
0  trust        one-time per machine: `agent --trust`, then `agent status`.
                Skip if you only use Claude Code.
1  pre-flight   run every technical claim before writing code (table below)
2  implement    interactive session only. Ends at one commit.
3  Gate 1       tests for the adversarial matrix; every new test mutation-checked
4  Gate 2       cold review of the diff: `/code-review`, then review-pr.md
5  fix          each fix is new code: tests + mutation check. Re-run Gate 2 once
                if the fixes were non-trivial, then stop.
6  E2E pre-PR   run the real thing, scoreboard in the PR, transcript on disk
7  PR           body states what each gate found, including "nothing"
8  merge        the repo owner merges
9  E2E post     re-run step 6 against merged `main`
```

## 1. Pre-flight: check the claims

Both gates read the diff; neither checks the notes it was built from. Run every
claim against the thing it names, before code depends on it.

| Claim | Settled by |
| --- | --- |
| a field, function, class or module name | `grep` - it exists, spelled that way |
| a library's behaviour | running it; the output goes in the PR or the notes |
| a git or PR citation | running the command, pinned to a commit range |
| a file path | it exists |
| a table ID, universe or geography | `scripts/verify_golden.py` against real metadata |

A claim that fails is corrected in the PR notes, with the command that settled it,
before implementation starts. Fixing it silently in code leaves the notes wrong for
the next reader. Not a numbered gate - it costs a `grep`.

## 2. Implement

Interactive, Claude Code or Cursor. Never headless: `agent --force` / `--yolo` is
all-or-nothing with no per-command allowlist, and the diff has to stay in the
session that writes it.

## 3. Gate 1 - tests and the mutation check

Tests covering the adversarial matrix in `docs/process-evidence.md`. **For every
new test: revert the behaviour it covers, run only that test, confirm it fails,
restore.** A test that passes against the broken implementation is not a check.
Revert one behaviour at a time; name the mutation for what it reverts, never by a
review index. Transcript to `evidence/slice-<N>/gate1.txt` with `GOOD` / `BAD`
labels above the real failure counts.

## 4. Gate 2 - cold-context review

Read the code with no knowledge of intent. Not a duplicate of Gate 1: a test from
the same mental model as the implementation cannot falsify that model. Two passes:

- **generic bugs**: `/code-review` (Claude Code) or the same cold read in a fresh
  subagent (Cursor Task / New Chat) — code only, no intent.
- **project invariants**: `docs/playbooks/review-pr.md`. Run the machines first; a
  non-zero exit ends the review.

Transcript to `evidence/slice-<N>/gate2.txt`; findings into the PR body, "nothing"
included.

## 5. Fixes are new code

Tests plus a mutation check for every fix. Gate 2 read the pre-fix diff, so re-run
it once on the fix commit when the fixes were non-trivial - a new function, a
changed error path, new prose making a factual claim, changed CI. A rename or a
one-line correction does not. Stop after one re-run; still fix what it finds.

## 6. E2E, before the PR and after the merge

`make eval` today; `make demo` once `scripts/run_demo.py` exists (slice 1; `--repeat
3` is in the recipe). Real system, real keys. Redirect stdout to
`evidence/slice-<N>/e2e-pre.txt` (no tee) and link it in the PR. Never Read the
transcript. Quote gated keys plus `demo.misses` from `evidence/latest.json` —
never `demo.trials`. A failing criterion keeps the PR open with that scoreboard;
reporting a red result is the correct outcome. After the merge, re-run against
merged `main` into `evidence/slice-<N>/e2e-post.txt` and comment the numbers on
the Jira ticket and the slice epic. PLAN.md STATUS stays a one-line close pointer
(floors met, `evidence/slice-<N>/`, epic URL). Do not append eval novels into PLAN.

## The handoff rule

Every phase **persists its output before the next begins** - to git, the PR body,
`evidence/slice-<N>/`, `.claude/PLAN.md`, **Jira** (project `CC`), or
`docs/process-evidence.md`. A phase that has not persisted has not finished. A
fresh context - Claude Code `/clear` or a subagent, Cursor New Chat or an
`agent` invocation - **reconstructs state from those artifacts, never from conversation history**.

**Jira (project `CC`) is the status source of truth.** Close with
`uv run python scripts/jira_transition.py CC-N --done --comment "…"` (evidence in
the comment). PLAN.md STATUS is a close pointer; post-merge numbers live on
the ticket. Name `CC-N` in commits and PRs.

## Delegating the token-heavy phases

Run Gate 1, Gate 2 and E2E in a fresh context so their reads and tool output do not
stay resident for the rest of the slice.

| | Claude Code | Cursor |
| --- | --- | --- |
| gate phase | fresh `general-purpose` subagent, **not** `fork` | fresh Task subagent or New Chat — same prompt, no caller context |
| isolated checkout | subagent `isolation: worktree` | worktree when the phase needs a clean checkout |

`scripts/gate.sh` / `scripts/gate.ps1` print the subagent prompt for either host;
neither shell can spawn the subagent. The subagent writes
`evidence/slice-<N>/<phase>.txt`; the caller does not edit it afterward.
`.gitattributes` forces LF so it stays byte-stable.
