# Playbook: running a slice

Canonical for every host. `.claude/skills/run-slice/SKILL.md`,
`.cursor/commands/run-slice.md` and `.agents/skills/run-slice/SKILL.md`
are thin pointers - edit shared procedure here. Worked examples and the adversarial
matrix are in `docs/process-evidence.md`, read at audit time, not every turn.

A slice (`.claude/PLAN.md`) ships as one or more PRs, each through this pipeline. A
PR that has not been demonstrated is not finished, however good the diff looks.

## The pipeline

```
0  trust        complete the selected host's workspace trust setup.
                Cursor CLI: `agent --trust`, then `agent status`.
1  pre-flight   run every technical claim before writing code (table below)
2  implement    interactive session only. Ends at one commit.
3  Gate 1       tests for the adversarial matrix; every new test mutation-checked
4  Gate 2       cold bug review of the diff, then review-pr.md
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

## AC/TC clearance — required for every story
Before implementation assign stable IDs/expected outcomes to every in-scope AC and TC. The PR/Jira matrix records ID, command/test, expected/observed result, PASS/FAIL/NOT RUN/UNKNOWN, evidence, tested head, relevant hashes/repeats, mutation result for new tests and reviewer verification.
Every item must be verified PASS before merge readiness; missing/failed/unrun items block. Gate 2 verifies substance. Only a dated explicit owner amendment removes scope (reason/destination recorded), never silent N/A/PASS. Existing applicable evidence may be reused with rationale; rerun affected checks after changes. Owner-only merge remains.
Refresh the matrix with required post-merge E2E on merged main before Done. No sealed/E2E transcript reads; use authorized aggregates. `scripts/closure.py check evidence/closure/<KEY>.toml` enforces the matrix (`jira_transition.py` runs it on every move to Done; `make check` checks form). `scripts/metric_compare.py` runs B/P/A/L under `evals/metric_protocol.toml`; never rerun until green. Reviewers still verify substance.

## 2. Implement

Interactive in the selected host (Claude Code, Cursor, Codex or equivalent),
with normal approval and sandbox controls. Never use headless implementation
or blanket permission bypasses such as `agent --force` / `--yolo`; the diff
has to stay in the session that writes it. Host selection changes adapters,
not project rules, checks, skills, budgets or owner responsibilities.

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
  subagent/session in any host — code only, no implementation intent. Do not read
  the slice plan, implementation notes or the caller's explanation until this
  pass has recorded its findings. Shared project rules still apply.
- **project invariants**: `docs/playbooks/review-pr.md`. Run the machines first; a
  non-zero exit ends the review.

Gate 1 and Gate 2's invariants pass also read the catalog matching touched paths: response / URL /
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
fresh context in any host **reconstructs state from those artifacts, never from conversation history**.
The shared `.claude/PLAN.md` and `.claude/DESIGN.md` paths remain valid for all
hosts; do not fork their state into host-specific copies.

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

| | Claude Code | Cursor | Codex / other hosts |
| --- | --- | --- | --- |
| gate phase | fresh `general-purpose` subagent, **not** `fork` | fresh Task subagent or New Chat | fresh subagent without caller history; Codex `fork_context: false` when supported, otherwise a fresh session |
| isolated checkout | subagent `isolation: worktree` | worktree when needed | explicit worktree when needed; do not assume subagents isolate files |

`scripts/gate.sh` / `scripts/gate.ps1` print the same host-neutral handoff;
they do not launch agents or choose an engine. The parent uses its host's
delegation tool, or hands the prompt to a fresh session if none is available.
Use native slash commands where available; the equivalent cold review is
required even when the command is absent. Do not replace it with self-review.

Pass only the repo path, phase, slice, exact review base/head and evidence path,
not caller history or implementation intent. Record branch, HEAD and any scoped
uncommitted changes in the evidence. Preserve unrelated user changes; mutations
run one at a time in an isolated worktree when necessary. Do not run gate phases
concurrently against shared files or the same evidence output. Preserve earlier
evidence before reruns and link both runs. The subagent writes
`evidence/slice-<N>/<phase>.txt`; the caller does not edit it afterward.
`.gitattributes` forces LF so it stays byte-stable.

Without `make`, execute and capture every command listed under the `eval` and
`demo` recipes in the Makefile, in recipe order. This includes both
`run_demo.py --repeat 3` and `run_grid.py --repeat 3`; the optional
`scripts/e2e_capture.py` helper does not run the geography grid and is not a
substitute for that command. Record all command output in the phase evidence.
A missing runtime, database, credential, network permission or fresh-context
capability is a reported blocker, never a skipped check reported as passing.
Live E2E needs the documented API keys and credit; Plus usage is separate.
Sealed sets stay owner-held on every host, whether or not host hooks enforce
access; request only the permitted aggregate results.
