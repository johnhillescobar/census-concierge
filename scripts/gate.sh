#!/usr/bin/env bash
# Run one gate phase of the slice pipeline in a fresh context and capture the
# transcript. See docs/playbooks/run-slice.md.
#
#   scripts/gate.sh <phase> <slice> [engine]
#
#   phase   gate1 | gate2 | e2e   (1 / 2 accepted as shorthand)
#   slice   the slice number, e.g. 0
#   engine  cursor (default) | claude
#
# cursor: shells out to `agent -p`, tee-ing raw output to
#         evidence/slice-<slice>/<phase>.txt. Nothing edits that file afterwards.
# claude: prints the exact prompt to hand to a fresh general-purpose subagent
#         (Claude Code has no CLI entry point to spawn one from a script).

set -euo pipefail

phase="${1:?phase: gate1 | gate2 | e2e}"
slice="${2:?slice number, e.g. 0}"
engine="${3:-cursor}"

case "$phase" in
  1|gate1) phase=gate1 ;;
  2|gate2) phase=gate2 ;;
  e2e)     phase=e2e ;;
  *) echo "unknown phase: $phase (want gate1 | gate2 | e2e)" >&2; exit 2 ;;
esac

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out_dir="$root/evidence/slice-$slice"
out="$out_dir/$phase.txt"
mkdir -p "$out_dir"

case "$phase" in
  gate1) task="run Gate 1 for the current slice per docs/playbooks/run-slice.md: tests for the adversarial matrix, and mutation-check every new test. Paste the mutation transcript with GOOD/BAD labels." ;;
  gate2) task="review the current branch diff for bugs, code only, no knowledge of intent; then run docs/playbooks/review-pr.md. State what each pass found, including nothing." ;;
  e2e)   task="run the slice acceptance commands against the real system (make eval; make demo --repeat 3 once it exists) and print every command with its verbatim output." ;;
esac

case "$engine" in
  cursor)
    command -v agent >/dev/null || { echo "cursor CLI 'agent' not on PATH" >&2; exit 127; }
    mode=(); [ "$phase" = gate2 ] && mode=(--mode ask)
    echo "agent -p ${mode[*]} \"$task\"  ->  $out"
    agent -p "${mode[@]}" "$task" 2>&1 | tee "$out"
    ;;
  claude)
    cat <<EOF
Hand this to a fresh general-purpose subagent (not fork), isolation: worktree:

  Read CLAUDE.md, docs/playbooks/run-slice.md, and the current slice in
  .claude/PLAN.md first. You have no context from the caller.
  Do exactly this phase, nothing downstream:
  $task
  Capture every command's raw output:  <cmd> 2>&1 | tee $out
  Report back only: the path $out, a one-line verdict, and (gate2) the findings.
EOF
    ;;
  *) echo "unknown engine: $engine (want cursor | claude)" >&2; exit 2 ;;
esac
