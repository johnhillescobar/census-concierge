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

## Pending batches (nothing done yet; each needs its own "yes")

- R1: repo. Commit this plan and the saved description. Decide the branch: revert `d9c5eb5` (wiring and prompt) and `4a89748` (the rule amendment from the 2026-10-18 design) or rework them, keeping the `figures.py` rendering where the 2026-10-04 design reuses it. Mark the three stale transcripts (`cc-121-gate1.txt`, `cc-121-gate2.txt`, `cc-121-gate2-rerun.txt`) as pre-rebuild or `git rm` them (default: mark).
- M1: memory. Rewrite `project_cc121_answer_figures.md` and `feedback_phase1_yardstick_url_is_product.md` once the direction is final.
- G: pre-flight of open claims, Gate 1, Gate 2 (fresh `general-purpose` subagents, transcripts under `evidence/slice-6/`), E2E pre-PR (`scripts/e2e_capture.py`, needs keys and credits), PR, merge, E2E post, Jira close card.
- Ruling needed: CLAUDE.md says phases persist to "git/PR/evidence and Jira"; `run-slice.md` says "or Jira". Default: one short Jira comment per gate.
