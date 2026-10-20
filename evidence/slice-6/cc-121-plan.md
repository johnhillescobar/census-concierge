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

## Pending batches (nothing done yet; each needs its own "yes")

- R2: repo. Rebase the local commits onto `origin/main` (15 commits ahead: PR #110 and #111), dropping `7aebf3a`, which duplicates `3b785a4` already on `main`. The branch is unpushed.
- J2: Jira correction comment: the 2026-10-20 comment says number words appear in 1 of 120 answers; that count used a word set that is now removed. Post a one-line withdrawal, plus the owner direction on number words (`owner`).
- P2: live probe of whether the model writes no digits when told not to (40 visible questions, repeat 1; needs OpenAI and Census credits). Only on an explicit go-ahead.
- M1: memory. Rewrite `project_cc121_answer_figures.md` and `feedback_phase1_yardstick_url_is_product.md` once the direction is final.
- G: Gate 1, Gate 2 (fresh `general-purpose` subagents, transcripts under `evidence/slice-6/`), E2E pre-PR (`scripts/e2e_capture.py`, needs keys and credits), PR, merge, E2E post, Jira close card.
- Ruling needed: CLAUDE.md says phases persist to "git/PR/evidence and Jira"; `run-slice.md` says "or Jira". Default: one short Jira comment per gate.
