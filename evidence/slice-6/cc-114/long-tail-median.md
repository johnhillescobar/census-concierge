# CC-114: the long_tail answered rate is about 0.708 (median), 0.8 points above its 0.700 floor

Recorded 2026-11-09 for the CC-114 PR. Aggregates and `demo.misses` only; no transcripts read.

## The median

`demo.long_tail.answered_rate`, `--repeat 3`, n = 120 trials per run, every run of this slice:

| Run | Code | long_tail | Trials answered |
|---|---|---|---|
| anchor | main 4b24f77 (pre-fix) | 0.708 | 85 |
| control | main 94566f5, same window as the head control | 0.708 | 85 |
| e2e-pre | candidate 828042c | 0.700 | 84 |
| e2e-final | head 06886a4 | 0.717 | 86 |
| control | head 06886a4, same window as the main control | 0.717 | 86 |
| e2e-final2 | head 3945694 (shipping head) | **0.692** | 83 |

- **Median of the six runs: 0.708 (85 of 120).** Sorted: 0.692, 0.700, 0.708, 0.708, 0.717, 0.717.
- Main alone (two runs): median 0.708. Head and candidate alone (four runs): median 0.7085.
- Pooled: main 170 of 240 = 0.708; head and candidate 339 of 480 = 0.706. The difference is below one trial per run.
- `evidence/latest.json` on main (2026-10-30, an earlier code state) reads 0.733, so the 0.708 median is a low point of the series, not the typical value.
- **The floor is `answered_rate >= 0.700` (84 of 120).** The median sits 1 trial above it; one run in six fell below (0.692). Main itself would fail the floor at about the same rate. A single `--repeat 3` demo cannot reliably certify this floor.

The shipping-head run (e2e-final2) is 0.692 and fails the floor. This is recorded as red, not rerun until it passes.

## Most long_tail misses are the same questions in every run

Across the six runs, nine long_tail questions miss on 18 of 18 trials (two more on 16 of 18). They miss on pre-fix main as well,
so they are the baseline, not noise, and they are about 27 to 33 of the 120 trials in every run:

| id | expected | got | what the facts say |
|---|---|---|---|
| q10 | C16001, county | B16001 | Two language-at-home tables; B16001 adds ability to speak English. Selector or oracle. |
| q11 | B08303, metro (CBSA) | place | The model states the metro level; the lookup refuses the shorthand (published name is "metropolitan statistical area/micropolitan statistical area"). Now flagged, not served. CC-106. |
| q14 | B08201, county | place | "Baltimore City" is a place and a county-equivalent. Model states `place`; `ambiguous_place` fires. Oracle. |
| q15 | B05002, county | B05012 | Both give the foreign-born count (B05012 is the plain nativity table). Selector or oracle. |
| q17 | B24010, county | B24114 | **B24010 is published only in ACS 1-year; ACS 5-year has C24010.** The demo's 5-year path can never select B24010. Oracle. |
| q18 | B25003 | B25009 | Tenure vs tenure by household size; both are valid tenure tables. Selector. |
| q20 | B07001, place | B07204 | Two mobility tables; B07204 is the place-level detail table. Selector or oracle. |
| q21 | B19058 | B22001 | B22001 is the direct SNAP-receipt table; B19058 is public assistance income or SNAP. Selector or oracle. |
| q23 | B25064, place | place+state | Two legs scored against one expected level. Misspecified golden. Oracle. |
| q26 | B23020, county | place | "Anchorage" is a place and a county-equivalent. Oracle. |
| q34 | B24080, place | B19053 | **Wrong universe:** B19053 is household self-employment income; B24080 counts workers by class. Selector. |

All table facts above were read from `data/raw/acs5/2024/groups.json.gz` and the other vintages' group files.
They show which tables exist; they do not show which one a researcher would prefer.

## Which stories can move these (Jira comments posted 2026-11-09)

| Misses | Story | What it owns here |
|---|---|---|
| q11 (metro level) | **CC-106** (comment 10830) | Metadata-published levels; accept a half of the slash-joined CBSA name by metadata match, resolve "Atlanta metro" against CBSA NAME evidence; "no city/metro silent substitution". |
| q14, q26, q23, q17 (goldens) and the floor's measurability | **CC-133** (comment 10831) | Independently reviewed expected interpretations (AC1), scorer-change bridge (AC3), sampling protocol. q17 expects B24010, published only in ACS 1-year. |
| q10, q15, q18, q20, q21 (table choice) | **CC-131** (comment 10832) | AC2/TC2 reconcile universe and cell against metadata, after CC-133 AC1 decides whether each golden stands. |
| q34 (household table for a worker question) | **CC-134**, Phase 2 under CC-124 | Not in CC-3 (owner decision, 2026-11-09). |
| unsupported-level candidates (t15) | **CC-131 AC4** | Already moved there from CC-114 (AC2b). |

CC-119 and CC-130 get no comment: no persistent miss is a parent-chain or cell-selection failure. The multi-county regions in
q17 and q21 resolve to county; their misses are table choices.
