# CC-96 pre-flight — claims vs measured

Raw command output: `evidence/cc-91/cc-96-preflight.txt`.

Settled on `main` @ `054f91a`. Jira `CC-96` In Progress, parent CC-91.
CC-76 post-merge miss summary (`evidence/slice-3/demo-miss-analysis.md`)
lists `q17`. CC-94 printout of the CC-93 post-merge scoreboard: `q17` 2/3
empty URL, r3 `county:140` `state:09`. Did not Read E2E transcripts.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| Informal multi-county names are not Census NAME rows | Live ACS5 2024 listings: `silicon` / `silicon valley` → 0 of 3222 counties, 0 of 32330 places, 0 of 935 MSA/micro areas. `San Jose-Sunnyvale-Santa Clara, CA Metro Area` exists under a different published name | **Holds.** No alias dataset can be replaced by NAME listing. |
| Treating this as ordinary ambiguous-place resolution risks silent substitution | `place_token(q17)` is the clause before `counties`. `named_rows` then last-word `valley` → `Naugatuck Valley Planning Region, Connecticut` `county:140` (pop 454969). Same FIPS as the CC-94 r3 URL | **Holds as the defect.** Not several Springfields. |
| A small user-editable candidate set (CC-37) is enough | CC-37 geography control cannot submit arbitrary `for`/`in`; it picks returned `GeoSpec`s. 0 hits → nothing to pick. CC-55 already parks a gazetteer until NAME ranking **and** that strip still fail a named golden question | **Holds as a constraint.** Do not gazetteer now. Named question if that until-clause is ever met: `q17`. |
| Class to support vs structured limitation | Published NAME heads (place / county / state / MSA as published) plus CC-95 same-name candidates. Informal vernaculars (Silicon Valley, DMV, SoCal) are not a NAME | **Holds.** Fail closed: 0 specs, no last-word substitute. |
| Line / file / dependency / latency cost | Alias module: new file + DESIGN §7 gazetteer + CC-55 forbid. Extra MSA listing: one Census GET, still 0 Silicon Valley hits; Atlanta metro is a different miss. Fail-closed: `named_rows` lives in `geo_list.py` (162/400); `_COUNTY` / `place_token` are in `geo.py` (**400/400**), so a greed fix must extract first. 0 new deps. 0 extra listings on the live path. A new warning code needs `docs/requirements.md` and `_WARNING_WITHOUT_FETCH`; empty URL without one of those three codes stays a miss. Do not raise a budget | **Holds.** |

## Decision

Fail closed is the policy, not current runtime. Do not ship an alias
gazetteer. One implementation leaf: stop last-word NAME substitution for an
unpublished token, without regressing `Harris County, Texas`. Do not pin
`q17` `answered_rate` or `B24010`. Until that leaf ships, `q17` can still
resolve as `county:140` CT.
