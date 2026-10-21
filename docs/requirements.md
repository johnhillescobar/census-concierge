# Response contract and guards

The short copy lives in `.claude/DESIGN.md` §4. This file is the catalog.
None of these block except an incomplete geography (below): warn (or decline a computation) and ship the answer.

## Every response

| field | rule |
|---|---|
| **URLs** | Full Census API URL per attempted request (`urls[]`): variables, geography, vintage. Present even when the fetch fails, except for an incomplete geography (below). `&key=` redacted. |
| **Margins of error** | Fetch `M` beside every `E`. Census missing sentinels are null, never zero. |
| **GEOID** | AFFGEOID `GEO_ID` on fetched rows. Names do not join to TIGER. |
| **Universe** | Display the published universe. Households ≠ families ≠ population ≠ housing units. |
| **Alternatives** | Related tables with title, universe, and why they differ. |
| **Plan** | `ResultPlan` from executed artifacts (table, estimate IDs, years, `GeoSpec`s). Never parsed from answer prose. Optional `AskRequest.plan` pins the next `POST /ask`. |

A silently short series is the same failure as a wrong one: dropped years, geographies, or variables are named, with a reason.

## Geography completeness

A question must carry the minimum its level takes (`finish._NEEDS`, measured live): every tract or block
group needs the state; one county or place by number, the state; one tract, state and county; one block
group, state, county and tract. One that carries less, or points at a place without naming it ("my county"),
is not answered: `geography_unsupported`, an answer saying what is missing, and empty `urls[]`, `rows` and
`alternatives`. No search, fetch or blocking question. A question asking which table holds something is
answered. The model reports level, places, county, pointing phrases and ask; code compares, no word scan.

## Slice 1 warning codes

| code | condition |
|---|---|
| `overlapping_vintage` | ACS5 periods sharing sample years are not comparable. |
| `moe_not_significant` | A difference inside the 90% MOE is indistinguishable, not a ranking. |
| `geography_unsupported` | The table is not published at the requested level, or the question lacks what its level needs (a tract number with no county, say). Do not substitute. |
| `comparison_too_large` | Row pairs x estimate columns is over `MAX_COMPARISON_WORK`; no pairwise comparison was computed. Rows, URL and MOE are unaffected. |
| `ambiguous_place` | A named place can denote several geographies (same name, different states) and the question picks none. Scope ("which counties?") is not ambiguity. Candidates are the result, never a blocking question. Eval labels: `scripts/label_grid_ambiguity.py`. |
| `universe_mismatch` | The question crosses households × families × population × housing units. |

## Answer text

| code | condition |
|---|---|
| `answer_figures_unverified` | The model's text stated a number the response does not carry; the rendered figures replace it. |

## Slice 3 warning codes — years

| code | condition |
|---|---|
| `measure_unavailable` | Census does not measure it. Offer the nearest real thing and name its universe. |
| `acs1_geography_ineligible` | ACS1 is published only for places of 65,000+. |
| `vintage_gap_2020` | No standard 2020 ACS1 release. Show a gap; never interpolate. |
| `boundary_change_2020` | Tract / block-group geometry was redrawn across 2020. |
| `variable_not_in_vintage` | Absent or redefined in part of the requested range. |

## Slice 3 warning codes — geographies

| code | condition |
|---|---|
| `zcta_not_zip` | ZIPs are USPS routes; ZCTAs are block-built. ~10% of ZIPs have no ZCTA. No ACS1. |
| `geography_not_nested` | Containment is not expressible in Census `for`/`in`. |
| `median_not_aggregatable` | Medians cannot be combined across areas. Decline the computation. |
| `moe_aggregation_degraded` | `sqrt(Σ MOEᵢ²)` degrades past a handful of areas. |
| `shared_sample` | Place-vs-parent (and other nested pairs) share ACS sample. |

Trap questions for these codes live in `evals/golden_questions.toml`.
Some codes exist on the contract but do not yet fire on every trial; residual
work is epic [CC-91](https://johnhillescobar.atlassian.net/browse/CC-91).
