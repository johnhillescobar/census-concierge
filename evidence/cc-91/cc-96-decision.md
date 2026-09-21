# CC-96 decision — 2026-09-20

Decision only. No production code. Live NAME listings this session:
`evidence/cc-91/cc-96-preflight.txt`. CC-76 post-merge miss summary:
`evidence/slice-3/demo-miss-analysis.md` (`q17` still in `demo.misses`).
CC-94 printout of CC-93 post-merge: `q17` 2/3 empty URL; r3 `B24114`
`county:140` `in=state:09`. Did not Read E2E transcripts.

## Answers

### Can NAME listings represent the region without an alias dataset?

The listing cannot. ACS5 2024: `silicon` / `silicon valley` match **0** of 3222
counties, **0** of 32330 places, **0** of 935 metro/micro areas. The published
neighbour is `San Jose-Sunnyvale-Santa Clara, CA Metro Area`, a different NAME.
That is a matcher fact, not “the agent must not answer alias questions.” The
LLM uses the existing tools (`search_tables`, `resolve_geography`, `build_url`,
`fetch_data`) and emits geography in Census shape.

### Is a CC-37 candidate set enough?

Not by itself for a 0-hit listing. CC-37 picks returned `GeoSpec`s; it cannot
submit arbitrary `for`/`in`. The agent still has the tools. A gazetteer
*module* remains the [CC-55](https://johnhillescobar.atlassian.net/browse/CC-55)
until-clause (NAME ranking and the plan strip still fail a named golden
question). That parks a module, not alias questions.

### What the matcher must not do

Informal multi-county vernaculars (Silicon Valley, DMV, SoCal) are not Census
NAME heads. `named_rows` must not last-word substitute. After a 0-hit listing,
the loop still has tools; it does not wait for the user to rename the place.

### Cost

| option | lines / files / deps / latency |
| --- | --- |
| Alias gazetteer *module* | CC-55 until-clause, not this spike. Informal questions use the existing four tools |
| Extra MSA listing | one Census GET; still 0 Silicon Valley hits; Atlanta metro is a different miss |
| Fail closed | `named_rows` in `geo_list.py` (162/400). `_COUNTY` / `place_token` sit in `geo.py` at **400/400**, so a greed fix must extract first. 0 deps. 0 extra listings |
| New warning code | `docs/requirements.md` + `_WARNING_WITHOUT_FETCH`. Not required to stop the lie |

Do not raise a budget.

## Silent substitution (why a leaf exists)

`detect_level(q17)` is `county`. `place_token` is the clause before
`counties`. `named_rows` retries the last word `valley` and ranks
**Naugatuck Valley Planning Region, Connecticut** `county:140` (pop 454969).
That is the CC-94 r3 URL. It is not `ambiguous_place`.

Last-word fallback is also how `population of Harris County, Texas`
(`place_token` = `population of harris`) still finds Harris. A leaf that
drops last-word must keep that control.

## Leaves created

One Story: [CC-99](https://johnhillescobar.atlassian.net/browse/CC-99) do not
resolve unpublished region names via last-word NAME hits. Until it ships,
`q17` can still become `county:140` CT. `q17` `answered_rate` / `B24010`
stay unpinned (`B24010` is still out of search `@10`).

## Not created in this spike

No gazetteer module (out of scope for the spike; CC-55 still owns that until-
clause). No Silicon Valley FIPS table, no MSA-metro story, no retrieval or
B/C leaf, no new warning code, no LangGraph alias graph.

## Addendum — 2026-09-20 (owner)

Informal and alias questions are in scope for the agent. The LLM collects
tool results and returns geography in the Census shape those tools require.
CC-96 did not forbid that. A gazetteer *module* is a later, separate until
(CC-55). CC-99 only stops the matcher last-word-substituting `valley` into
Naugatuck Valley CT.
