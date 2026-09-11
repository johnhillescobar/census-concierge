<#
.SYNOPSIS
  Run one gate phase of the slice pipeline in a fresh context and capture the
  transcript. See docs/playbooks/run-slice.md.

.EXAMPLE
  scripts\gate.ps1 gate2 0
  scripts\gate.ps1 gate1 1 claude

  phase   gate1 | gate2 | e2e  (1 / 2 accepted as shorthand)
  slice   the slice number, e.g. 0
  engine  cursor (default) | claude

  cursor: shells out to `agent -p`, tee-ing raw output to
          evidence/slice-<slice>/<phase>.txt. Nothing edits that file afterwards.
  claude: prints the prompt to hand to a fresh general-purpose subagent.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$Phase,
  [Parameter(Mandatory)][int]$Slice,
  [ValidateSet('cursor', 'claude')][string]$Engine = 'cursor'
)

$ErrorActionPreference = 'Stop'

$Phase = switch ($Phase) {
  { $_ -in '1', 'gate1' } { 'gate1' }
  { $_ -in '2', 'gate2' } { 'gate2' }
  'e2e' { 'e2e' }
  default { Write-Error "unknown phase: $Phase (want gate1 | gate2 | e2e)"; exit 2 }
}

$root = Split-Path -Parent $PSScriptRoot
$outDir = Join-Path $root "evidence/slice-$Slice"
$out = Join-Path $outDir "$Phase.txt"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$task = switch ($Phase) {
  'gate1' { 'run Gate 1 for the current slice per docs/playbooks/run-slice.md: tests for the adversarial matrix, and mutation-check every new test. Paste the mutation transcript with GOOD/BAD labels.' }
  'gate2' { 'review the current branch diff for bugs, code only, no knowledge of intent; then run docs/playbooks/review-pr.md. State what each pass found, including nothing.' }
  'e2e'   { 'run the slice acceptance commands against the real system (make eval; make demo --repeat 3 once it exists) and print every command with its verbatim output.' }
}

switch ($Engine) {
  'cursor' {
    if (-not (Get-Command agent -ErrorAction SilentlyContinue)) {
      Write-Error "cursor CLI 'agent' not on PATH"; exit 127
    }
    $mode = if ($Phase -eq 'gate2') { @('--mode', 'ask') } else { @() }
    "agent -p $($mode -join ' ') `"$task`"  ->  $out"
    & agent -p @mode $task 2>&1 | Tee-Object -FilePath $out
  }
  'claude' {
    @"
Hand this to a fresh general-purpose subagent (not fork), isolation: worktree:

  Read CLAUDE.md, docs/playbooks/run-slice.md, and the current slice in
  .claude/PLAN.md first. You have no context from the caller.
  Do exactly this phase, nothing downstream:
  $task
  Capture every command's raw output:  <cmd> 2>&1 | tee $out
  Report back only: the path $out, a one-line verdict, and (gate2) the findings.
"@
  }
}
