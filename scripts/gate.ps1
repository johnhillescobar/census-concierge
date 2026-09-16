<#
.SYNOPSIS
  Print the handoff to run one gate phase in a fresh subagent. See docs/playbooks/run-slice.md.

.EXAMPLE
  scripts\gate.ps1 gate2 0

  phase   gate1 | gate2 | e2e-pre | e2e-post  (1 / 2 / pre / post accepted as shorthand)
  slice   the slice number, e.g. 0

  Neither host can spawn a subagent from a shell script. This prints the prompt;
  the parent session delegates to a fresh general-purpose subagent (Claude Code)
  or Task subagent / New Chat (Cursor). Capture raw output to
  evidence/slice-<slice>/<phase>.txt — the subagent writes it, not the caller.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$Phase,
  [Parameter(Mandatory)][int]$Slice
)

$ErrorActionPreference = 'Stop'

$Phase = switch ($Phase) {
  { $_ -in '1', 'gate1' } { 'gate1' }
  { $_ -in '2', 'gate2' } { 'gate2' }
  { $_ -in 'pre', 'e2e-pre' } { 'e2e-pre' }
  { $_ -in 'post', 'e2e-post' } { 'e2e-post' }
  default { Write-Error "unknown phase: $Phase (want gate1 | gate2 | e2e-pre | e2e-post)"; exit 2 }
}

$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root "evidence/slice-$Slice/$Phase.txt"

$task = switch ($Phase) {
  'gate1' { 'run Gate 1 for the current slice per docs/playbooks/run-slice.md: tests for the adversarial matrix, and mutation-check every new test. Paste the mutation transcript with GOOD/BAD labels.' }
  'gate2' { 'review the current branch diff for bugs, code only, no knowledge of intent; then run docs/playbooks/review-pr.md. State what each pass found, including nothing.' }
  'e2e-pre' { 'run the slice acceptance commands against the real system (make eval; make demo --repeat 3 once it exists), before the PR. Tee raw output to the evidence path. Do not Read that file. Report the printed DEMO/MISSES scoreboard only.' }
  'e2e-post' { 'run the slice acceptance commands against the real system (make eval; make demo --repeat 3 once it exists) against merged main, after the merge. Tee raw output to the evidence path. Do not Read that file. Report the printed DEMO/MISSES scoreboard only.' }
}

@"
Hand this to a fresh general-purpose subagent (not fork), isolation: worktree when needed:

  Read CLAUDE.md, docs/playbooks/run-slice.md, and the current slice in
  .claude/PLAN.md first. You have no context from the caller.
  Do exactly this phase, nothing downstream:
  $task
  Capture every command's raw output to:  $out
  Report back only: the path $out, a one-line verdict, and (gate2) the findings.
"@
