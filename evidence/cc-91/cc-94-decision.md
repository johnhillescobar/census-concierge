# CC-94 decision — 2026-09-20

Diagnostic only. No production code. Pinned post-merge scoreboard:
`evidence/slice-3/cc-93-e2e-post.txt` (`answered_rate` 0.850, `p95` 18.308s,
`--repeat 3`, n=186). Retrieval floors from `evidence/latest.json`
(`retrieval_at_10` 0.90, `selector_at_1` 0.875, `index_hash` 377cd59fe62a) —
that file is the last `merge_evidence()` write (186 trials), not a reconstructed
post-merge stub. Did not Read the E2E transcript body. Used the DEMO/MISSES
printout URLs, retrieval/selector miss lists, one `search()` top-10 pass, and
`place_token`/`filter_rows`.

## Groups

### 1. Finish resolves the raw question; NAME listing misses the place

**Mechanism.** `finish_tools` calls `resolve_geography` with the user question
when `urls[]` is empty. `place_token` returns the whole sentence. `filter_rows`
matches the NAME head against that token (`==`, prefix, or word boundary), so
"Detroit city, Michigan" does not match
`why are so many homes in detroit sitting empty?`. No `GeoSpec`, no URL.
`search()` still ranks `B25004` at 2; the selector does not miss `q39`.

**Evidence.** `q39` 3/3 empty table and empty URL, no warning. `t07` r2 same
empty path (`place_token` of the Phoenix question also matches no Phoenix NAME
row). `t07` r3 is a different miss (wrong table on a legal ACS1 Phoenix URL).

**Owner.** [CC-98](https://johnhillescobar.atlassian.net/browse/CC-98). Not CC-93 (nothing
was built). Not CC-95 (Detroit / Phoenix are unambiguous). Not CC-97 (`t07` r3
already fetched ACS1 for Phoenix).

**Boundary.** `api/src/geo.py` `place_token` (and/or the query `finish.py`
passes). Mutation: a full-question token that today matches zero NAME rows
should match the published place; revert the extract, the new test fails.

### 2. Informal multi-county region — already owned

`q17` 2/3 never-built; r3 fetched `B24114` for Connecticut county 140.
`B24010` is also out of the search top-10. Geography is CC-96. Do not add a
retrieval leaf on the same ID.

### 3. Published same-name geography — already owned

`q10` r3 is `place:63116` in `state:42` (Pennsylvania), not Queens County NY.
CC-95. r1/r2 already resolved Queens NY; those misses are group 4.

### 4. Selector prefers B over C — no change

`q10` is the only golden `expect_table` starting with `C`. `search()` ranks
`C16001` at 1; `choose()` returns `B16001` (prompt: prefer B when both fit).
Demo 3/3 `B16001`. B is the detailed twin; C is collapsed. Do not invert that
rule for one fixture. Alternatives panel is CC-11.

### 5. Expected table out of search top-10 — no change

`q17` `q18` `q20` `q34` are the four long-tail `@10` misses (floor 0.90 is
met). Selector cannot pick a table it never sees. Distinct cousins, not one
code-boundary fix. A `B01003` wording pin for `t07` is the predecessor's
constant-table fake. Trap rate is not gated. User-facing cousin display is
CC-11 alternatives, not a new retrieval story.

### 6. 1/3 noise inside floors — no change

`q08` race iteration `B18101F` (member of the correct family, Vermont counties
correct). `q18` tenure cousin once. `q43` travel-time vs departure-time once.
`q15` / `q41` retrieval `@1` misses that the selector already recovers.

## Leaves created

One Story: [CC-98](https://johnhillescobar.atlassian.net/browse/CC-98) extract a
published place name when finish resolves the raw question. Live acceptance:
`q39`. Empty-URL `t07` repeats only, not `B06001`.

## Not created

No retrieval story, no B/C selector story, no population pin, no duplicate of
CC-93 / CC-95 / CC-96 / CC-97.
