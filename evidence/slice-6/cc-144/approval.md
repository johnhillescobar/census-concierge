# CC-144: what the owner approves (AC3)

20 descriptions. Read `snapshots/<KEY>.before.md` against `snapshots/<KEY>.after.md`. In each, the pasted blocks listed in
`plan.md` become this one line, and the "Existing scope (...)" pointer becomes "Existing scope":

> Gate: docs/playbooks/run-slice.md; scripts/closure.py checks the AC/TC record, and scripts/metric_compare.py judges
> measured runs by evals/metric_protocol.toml.

The `.md` files show text only. Links, headings and lists are kept (the write is compared in full), but are not visible there.
Criterion IDs are unchanged in all 20. Eight of them have no AC/TC IDs, so for those only the before/after read protects.

**Read "A requirement the apply removes" below first. Approving the snapshots accepts it.**

## How to approve and apply

Run both from the worktree folder (`.worktrees/cc-144`). The first, in PowerShell, puts the manifest hash alone in
`APPROVED`; the file may be UTF-8, or UTF-16 as Windows PowerShell 5.1 writes it:

    'b586fe375a9c511c7e37d8f88e97eec55f9b22a12f95e4fa21c5b39662410e05' > evidence\slice-6\cc-144\snapshots\APPROVED

    uv run --env-file ../../.env python scripts/jira_gate_line.py --apply --approved evidence/slice-6/cc-144/snapshots

The worktree has no `.env` of its own, so `--env-file` is needed. A live dry run on the final code (`live-five.txt`) made
81 files byte-identical to the committed ones, with the same hash.

## While the apply runs

**Do not edit any of the 20.** No way was found to make a Jira write conditional, so an edit that lands between the
script's last read and its write is overwritten. The script cannot prevent it. It counts a write only when the one new
description change in the history goes from the text read before the write to the text read after it, and the ticket, read
last, still holds the approved description under the same key and is open. Otherwise it stops and leaves `FAILED`; Jira's
history keeps each version.

Edit a ticket by hand only **after** the apply: a description changed before it is refused as stale.

**The first apply may stop after CC-104, the first ticket in the order, although nothing is wrong.** No description has
been written, so it is not known that Jira's history entry for this script's write holds exactly that text, or lists it at
once, or that a read right after a write is current. If not, the run leaves `FAILED` after one ticket: check that ticket
and its History before deleting the file.

After the apply, run the dry run again (TC3) and compare its "open ticket(s) read" count with Jira's own.

## What the script does not catch

| Limit (`preflight-599a57d.md`) | What happens | Decided by |
| --- | --- | --- |
| L1 | an edit between the last read and the write is overwritten; it is caught only as above | no fix found |
| L2 | a change after a ticket's last read is not seen, even while later tickets are written | default |
| L3 | while this write's history entry is not listed, another entry with the same two texts is taken for it | **owner, 2026-11-25** |
| L4 | a change that Jira's text form does not show cannot be compared | no fix found |
| L5 | the behaviour listed in the paragraph above on the first apply was never observed | needs a write |
| L6 | a ticket the search does not list is not read; `jira_fetch._search` can return a short list with no error | **owner, 2026-11-25**: shared code unchanged |

L6: the 54 open tickets are under the 100 per page it asks for, and on the final code the dry run, the search and Jira's
own count all gave 54 (`live-five.txt`). The L6 decision was made in chat. It is recorded here and in
`preflight-599a57d.md`; CC-144 has no Jira comment about it.

Also not recognised: a copy of the pasted wording rewritten in all of its opening words and long sentences, or held only
in a node's attributes (an expand's title); and a wrong value in a reply that has the right shape.

## Choices made without the owner (`default`, each revertible)

- A dry run stops, changing nothing in its folder, when the search or any ticket's read fails, an HTTP error included, so
  that an outage does not remove an earlier set. A ticket deleted after the search listed it does this until the search
  catches up. `--apply` refuses such a ticket and goes on.
- A history page that is empty before the total it gives is rejected.
- Without `--out`, each dry run makes a new temporary folder, and removes it if nothing was written there.
- **AMENDED closure rows need no command.** AC4's text has no such exemption.

## A requirement the apply removes

**"Unresolved review findings block shipping and Done"** (L1 below) is in the removed text, and no repo file states it in
full: `review-pr.md` allows "Ship it with follow-ups" and blocks only silent-wrong-answer findings.

## Requirements the removed text states and no repo file states in full (Gate 2 search)

These numbers are this list's own, not the script limits above.

- **L1** "unresolved review findings block shipping and Done". The one that changes behaviour.
- **L2** CC-104 only: its own clearance paragraph says post-merge evidence for TC14 is not due before merge. AC11 and
  TC14 keep the run timing, not that exemption. CC-104 resumes after CC-145.
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

## Text that stays and will read wrong (found by Gate 2; the script edits no criterion)

| Ticket | Line | Problem |
| --- | --- | --- |
| CC-3 AC4 | "apply the stricter B/P/A/L ... gates above" | points at removed gates; treats A as blocking |
| CC-39, CC-43, CC-107, CC-108 | checklist: "no more than 3 points below the 0.742 baseline (>= 0.712) and ... this ticket's own pre-run" | the ratified rule allows 0.07 and compares pooled runs. PLAN keeps the 0.712 floor; the pre-run half conflicts |
| CC-104 AC11, amendments | comparisons against A | the protocol makes A report-only |
| CC-104 history section | "the rule it sat beside still holds in that paragraph" | the paragraph is gone |
| CC-132 | "mandatory AC/TC clearance already applied to CC-3"; AC1 "B/P/A/L non-regression gates" | both point at removed text |

CC-42 and CC-136 also use the names A/L and B/P/A/L, which PLAN still defines.

Not edited by CC-144: `.claude/DESIGN.md` section 8 says "Jira the full protocol", which is no longer so after the apply,
and PLAN's latency paragraph still requires "no observed worsening" where the protocol allows 2.5 s. Both belong with CC-145.

## Before anything is pushed

- **The repository is public.** Pushing publishes the 20 ticket-description snapshots. The invariants review's pattern
  scan of CC-144's evidence, fixtures, script and tests found no email, API key or token (`gate2-r5-invariants.txt`).
- **A PR to `origin/main` would also include e323eaa**, a harness commit that is on local `main` and no remote. It is
  outside this ticket and no review of this ticket read it.
- **Four review files are not in git** (`gate2-code-365adee.txt`, `gate2-codex-599a57d.txt`, `gate2-cursor-599a57d.txt`,
  `gate2-owner-review.txt`), though this ticket's records cite the first three. They are the owner's and were left alone.
  One more outside review exists only as text pasted into the session.

## Gate results

Earlier rounds, all kept: Gate 1 `gate1.txt` and `gate1-fixes.txt`; Gate 2 `gate2.txt`, `gate2-r2.txt` and their fix
files; the owner's outside reviews of d1c5ee4 (three script bugs, `review3-fixes.txt`) and of 365adee (four more,
`review4-fixes.txt`). Outside reviews of 599a57d then found more (`preflight-599a57d.md`), fixed in 22c6ab8.

This round:

| Step | Read | Result | File |
| --- | --- | --- | --- |
| Gate 1, separate agent | 85ed3e9 | every product revert caught after tests were added; one low defect and 10 stand-in survivors, handled in 9485c97 | `gate1-r5.txt`, `gate1-r5-fixes.txt` |
| cold bug review (another model) | 7f34a67 | 5 low, none blocking | `gate2-r5.txt` |
| `/code-review` | 7f34a67 | 4 nits | `gate2-r5-code-review.txt` |
| `review-pr` | 0b2088c | **Not yet**: closure record stale, AC3 and TC3 not run | `gate2-r5-invariants.txt` |
| fix b8f66f0 | | 23 of 23 reverts caught | `gate2-r5-fixes.txt` |
| the one cold re-run | 16d510d | 2 low, 3 nits | `gate2-r5-rerun.txt` |
| fix 6f054c5 | | 10 of 10; this round's earlier sets 23 of 23, 13 of 13 and 10 of 10 | `gate2-r5-rerun-fixes.txt`, `gate2-r5-rerun-earlier-sets.txt` |
| `make check` recipe lines | f356193 | all exit 0: 2128 passed, 34 skipped, 8 xfailed; 112 web tests | `make-check-five.txt` |
| live dry run, reads only | f356193 | 54 read, 20 to change, 0 refused | `live-five.txt` |

- **No cold review has read 6f054c5.** The playbook allows one re-run after a fix.
- `review-pr` ran before the two fix rounds and has not read the final code.
- The mutation checks of 9485c97, b8f66f0 and 6f054c5 were run by the session that wrote the fixes, not by a separate agent.
  First runs that missed a revert or stopped on a stale anchor are kept in the same files.
- Mutation sets from before this round were last rerun at 85ed3e9 (`gate1-r5.txt`), not on the final code.

Closure: AC1 AC2 AC4 TC1 TC2 PASS; AC3 TC3 NOT RUN. Earlier `make-check*.txt` and `closure-run*/` are kept.
No E2E: no `api/src`, `evals/` or run-harness file changed.
