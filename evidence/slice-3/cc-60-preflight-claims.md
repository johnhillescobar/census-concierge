# CC-60 pre-flight — claims vs measured

Raw command output: `evidence/slice-3/cc-60-preflight.txt`.

Settled on `feat/cc-29-series-guards` @ `01d3b2e` (CC-61 merged; geography lists still CC-63/65).

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| `t15` / `t16` / `q24` exist; t15 expects `zcta_not_zip`, t16 `geography_not_nested` | `evals/golden_questions.toml`; `scripts/verify_golden.py` — t15/q24 `B19013` Households, geo level `zip code tabulation area`; t16 `B17001` poverty universe | **Holds.** Warning codes appear only in the golden file, not in `api/src`. |
| Guards are pure functions over the execution record at assemble | `evaluate()` in `guards.py`; `assemble()` calls `finish_aggregation` → `evaluate` | **Holds as a gap.** Add two slice-3 guards to that loop. No fifth tool, no new route, no graph node. |
| ZIP ≠ ZCTA; ZCTAs nest in nothing; no ACS1; 2020 defs differ | live `geography.json` 2023: ACS5 ZCTA `860` `requires=None`; ACS1 ZCTA rows **0**. Live ACS5 fetch: `ZCTA5 90210` `GEO_ID=860Z200US90210`. `legal_predicate(zcta, {county}, wildcard=True)` is `None` | **Holds.** |
| Tracts nest in counties, not places | live ACS5 2023 tract `140` requires `state,county`, `optionalWithWCFor=county` | **Holds.** |
| Non-expressible containment must not invent a fetch | `resolve_geography` already returns `matches=[]` when a parent level is unresolved; `build_url` refuses a `for` not in `allowed_geographies` | **Holds as a gap.** Tag that failure as `nested=False` only when `geography.json` never places the child in that parent. Do not resolve Denver County as a silent substitute. |
| A valid single-vintage ACS5 ZCTA remains fetchable | q24 last token `90210`; listing filter already matches `ZCTA5 90210`; warning must not fire on the word ZCTA | **Holds as a gap.** `zcta_not_zip` keys off `\bzip\b`, not ZCTA. |
| Demo scoring currently requires a URL for every warning except `ambiguous_place` | `scripts/run_demo.py` `is_answered` | **Holds as a constraint.** `geography_not_nested` has no legal Census URL; score it like `ambiguous_place`. `zcta_not_zip` still requires the ACS5 ZCTA URL (t15). |
| Room in the budgets | `check_budgets.py --structural-only` | **Holds with a constraint.** `ask.py` **397/400** — absorb `nested` without a net line gain beyond the cap. `geo.py` 374/400. `guards.py` 280/400. `doc_lines` **1800/1800** — do not edit PLAN/DESIGN. No new tool/route/model. |

## Decision

Two guards on the existing `evaluate()` loop. `t15` (ZIP language) emits `zcta_not_zip` and still ships any resolved ACS5 ZCTA rows. `t16` (`nested=False` from resolve) emits `geography_not_nested`, keeps `matches=[]`, and does not substitute a coextensive county. `geography_unsupported` skips when `nested` is false so the two codes do not double-fire. `nests_in()` reads `geography.json` rows so legal tract-in-county containment is not labelled non-nesting.

CC-65 still owns ZCTA code extraction, ACS1 rejection-before-fetch, and GEOID preservation. This ticket consumes the legality table that already exists and records `nested` on `geo_status`.

## Out of this ticket

Geography lists / fan-out (CC-63, CC-64). ZCTA spec construction and ACS1 rejection (CC-65). Vintage policy (CC-31). Overlapping-ACS5 override persistence (CC-62). Charts (slice 4). A fifth tool.
