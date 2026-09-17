# CC-72 pre-flight — claims vs measured

Raw command output: `evidence/slice-3/cc-72-preflight.txt`.

Settled on `origin/main` @ `6d415ac` (CC-71 PR #41 merged; e2e-capture PR #43). Jira `CC-72` To Do, parent CC-2, supersedes CC-68. Override UI is out of scope.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| ACS1 only where Census publishes the geography, including the 65,000+ rule | live ACS1 2023 `place:*&in=state:50` **HTTP 204**; Middlebury CDP `place:44275` **204**; ACS5 2024 pop **7220**. CA ACS1 places **142**, pop min **63223** (one under 65k). CA ACS1 counties include Tehama **64896**. `geography.json` ACS1 has `place`/`county`, **0** tract/ZCTA/block group rows | **Holds as a gap.** Do **not** gate on `population >= 65000` — Census publishes some areas slightly under. Authority is ACS1 HTTP **200 with rows** vs **204**. Level legality is `geography.json` (tract/ZCTA/block group have no ACS1 row). Listing already fetches `B01003_001E` but `GeoSpec` drops it; `geo.py` is **400/400** so eligibility is a NAME/GET probe at fetch, not a geo.py change. |
| Default non-overlapping ACS5 end years; consecutive ACS5 needs an explicit override that keeps the warning | `fetch_data` attempts every requested year; `overlapping_vintage` warns after the fact; `AskRequest` is `question` only | **Holds as a gap.** Consecutive requested years (`max-min+1 == n`, n≥2) destagger to first-requested end years ≥5 apart (2017–2023 → **2017, 2022**, matching t10/t11 notes). Gapped pairs (`[2019, 2022]`, t01) still fetch and warn. Override is `FetchDataTool.allow_overlapping_acs5` (not AskRequest / not UI). `overlapping_vintage` already cannot be stripped. |
| `t11` emits `acs1_geography_ineligible` and offers non-overlapping ACS5 | `evaluate()` has no such guard; prompt says Prefer ACS5 | **Holds as a gap.** Middlebury is ACS1-ineligible (204). Consecutive ACS5 years destagger to 2017+2022 and the fetch artifact flags ineligible. |
| `t12` emits `vintage_gap_2020`; 2020 is a visible gap, never interpolated or dropped silently | cached ACS1 vintages **no 2020**; live ACS1 2020 groups.json and Fresno GET **404**; ACS1 2019/2021 Fresno **200**; ACS5 2020 Fresno **200** | **Holds as a gap.** Today a 2020 ACS1 request is **attempted** and lands in `failed_years`. Policy omits 2020 from ACS1 attempted years with reason `vintage_gap_2020`; no row is invented. ACS5 2020 stays fetchable. |
| Requested / attempted / returned / omitted years stay ordered with machine-readable reasons | lists exist; `omitted_years` is only the `MAX_YEARS=12` tail; no reasons field | **Holds as a gap.** Add `omission_reasons[]` parallel to `omitted_years` (`vintage_gap_2020`, `overlapping_vintage`, `unpublished_vintage`, `max_years`, `no_url`). Client regen in the same commit. |
| Room in the budgets; do not raise `max_file_loc`; do not edit PLAN/DESIGN | `ask.py` **398**; `geo.py` **400**; `guards.py` **318**; `fetch.py` **262**; `doc_lines` **1800/1800**; `domain_models` **6/15**; `tool_schemas` **8/12**; `api_src_files` **20/40** | **Holds as a constraint.** New `vintages.py` (dataclass plan, not a BaseModel). No `geo.py`. Move `_latest_vintages` out of `ask.py`. No PLAN/DESIGN. |

## Decision

`vintages.plan_years` chooses the dataset and the attempted years before any Census GET (except one ACS1 probe for a consecutive ACS5 series). `fetch_data` fans out only the plan. Guards read the artifact at assemble. Variable compatibility, significance, charts, and override UI stay out.

`t10` still expects `overlapping_vintage`. Correct Cuyahoga behavior is ACS1 annual, which will not emit that warning. Recorded; golden is not this ticket.

## Out of this ticket

Variable compatibility (`variable_not_in_vintage`). Significance. Charts and plan strip (slice 4). Override UI / `AskRequest` field. Multi-geography fan-out (CC-64). PLAN/DESIGN edits. Raising any budget.
