# CC-75 pre-flight — claims vs measured

Raw command output: `evidence/slice-3/cc-75-preflight.txt`.

Settled on `origin/main` @ `1b6e7d9` (CC-74 merged). Jira `CC-75` To Do → In Progress, parent CC-2, supersedes CC-67. CC-72 is Done.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| Each leg checks exact E/M variables, definition, and universe against that dataset/vintage’s metadata | Availability matrix stores per-year `title`, `universe`, and estimate suffixes (M is paired at fetch). `table_facts` already used by `build_url`; `fetch_data` has `published` years only — no per-year variable check. Variable labels are not in the matrix; 2017 vs 2024 `B28001` labels are identical after `label_phrase` | **Holds as a gap.** Join on the matrix in `fetch_data` before GET. Treat empty/`HSHLD`/`Households` and inflation/title-case as the same definition; a real universe or stripped-title change is material. Do not rebuild the matrix. |
| Absence or material redefinition emits localized `variable_not_in_vintage` and prevents a silent join | `evaluate` names: overlapping_vintage … boundary_change_2020 — **no** `variable_not_in_vintage`. `plan_years` omits unpublished vintages as `unpublished_vintage`, not missing variables. ACS5 2016 exists; `B28001`/`B28002` are **absent** in 2016 and present 2017–2024 with the same 11 suffixes | **Holds as a gap.** Omit incompatible attempted years (no GET, no rows) with `variable_not_in_vintage`. Keep overlapping/gap reasons. Ship URLs for years that remain. |
| `t14` identifies years where the computer variable is absent or materially different | `t14` `expect_warning = "variable_not_in_vintage"`, text “since 2013”. Matrix first year is 2016; zero `B28*` tables in 2016 ACS5; `B28001` starts 2017. Labels 2017=2024 | **Holds.** Fire from fetch omissions **and** question years (`since 2013`) against `table_facts`, so a silent start-at-2017 still warns. 2016 is the in-matrix miss. |
| `t09` emits `measure_unavailable` before fetch and explains households with smartphone access | `t09` `expect_warning = "measure_unavailable"`. Guard list has no such function. `B28001_005E` is “Smartphone” under universe Households. Census has no device-count table | **Holds as a gap.** Question-only guard (cell/mobile phones), like `zcta_not_zip`. Does not skip fetch. Detail names B28001 / households / smartphone. |
| `make demo` includes `t09` and `t14`; stop dropping `t09`–`t14` in `is_slice1()` | `is_slice1` drops `t>=9`, holdout, and `q23`. Golden scope test asserts `t09` out and n=51 | **Holds as a gap.** Drop `t>=15` instead. Holdout, `q23`, `t15`–`t18` stay out. n becomes 57. |
| When those warnings fire, `urls[]` still ships | `_WARNING_WITHOUT_FETCH` is only `ambiguous_place` / `geography_not_nested`. Empty URL with the right warning is `empty url`. `series_from_record` already keeps a built URL | **Holds as a constraint.** Do not clear URLs on these warnings. Omit incompatible years from rows, not from kept-year URLs. |
| CC-72 must be Done; no new tool; no budget raise | CC-72 Done. `ask.py` 391/400; `guards.py` 389/400; `fetch.py` 368/400; `doc_lines` 1781/1800; tools 4/6 | **Holds as a constraint.** New guards live in `vintages.py` so `guards.py` only gains evaluate names. Wire `table_facts` into `fetch_data`. No PLAN/DESIGN prose beyond the checkbox; ARCHITECTURE only. |

## Decision

Filter `fetch_data` attempted years through the availability matrix (suffixes + normalized title/universe). Emit `variable_not_in_vintage` for omitted incompatible years and for question years the table does not cover. Emit `measure_unavailable` from cell-phone wording without blocking fetch. Include `t09`–`t14` in `make demo`.

## Out of this ticket

`MOE_diff` / shared-sample caveat / `q23` / `t15`–`t18` (CC-76). Cousin-table long-tail misses. Plan strip (slice 4). Raising any budget. A semantic ontology. Variable labels in the matrix.
