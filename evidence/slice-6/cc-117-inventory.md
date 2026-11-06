# CC-117 inventory: every place a table is chosen or injected from question text

Taken on `d0d7995` (main). Commands: `git grep -n "pinned_table\|device_table\|measure_unavailable\|_with_device\|Sibling\|_BRACKET_TABLE"`
and a scan of `api/src` for table-ID literals (`\b[BC]\d{5}[A-I]?\b`).

| # | Site | What it does from question text | CC-117 action |
|---|---|---|---|
| 1 | `vintages.py` `_RENT`, `_FAMILY_INCOME`, `_DISTRIBUTION`, `_POVERTY`, `_UNINSURED`, `_COMPUTER`, `_DEVICE` (7 regexes) + 6 table-ID constants | map phrases to B25064, B19113, B19001, B17001, B27001, B28001 | removed |
| 2 | `vintages.py` `device_table`, `pinned_table` | return the pinned ID | removed |
| 3 | `tools.py` `_with_device_table` (called in `SearchTablesTool._arun`) | promotes the pinned table, or injects it into hits when retrieval did not return it | removed |
| 4 | `finish.py` `finish_tools` (`pin`) | re-runs search when the pin is absent from the pool; uses the pin as the build table | removed; build uses plan table or `pool[0]` |
| 5 | `rerank.py` `PROMPT` "Sibling rules" | names commute, SNAP and college-major cases and their table titles | replaced by one measure-agnostic principle |
| 6 | `vintages.py` `measure_unavailable` (reads `_DEVICE`), registered in `guards.evaluate` | warns that ACS does not count devices; text names B28001 | removed with `_DEVICE`; warning no longer raised (see Losses) |
| 7 | `guards.py` `_BRACKET_TABLE = "B19001"` in `finish_aggregation` | adds B19001 to Alternatives when the *selected* table is B19013 and the question asks to combine areas | **kept, flagged.** Keyed on the selected table plus `_COMBINE`, not a pick; it adds an alternative only. Owner decision if it should go. |
| 8 | `guards.py` `_household_income_median` (`== "B19013"`) and the B19001 sentence in `median_not_aggregatable` | warning text keyed on the selected table | kept, same as 7 |

Not table choice (checked, left alone): `retrieval/text.py`, `metadata.py`, `build.py` mention IDs in comments only.

Leakage baseline: the 8 `# CC-117:` lines in `evals/leakage_baseline.txt` deleted (the file only shrinks).
`check_invariants.py` regex call sites: 62 -> 55 (delta -7).
