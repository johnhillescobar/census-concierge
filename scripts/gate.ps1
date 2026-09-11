<#
.SYNOPSIS
  Run one gate phase of the slice pipeline in a fresh context and capture the
  transcript. See docs/playbooks/run-slice.md.

.EXAMPLE
  scripts\gate.ps1 gate2 0
  scripts\gate.ps1 gate1 1 claude
  scripts\gate.ps1 e2e-post 0

  phase   gate1 | gate2 | e2e-pre | e2e-post  (1 / 2 / pre / post accepted as shorthand)
  slice   the slice number, e.g. 0
  engine  cursor (default) | claude

  cursor: shells out to `agent -p`, tee-ing raw output to
          evidence/slice-<slice>/<phase>.txt. Nothing edits that file afterwards.
          Exits non-zero (and says so) when `agent` itself failed, so a failed
          gate cannot be mistaken for a recorded pass.
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
  { $_ -in 'pre', 'e2e-pre' } { 'e2e-pre' }
  { $_ -in 'post', 'e2e-post' } { 'e2e-post' }
  default { Write-Error "unknown phase: $Phase (want gate1 | gate2 | e2e-pre | e2e-post)"; exit 2 }
}

$root = Split-Path -Parent $PSScriptRoot
$outDir = Join-Path $root "evidence/slice-$Slice"
# One file per phase, including separate e2e-pre.txt / e2e-post.txt - the
# playbook's handoff record depends on the pre-PR and post-merge runs never
# overwriting each other.
$out = Join-Path $outDir "$Phase.txt"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$task = switch ($Phase) {
  'gate1' { 'run Gate 1 for the current slice per docs/playbooks/run-slice.md: tests for the adversarial matrix, and mutation-check every new test. Paste the mutation transcript with GOOD/BAD labels.' }
  'gate2' { 'review the current branch diff for bugs, code only, no knowledge of intent; then run docs/playbooks/review-pr.md. State what each pass found, including nothing.' }
  'e2e-pre' { 'run the slice acceptance commands against the real system (make eval; make demo --repeat 3 once it exists), before the PR, and print every command with its verbatim output.' }
  'e2e-post' { 'run the slice acceptance commands against the real system (make eval; make demo --repeat 3 once it exists) against merged main, after the merge, and print every command with its verbatim output.' }
}

switch ($Engine) {
  'cursor' {
    if (-not (Get-Command agent -ErrorAction SilentlyContinue)) {
      Write-Error "cursor CLI 'agent' not on PATH"; exit 127
    }
    $mode = if ($Phase -eq 'gate2') { @('--mode', 'ask') } else { @() }
    "agent -p $($mode -join ' ') `"$task`"  ->  $out"
    # `2>&1` on a native command under $ErrorActionPreference = 'Stop' wraps
    # each stderr line as a terminating NativeCommandError in PowerShell 5.1 -
    # it would abort the script on agent's first stderr line, before the
    # $LASTEXITCODE check below ever runs. Relax to 'Continue' for just this
    # call so a failing agent is reported by exit code, not by an exception.
    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & agent -p @mode $task 2>&1 | Tee-Object -FilePath $out
    $agentExit = $LASTEXITCODE
    $ErrorActionPreference = $previousEap
    # Tee-Object has no -Encoding parameter in Windows PowerShell 5.1 (added
    # in PS7+) and defaults to UTF-16LE, while gate.sh's `tee` writes UTF-8.
    # Re-encode so the same evidence convention does not depend on which OS
    # wrote the file.
    [System.IO.File]::WriteAllText($out, (Get-Content -Path $out -Raw), (New-Object System.Text.UTF8Encoding($false)))
    # Tee-Object is the last command in the pipeline, so PowerShell's own
    # success/failure tracking would otherwise report this wrapper as having
    # succeeded regardless of whether `agent` did. $LASTEXITCODE still holds
    # the exit code of the last native executable that ran (agent), so check
    # it explicitly - the transcript is already written either way.
    if ($agentExit -ne 0) {
      # Write-Error itself throws under ErrorActionPreference = 'Stop', which
      # would mask agent's real exit code behind PowerShell's generic 1.
      # Write directly to stderr so `exit $agentExit` below is what callers see.
      [Console]::Error.WriteLine("agent exited $agentExit - transcript saved to $out; gate did not pass")
      exit $agentExit
    }
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
