# CC-99 pre-flight — claims vs measured

Raw command output: `evidence/cc-91/cc-99-preflight.txt`.

Settled on `origin/main` @ `ba90c51`. Jira `CC-99` In Progress, parent CC-91.
CC-96 already settled live ACS5 2024 listings (0 `silicon valley`
place/county/MSA hits; last-word `valley` → `county:140` CT) in
`evidence/cc-91/cc-96-preflight.txt`. Did not Read E2E transcripts. Did not
open a gazetteer, MSA-metro, or retrieval leaf.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| `named_rows` last-word fallback is what produces a Valley* county | `filter_rows("silicon valley")` is `[]`. `named_rows("silicon valley")` equals `named_rows("valley")`: Naugatuck Valley Planning Region CT `county:140` then Valley County ID. Rank is population, so CT wins. Same FIPS as the CC-94 r3 URL | **Holds as the defect.** |
| Latest demo miss is still this mechanism | `evidence/latest.json` q17 3/3 `ambiguous_place` (several Valley* hits after CC-95). Not a gazetteer miss and not finish/`place_token` (CC-98) | **Holds.** Fail closed is 0 specs, not a candidate list of Valley counties. |
| `place_token` of q17 is the clause before `counties` | `detect_level=county`; token `occupation breakdown for workers in silicon valley`. Greedy `_COUNTY` in `geo_list.py` | **Holds.** `_COUNTY` now lives in `geo_list.py` (CC-98 moved it); geo.py is 381/400 and stays untouched. |
| Harris still depends on last-word today | `place_token("population of Harris County, Texas")` is `population of harris`; `named_rows` last-word finds Harris TX. Bare `Harris County, Texas` is already `harris` | **Holds as the control.** Drop last-word only after the county token is the name before `county`. |
| Room in the budgets | geo_list.py **200/400**, geo.py **381/400**, ask.py 399, doc_lines 1574/1800. 0 new files/deps/tools/routes/warning codes | **Holds.** Do not raise a budget. |

## Decision

Stop last-word NAME substitution in `named_rows`. Tighten `_COUNTY` so
`population of Harris County, Texas` tokenizes as `harris` without that
fallback. Informal/alias questions stay the existing tools (CC-96). Do not
pin `q17` `answered_rate` or `B24010`.

## Out of this ticket

Gazetteer or alias dataset (CC-55, CC-96). Same-name published geography
(CC-95). Finish extracting a published place (CC-98). ACS1 ineligible
(CC-97). Atlanta metro / MSA listing. Table retrieval / B24010.
Candidate-picker UI (CC-37). New warning codes, tools, routes, dependencies,
graph nodes, budget changes.
