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

Gate 1 and Gate 2 also read the catalog matching touched paths: response / URL /
Census / UI → `docs/requirements.md`; `/ask` → `docs/ask-path.md`; index /
search / rerank → `docs/retrieval.md`; scope → `docs/slices.md`.

Transcript to `evidence/slice-<N>/gate2.txt`; findings into the PR body, "nothing"
included.

## 5. Fixes are new code

Tests plus a mutation check for every fix. Gate 2 read the pre-fix diff, so re-run
it once on the fix commit when the fixes were non-trivial - a new function, a
changed error path, new prose making a factual claim, changed CI. A rename or a
one-line correction does not. Stop after one re-run; still fix what it finds.

## 6. E2E, before the PR and after the merge

`make eval` and `make demo` (`--repeat 3` is in the recipe). Real system, real
keys. From slice 6, also one sealed-set run at story close, reporting the
regression-minus-sealed gap (DESIGN §8.6); aggregates only. Redirect stdout to
`evidence/slice-<N>/e2e-pre.txt` (no tee) and link it in the PR. Never Read the
transcript. Quote gated keys plus `demo.misses` from `evidence/latest.json` —
never `demo.trials`. A failing criterion keeps the PR open with that scoreboard;
reporting a red result is the correct outcome. After the merge, re-run against
merged `main` into `evidence/slice-<N>/e2e-post.txt` and comment the numbers on
the Jira ticket and the slice epic. PLAN.md STATUS stays a one-line close pointer
(floors met, `evidence/slice-<N>/`, epic URL). Do not append eval novels into PLAN.

Every close comment carries the **close card**, all at the same `--repeat`: long_tail
`demo.answered_rate`, grid visible / held-out, retriever@10 / selector@1,
`demo.p95_latency_seconds` with the slowest trial, api LOC before / after, and the
`re.*` call-site delta. `check_budgets.py` prints the p95, slowest trial and LOC;
`check_invariants.py --base origin/main` prints the regex delta. A p95 over the ceiling
passes only with the owner's `[waiver]` line in `budgets.toml`, for that one run.

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

## Session rules for long reviews and multi-write sessions

Added 2026-10-04 after a review session drifted (`evidence/checkpoint-2026-10-04/`).

1. **Phase gate.** Open with the yardstick for the slice in hand. Through slice 8 the
   product is a sound, flexible, robust URL with nothing from model memory; the
   analytical agent is phase 2, direction only. Re-read `CLAUDE.md` and memory first.
2. **One plan file** in `evidence/` is the only place the plan lives. List every outward
   write (Jira, repo, memory) in it before it happens; batch them, one "yes" per batch.
3. **Never write from a fragment.** A truncated or quoted-looking message is read-only
   input; Jira and repo writes wait for a full sentence.
4. **Tag decisions** `owner` (the owner said it) or `default` (revertible). A default is
   never recorded in Jira as an owner decision.
5. **One question batch per phase**, each question with a default. Otherwise proceed.
6. **After a drift complaint**, nothing outward until the plan file is reconciled.

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
