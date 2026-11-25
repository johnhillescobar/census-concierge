# CC-144: what the owner approves (AC3)

20 descriptions. Read `snapshots/<KEY>.before.md` against `snapshots/<KEY>.after.md`. In each, the pasted blocks listed in
`plan.md` become this one line, and the "Existing scope (...)" pointer becomes "Existing scope":

> Gate: docs/playbooks/run-slice.md; scripts/closure.py checks the AC/TC record, and scripts/metric_compare.py judges
> measured runs by evals/metric_protocol.toml.

The `.md` files show text only. Links, headings and lists are kept (the write is compared in full), but are not visible there.
Criterion IDs are unchanged in all 20. Eight of them have no AC/TC IDs, so for those only the before/after read protects.

To approve, put the manifest hash alone in `snapshots/APPROVED`:
`b586fe375a9c511c7e37d8f88e97eec55f9b22a12f95e4fa21c5b39662410e05`

Edit a ticket by hand only **after** the apply: a description changed before it is refused as stale.

**Do not edit any of the 20 while the apply runs.** Jira offers no conditional write, so an edit that lands between the
script's last read and its write is overwritten. The script detects this afterwards from the ticket history, stops and
says so; Jira's history keeps the overwritten text. It cannot prevent it.

The hash is the same as before the three later fixes because the proposed text did not change. The script did.

## Text that stays and will read wrong (found by Gate 2; the script edits no criterion)

| Ticket | Line | Problem |
| --- | --- | --- |
| CC-3 AC4 | "apply the stricter B/P/A/L ... gates above" | points at removed gates; treats A as blocking |
| CC-39, CC-43, CC-107, CC-108 | checklist: "no more than 3 points below the 0.742 baseline (>= 0.712) and ... this ticket's own pre-run" | the ratified rule allows 0.07 and compares pooled runs. PLAN keeps the 0.712 floor; the pre-run half conflicts |
| CC-104 AC11, amendments | comparisons against A | the protocol makes A report-only |
| CC-104 history section | "the rule it sat beside still holds in that paragraph" | the paragraph is gone |
| CC-132 | "mandatory AC/TC clearance already applied to CC-3"; AC1 "B/P/A/L non-regression gates" | both point at removed text |

CC-42 and CC-136 also use the names A/L and B/P/A/L, which PLAN still defines.

## Requirements the removed text states and no repo file states in full (Gate 2 search)

- **L1** "unresolved review findings block shipping and Done". `review-pr.md` allows "Ship it with follow-ups" and
  blocks only silent-wrong-answer findings. The one that changes behaviour.
- **L2** CC-104 only: its own clearance paragraph says post-merge evidence for TC14 is not due before merge. AC11 and
  TC14 keep the run timing, not that exemption. CC-104 is next to resume.
- **L3** an unsupported result may pass a negative control, never a supported positive case.
- **L4** a new capability's initially unavailable score is not compared with unrelated legacy categories.
- **L5** interpretation, faithful execution and end-to-end answers are scored separately (CC-3 and CC-132 still say it).
- **L6** supported scope and thresholds are frozen before implementation.
- **L7** the matrix carries B/P/A/L values, uncertainty, inherited floors and dependency evidence.
- **L8** a gain in one story category cannot offset a loss in another (the script enforces this for frozen cohorts only).
- **L9** baseline and candidate run at the same concurrency.
- **L10** uncertainty is not a proven improvement; a runtime repair cannot trade quality for latency.
- **L11** the audit paragraph's "these additions do not reopen a Done story or claim implementation is complete".

The old no-observed-decrease, -0.02 bound, 3-point and blocking-A rules were replaced on purpose by the ratified rule
and are not losses.

Not edited by CC-144: `.claude/DESIGN.md` section 8 says "Jira the full protocol", which is no longer so after the apply,
and PLAN's latency paragraph still requires "no observed worsening" where the protocol allows 2.5 s. Both belong with CC-145.

## Gate results

Gate 1 `gate1.txt` (81 GOOD, 0 BAD, after tests were added for 20 surviving probes; it found two defects, fixed in
`gate1-fixes.txt`). Gate 2 `gate2.txt` (ten code findings, fixed in `gate2-fixes.txt`; its third run is 25 GOOD, 0 BAD, the
first two kept). Re-run `gate2-r2.txt` (round one fixed; three low findings, fixed in `gate2-r2-fixes.txt`). An outside review of d1c5ee4, run by the owner,
then found three script bugs the gates had not stopped: lost edits and overlapping runs, an inexact copy left beside the
gate line, and cleanup deleting files a manifest named. Fixed: `review3-fixes.txt`, `review3-probes.txt`. **No review has
read these last fixes or the re-run ones.** `make-check-final.txt`: every recipe step passes on the final code (`npm ci` first failed twice on a locked folder;
`make-check-failed-over-pinned-file.txt` is a run that overwrote a pinned file and failed for that reason; `make-check.txt`
is the earlier passing run). Per-criterion output: `closure-run-final/`. Closure: AC1 AC2 AC4 TC1 TC2 PASS; AC3 TC3 NOT RUN.
No E2E: no `api/src`, `evals/` or run-harness file changed.
