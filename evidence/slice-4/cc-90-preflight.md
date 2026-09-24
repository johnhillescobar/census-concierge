# CC-90 pre-flight — claims vs measured

Raw commands in this file. Settled on `origin/main` @ `320b85d` (CC-35
post-merge). Jira `CC-90` To Do, parent CC-11. Did not Read E2E transcripts.
Did not open sibling story descriptions.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| `ExecutionRecord` and search/geo/build/fetch artifacts contain each proposed plan field, or name the smallest missing provenance | `ExecutionRecord` fields: table_id, universe, url, geographies (`GeoSpec`), fetch (`FetchDataResult` year buckets + dataset), allow_overlapping_acs5, pool (title/universe per hit). `BuildUrlResult.variables` (E+M). `CensusURL.estimate_table()` recovers estimate suffixes from the redacted URL. **`variables[]` is not on `ExecutionRecord`.** | **Holds as a gap.** Recover estimate IDs from the built `CensusURL`, not from answer prose. Do not add a record field. |
| Plan values match executed Census URLs for q01, t09, q23 without parsing answer prose | `CensusURL` on q01-shaped Harris ACS5 2024: year 2024, dataset acs5, `estimate_table=('B01003', ['001E'])`, `for=county:201`, `in=state:48`, `&key=` stripped. q23: Austin `place:05000 in=state:48` and Texas `state:48`, both `B25064`/`001E`. t09 question years `requested_years('…since 2017', 2024)=2017..2024`; `plan_years(..., acs1_ok=True)` → dataset acs1, attempted without 2020, omitted `[2020]` / `vintage_gap_2020`. Live-chart capture (not a transcript) already has q01 one GEOID and q23 two GEOIDs. | **Holds.** Mechanical match is `CensusURL` + `plan_years` + `GeoSpec.for_spec`. |
| Existing availability/geography helpers can validate plan consistency without a new validator layer | `legal_predicate('zip code tabulation area', frozenset(), wildcard=False, entries=geo_entries('acs1', 2023))` is `None` (0 ZCTA rows). Same call on ACS5 2024 returns code `860`. `drop_incompatible` with fixture `{2024: {variables: ['001E']}}` omits `999E` (`variable_not_in_vintage`) and keeps `001E`. | **Holds.** `ResultPlan` calls those helpers; do not add `validate_plan()`. |
| The contract fits domain-model, API LOC, file-size, and generated-client budgets | `check_budgets.py --structural-only`: api src LOC **4000/4000**, largest file **399/400** (`ask.py`; `fetch.py` 397), domain models **8/15**, api files 24/40, routes 1, tools 4. `AskResponse` has no `plan`. `Alternative` is `table_id`+`reason` only. | **Holds as a constraint.** One new domain model (`ResultPlan`) fits. Net `api/src` lines must be ≤0. Compact `build_url` rejects and the alternatives loop to pay for the model. Do not raise a budget. Regenerated `packages/client` is the drift gate, not a line budget. |

## Probe output

```
ExecutionRecord ['allow_overlapping_acs5', 'fetch', 'geo_status', 'geographies', 'geography', 'pool', 'table_id', 'universe', 'url', 'vintages', ...]
AskResponse has plan False
Alternative ['table_id', 'reason']
GeoSpec ['level', 'name', 'geoid', 'for_spec', 'in_spec', 'dataset', 'vintage', 'codes']
BuildUrlResult.variables present; FetchDataResult year buckets present
```

```
q01 CensusURL year=2024 dataset=acs5 estimate_table=('B01003', ['001E'])
q01 for=county:201 in=state:48 key_in_str=False
q23 Austin B25064/001E for=place:05000 in=state:48
q23 Texas  B25064/001E for=state:48
t09 requested [2017..2024]
t09 plan_years VintagePlan(dataset='acs1', attempted=[2017, 2018, 2019, 2021, 2022, 2023, 2024], omitted=[2020], reasons=['vintage_gap_2020'])
```

```
acs1 geography.json rows 19, ZCTA rows 0, legal_predicate None
acs5 ZCTA rows 1, legal_predicate GeoLevel(code='860')
drop_incompatible 999E: kept=[] omitted=[2024]
drop_incompatible 001E: kept=[2024]
```

```
ok    api src LOC               4000 <= 4000
ok    largest file LOC           399 <= 400
ok    domain models                8 <= 15
ok    api routes                   1 <= 10
ok    agent tools                  4 <= 6
```

## Decision

Add `ResultPlan` on `AskResponse.plan`, assembled from `ExecutionRecord` +
`CensusURL.estimate_table()` + fetch year buckets. Reuse `GeoSpec` for
`geographies`. Extend `Alternative` with `title` and `universe` (pool hits
already have both; family members inherit the parent; guard-supplied `B19001`
uses the published household-income labels).

`plan.years` is attempted (issued) vintages, not omitted. `plan.requested_years`
is the fetch request list. Failed HTTP stays in `years`; omitted does not.

Contract checks: ACS1+ZCTA via `legal_predicate`; estimate IDs must belong to
`table_id`. Vintage membership stays at `build_url` / `drop_incompatible` —
CI has no availability matrix at import.

## Out of this ticket

Overrides (`AskRequest`, CC-89). Plan-strip UI (CC-37). Two-pane shell (CC-88).
CSV, Vega, persistence, follow-ups. Raising any budget.
