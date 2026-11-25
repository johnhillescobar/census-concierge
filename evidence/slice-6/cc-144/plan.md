# CC-144 plan: one line names the gate in every open ticket

Branch `cc-144/gate-line` (worktree `.worktrees/cc-144`), cut from origin/main 0b69842. Contract: the Jira description of CC-144.
Final run: not required (no `api/src`, `evals/` or run-harness file; CC-143 AC11, computed by `closure.py`).

## Criteria and expected outcomes (fixed before code)

| ID | Expected |
| --- | --- |
| AC1 | `--dry-run` lists every open ticket carrying the pasted wording and writes before/after snapshots; the only Jira calls are reads |
| AC2 | `pytest api/tests/test_jira_gate_line.py -q` passes; a ticket whose criterion IDs would change is refused |
| AC3 | owner approves the snapshots; `--apply --approved <dir>` writes only them; each edited ticket has the same IDs after |
| AC4 | the playbook pre-flight step says every criterion names a command; `closure.py check` rejects a row without one |
| TC1 | an edit that would drop or add an ID is refused, ticket unchanged |
| TC2 | `--apply` without an approved snapshot directory exits non-zero and writes nothing |
| TC3 | a second `--dry-run` after `--apply` finds nothing left |

## Pre-flight claims

| Claim | Command | Result |
| --- | --- | --- |
| "about 23 open tickets" carry the wording | JQL `project = CC AND statusCategory != Done`, 54 issues, text compared | **20**: CC-3 39 42 43 77 82 104 105 106 107 108 115 118 119 122 129 130 131 132 136 |
| the paste is identical everywhere | paragraph text compared | three blocks; two have one variant each, both on CC-104 |
| the closure check rejects a row with no command | `closure.problems` on a NOT RUN row | **no**: only PASS rows are checked. That is the AC4 change |
| existing manifests survive the stricter check | every `evidence/closure/*.toml` | rows with no command are all AMENDED (CC-125, CC-126, CC-138) |
| room for a playbook line | `check_budgets.py --structural-only` | doc lines 1820/1820: the sentence goes on an existing line |
| criterion IDs are unique per ticket | `required_ids` per line | **no**: CC-3 has AC1 in two sections, so IDs are compared with repeats, in order |

## What is replaced

Each affected ticket ends with exactly one line:

> Gate: docs/playbooks/run-slice.md; scripts/closure.py checks the AC/TC record, and scripts/metric_compare.py judges measured runs by evals/metric_protocol.toml.

1. The paragraph "Metric progression and non-regression contract (2026-11-08 refinement)": 18 tickets.
2. The paragraph "Mandatory AC/TC clearance before shipping": 18 tickets.
3. The paragraph "Existing AC/TC, earned floors, family-based uncertainty, ...": 8 tickets.
4. In tickets that lose block 1, the line "Existing scope (the stricter metric contract above controls ...)" becomes "Existing scope".

A paragraph is replaced only when its text matches the pasted text exactly (sha256). A reworded copy refuses the ticket.
Never edited: AC/TC lines, checklist criteria, "Model-owned intent" blocks, anything ticket-specific.

## Defaults (revertible; the owner sees them at snapshot approval)

- `default` The scope of "pasted gate wording" is the three blocks and the one pointer line above.
- `default` CC-104's variants are replaced too. They differ in pre-merge/post-merge staging and drop the CC-125/126 sentence.
- `default` Approval is a file `<dir>/APPROVED` holding the sha256 of `<dir>/manifest.json`, written by the owner. New snapshots void it.
- `default` AMENDED manifest rows need no command: they are out of scope.
- `default` A ticket that never carried the wording gets no line (AC1 lists only carriers).

## Outward writes, in order

1. Jira: CC-144 To Do -> In Progress (`jira_transition.py`), at implementation start.
2. Git: commit on `cc-144/gate-line`. Push and a draft PR: ask first.
3. Jira: the 20 description edits, by the script only, after the owner approves the snapshots (owner decision on CC-144).
4. Jira: one comment on CC-144 with the gate results.
