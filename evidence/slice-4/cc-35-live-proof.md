# CC-35 owned live proof

Did not Read E2E transcripts. Captured from the running UI at
`http://localhost:5173/` with `POST /ask` on this branch.

## q02 — Median household income for all counties in Oregon

`evidence/slice-4/cc-35-live-table.json` and `cc-35-q02-table.png`.

- Table, not a first-row list (`scalar_list: false`). Meta GEOID is `36 areas`.
- 36 rows / 36 GEOIDs — every Oregon county, Baker through Yamhill.
- Each row: GEOID, name, `acs5`, year `2024`, period `2020-2024`, table
  `B19013`, variable `B19013_001E`, estimate, matching MOE.
- Universe `Households` on the response. URL is the full `county:*` /
  `in=state:41` request, no `key=`.
- No Census sentinels, no MOE rendered as 0.

## Missing MOE fixture

`evidence/slice-4/cc-35-missing-moe.json` and `cc-35-missing-moe.png`.

Intercepted `/ask` with two counties and a one-element `moe[]`. Baker shows
`2,400`. Benton shows `—`, not `0` and not Baker's margin.

## Keyboard

`table-scroll` `tabIndex` is 0. Headers are GEOID, Name, Dataset, Year,
Period, Table, Variable, Estimate, MOE.
