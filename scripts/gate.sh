#!/usr/bin/env bash
# Print the handoff to run one gate phase in a fresh subagent. See docs/playbooks/run-slice.md.
#
#   scripts/gate.sh <phase> <slice>
#
#   phase   gate1 | gate2 | e2e-pre | e2e-post   (1 / 2 / pre / post accepted as shorthand)
#   slice   the slice number, e.g. 0
#
# This prints a host-neutral prompt; it does not launch agents. The parent
# delegates to a fresh subagent without caller history, or a fresh session.
# Claude Code, Cursor and Codex use the same phase requirements. Capture raw output to
# evidence/slice-<slice>/<phase>.txt — the subagent writes it, not the caller.

set -euo pipefail

phase="${1:?phase: gate1 | gate2 | e2e-pre | e2e-post}"
slice="${2:?slice number, e.g. 0}"

case "$phase" in
  1|gate1) phase=gate1 ;;
  2|gate2) phase=gate2 ;;
  pre|e2e-pre)  phase=e2e-pre ;;
  post|e2e-post) phase=e2e-post ;;
  *) echo "unknown phase: $phase (want gate1 | gate2 | e2e-pre | e2e-post)" >&2; exit 2 ;;
esac

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="$root/evidence/slice-$slice/$phase.txt"

case "$phase" in
  gate1) task="run Gate 1 for the current slice per docs/playbooks/run-slice.md: tests for the adversarial matrix, and mutation-check every new test. Paste the mutation transcript with GOOD/BAD labels." ;;
  gate2) task="review the current branch diff for bugs, code only, no knowledge of intent; then run docs/playbooks/review-pr.md. State what each pass found, including nothing." ;;
  e2e-pre)  task="run make eval and make demo against the real system, before the PR. Repeat 3 is already in the make demo recipe." ;;
  e2e-post) task="run make eval and make demo against merged main, after the merge. Repeat 3 is already in the make demo recipe." ;;
esac

case "$phase" in
  gate2) setup="Read CLAUDE.md and docs/playbooks/run-slice.md. Record the code-only bug review before reading .claude/PLAN.md or implementation notes. Then read the plan and applicable catalogs for the invariants pass." ;;
  *) setup="Read CLAUDE.md, docs/playbooks/run-slice.md, and the current slice in .claude/PLAN.md first. Gate 1 also reads the catalogs matching touched paths." ;;
esac

case "$phase" in
  e2e-pre|e2e-post)
    capture="Redirect every command's output to $out (no tee). Do not Read that file."
    report="Report back only: the path $out, a one-line verdict, and the DEMO/MISSES scoreboard from evidence/latest.json (gated keys plus demo.misses, never demo.trials)."
    ;;
  gate2)
    capture="Capture every command's raw output to:  $out"
    report="Report back only: the path $out, a one-line verdict, and the findings."
    ;;
  *)
    capture="Capture every command's raw output to:  $out"
    report="Report back only: the path $out and a one-line verdict."
    ;;
esac

cat <<EOF
Hand this to a fresh subagent without caller history, or a fresh session.
Claude Code: general-purpose, not fork. Cursor: fresh Task / New Chat.
Codex: fork_context: false when supported. Use an explicit worktree when needed.

  You have no context from the caller. Work from the repo and persisted evidence.
  Record repo path, branch, HEAD, review base/head and scoped uncommitted changes.
  $setup
  Catalogs matching touched paths:
  (docs/requirements.md, docs/ask-path.md, docs/retrieval.md, docs/slices.md).
  Without make, execute the underlying Makefile recipes in order.
  Preserve prior evidence before reruns; never overwrite another gate's output.
  Do exactly this phase, nothing downstream:
  $task
  $capture
  $report
EOF
