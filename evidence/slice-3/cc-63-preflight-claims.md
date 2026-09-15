# CC-63 pre-flight — claims vs measured

Raw command output: `evidence/slice-3/cc-63-preflight.txt`.

Settled on `origin/main` @ `918304c` (CC-28 merged; geography result is still `matches: list[dict]`).

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| `resolve_geography` returns an ordered list of specs with level, display name, GEOID/codes, and exact `for`/`in` | `ResolveGeographyResult.model_fields == ['matches', 'wildcard', 'legal', 'detail']`; `matches` is `list[dict[str, str]]`; no `GeoSpec` | **Holds as a gap.** Replace `matches` with `specs: list[GeoSpec]`. Ranked order already exists (`rank_matches`); keep it. |
| Every emitted combination is authorized by indexed `geography.json` for the selected dataset and vintage | `default_tools` hard-codes `geo_entries("acs5", acs5)`; `ResolveGeographyInput` has no `dataset`/`vintage`. ACS1 2024 has no tract/ZCTA rows; ACS5 2024 does. ACS1 2020 file is absent (`FileNotFoundError`). | **Holds as a gap.** Look up `geo_entries(dataset, year)` per call. Missing metadata fails closed, no listing. |
| Removing an otherwise plausible combination from a metadata fixture causes resolution to fail safely before fetch | `legal_predicate` already returns `None` when the row is absent; tool still emits a state spec when `legal` is false; non-wildcard illegal paths still call `list_geographies` | **Holds as a gap.** Empty `specs` when unauthorized; do not list names; `build_url` has nothing allowed so fetch cannot run. |
| Executable geography state is structured; prose is summary only and cannot override the metadata result | Artifact is untyped dicts; `_absorb` copies those dicts; `build_url` reads `for_spec` from the model then `geography.get("for")`. `allowed_geographies` already rejects pairs not in the resolved list. | **Holds as a gap.** Store `GeoSpec` on the execution record. Summary stays the model-visible string. Model `for_spec` may select among specs, never invent a pair. |
| Existing single-geography and ambiguous-place behavior remains intact | Cook County / Springfield / Portland tests; `matches[0]` is selected; `ambiguous_place` fires on `len(geographies) > 1` | **Holds.** Keep ranking, `specs[0]` selection, and the warning. No AskResponse geography array (UI out of scope). |
| Room in the budgets | `ask.py` **393/400**; `geo.py` **374/400**; `domain models` **5/15**; `tool schemas` **8/12**; `doc_lines` **1800/1800** | **Holds with a constraint.** `GeoSpec` is a domain model in `contract.py` (budget comment already names it). Do not put it on `AskResponse` (no client regen). Do not edit PLAN/DESIGN. No fifth tool, no geo fan-out (CC-64), no ZCTA policy (CC-65). |

## Decision

`resolve_geography` takes optional `dataset`/`vintage`, loads that vintage's `geography.json` rows, and returns ordered `GeoSpec` values (`level`, `name`, `geoid`, `for_spec`, `in_spec`, derived `codes`, `dataset`, `vintage`). Illegal or missing metadata yields empty `specs` before any NAME listing. `build_url` still refuses a pair that is not in those specs.

## Out of this ticket

Multi-geography fetching (CC-64). ZCTA / non-nesting policy (CC-65). Warning prose (CC-60). Vintage policy (CC-68). Charts and plan strip (slice 4). A fifth tool.
