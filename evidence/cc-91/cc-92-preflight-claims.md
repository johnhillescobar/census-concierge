# CC-92 pre-flight — claims vs measured

Raw command output: `evidence/cc-91/cc-92-preflight.txt`.

Settled on `origin/main` @ `fb77a1e` (docs-align). Jira `CC-92` To Do, parent CC-91.
CC-76 post-merge scoreboard (`evidence/slice-3/demo-miss-analysis.md`, `evidence/latest.json`):
`t14` missing `variable_not_in_vintage` on ACS1 US trials; ACS5 trials warn.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| `t14` can ship B28001 rows without `variable_not_in_vintage` | latest.json repeat 3: ACS1 2016–2024 `for=us:1`, 8 rows, warnings `vintage_gap_2020` only. Repeat 1 ACS5 county listing did warn. Guard with that ACS1 artifact returns `None` | **Holds.** Lost on the ACS1 path. |
| Per-vintage E/M, definition, universe vs authoritative metadata | Matrix stores E suffixes only (`metadata.variables` drops M). ACS5 2016 B28001 **ABSENT**; ACS1 2016 **present**, 11 E, same title/universe encoding as 2024 (`same_definition` True). Trailing-colon label_sig 2016≠2024 is punctuation, not a redefinition. On-disk `label_sig` is missing (`None`) | **Holds as a gap.** ACS5 2016 absence is never recorded once ACS1 wins. Requiring M against the E-only matrix would drop every year. |
| Finish-time scan recovers silent start-at-2017 | `variable_not_in_vintage` reparses `question_years` (`[2013]`), clamps to first published year of the **chosen** dataset, then `drop_incompatible`. ACS1 published starts 2016 and B28001 exists there, so 2013–2015 are dropped from the scan | **Holds as the lost state.** Clamping plus ACS1 choice erase the ACS5 2016 hole. Ticket: do not add another finish-time layer. |
| Warning must not depend on LLM prose / tool-call luck / question text | Model years `[2016..2024]` omit 2013. Fetch `requested_years` then never includes 2013. Guard re-parses the question and still misses on ACS1 | **Holds.** Persist the question span on fetch; emit from `omission_reasons` only. |
| Compatible legs keep URL, E/M, GEOID, universe, vintage | ACS1 miss still has paired E/M URLs and rows. `_apply_variables` only sees `plan.attempted` after unpublished/gap drops | **Holds as a constraint.** Reclassify unpublished years *before* the table’s first in-matrix year when any dataset has a published hole in the requested span. Do not omit ACS1 2016 (it exists). Do not treat B19013-since-2013 unpublished years as missing (no hole). |

## Decision

At fetch: union the question’s requested span into `requested_years`. After `plan_years`, join attempted years on E (and M when the reference vintage lists M) plus definition/universe. If any dataset has a published hole for the table in that span, unpublished years before the chosen dataset’s first present year become `variable_not_in_vintage`. The assemble guard reads those reasons only.

## Out of this ticket

ACS1 geography eligibility (CC-97). Table retrieval. Geography aliases. URL construction. UI. New tools/routes/dependencies/graph nodes. Budget changes. Rebuilding `availability.json.gz`. Treating colon-only label_sig as a redefinition.
