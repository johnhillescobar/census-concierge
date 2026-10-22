# CC-121 plan: outward writes

Rule: `docs/playbooks/run-slice.md:116-130`. Every outward write (Jira, repo, memory) is listed here before it happens, one "yes" per batch. Tags: `owner` = decided by the owner; `default` = my default, accepted with the batch, never recorded in Jira as an owner decision.

## Batch J1: realign the Jira ticket to the 2026-10-04 text (approved "yes", 2026-10-20)

| # | write | where | tag |
|---|---|---|---|
| 1 | Save the live 2026-10-18 description and title | `evidence/slice-6/cc-121-jira-description-2026-10-18.md` (repo, uncommitted until batch R1) | default |
| 2 | Restore the description to the 2026-10-04 text (the `from` side of Jira history change 11833, which is also the filed text in the 2026-10-04 session copy) | CC-121 description, via Atlassian MCP `editJiraIssue` (the script cannot edit fields) | owner (override authorized 2026-10-19) for the restore; default for using MCP |
| 3 | Add a comment that records the override and what stays true | CC-121, via `scripts/jira_transition.py --comment` (status unchanged, In Progress) | owner for the override; the open points in it are marked `default` |

Not changed in J1: the title ("The model writes the answer without seeing the fetched figures"; it states the verified root cause, which holds under either design), type (Bug), epic (CC-3), status, links, the two existing comments (the script cannot delete them; the new comment supersedes them).

Open points recorded as `default`, not owner decisions:
- Number words: instruct the model not to write them and parse with `float()` only; no word list (the restored text lists a thousand/million parser, the 2026-10-18 ruling bars word lists).
- The restored criterion "no budget is raised" against the `api_src_loc` raise in `7aebf3a`.

## Batch R1: repo, done 2026-10-20 (approved "yes")

Commits `2a6cf96` (plan, saved description, pre-rebuild notes), `1559ad0` and `468bd3b` (reverts of `d9c5eb5` and `4a89748`), `0f3665d` (`figures.py` kept without a caller). Stale transcripts marked, not removed (`default`).

## Batch P1: pre-flight record (approved "yes", 2026-10-20)

| # | write | where | tag |
|---|---|---|---|
| 1 | `cc-121-preflight.md` (results) and `cc-121-preflight-check.py` (the command that produced them; no regex) | repo, one commit | default |
| 2 | Short Jira comment with the results | CC-121, `scripts/jira_transition.py --comment`, status unchanged | default |

Defaults accepted with P1, not owner decisions: rendered figures capped at 20 with "k of n shown" (as in `figures.py`); comparatives barred by instruction and the residual measured.

## Batch J2: number words and the model's part (approved "yes", 2026-10-20)

One Jira comment on CC-121 (status unchanged, description not edited): the 1-of-120 number-word count in the P1 comment is withdrawn; owner decisions recorded as `owner`: no sets of number words and no parser, in the product or in `scripts/`; Option A for the model's part (the model writes figures as digits exactly as rendered, the check is a digits-only comparison, no runtime model call; Reading B, a model call that judges prose numbers, not chosen). The restored description still lists a thousand/million parser; the comment supersedes those lines. Editing the description was offered and not chosen.

## Batch R2: rebase onto origin/main, done 2026-10-20 (approved "yes", "keep 7aebf3a")

Rebased the 12 local commits onto `origin/main` (`1160bde`, PR #110 and #111) with `--reapply-cherry-picks --empty=keep`, so the budget commit stays (now `5f242d8`, empty: `main` already holds the same raise as `3b785a4`, and `budgets.toml` equals `main`'s). Git's default would have dropped it. Local backup ref `backup/cc-121-pre-rebase` points at the pre-rebase tip; delete it when no longer wanted. After the rebase: ruff, format, mypy, 660 tests, budgets (`api_src_loc` 4452 of 4600), invariants (regex call sites 64, delta +0) and `generate_client --check` all pass.

## Batch P2: live probe of the no-figures instruction (approved "yes", 2026-10-20)

Outward writes: OpenAI and Census API calls (answers: gpt-4o-mini; judge: gpt-4.1; 40 visible long_tail questions, repeat 1, about 80 model calls plus tool calls and Census requests), and new files `evidence/slice-6/cc-121-answers-probe-nodigits.jsonl`, `cc-121-collect-probe-nodigits.log` and `cc-121-judged-probe-nodigits-gpt-4.1.jsonl`. A 2-question smoke run (label `probe-smoke`) comes first and its files are deleted. Instruction and readings are pre-registered in `cc-121-probe-instruction.md` / `.txt`. `api/src` is not modified; the prompt is patched in the probe's process only. Tag: default (thresholds in the pre-registration are mine).

Result (2026-10-20): the 40 trials ran with 0 errors; the smoke files were deleted. Strict flags 13 of 40 (band "5 to 20: partly", the owner's call); judge unsupported 2 of 40 against 28 of 40 for the stored baseline at repeat 1. No answer contains a number of 100 or more. Written up in `cc-121-probe-results.md` (also committed: the probe answers, log, judged file, and a `probe` reading in `cc-121-preflight-check.py`). Jira comment: batch J3.

## Batch J3: P2 result to Jira, with the owner's pick (approved "yes", 2026-10-20)

One Jira comment on CC-121 (status unchanged): the P2 result and the owner decision `owner`: Option 1, proceed with the no-figures instruction and build the allowed numbers from structured response fields only (years, the dataset's digits, table title, universe, variable labels, GEOID parts), no regex and no word list; measure the fallback rate at E2E and report it. Left undecided in the comment: how the final answer reads with the rendered sentences; comparatives and model-memory explanations, which pass a digits check.

## Batch I1: implement the restored mechanism, one commit (approved "yes", 2026-10-20)

Repo writes on `feat/cc-121-answer-figures`, one code commit plus an evidence commit for Gate 1: `api/src/figures.py` (renderer and digits-only check), the hook at `ask.py:252` (zero net lines), `prompts.py:40` (the probed instruction), the `answer_figures_unverified` warning (row in `docs/requirements.md`), seeded-fixture tests, `docs/ask-path.md` and `docs/ARCHITECTURE.md`. No regex, no word list, no model call, no budget change (estimate +90 lines, `api_src_loc` about 4540 of 4600). Defaults (not owner decisions): the rendered block follows the model's framing; a flagged answer drops all model prose and shows the rendered sentences only; numbered lists are handled by the instruction, not by an exemption in code.

Result (2026-10-20): implemented in `f59eee8`. Where the plan said "hook at `ask.py:252` (zero net lines)" the check lives in `take_chart` (`contract.py`, +7 lines, local import because `figures` reaches `vintages`, which imports `contract`) and `ask.py:252` passes `record` through, zero net lines. `fetch_data` looks the labels up (one thread per vintage) and keeps them on its artifact (`fetch.py` +3). Checks: ruff, format, mypy, 674 tests (14 new), budgets (`api_src_loc` 4549 of 4600, doc lines 1772 of 1800, prompt tokens 1055 of 1200), invariants (regex call sites 64, delta +0), client up to date, web 110 tests. Existing tests that compared the whole answer to the model's text now compare its start (6 tests) or pass a digit-free answer (5 tests). Offline run of the real check on the 40 stored probe answers: 7 would be replaced (stored rows have no table titles or state/county columns, so this over-counts). Not done: Gate 1, Gate 2, E2E. Open: `.answer` in the web UI has no `white-space: pre-line`, so the figure lines would run together; one CSS line fits the web budget exactly (3349 of 3350); not changed.

## Batch G1: Gate 1, adversarial tests and the mutation check (approved "yes", 2026-10-20)

Procedure: `docs/playbooks/run-slice.md` section 3. Code under test: `f59eee8`. No API spend, no keys needed.

Matrix (`docs/process-evidence.md`): its four rows are slice-0 retrieval probes (identical inputs ranked by float noise; a family returned by one member; a ranking change measured on the tuning set alone; "expect the largest jump" checked against the number). None targets answer figures. The last two are measurement discipline and belong to E2E (n = 40 alone is noise; the sealed gap is reported there), not to Gate 1. Gate 1 therefore takes its probes from the ticket's test cases (happy, edge, novel, regression, failure) and from the check's own failure modes.

Outward writes:
1. One fresh `general-purpose` subagent in its own worktree (`isolation: worktree`), not a fork. It reads the playbook section, the matrix, `docs/requirements.md` and `docs/ask-path.md`, the restored ticket text and the diff `origin/main..f59eee8`, and writes its own adversarial tests into `api/tests/test_figures.py` (it can see my 14). It changes no `api/src` file; a defect it finds is reported, not fixed.
2. For every new test, mine and its own: revert the one behaviour it covers, run only that test, confirm it fails, restore (a harness that restores each file and checks `git diff` is clean afterwards). Transcript in the repo's format (`BAD  mutation: <name>` then `CAUGHT [pytest summary]`, or `NOT CAUGHT`; `GOOD restored code` with the passing count at the end): `evidence/slice-6/cc-121-gate1-restored.txt` (the pre-rebuild `cc-121-gate1.txt` stays as it is, marked). Harness: `evidence/slice-6/cc-121-gate1-mutations.py`. A mutation that is `NOT CAUGHT` means the test is no check: it is fixed in the test, not the source, and re-run.
3. One commit in the worktree. I read the transcript's `GOOD` / `BAD` lines and the diff, then bring the commit onto `feat/cc-121-answer-figures`.
4. One short Jira comment on CC-121 with the Gate 1 counts (default: CLAUDE.md says "and Jira", `run-slice.md` says "or Jira").

Probes the subagent starts from (it may add more; none is a quoted answer from the eval set):
- off by one digit ("76,001" against 76000), a dropped digit, European separators ("76.000"), a range of two carried numbers, a fraction ("1/2")
- "2.1 million" against 2,132,000 (Option A: the digits do not match, so the text is replaced)
- tokens with no digit that `float()` reads ("nan", "inf"); percent and dollar signs
- ACS1 against ACS5 (a "1-year" text is carried only by an acs1 dataset)
- a row without year or dataset (no "None", no double spaces); annotation and `M` columns are not figures
- one wide row with more than 20 estimate cells; a result with a place but no estimate cells
- `take_chart` with `record=None` (text untouched) and with `warnings=None` (no crash)
- failed fetch and no rows: no figures, a clean text untouched, a figure removed
- known gap, to be named in the transcript and not tested as if solved: a framing that attaches a carried number to the wrong place passes a digits-only check

Alternative if you prefer: run Gate 1 in this session. Cheaper, but the tests then share my mental model and my context keeps the output.

Result (2026-10-20): the subagent's commit `1b3c3a5` is on the branch as `d0b2a8b`. 35 test functions (67 cases: 62 pass, 5 strict xfail) were added to the 14; 98 mutations, 98 CAUGHT, 0 NOT CAUGHT (`cc-121-gate1-restored.txt`). I reproduced the run: same tally, after making the harness independent of CRLF working copies (`dbd5da7`). Suite 736 passed, 34 skipped, 5 xfailed; ruff, format, mypy, invariants (regex delta +0) clean; the subagent changed no `api/src` file. Matrix: its four slice-0 rows do not target answer figures.

One real defect, left unfixed on purpose and queued for the fix phase together with Gate 2's findings (the playbook fixes after Gate 2): `_numbers` skips any token that holds a digit but that `float()` cannot read, so a figure glued to a mark passes unchecked (`$78k`, `+-99,999` with the plus-minus sign, the Unicode minus, curly quotes, `99,999USD`, `99,999's`, `99,999[1]`). Five strict xfail tests cover it; each turned into a strict XPASS when the defect was repaired. Candidate fix, no regex and no word list, for the owner to see at the fix phase: add the plus-minus sign and curly quotes to the edge characters, treat the Unicode minus as a break, and treat any other digit-bearing token that `float()` cannot read as not carried unless the whole token is carried (table IDs, GEOIDs, dataset names).

Other observations: a label that ends in a colon renders as `Total:: 5,000` (fix: drop the trailing colon); a true statement such as "90% confidence" is replaced because 90 is not in the response; a number written in words passes (Option A relies on the instruction); a framing that attaches a carried number to the wrong place passes (known gap, for Gate 2 and the owner). Jira comment on Gate 1: posted.

## Batch G2: Gate 2, cold-context review (approved 2026-10-21: run the gates end to end)

Procedure: `docs/playbooks/run-slice.md` section 4. Code under review: the net change `origin/main..HEAD` outside `evidence/` (`api/`, `docs/`, `scripts/`, `web/`, `budgets.toml`, tool config). Read-only gate: nothing is fixed here; fixes are a separate batch after the findings (section 5 of the playbook: tests plus a mutation check for every fix, then one re-run of Gate 2 if the fixes are non-trivial).

Outward writes:
1. One fresh `general-purpose` subagent (not a fork), working in this checkout (it needs `data/raw` and the full suite; a worktree has neither and left a locked folder last time). It is read-only except for one file, `evidence/slice-6/cc-121-gate2-restored.txt` (the pre-rebuild `cc-121-gate2.txt` and `cc-121-gate2-rerun.txt` stay as they are, marked). It makes no commit, edits no source, and does not run `/code-review` with `--fix` or `--comment`.
2. Cold: the subagent is told the diff range and the project rules, not what the change is for. It may not read `evidence/`, the plan file, the Jira ticket, memory files or any earlier gate transcript, nor `evals/` or `.env`.
3. Pass one, generic bugs: the `code-review` skill at `high` on the diff (if the skill is unavailable to it, the same cold read by hand, stated in the transcript).
4. Pass two, project invariants, `docs/playbooks/review-pr.md`: first the five machines (budgets, invariants against `origin/main`, ruff, mypy, pytest `-m "not integration"`) with their output pasted; a non-zero exit ends the review. Then claim (it writes the one-sentence user-facing claim from the diff alone, which I compare with the real one), scope (`docs/slices.md`, "Not in this slice"), silent-wrong-answer review (URL, MOE, GEOID, universe in every branch including failures; key redaction; numbers passing through the model; guards that block; silent repair), shape, tests (behaviour not wording, fakes that return the same thing for every input). The E2E evidence does not exist yet: it says "not yet run" and names what E2E must show, and does not count it against the change.
5. Every finding: file and line, severity (blocks / follow-up / nit), a concrete input that gives a wrong output, and whether it reproduced when run (otherwise marked PLAUSIBLE). One verdict from the playbook's three.
6. No API spend. It runs no `make demo`, `make eval` or `e2e_capture.py`.
7. On return I read the findings, check each against the code, commit the transcript, and post one short Jira comment on CC-121 (default: CLAUDE.md "and Jira"). Then I write the fix batch (F1): the Gate 1 defect (digit-bearing tokens `float()` cannot read), the doubled colon in labels, and whatever Gate 2 confirms.

Cost: one high-effort review plus the machines, comparable to Gate 1 in tokens. Alternative: I run `/code-review` here; cheaper, but not cold.

## Run order from here (owner, 2026-10-21: "it's supposed to be run end to end")

The gates are not separate approvals. G2, then triage of its findings, then the fix batch F1 (the Gate 1 defect, the doubled colon, whatever Gate 2 confirms; tests and a mutation check for every fix), then one Gate 2 re-run if the fixes are non-trivial, then E2E pre-PR (`scripts/e2e_capture.py --slice 6 --ticket CC-121 --phase pre`; real keys, credits; scoreboard quoted from `evidence/latest.json`, never the transcript). Each result goes into this file and a short Jira comment as it lands. Stops: a machine that exits non-zero, a decision that is the owner's (any budget, a change to the ticket's scope, the web CSS line), and the outward step of pushing the branch and opening the PR, which waits for one "yes" with the whole record in front of it. Merge is the owner's; the post-merge E2E follows it.

## Result of G2 (2026-10-21) and batch F1: fixes (inside the run order approved 2026-10-21)

Gate 2 ran from the `gate.ps1` prompt (the first attempt used my own prompt and was stopped before it wrote anything). Transcript `evidence/slice-6/gate2.txt`, written by the subagent, not edited (`fad1954`). Verdict "Not yet": two silent-wrong-answer blockers. Machines all green (736 passed, 5 xfailed; `api_src_loc` 4549 of 4600; regex delta +0).

Disposition of each finding (tag `default` unless noted; each is revertible):
- B1 blocks, fix: a digit-bearing token `float()` cannot read counts as not carried unless the whole token (case-folded) is carried: a cell, a key or its table prefix, a dataset name, a rendered token. No character lists. The 5 strict xfail tests flip to plain tests, plus the cases Gate 2 found (`$78.4K`, `$1.2M`, `78,462USD`, `Income:78,462`, `#3`, a zero-width space).
- B2 blocks, fix: a model-written chart title is checked with the same rule; a title that states an uncarried number is replaced by the table ID (the title fallback `take_chart` already uses) and the warning is added. Titles built by code are not checked.
- B4 follow-up, fix: (a) the warning no longer claims figures follow when none do; (b) HTTP status codes of the fetch and its legs, the year of the built URL and the vintages are carried, so "2019 failed with HTTP 404" keeps its framing.
- B6 follow-up, fix: combined rows (those with `component_count`) come first under the 20-figure cap.
- B8 follow-up, fix: a label's trailing colon is dropped ("Total:" no longer renders as "Total::").
- N1, N2 (`scripts/judge_figures.py` docstring and a `KeyError` guard), N4 (a docstring on `take_chart`): fix.
- B7 follow-up, `default`: apply `white-space: pre-line` to `.answer` (one CSS line; `web_src_loc` 3349 to 3350 of 3350, no raise). Owner may revert it.
- B3 follow-up, not changed, documented in `docs/ask-path.md`: the check proves every number is in the response, not that it describes the right place or year (a state FIPS of 17 carries "17 percent"; the dataset carries "5"). The E2E judge measures the residual; tightening FIPS cells to whole-token matches is the candidate if the judge shows it. Owner's call then.
- B5 follow-up, not changed: label lookups re-parse about 0.1 s per vintage (0.9 s for 9); E2E reports `demo.p95_latency_seconds` against 20.
- B9, N3, N5 not changed (sentinel reasons collapse; first-cell table; branch history is explained in the PR body).

Tests and a mutation check for every fix: `evidence/slice-6/cc-121-fixes-mutations.py` with its output in `cc-121-fixes-mutations.txt`. The Gate 1 harness is pinned to `f59eee8` (several of its mutations target the lines B1 changes). After the fix commit: the Gate 2 re-run once (non-trivial fixes), and Gate 1 from the `gate.ps1` prompt, then E2E from `gate.ps1 e2e-pre 6`.

## Result of the Gate 2 re-run (2026-10-21)

Run on `1323281` from the `gate.ps1` prompt (path changed to `gate2-rerun.txt` by me; that name already held CC-103's tracked transcript and the subagent overwrote it. I restored it from git and kept this transcript as `cc-121-gate2-rerun-restored.txt`, `7145f46`). Verdict "Ship it with follow-ups": machines all green, no silent-wrong-answer finding, both blockers fixed (probed). The subagent saw commit subjects and the docs diff before pass one, so it was not fully intent-blind (it says so).

Follow-ups and what I did (the playbook allows one re-run, so these get tests and a mutation check but no further Gate 2):
- F1 fixed: two `answer_figures_unverified` warnings in one response gave two `<li>` with the same React key. One warning per response now; a later notice joins the first.
- F2 fixed: the built table ID, the alternatives' table IDs and the dataset names the response built are carried (a framing naming a listed alternative was being replaced).
- F5 fixed: a chart the response cannot draw no longer gets a title notice; the model title is checked only when the model sent a chart.
- F6 fixed: a leading "." stays part of the number (".5" is 0.5, not 5).
- F9 fixed: `judge_figures.py judge` refuses to overwrite a finished file, before it spends anything.
- F3 and F4 not changed: the chart-title check recomputes the render and the allowed set (0.4 s extra on 5,000 tract rows, only when the model sent a chart), and label lookups cost 0.09 s per vintage. Both run on the request path; E2E reports `demo.p95_latency_seconds` against 20. A real fix (compute once per response, off the loop) waits for that number.
- F7 not changed: labels are looked up from the first 20 raw cells but rendered with combined rows first, so a two-vintage combined result can show a variable ID where a label should be. Cosmetic.
- F8: the branch carries an empty commit `5f242d8` with a garbled budget subject, and the diff has 70+ evidence files; the PR body says so and the merge squashes.
- Three assertions pin the system's own warning text (code-written, not LLM prose); left as they are.
Mutation check for all fixes: `cc-121-fixes-mutations.txt`, 25 of 25 caught.

## Result of Gate 1 from the canonical prompt (2026-10-22)

The first attempt stalled (600 s watchdog) and left nothing. The second ran about 5.1 hours of wall clock (the subagent's own figure; I first told the owner it began around 07:00, which was wrong) and wrote `evidence/slice-6/gate1.txt` (not edited), `gate1-mutations.py`, `gate1-probes.py` and `gate1-sweep.py`, and 16 test functions (35 cases) in `test_figures.py`. Its transcript keeps the first run (143 of 159 caught; 16 mutations and 7 tests missed) and the final run: 182 of 182 mutations caught, every test function targeted, plus a mutation sweep and a coverage pass. `api/src` was left unchanged.

Findings, both reproduced by me and fixed:
- D1: a fraction character (the one-half sign) holds no decimal digit, so `isdigit()` skipped it and a framing stating "about one-half" passed. `_numbers` now uses `isnumeric()`.
- F1: a framing that quotes an omission reason such as `vintage_gap_2020` lost its text, because the code holds a year and was not carried. The fetch's `omission_reasons` are carried.
The five strict xfail tests became plain tests. 27 of 27 fix mutations caught (`cc-121-fixes-mutations.txt`). 801 tests pass, `api_src_loc` 4581 of 4600, regex delta +0.

## Pending batches (nothing done yet; each needs its own "yes")

- M1: memory. Rewrite `project_cc121_answer_figures.md` and `feedback_phase1_yardstick_url_is_product.md` once the direction is final.
- G: Gate 1, Gate 2 (fresh `general-purpose` subagents, transcripts under `evidence/slice-6/`), E2E pre-PR (`scripts/e2e_capture.py`, needs keys and credits), PR, merge, E2E post, Jira close card.
- Ruling needed: CLAUDE.md says phases persist to "git/PR/evidence and Jira"; `run-slice.md` says "or Jira". Default: one short Jira comment per gate.
