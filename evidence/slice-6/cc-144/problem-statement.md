# CC-144: the broader problem, every affected place, what must always hold

Written 2026-11-26 by the implementing session, at the owner's request, before the final project-rules review.
It is a claim to be tested, not a finding. Line numbers: `scripts/jira_gate_line.py` unless named.

## The broader problem

**Something is reported as done, clean, preserved or verified on evidence that does not show it.**

The review rounds kept finding new instances of it, in the script, in the checks of the script, and in the records:

| Form | Instances |
| --- | --- |
| a success compared too little | text only, so a lost link passed (`gate2.txt` P1-1); other lines of the history dropped before counting; another person's history entry taken for this write |
| "nothing left" without having looked | empty search read as clean (P1-4); reworded, split or moved wording (P1-2, P1-8, code-review nit 1); a non-document read as clean; a lagging search index; a refused ticket missing from the approval (P1-7) |
| a reply trusted without checking it | another key after a move; absent or wrong-typed text matching absent text; wrong shapes crashing or reading as open |
| a state change not looked at | closed before or during the write; an edit during the write; an interrupt leaving no FAILED |
| a failure leaving no usable account | HTTP or network errors ending the run without totals; a dry run deleting the files to restore or approve from |
| a test or record claiming more than it ran | a stand-in Jira unlike Jira; stale closure rows; `apply-readback.txt` `same_ids` used `closure.required_ids` on whole text, which drops repeats, yet was reported as "same IDs" (redone in `apply-readback-2.txt`) |

Fixes mostly handled the reported instance. The property that failed was not stated across all places until
`preflight-599a57d.md`, and only for P1-P5 there.

## Every affected place

### A. Statements the script makes

| Place | Claim |
| --- | --- |
| `_listed_keys` 355-362 | this is the list of open tickets (limit L6) |
| `_read_each` 326-352 | each listed ticket was judged, or is refused |
| `changes` 239-253, `refusal` 210-227 | this ticket carries the wording or not; this edit is safe |
| `dry_run` 365-434 | the "N read, M left, K refused" line, exit code, snapshot set |
| `_discard` 292-300, `dry_run` 392-411 | nothing needed for restore or approval is removed |
| `approved_snapshots` 447-470 | these are the bytes the owner approved |
| `apply` 580-599 | one run of a folder at a time |
| `_apply_approved` 625-632 | "done: already reads as approved". It prints before the closed check and is in neither total at 662 |
| `_apply_approved` 633-663 | refusals; FAILED set before the write; totals; exit code |
| `_write` 544-577 | "written" |
| `_fields`, `_issue`, `_text`, `_description_changes` 488-542 | each reply is about this ticket, whole, and of the right type |
| `_stored_form` 473-485 | the stored document equals the approved one |

### B. Records that say something was checked

`evidence/closure/CC-144.toml` (`observed`, `reviewer`, `affects`, `tested_head` of all seven rows); `approval.md`;
`apply.txt`, `tc3.txt`, `apply-readback*.txt`; commit messages; the future PR body and Jira comment.
`scripts/closure.py` 38 and 167 ask only that `reviewer` is non-empty: AC3 and TC3 are PASS with a reviewer text that
says no reviewer has read the run, and `CLOSURE OK` follows. `run-slice.md` line 47 requires verified PASS.

### C. Ticket text and rules after the apply

- The 20 live descriptions. Lines that still point at removed text: `approval.md`, "Text that stays and will read
  wrong". The script's refusal covers the three paragraph openings, one pointer phrase and long pasted sentences, not
  other references such as "gates above".
- Requirements removed and stated in full nowhere in the repo: `approval.md` L1-L11. L1 is "unresolved review findings
  block shipping and Done". `docs/playbooks/review-pr.md` allows "Ship it with follow-ups".
- Rule files that now restate or rely on removed wording: `.claude/DESIGN.md` 123 ("Jira the full protocol");
  `.claude/PLAN.md` 70 ("no observed worsening").

### Adjacent, outside CC-144's scope

On main since e323eaa, `.claude/hooks/ctx.py` denies a subagent call labelled Gate 2 (other than the invariants pass)
unless it uses `gate2-cold`, while `run-slice.md` 148, the `run-slice` skill, `gate.sh` and `gate.ps1` say
`general-purpose`.

## What must always hold

| ID | Property |
| --- | --- |
| H1 | No write unless the approval names the exact bytes, and the last reads before the write show the same key, open, and the approved "before" |
| H2 | "written" only from reads made after the write, about the same key, whole and rightly typed, showing the approved document, open, and this write's one history change |
| H3 | A ticket that was not read or cannot be judged is never counted as clean or done: it is refused or stops the run, and the exit code is not 0 |
| H4 | Every printed line and total is true as of the reads behind it, and every ticket in the approved set is accounted for |
| H5 | A write not confirmed stops the run, leaves a durable marker and keeps the restore source; no run of the tool removes either |
| H6 | Only the approved text changes: AC/TC IDs are equal in order with repeats |
| H7 | No surviving text depends on removed text, and no requirement disappears unless the owner saw it and decided |
| H8 | A record claims no more than the check behind it ran; it names the commit and who checked; a passing form check is not reported as a review |
| H9 | A test stand-in matches the live system in every field the script relies on, and unobserved behaviour is labelled |

## Where these cannot or do not fully hold

- H1, H2: an edit between the last read and the PUT is overwritten (L1); another history entry with the same two texts
  can be taken for this write while this write's entry is unlisted (L3); changes the v2 text omits (L4).
- H2: a change after a ticket's last read is not seen (L2).
- H3: a ticket the search omits is not read (L6).
- H7: does not hold for the references in C. They were listed on the approval sheet before the owner approved.
- H8: `closure.py` cannot tell a review from a sentence saying there was none.
