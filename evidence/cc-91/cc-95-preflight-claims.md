# CC-95 pre-flight — claims vs measured

Raw command output: `evidence/cc-91/cc-95-preflight.txt`.

Settled on `main` @ `d36cef5`. Jira `CC-95` To Do, parent CC-91.
CC-76 post-merge misses (`evidence/slice-3/demo-miss-analysis.md`): q10, q11,
q15, q17, q18, q20, q34, q39, q41, t07, t11, t14. Did not Read transcripts.
Live NAME listing: ACS5 2024 `place:*&in=state:*` (32330) and `county:*` (3222).

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| A published name can match several Census NAME rows | `filter_rows("springfield")` → 29 places. `filter_rows("cook")` on counties → 3 (IL, GA, MN). Ranking already `place class, population, GEO_ID` (`rank_matches`) | **Holds.** Target the same-name fixture (`t05` / Cook County). |
| Candidates on the response are executable GeoSpecs, not a name string | `AskWarning.model_fields == ['code', 'detail']`. `GeoSpec` already has level, name, geoid, for_spec, in_spec, dataset, vintage, codes. `ambiguous_place` joins `row.name` into `detail`. `assemble` does not copy `record.geographies` onto the response | **Holds as a gap.** Put ranked `GeoSpec`s on `AskWarning.candidates`. Building `CensusURL` from those fields redacts `&key=` (measured). Do not add `ResultPlan` (CC-90). |
| Silent first-match substitution | `t05` 3/3 answered with `ambiguous_place` **and** `place:70000&in=state:29` (Springfield MO). `ask.py` `_absorb` sets `geography = geographies[0]`. Model summary hides alternative codes (`state:13 not in content`) | **Holds as a constraint.** Keep `specs[0]` as the current usable result (CC-37). Make the rest executable on the warning so the pick is not silent. |
| q10 is a published-name miss, not informal | r1 `county:081&in=state:36` (Queens NY) wrong table `B16001`. r2/r3 `place:63116&in=state:42` with **no** `ambiguous_place`. Live NAME: 1 place `Queens Gate CDP, Pennsylvania` (pop 1602) and 1 county `Queens County, New York` (pop 2323052). `filter_rows` prefix-matches `Queens Gate` because the head starts with `queens ` | **Holds as a gap.** Tighten `filter_rows` so a leading token must be the whole head or the head plus a Census class (`city`/`county`/`CDP`/…). Empty place listing then falls back to county. Do not rank county above city when both are real hits (Milwaukee County 926k > Milwaukee city 567k would regress q18). |
| Exclude wrong-table and informal-region | `silicon valley` → 0 place and 0 county NAME hits (CC-96 / q17). q10 table `C16001` vs `B16001` is the B/C selector, not this leaf. q11 Atlanta is cousin-table + CBSA. q39 Detroit / t07 Phoenix empty URL is finish `place_token` of the raw question (CC-98); both names have several place rows when the token is just the city | **Holds.** Do not pin golden IDs in tests. Live proof is q10 r2/r3 geography, not answered_rate on C16001. |
| Unambiguous place/county/metro/wildcard/ZCTA/non-nesting must not regress | `Harris County, Texas` is already a single county spec in tests. `Portland, Maine` stays state-qualified. Metro, wildcard, ZCTA, `geography_not_nested` are other `for_level`s — county fallback is `for_level == "place"` and `level is None` only | **Holds as a constraint.** One unambiguous control: Harris County. |
| Room in the budgets | geo.py **394/400**, ask.py **399/400** (do not edit), guards.py **368/400**, geo_list.py **142/400**, domain models **7/15**, doc_lines **1557/1800**. `candidates: list[GeoSpec]` is not a new model. Client regen required | **Holds.** Extract `named_rows` so the county fallback fits in geo.py. |

## Decision

1. `filter_rows`: leading token + Census class, not arbitrary prefix. Later whole-word still matches `West Springfield`.
2. Unspecified place with zero NAME hits: list counties with the same `in=` and reuse `named_rows`.
3. `ambiguous_place` ships `candidates: list[GeoSpec]` in ranked order. `specs[0]` remains selected. No new tool, route, graph node, or ResultPlan.

## Out of this ticket

Informal regions (CC-96). Finish extracting a place from the raw question (CC-98). ResultPlan (CC-90) and candidate-picker UI (CC-37). Gazetteer. Metro listing. Budget raises.
