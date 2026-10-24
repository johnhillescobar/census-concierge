# Census API geography probes: minimum parents per level

- Date measured: 2026-10-24
- Dataset: `https://api.census.gov/data/2023/acs/acs5` (ACS 5-year, 2023), `get=NAME,B01003_001E`
- Supplementary: ZCTA only, on `2021/acs/acs5` and `2019/acs/acs5` (requests 79, 80)
- Test units: Wyoming (state 56), Albany County (001). Real codes were discovered from small listings first: tract 962700, county subdivision 91100, place 13900 (Cheyenne), block group 1 in tract 962700, ZCTA 82070, urban area 00037, MSA 16220.
- Requests: 81 in all, sequential, 0.5 s apart. 78 data queries, and 3 fetches of `geography.json` (requests 1 and 68, plus one more for the `wildcard` fields). No HTTP 429 or 503 was seen.
- Key handling: the key was passed as a request parameter and removed from every recorded URL and error text. The saved file was searched for the key and it appears nowhere.
- Row counts are data rows (header excluded). `rows=-` means no data came back.

## Results

Each URL has `key` removed and spaces and `*` shown unencoded. The `in` clause is written as the Census reads it, with a space between parents.

| # | level | form | HTTP | rows | error |
|---|---|---|---|---|---|
| 2 | county | 1 no in | 200 | 3222 |  |
| 3 | county | 2 in=state:56 | 200 | 23 |  |
| 4 | county | 5 one 001, no in | 400 | - | ambiguous geography "county:001" (qualify with state) |
| 5 | county | 5 one 001, in=state:56 | 200 | 1 |  |
| 6 | place | 1 no in | 200 | 32325 |  |
| 7 | place | 2 in=state:56 | 200 | 205 |  |
| 8 | place | 5 one 13900, no in | 400 | - | ambiguous geography "place:13900" (qualify with state) |
| 9 | place | 5 one 13900, in=state:56 | 200 | 1 |  |
| 10 | county subdivision | 1 no in | 400 | - | unknown/unsupported geography hierarchy |
| 11 | county subdivision | 2 in=state:56 | 200 | 71 |  |
| 12 | county subdivision | 3 in=state:56 county:* | 200 | 71 |  |
| 13 | county subdivision | 4 in=state:56 county:001 | 200 | 4 |  |
| 14 | county subdivision | 5 one 91100, state only | 400 | - | ambiguous geography "county subdivision:91100" (qualify with county) |
| 15 | county subdivision | 5 one 91100, state+county:* | 400 | - | wildcard mismatch in geography hierarchy |
| 16 | county subdivision | 5 one 91100, state+county:001 | 200 | 1 |  |
| 17 | tract | 1 no in | 400 | - | unknown/unsupported geography hierarchy |
| 18 | tract | 2 in=state:56 | 200 | 160 |  |
| 19 | tract | 3 in=state:56 county:* | 200 | 160 |  |
| 20 | tract | 4 in=state:56 county:001 | 200 | 11 |  |
| 21 | tract | 5 one 962700, state only | 400 | - | ambiguous geography "tract:962700" (qualify with county) |
| 22 | tract | 5 one 962700, state+county:* | 400 | - | wildcard mismatch in geography hierarchy |
| 23 | tract | 5 one 962700, state+county:001 | 200 | 1 |  |
| 24 | block group | 1 no in | 400 | - | unknown/unsupported geography hierarchy |
| 25 | block group | 2 in=state:56 | 400 | - | unknown/unsupported geography hierarchy |
| 26 | block group | 3 in=state:56 county:* | 200 | 457 |  |
| 27 | block group | 3 in=state:56 county:* tract:* | 200 | 457 |  |
| 28 | block group | 4 in=state:56 county:001 (tract omitted) | 200 | 33 |  |
| 29 | block group | 4 in=state:56 county:001 tract:* | 200 | 33 |  |
| 30 | block group | 5 one bg 1, state only | 400 | - | unknown/unsupported geography hierarchy |
| 31 | block group | 5 one bg 1, state+county:* | 400 | - | ambiguous geography "block group:1" (qualify with tract) |
| 32 | block group | 5 one bg 1, state+county:001 | 400 | - | ambiguous geography "block group:1" (qualify with tract) |
| 33 | block group | 5 one bg 1, state+county:001+tract:* | 400 | - | wildcard mismatch in geography hierarchy |
| 34 | block group | 5 one bg 1, state+county:*+tract:962700 | 400 | - | wildcard mismatch in geography hierarchy |
| 35 | block group | 5 one bg 1, full chain tract 962700 | 200 | 1 |  |
| 36 | zcta | 1 no in | 200 | 33772 |  |
| 37 | zcta | 2 in=state:56 | 400 | - | unknown/unsupported geography hierarchy |
| 38 | zcta | 5 one 82070, no in | 200 | 1 |  |
| 39 | zcta | 5 one 82070, in=state:56 | 400 | - | unknown/unsupported geography hierarchy |
| 40 | congressional district | 1 no in | 200 | 440 |  |
| 41 | congressional district | 2 in=state:56 | 200 | 1 |  |
| 42 | congressional district | 5 one 00, no in | 400 | - | ambiguous geography "congressional district:00" (qualify with state) |
| 43 | congressional district | 5 one 00, in=state:56 | 200 | 1 |  |
| 44 | state leg. district (upper) | 1 no in | 400 | - | unknown/unsupported geography hierarchy |
| 45 | state leg. district (upper) | 2 in=state:56 | 200 | 31 |  |
| 46 | state leg. district (upper) | 5 one 001, no in | 400 | - | unknown/unsupported geography hierarchy |
| 47 | state leg. district (upper) | 5 one 001, in=state:56 | 200 | 1 |  |
| 48 | state leg. district (lower) | 1 no in | 400 | - | unknown/unsupported geography hierarchy |
| 49 | state leg. district (lower) | 2 in=state:56 | 200 | 62 |  |
| 50 | state leg. district (lower) | 5 one 001, no in | 400 | - | unknown/unsupported geography hierarchy |
| 51 | state leg. district (lower) | 5 one 001, in=state:56 | 200 | 1 |  |
| 52 | school district (unified) | 1 no in | 200 | 10904 |  |
| 53 | school district (unified) | 2 in=state:56 | 200 | 48 |  |
| 54 | school district (unified) | 5 one 00730, no in | 400 | - | ambiguous geography "school district (unified):00730" (qualify with state) |
| 55 | school district (unified) | 5 one 00730, in=state:56 | 200 | 1 |  |
| 56 | puma | 1 no in | 200 | 2486 |  |
| 57 | puma | 2 in=state:56 | 200 | 5 |  |
| 58 | puma | 5 one 00100, no in | 400 | - | ambiguous geography "public use microdata area:00100" (qualify with state) |
| 59 | puma | 5 one 00100, in=state:56 | 200 | 1 |  |
| 60 | urban area | 1 no in | 200 | 2637 |  |
| 61 | urban area | 2 in=state:56 | 400 | - | unknown/unsupported geography hierarchy |
| 62 | urban area | 5 one 16147, no in | 204 | - | no content |
| 63 | urban area | 5 one 16147, in=state:56 | 400 | - | unknown/unsupported geography hierarchy |
| 64 | msa/micropolitan | 1 no in | 200 | 935 |  |
| 65 | msa/micropolitan | 2 in=state:56 | 400 | - | unknown/unsupported geography hierarchy |
| 66 | msa/micropolitan | 5 one 16220, no in | 200 | 1 |  |
| 67 | msa/micropolitan | 5 one 16220, in=state:56 | 400 | - | unknown/unsupported geography hierarchy |
| 69 | state | 1 for=state:* | 200 | 52 |  |
| 70 | state | 5 one state:56 | 200 | 1 |  |
| 71 | urban area | 1 no in (listing, to discover a real code) | 200 | 2637 |  |
| 72 | urban area | 5 one real 00037, no in | 200 | 1 |  |
| 73 | urban area | 5 one real 00037, in=state:56 | 400 | - | unknown/unsupported geography hierarchy |
| 74 | block group | 3 in=state:56 tract:* (county omitted) | 400 | - | unknown/unsupported geography hierarchy |
| 75 | place | 3 in=state:56 county:001 (not county nested) | 400 | - | unknown/unsupported geography hierarchy |
| 76 | tract | 2 in=state:56 (listing, to count code repeats) | 200 | 160 |  |
| 77 | tract | 5 one 962900 (unique in WY), state only | 400 | - | ambiguous geography "tract:962900" (qualify with county) |
| 78 | tract | 5 one 962700 (repeats x2 in WY), state only | 400 | - | ambiguous geography "tract:962700" (qualify with county) |
| 79 | zcta (acs5 2021) | 2 in=state:56 | 400 | - | unknown/unsupported geography hierarchy |
| 80 | zcta (acs5 2019) | 2 in=state:56 | 200 | 178 |  |

## Request log (key removed)

2. `2023/acs/acs5?get=NAME,B01003_001E&for=county:*`
3. `2023/acs/acs5?get=NAME,B01003_001E&for=county:*&in=state:56`
4. `2023/acs/acs5?get=NAME,B01003_001E&for=county:001`
5. `2023/acs/acs5?get=NAME,B01003_001E&for=county:001&in=state:56`
6. `2023/acs/acs5?get=NAME,B01003_001E&for=place:*`
7. `2023/acs/acs5?get=NAME,B01003_001E&for=place:*&in=state:56`
8. `2023/acs/acs5?get=NAME,B01003_001E&for=place:13900`
9. `2023/acs/acs5?get=NAME,B01003_001E&for=place:13900&in=state:56`
10. `2023/acs/acs5?get=NAME,B01003_001E&for=county subdivision:*`
11. `2023/acs/acs5?get=NAME,B01003_001E&for=county subdivision:*&in=state:56`
12. `2023/acs/acs5?get=NAME,B01003_001E&for=county subdivision:*&in=state:56 county:*`
13. `2023/acs/acs5?get=NAME,B01003_001E&for=county subdivision:*&in=state:56 county:001`
14. `2023/acs/acs5?get=NAME,B01003_001E&for=county subdivision:91100&in=state:56`
15. `2023/acs/acs5?get=NAME,B01003_001E&for=county subdivision:91100&in=state:56 county:*`
16. `2023/acs/acs5?get=NAME,B01003_001E&for=county subdivision:91100&in=state:56 county:001`
17. `2023/acs/acs5?get=NAME,B01003_001E&for=tract:*`
18. `2023/acs/acs5?get=NAME,B01003_001E&for=tract:*&in=state:56`
19. `2023/acs/acs5?get=NAME,B01003_001E&for=tract:*&in=state:56 county:*`
20. `2023/acs/acs5?get=NAME,B01003_001E&for=tract:*&in=state:56 county:001`
21. `2023/acs/acs5?get=NAME,B01003_001E&for=tract:962700&in=state:56`
22. `2023/acs/acs5?get=NAME,B01003_001E&for=tract:962700&in=state:56 county:*`
23. `2023/acs/acs5?get=NAME,B01003_001E&for=tract:962700&in=state:56 county:001`
24. `2023/acs/acs5?get=NAME,B01003_001E&for=block group:*`
25. `2023/acs/acs5?get=NAME,B01003_001E&for=block group:*&in=state:56`
26. `2023/acs/acs5?get=NAME,B01003_001E&for=block group:*&in=state:56 county:*`
27. `2023/acs/acs5?get=NAME,B01003_001E&for=block group:*&in=state:56 county:* tract:*`
28. `2023/acs/acs5?get=NAME,B01003_001E&for=block group:*&in=state:56 county:001`
29. `2023/acs/acs5?get=NAME,B01003_001E&for=block group:*&in=state:56 county:001 tract:*`
30. `2023/acs/acs5?get=NAME,B01003_001E&for=block group:1&in=state:56`
31. `2023/acs/acs5?get=NAME,B01003_001E&for=block group:1&in=state:56 county:*`
32. `2023/acs/acs5?get=NAME,B01003_001E&for=block group:1&in=state:56 county:001`
33. `2023/acs/acs5?get=NAME,B01003_001E&for=block group:1&in=state:56 county:001 tract:*`
34. `2023/acs/acs5?get=NAME,B01003_001E&for=block group:1&in=state:56 county:* tract:962700`
35. `2023/acs/acs5?get=NAME,B01003_001E&for=block group:1&in=state:56 county:001 tract:962700`
36. `2023/acs/acs5?get=NAME,B01003_001E&for=zip code tabulation area:*`
37. `2023/acs/acs5?get=NAME,B01003_001E&for=zip code tabulation area:*&in=state:56`
38. `2023/acs/acs5?get=NAME,B01003_001E&for=zip code tabulation area:82070`
39. `2023/acs/acs5?get=NAME,B01003_001E&for=zip code tabulation area:82070&in=state:56`
40. `2023/acs/acs5?get=NAME,B01003_001E&for=congressional district:*`
41. `2023/acs/acs5?get=NAME,B01003_001E&for=congressional district:*&in=state:56`
42. `2023/acs/acs5?get=NAME,B01003_001E&for=congressional district:00`
43. `2023/acs/acs5?get=NAME,B01003_001E&for=congressional district:00&in=state:56`
44. `2023/acs/acs5?get=NAME,B01003_001E&for=state legislative district (upper chamber):*`
45. `2023/acs/acs5?get=NAME,B01003_001E&for=state legislative district (upper chamber):*&in=state:56`
46. `2023/acs/acs5?get=NAME,B01003_001E&for=state legislative district (upper chamber):001`
47. `2023/acs/acs5?get=NAME,B01003_001E&for=state legislative district (upper chamber):001&in=state:56`
48. `2023/acs/acs5?get=NAME,B01003_001E&for=state legislative district (lower chamber):*`
49. `2023/acs/acs5?get=NAME,B01003_001E&for=state legislative district (lower chamber):*&in=state:56`
50. `2023/acs/acs5?get=NAME,B01003_001E&for=state legislative district (lower chamber):001`
51. `2023/acs/acs5?get=NAME,B01003_001E&for=state legislative district (lower chamber):001&in=state:56`
52. `2023/acs/acs5?get=NAME,B01003_001E&for=school district (unified):*`
53. `2023/acs/acs5?get=NAME,B01003_001E&for=school district (unified):*&in=state:56`
54. `2023/acs/acs5?get=NAME,B01003_001E&for=school district (unified):00730`
55. `2023/acs/acs5?get=NAME,B01003_001E&for=school district (unified):00730&in=state:56`
56. `2023/acs/acs5?get=NAME,B01003_001E&for=public use microdata area:*`
57. `2023/acs/acs5?get=NAME,B01003_001E&for=public use microdata area:*&in=state:56`
58. `2023/acs/acs5?get=NAME,B01003_001E&for=public use microdata area:00100`
59. `2023/acs/acs5?get=NAME,B01003_001E&for=public use microdata area:00100&in=state:56`
60. `2023/acs/acs5?get=NAME,B01003_001E&for=urban area:*`
61. `2023/acs/acs5?get=NAME,B01003_001E&for=urban area:*&in=state:56`
62. `2023/acs/acs5?get=NAME,B01003_001E&for=urban area:16147`
63. `2023/acs/acs5?get=NAME,B01003_001E&for=urban area:16147&in=state:56`
64. `2023/acs/acs5?get=NAME,B01003_001E&for=metropolitan statistical area/micropolitan statistical area:*`
65. `2023/acs/acs5?get=NAME,B01003_001E&for=metropolitan statistical area/micropolitan statistical area:*&in=state:56`
66. `2023/acs/acs5?get=NAME,B01003_001E&for=metropolitan statistical area/micropolitan statistical area:16220`
67. `2023/acs/acs5?get=NAME,B01003_001E&for=metropolitan statistical area/micropolitan statistical area:16220&in=state:56`
69. `2023/acs/acs5?get=NAME,B01003_001E&for=state:*`
70. `2023/acs/acs5?get=NAME,B01003_001E&for=state:56`
71. `2023/acs/acs5?get=NAME,B01003_001E&for=urban area:*`
72. `2023/acs/acs5?get=NAME,B01003_001E&for=urban area:00037`
73. `2023/acs/acs5?get=NAME,B01003_001E&for=urban area:00037&in=state:56`
74. `2023/acs/acs5?get=NAME,B01003_001E&for=block group:*&in=state:56 tract:*`
75. `2023/acs/acs5?get=NAME,B01003_001E&for=place:*&in=state:56 county:001`
76. `2023/acs/acs5?get=NAME,B01003_001E&for=tract:*&in=state:56`
77. `2023/acs/acs5?get=NAME,B01003_001E&for=tract:962900&in=state:56`
78. `2023/acs/acs5?get=NAME,B01003_001E&for=tract:962700&in=state:56`
79. `2021/acs/acs5?get=NAME,B01003_001E&for=zip code tabulation area:*&in=state:56`
80. `2019/acs/acs5?get=NAME,B01003_001E&for=zip code tabulation area:*&in=state:56`

## What each level needs, as measured

"Listing" is `for=<level>:*`. "One unit" is `for=<level>:<code>` where the code really exists.
"Needs" is the least that returned HTTP 200 with data. A parent written as a wildcard
(`county:*`) counts as written, not as a real parent.

| level | listing needs | one unit by number needs |
|---|---|---|
| state | nothing | nothing |
| county | nothing (3,222 rows nationwide) | state |
| place | nothing (32,325 rows nationwide) | state |
| county subdivision | state (no `in` is HTTP 400); `county:*` optional | state and county (`county:*` refused) |
| tract | state (no `in` is HTTP 400); `county:*` optional | state and county (`county:*` refused) |
| block group | state, and the URL must write `county:*` itself (`in=state:56` alone is HTTP 400); `tract:*` optional | state, county and tract (any wildcard in the chain refused) |
| zip code tabulation area | nothing; a state parent is refused in 2023 and 2021 (HTTP 400), accepted in 2019 | nothing; a state parent is refused (2023) |
| congressional district | nothing (440 rows nationwide) | state |
| state legislative district, upper | state (no `in` is HTTP 400) | state |
| state legislative district, lower | state (no `in` is HTTP 400) | state |
| school district (unified) | nothing (10,904 rows nationwide) | state |
| public use microdata area | nothing (2,486 rows nationwide) | state |
| urban area | nothing; a state parent is refused | nothing; a state parent is refused; a code that does not exist returns HTTP 204 with no body |
| metropolitan/micropolitan statistical area | nothing; a state parent is refused | nothing; a state parent is refused |

Three more measurements that bear on the table:

- The "ambiguous geography" refusal is structural, not a check that the number repeats.
  Tract `962900` occurs once among Wyoming's 160 tracts and `962700` occurs twice. With the
  state alone, both return HTTP 400 `ambiguous geography ... full qualify it with county`
  (requests 77 and 78).
- For one block group, the number `1` with state and county returns `ambiguous ... qualify
  it with tract`; with `county:001 tract:*` it returns `wildcard mismatch`; with
  `county:* tract:<real>` it returns `wildcard mismatch`. Only the full chain of real
  codes returns data (requests 32 to 35).
- For a block group listing, writing `tract:*` is optional but writing `county:*` is not:
  `in=state:56 tract:*` (county omitted) is HTTP 400 (request 74).

## Comparison with `_NEEDS` in `api/src/finish.py`

`_NEEDS` has five rows. Each is checked against the measurements above.

| `_NEEDS` row | the program's claim | measured | verdict |
|---|---|---|---|
| `("tract", False)` | every tract in a state needs the state | no `in`: HTTP 400. `in=state:56`: 200, 160 rows. Adding `county:*`: 200, the same 160 rows (requests 17 to 19) | AGREE |
| `("block group", False)` | every block group in a state needs the state, if the URL writes `county:*` itself; leaving it out is HTTP 400 | `in=state:56`: HTTP 400. `in=state:56 county:*`: 200, 457 rows. With `tract:*` as well: the same 457 rows. `in=state:56 tract:*`: HTTP 400 (requests 24 to 29, 74) | AGREE |
| `("county", True)` | one county by number needs the state | `county:001` with no `in`: HTTP 400 `ambiguous ... qualify it with state`. With `in=state:56`: 200, 1 row (requests 4 and 5) | AGREE |
| `("tract", True)` | one tract by number needs state and county; a county wildcard is refused | state only: HTTP 400 `ambiguous ... qualify it with county`. State and `county:*`: HTTP 400 `wildcard mismatch`. State and `county:001`: 200, 1 row (requests 21 to 23, 77, 78) | AGREE |
| `("block group", True)` | one block group by number needs state, county and tract | state only: 400 `unknown/unsupported hierarchy`. State and `county:*`: 400 `ambiguous`. State and `county:001`: 400 `ambiguous`. Wildcard anywhere in the chain: 400 `wildcard mismatch`. Full chain of real codes: 200, 1 row (requests 30 to 35) | AGREE |

The unlisted default is "needs nothing". For the levels in the program's vocabulary:

| level and form | table says | measured | verdict |
|---|---|---|---|
| county listing | nothing | 200, 3,222 rows, no `in` (request 2) | AGREE |
| place listing | nothing | 200, 32,325 rows, no `in` (request 6) | AGREE |
| state, listing or one | nothing | 200 for `state:*` (52 rows) and `state:56` (requests 69, 70) | AGREE |
| zcta, listing or one | nothing | 200 with no `in`: 33,772 rows for the listing, 1 row for `82070` (requests 36, 38) | AGREE |
| place identified by number | nothing (there is no `("place", True)` row) | `place:13900` with no `in`: HTTP 400 `ambiguous ... qualify it with state`. With `in=state:56`: 200, 1 row (requests 8, 9) | DISAGREE: needs the state |

## Disagreements and gaps

1. **One place by number needs the state.** The table has no `("place", True)` row, so the
   default "needs nothing" lets a place written by its code through, and the live API
   refuses it. Of everything in the program's vocabulary this is the only disagreement.
   It is a rare question (a user writes a place FIPS code), but it is a miss.
2. **ZCTA with a state is a trap that the table cannot express.** In the 2023 and 2021
   vintages a ZCTA URL with `in=state:56` is HTTP 400, so "ZCTAs in Wyoming" cannot be a
   state-filtered listing, and the URL must carry no `in` for a ZCTA. In 2019 the same
   URL returns 200 with 178 rows. `_NEEDS` agrees (a ZCTA needs nothing), but any code
   that adds the state as a parent to a ZCTA URL breaks on 2021 and later. This is
   measured for ACS 5-year 2023, 2021 and 2019 only; 2020 and 2022 were not measured.
3. **Levels the table does not cover, outside the program's vocabulary.** The default
   "needs nothing" is wrong for these. County subdivision listings need the state, and one
   subdivision by number needs state and county. State legislative district listings
   (upper and lower) need the state. One congressional district, school district
   (unified) or public use microdata area by number needs the state, though their listings
   need nothing. `detect_level` does not return any of these levels today, so this is a
   gap in waiting, not a live bug.
4. **The unit-number refusal does not depend on the number.** The `_NEEDS` single rows
   are right even when the number happens to be unique in the state (tract `962900`).
   Nothing in the table needs a "is this number repeated" check.

## What predicted the listing results

The dataset's `geography.json` marks `wildcard` and `optionalWithWCFor` for each level.
Read as "the named parent may be omitted if its wildcard is written", it matched every
listing result above, including all the HTTP 400s:

- county, place, congressional district, public use microdata area and school district
  (unified): the state is optional. Measured: a listing with no `in` returned 200.
- county subdivision and tract: the county is optional but the state is not. Measured:
  no `in` is 400, `in=state:56` is 200.
- block group: only the tract is optional, so the county and state are required. Measured:
  `in=state:56` is 400, `in=state:56 county:*` is 200.
- state legislative district (upper and lower): neither field is set, so the state is
  required. Measured: no `in` is 400.

The comment above `_NEEDS` says `requires` lists more than the program needs. That is
true (`requires` is the "one unit" chain, and it overstates every listing), but
`optionalWithWCFor` is a separate field and is not covered by that comment. `requires`
also matches every "one unit" measurement above. This is an observation for the main
agent to weigh, not a change.
