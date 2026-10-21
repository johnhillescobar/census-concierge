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

## Pending batches (nothing done yet; each needs its own "yes")

- M1: memory. Rewrite `project_cc121_answer_figures.md` and `feedback_phase1_yardstick_url_is_product.md` once the direction is final.
- G: Gate 1, Gate 2 (fresh `general-purpose` subagents, transcripts under `evidence/slice-6/`), E2E pre-PR (`scripts/e2e_capture.py`, needs keys and credits), PR, merge, E2E post, Jira close card.
- Ruling needed: CLAUDE.md says phases persist to "git/PR/evidence and Jira"; `run-slice.md` says "or Jira". Default: one short Jira comment per gate.
