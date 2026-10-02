# CC-114 classification rule

Written and committed **before** any per-question outcome is classified (CC-114
generalization criteria; CC-3 AC6-AC11). Inputs this rule may read: question
text, `expect_*` fields, ACS geography metadata, Census relationship data.
Inputs it may not read: which trials passed or failed. It runs over **every**
golden that has `expect_geo_level`, passing ones included. A golden changes only
by this rule, with the reason written in the commit. The scorer is never loosened.

## Decision order (first match wins)

1. **Named level.** The question text contains a level word (`tract`, `county` /
   `counties`, `state`, `metro`, `ZIP` / `ZCTA`). The expected level is the named
   level. A fetch at another level is **pipeline wrong**.
2. **Bare place name.** No level word. The named entity is a place, a
   county-equivalent, or both. Coterminous test, fixed now: the place is listed
   in exactly one county in the 2020 `place_by_county` reference file, and its
   2020 Gazetteer `ALAND` is within 1% of that county-equivalent's `ALAND`
   (ratio in [0.99, 1.01]). Coterminous -> both levels are correct answers
   (**golden arguable**: the golden accepts the set, with the reason).
   Not coterminous -> the golden's level stands and any other level is
   **pipeline wrong**.
3. **Table cannot serve the level.** The expected level is absent from the
   geography metadata for every cached vintage of the table's dataset ->
   **table cannot serve**. Correct behavior is a warning with the nearest
   available level, never silent substitution.
4. **Multi-leg question** (comparison, "X to the state average"). Expected
   levels are stated per leg. A golden with one level for several legs is
   **golden misspecified** (scorer precision, reported apart from code gains).
5. **Trap golden** (`expect_warning`). A level mismatch is classified by rules
   1-4 only when a URL was fetched; a missing expected warning is not a level
   problem and is routed to the warning's owner, not counted here.
6. Anything else is **unclassified** and stays visible; it is not forced into a
   bucket.

## Buckets

`pipeline_wrong` | `golden_arguable` | `table_cannot_serve` |
`golden_misspecified` | `not_a_level_problem` | `unclassified`

## Reproduce

`uv run python scripts/classify_geo_levels.py` (reads `evidence/latest.json`
trials and `evals/golden_questions.toml`; writes
`evidence/slice-6/cc-114-classification.md`).

## Amendment (still before any outcome was classified)

Pre-flight claim failed: the rule first named a "2020 place-county relationship
file". `curl` on `https://www2.census.gov/geo/docs/maps-data/data/rel2020/place/`
lists only `tab20_place20_place10_*`, so no such file exists. Replaced by the
Gazetteer (`2020_Gaz_place_national.zip`, `2020_Gaz_counties_national.zip`, both
HTTP 200) and `codes2020/place_by_cou/` (HTTP 200). Threshold unchanged at 1%.
