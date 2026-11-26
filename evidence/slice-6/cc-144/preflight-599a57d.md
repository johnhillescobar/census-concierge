# CC-144: pre-flight for the findings on 599a57d (for the owner, before any code change)

Code at 599a57d. Nothing here is fixed yet. Reviews: `gate2-codex-599a57d.txt`, `gate2-cursor-599a57d.txt`, and a second
review the owner pasted into the session (late edit, lost link). Runs: `preflight-599a57d-matrix.txt` (fake Jira, current
code, script in `preflight-599a57d-matrix.py.txt`), `preflight-599a57d-live.txt` (real Jira, search and GET only).
Line numbers are `scripts/jira_gate_line.py`.

## Verdicts

| Review claim | Verdict |
| --- | --- |
| moved ticket accepted under its old key (Codex) | valid: P1 |
| missing v2 text and an empty history row count as this write (Codex, Cursor) | valid: P2 |
| two description items in one history row, only the last compared (Cursor) | valid: P3 |
| an edit after the read-back, its row not yet listed, still "written" (pasted) | valid: P4 |
| a link added before the write is lost and "written" (pasted) | not as stated: only a fake that drops links. Valid as a test defect: P5 |
| another row with the same two texts is accepted (Cursor) | reproduces; a limit (L3), not fixed |
| v2 returns a document, so every write fails (Cursor) | not seen: 148 of 148 non-empty are strings. P2's type check would stop it before a write |

## P1. A reply is not checked to be about the ticket asked for

Places: dry-run read (`_read_each` 279); search keys (279); apply: v2 read (500), stored read (501) including the "done"
path (502), PUT by key (423), read-back v2 (424) and stored (425); `_listed` accepts any project (256). The history reply
carries no key, so only the issue reads around it can cover it.

Must hold: every issue reply used carries the requested key; only `CC-` keys are listed or written. A mismatch at the dry
run refuses the ticket (exit 1, not in the manifest); before a write refuses it (no write); after a write leaves FAILED
naming the key that answered.

## P2. Absent or wrong-typed values are accepted as evidence

Places: v2 `was` (500) and `now` (424): no type check; history ends (412) are compared with those two, so they are covered
once both must be non-empty strings; dry run (219) **silently counts a ticket as clean when its description is not a
document** (found while tracing; run: "0 ticket(s) left to change", exit 0). Already safe: pre-write and read-back
descriptions are compared whole with the snapshot; missing `status`, `values` or `total` raise; an empty search is a
fault. Pre-write read errors are not caught (499-501): the run ends with a traceback, nothing written (from the code).

Must hold: a ticket is clean only when its description is a document without the wording, or null (empty); any other type
is an error. No write without a non-empty v2 string before it; no "written" without one after it.

## P3. Part of the history is dropped before counting

Place: `_description_changes` (409-412) keeps one pair per row id. Same function, checked on real data: the `fieldId`
filter (0 description items lack it), paging (CC-42 read 3 rows at a time equals one read), ids (numeric, unique).

Must hold: across all new rows there is exactly one description item. A row seen on two pages counts once.

## P4. "written" claims more than the last read showed

Places: `_write` reads the history last (426), after the stored description; the "written" line, FAILED removal, the
count, exit 0; the docstring and `approval.md`. The "done" line and the dry run's counts are true as of each read.

Must hold: "written" is printed and FAILED removed only if the script's **last** request for that ticket returned the
approved description, the requested key, open. Change: read the issue record after the history (a reorder, no new request).

## P5. The test fake is not Jira where the script depends on it

| Reply | Test fake | Real Jira |
| --- | --- | --- |
| v2 text | drops marks | link 47/47, code 1372/1372, bold 136/136, italic 7/7 show (earlier run) |
| issue reply | no `key`, `id` | both, on 149/149 for v2 and v3; asking `cc-104` answers `CC-104` |
| empty description | v2 `""` | v3 null and v2 null (1 ticket) |
| history row | id `CC-1-0`; no `author`, `created` | numeric id, `author`, `created`, `items` |
| history page | `values`, `total` | also `startAt`, `maxResults`, `isLast` |
| history item | `fieldId`, `fromString`, `toString` | also `field`, `fieldtype`, `from`, `to`; 258/258 rows have one item, both ends text |
| search | returns descriptions, ignores the query | each issue has `id`, `key`, `fields` |
| PUT | returns `{}` | `_api` turns an empty body into `{}` (code read; no PUT sent) |
| history timing | listed at once | **not known** |

Must hold: every field the script reads has, in the fake, the shape and type seen on Jira; behaviour not seen is labelled
as an assumption in the fake.

## Combined test cases

Oracle: (a) no write when a change was visible to a pre-write read; (b) another person's change overwritten by the write
is never reported "written"; (c) the P4 rule. Fix for (b)'s limits: L3 and L4 are excluded by name.

**T1, timing: 96 cases.** One action before each of the 7 requests about a ticket (positions 0-6) or after the last (7).
Actions: edit, link (history late: none, theirs, ours, both), close, move (none, ours).
Order after the P4 change: history, v2, stored | PUT, v2, history, stored.

| Position | Expected |
| --- | --- |
| 0-2 | refused, no write |
| 3 (just before PUT) | the write cannot be stopped; not "written", FAILED left |
| 4-6 | not "written", FAILED left (a close after the write also stops: over-reports, safe) |
| 7 | "written" allowed (L2) |

Current code, run: breaks only at position 6 for edit and link (their row late) and close, and at 0-6 for move (history on
time); move also writes at 0-2. No case reports an overwritten edit or link as "written". After the change all 96 must
pass: a prediction until run.

**T2, bad replies.** At each reply the script uses: another key; description string where a document belongs; v2 null,
`""`, object. History: ends missing; two items in one row (other one first, and last); two rows; one row on two pages
(counts once). Together: v2 null both times with an empty history row. Before a write: refused, no write. After: FAILED.

**T3, dry run.** Between search and read: edit (picked up), close (dropped), move (refused, exit 1). Description string or
object (refused, exit 1, never counted clean); null (clean). A manifest with a non-CC key: nothing written.

**T4, limits pinned.** The L2 and L3 cases pass as "written", named as limits, so a change in behaviour is seen.

Every new check is mutation-checked: removing it fails a test.

## Known limits

- **L1** An edit between the last pre-write read and the PUT is overwritten. No conditional write was found.
- **L2** A change after a ticket's last read is not seen, including while later tickets are written. No end-of-run pass.
- **L3** With this write's row not listed, another row with the same two texts is accepted. Requiring the script's account
  would help only against another account: on the 20 tickets 101 of 120 past changes are the token's account, 19 another.
  `default`: leave as a limit.
- **L4** A change the v2 text does not show. None of 258 real changes has identical ends, which does not prove there is no
  such change. The 20 tickets hold only link (11) and code (5) marks and headings, paragraphs, lists and line breaks.
- **L5** Not observed, because it needs a write or a moved ticket (no Key or project change in any CC history): the PUT
  reply; that this write's history ends equal the v2 text and are listed at once; that a GET after a PUT is current, and
  that a GET shows others' edits at once; whether an old key works for GET or PUT; history of an emptied description.
  If the first apply fails for one of the first two reasons it stops after CC-104, the first ticket.
- **L6** A ticket the search does not list is not read. The shared `jira_fetch._search` also returns a short list without
  an error when a later page has no `issues` or a page token repeats (run; found while tracing). 54 open tickets are under
  its 100 per page. `owner` (2026-11-25, in chat): "leave the shared code unchanged and document its limit, keeping
  CC-144 to one script". Recorded here and in `approval.md`.

## If approved

Change `scripts/jira_gate_line.py`, its tests, and CC-144 evidence (`approval.md`: these limits, and CC-3 corrected to
CC-104). No ticket wording, rule or budget. The proposed ticket text is not touched, so the manifest hash should stay
`b586fe37...` (to confirm by a live dry run). Then: mutation checks including the earlier sets, `make check`, live read-only
dry run, closure record, and an independent review (Codex or Opus cold read, `/code-review`, `review-pr`) before any claim
that it is ready. No APPROVED file and no `--apply` without the owner.
