# CC-138 response GEOID follow-up

Base `7944012aa9f31a9fec8ec822dfb1f11e20338de9`. The owner requested investigation and a fix that preserves the provider failure and multi-URL behavior. This batch covers the local response and client change, tests, documentation, and gate evidence.

| ID | Expected outcome | Evidence |
| --- | --- | --- |
| AC1 | Census `rows` and positional `moe` contain source data. `combined_rows` carries calculated totals and their margins. | `/ask` wire response, same GEOID predicate, numeric aggregation tests |
| TC1 | The total, its MOE, and both Census URLs survive a provider failure after a multi-geography fetch. Earlier failure remains bounded. | `/ask` wire response with and without a late 503, existing failure tests |
| TC2 | Browser display and CSV retain the same calculated total and margin when either response format is encountered. | Normalization and CSV comparison, generated client drift check |
| TC3 | Benchmark row coverage and MOE checks still count all delivered figures, while the existing GEOID and answer checks retain their definitions. | Harness equivalence test and frozen scorer and cohort hashes |
| TC4 | The browser reports a Census fetch failure only after Census was actually requested. | Built-only regression test and existing failed-fetch controls |

The contract field audit found three GEOID failures in each run: 3/180 GPT-4o mini, 3/170 original Sol, and 3/172 Sol with the provider-failure fix. Each run had zero MOE, universe, and alternatives failures. The aggregate records carry no row content. Independent offline reproduction found the same failure signature when the server appended a calculated total with no official Census GEOID after two fetched rows with valid GEOIDs.

Preflight on the old producer failed both direct `/ask` cases with the third, empty GEOID. The side-by-side harness tests lost the separate total from the row count. The browser test missed the calculated total from the normalized dataset until it consumed both fields.

Commit `56a3a9e0` introduced the deliberately empty aggregate GEOID. Commit `71fa8d5b` added the all-rows GEOID check. The response change separates fetched and calculated data and leaves the GEOID check intact. Older stored snapshots keep their original rows and remain renderable. New API clients read calculated totals from `combined_rows`. The benchmark counts the same delivered rows and checks the same margin columns in both formats. Historical run records are preserved.

The cold review found that the browser treated a built-only URL as a Census failure on the previous provider-failure path. The new display test failed when the attempted years were empty. The display now uses attempted years to distinguish that state from a Census request that returned no rows.
