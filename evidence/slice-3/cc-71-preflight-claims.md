# CC-71 pre-flight — claims vs measured

Raw command output: `evidence/slice-3/cc-71-preflight.txt`.

Settled on `origin/main` @ `3d88323` (CC-70 PR #40 merged). Jira `CC-71` To Do, parent CC-2, supersedes CC-65. CC-63 is Done. CC-60 owns warning semantics; this Story owns resolution mechanics only.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| A valid ACS5 ZCTA is `for=zip code tabulation area:<code>` with no `in=` and a GEOID | live ACS5 2024 `860` `requires=()`; q24 resolves `zip code tabulation area:90210` `in=''` `geoid=860Z200US90210` via a national `:*` listing | **Holds as a gap.** The clauses are right; the listing is a Census GET of every ZCTA. Extract the 5-digit code and emit the spec without listing. GEOID on the spec stays empty so assemble takes the fetched `GEO_ID` — a constructed `860Z200US` prefix would win over a 2010-definition row. |
| ZCTA is rejected for ACS1 before fetch; q24 stays fetchable on ACS5 | live ACS1 2023/2024 ZCTA rows **0**; `legal_predicate` ACS1 is `None`; q24 `dataset=acs1` returns `legal=False specs=[] listed=[]` | **Holds as behavior, not as a test.** Production already fail-closes before listing. Add a dataset-aware test so a later listing cannot sneak back. `build_url` already refuses a geography whose resolved dataset is not the requested one. |
| Tract-inside-place and ZCTA-inside-place return structured non-nesting before fetch | t16 and `zctas inside Denver` already `nested=False listed=[]`. `"the part of ZIP 80202 inside Denver"` is `legal=True nested=True` and **lists** | **Holds as a gap.** `_WITHIN` requires `zip codes?` immediately before `inside`, so a 5-digit code and a bare `zip` miss. In production the last-token fallback would not catch `80202` either (`denver` is last); a query whose last token is the code would silently ship a parentless ZCTA. |
| No invented `for`/`in`, silent county/place substitution, or areal allocation | Oregon-qualified named ZCTA and `all ZCTAs in Oregon` already `nested=False`. Listing `:*` then filtering is not an invented clause, but it is a fetch | **Holds.** Named-code short-circuit must still sit behind `legal_predicate` so an ACS1 (or fixture with no `860` row) cannot mint a spec. |
| Largest file 398/400; `geo.py` 391/400; do not raise `max_file_loc`; do not edit PLAN/DESIGN | `check_budgets.py --structural-only`; `ask.py` **398**; `geo.py` **391** | **Holds as a constraint.** Nine lines in `geo.py`. Regex change must be net-zero lines. No `ask.py`. `doc_lines` 1800/1800. |

## Decision

Tighten `_WITHIN` so an optional 5-digit code and a bare `zip` take the existing unresolved-parent `nested=False` path (no listing). After `legal_predicate` succeeds, a non-wildcard ZCTA with a 5-digit code becomes `for=zip code tabulation area:<code>` with empty `in_spec` and does not list. ACS1 stays fail-closed because that vintage has no ZCTA row. Tests: ACS5 named ZCTA (no listing), ACS1 rejection (no listing), tract-in-place, named ZIP-in-place, and a tmp_path `geography.json` row as the authority. Mutation-check each new/changed test.

E2E is owned by the operator this session; this PR still ships Gate 1 and Gate 2.

## Out of this ticket

Warning wording (CC-60). Vintage policy (CC-31 / CC-68). Overlapping-ACS5 override (CC-62). Multi-geography fetch (CC-64). Gazetteers, block allocation, map UI. A fifth tool, route, or graph node. Raising `max_file_loc`. PLAN/DESIGN edits.
