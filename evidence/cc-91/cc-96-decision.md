# CC-96 decision — 2026-09-20

Decision only. No production code. Live NAME listings this session:
`evidence/cc-91/cc-96-preflight.txt`. CC-76 post-merge miss summary:
`evidence/slice-3/demo-miss-analysis.md` (`q17` still in `demo.misses`).
CC-94 printout of CC-93 post-merge: `q17` 2/3 empty URL; r3 `B24114`
`county:140` `in=state:09`. Did not Read E2E transcripts.

## Answers

### Can NAME listings represent the region without an alias dataset?

No. ACS5 2024: `silicon` / `silicon valley` match **0** of 3222 counties, **0**
of 32330 places, **0** of 935 metro/micro areas. The published neighbour is
`San Jose-Sunnyvale-Santa Clara, CA Metro Area`, a different NAME.

### Is a CC-37 candidate set enough?

Not for a 0-hit region. CC-37 picks returned `GeoSpec`s; it cannot submit
arbitrary `for`/`in`. Empty candidates give the strip nothing to edit.
That is the [CC-55](https://johnhillescobar.atlassian.net/browse/CC-55)
until-clause, not a gazetteer now. Named question if it is ever revisited:
`q17`.

### What class is supported, and what fails closed?

**Supported:** Census-published NAME heads (place, county, state, MSA as
published) and CC-95 same-name candidates.

**Limitation:** informal multi-county vernaculars (Silicon Valley, DMV, SoCal).
0 `GeoSpec`s. Do not last-word substitute. Do not add a new warning code on
this ticket — empty URL stays unanswered until the user names a published
geography.

### Cost

| option | lines / files / deps / latency |
| --- | --- |
| Alias gazetteer | new module; DESIGN §7 and CC-55 forbid it |
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

## Not created

No gazetteer, no Silicon Valley county list, no MSA-metro story, no retrieval
or B/C leaf, no new warning code.
