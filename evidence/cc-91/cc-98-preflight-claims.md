# CC-98 pre-flight — claims vs measured

Raw command output: `evidence/cc-91/cc-98-preflight.txt`.

Settled on `origin/main` @ `dcdfa23`. Jira `CC-98` To Do, parent CC-91.
Did not Read E2E transcripts. Re-proved the CC-94 mechanism; did not reopen
retrieval, B/C, or informal-region misses.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| Finish resolves the raw question when `urls[]` is empty | `finish_tools` dispatches `resolve_geography` with `query=_listing_query(question)`. `_listing_query` returns the question unless a by-county listing rewrite matches | **Holds.** |
| `place_token` of the full question matches zero NAME rows | q39 token is the nine-word sentence; live ACS5 2024 `place:*` `filter_rows` 0. t07 token is the nine-word sentence; 0 hits. Fake listing same | **Holds.** |
| The bare published place name matches | Live `detroit` → 6 places, `named_rows[0]` Detroit city, Michigan `place:22000` `state:26`. `phoenix` → 4 places, Phoenix city, Arizona `place:55000`. Ranking already class then population | **Holds.** Several rows; `specs[0]` is the large city. Not CC-95 Queens-style prefix. |
| Expected table can already be in the search pool | `latest.json` retrieval q39 `got` includes `B25004`. Selector is not the miss. Demo q39 3/3 `table=None` `n_url=0` `warnings=[]` | **Holds.** Never-built, not a wipe (CC-93) and not same-name (CC-95). |
| Informal regions stay CC-96 / CC-99 | q17 `detect_level=county`; `place_token` is still the clause before `counties`. Do not extract `silicon valley` ahead of `_COUNTY` | **Holds as a constraint.** |
| Controls | `New York City` → `new york`. `Austin, Texas` → `austin`. `State College, Pennsylvania` → `state college`. `Harris County, Texas` → `population of harris` (last-word still CC-99) | **Holds as a constraint.** |
| Room in the budgets | geo.py **400/400** so the extract cannot grow this file. geo_list.py **162/400**. finish.py 109. ask.py 399. 0 new files/deps/tools. doc_lines 1571/1800 | **Holds.** Move `place_token` into `geo_list.py` and extract there. Do not raise a budget. |

## Decision

`place_token` extracts the capitalized span after `in` / `for` / `of` (years skipped) so NAME listing can match. `_COUNTY` still wins first. Do not pin golden IDs in tests. Live AC is `q39`. Empty-URL `t07` repeats only, not `B01003` wording.

## Out of this ticket

Informal aliases (CC-96), last-word NAME substitution (CC-99), same-name candidates (CC-95), ACS1 ineligible (CC-97), retrieval, B/C selector, `B01003` pins, candidate-picker UI, new tools/routes/dependencies/graph nodes, budget changes.
