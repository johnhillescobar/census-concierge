# CC-97 pre-flight — claims vs measured

Raw command output: `evidence/cc-91/cc-97-preflight.txt`.

Settled on `origin/main` @ `102dd35`. Jira `CC-97` To Do, parent CC-91.
CC-76 post-merge miss summary (`evidence/slice-3/demo-miss-analysis.md`): `t11` missing `acs1_geography_ineligible`. Did not Read E2E transcripts.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| `t11` can ship the expected table and ACS5 fallback without `acs1_geography_ineligible` | CC-76 miss summary names `t11`. Guard with destaggered ACS5 years, overlapping omissions, and `acs1_ineligible=False` returns `[]`. `fetch=None` returns `[]`. Current `latest.json` t11 is 3/3 with the warning (probe path), so the miss is path-dependent, not a missing function | **Holds.** Lost when the flag is not persisted. |
| Eligibility is a geography fact (204/empty vs 200 with rows), not a 65k cutoff | Live ACS1 2024 Middlebury `place:44275` **HTTP 204** for B23025, B01003, and NAME-only. ACS5 2017 and 2024 **200**, 1 row. Harris / Cuyahoga / Phoenix ACS1 **200** with rows. `geography.json` ACS1 has `place`/`county`; tract/ZCTA/block group are ACS5-only | **Holds.** Same authority as CC-72. |
| Warning must come from requested-series, geography, dataset, and availability state — not LLM prose or a golden id | `wants_acs1(t11)` is **False** (`1-year\|acs1` only). Assemble reads `fetch.acs1_ineligible` only. `plan_years` sets that flag only on the series destagger branch (`acs1_ok is False`). ACS1 204 fallback calls `plan_years(dataset="acs5", acs1_ok=False)`; a non-series year list takes the else branch and **drops the flag** (`years=[2017,2022]` → ineligible False) | **Holds as the lost state.** Planning, not assemble. Fetch already passes `acs1_ok=False` after 204/404. |
| Probe-unknown destagger must not be treated as geography-ineligible | `acs1_ok=None` destaggers to 2017+2022 with `acs1_ineligible=False`. Fetch 400/500/malformed 200 already tested | **Holds as a constraint.** Do not warn on unknown. |
| Defensible ACS5 legs keep URL, E/M, GEOID, universe, dataset, vintage, table, omission reasons | ACS5 Middlebury B23025 2017 and 2024 live 200 with NAME/GEO_ID/E/M. B23025 is present every ACS5/ACS1 vintage in the matrix (7 E). `variable_not_in_vintage` on current t11 trials is out of this ticket | **Holds as a constraint.** Do not reopen variable compatibility. |
| Eligible ACS1 and non-overlapping ACS5 must not regress | Harris/Cuyahoga/Phoenix ACS1 200. `plan_years(..., acs1_ok=True)` stays ACS1 and omits 2020. Overlapping override keeps consecutive ACS5 with ineligible False | **Holds as a constraint.** |

## Decision

`plan_years` treats `acs1_ok=False` as known geography-ineligible on any ACS5 plan it emits, including a non-series fallback after ACS1 204/404. Default `acs1_ok` becomes `None` (unknown) so gapped ACS5 years and unprobed calls do not inherit a false ineligible flag. The assemble guard still reads the fetch artifact only.

## Out of this ticket

`t14`, table selection, informal regions, `wants_acs1` wording, finish-loop repair, variable-definition compatibility, UI, new routes/tools/dependencies/graph nodes, budget changes.
