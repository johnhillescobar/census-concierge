# CC-104 plan (the one plan file for this story)

Branch `cc-104/structured-geography`, cut from `main` 1b50b3b on 2026-11-11. Yardstick (phase 1): a sound,
flexible, robust URL; the model states intent, code executes it. Prerequisites CC-114 and CC-133 are Done in Jira.
Rules: `CLAUDE.md`, `docs/playbooks/run-slice.md`. Jira CC-104 owns scope; AC1-5 / TC1-5 are its own identifiers.

## Pre-flight: claims in the ticket and its comments, run against the repo

| Claim | Settled by | Result |
| --- | --- | --- |
| WILDCARD / WITHIN phrase gates exist | `grep` api/src | True: `geo_list.py:11,17`; used by `geo.py` (`_arun`, `_resolve`, `_nation`). |
| `detect_level`, `split_comparison`, `find_state`, `place_token`, `_nation`, `_US` exist | `grep` | True: `geo.py:36,101,109,137`, `geo_list.py:85,120`. |
| finish rescans exist | `grep` | True: `_LISTING`, `_BY_COUNTY`, `_listing_level`, `_listing_query`, `_wrong_listing`, `_wrong_comparison` (`finish.py:59-114`); `incomplete()` also tests the model's `pointing`/`numbered` strings against `_key(record.question)` (`finish.py:240-258`). |
| English reconstruction exists | `grep` | True: `finish.py:95` and `:309` build `"every {unit} in ..."`; the final fallback sends `query="nationwide"` (`finish.py:380`). |
| `geo.py` also scans prose beyond the named helpers | read | True: `_resolve` has a ZIP regex on `query` (`geo.py:364`), `us = re.search(...)` on `parent_text` (`:338`) and `detect_level(query)` for the county redo (`:408`). These go with the rest. |
| `compare.py`, `ask.py` read the question | `grep` | True: `compare.py:107` (`_COMPARE.search(record.question)`); `ask.py:263` passes `record.question` to `pin_tool_args` (search_tables only: model-owned retrieval, stays); `ask.py:380` is time (CC-129). `compare.py:107` is a geography-adjacent read; decide in D5. |
| "Five baseline lines tagged for removal by this story" (Jira comment 10833) | `cat evals/leakage_baseline.txt`; `check_invariants --base origin/main` | **False on main.** The baseline commit `28560dc` exists only on `chore/leakage-baseline-cc-114` (an old branch, 273 files behind); `evals/leakage_baseline.txt` on main has 5 other lines. `check_invariants` is already red with 6 leakage hits on main (contract.py x2, geo.py:36, geo.py:349, geo_level.py x3, geo_list.py:80, guards.py:32). Owner action, not mine (D7). |
| Main is green | `check_budgets`, `check_invariants` | **False, inherited:** p95 25.472 > 20, answered_rate 0.683 < 0.700, 6 leakage hits. Regex call sites 55 (delta +0). |
| Budget headroom | `check_budgets` | **Zero.** api LOC 4890/4890, largest file 408/410 (`finish.py` 404 lines), doc lines 1820/1820, prompt tokens 1095/1200. The change must be net-negative in api LOC and docs. |
| A frozen CC-104 cohort exists | `evals/metric_protocol.toml`, `golden_questions.toml` | **No.** Protocol cohorts are `long_tail` (48), `trap` (18), `core` (4). Geography level is in `expect_geo_level` (long_tail: county 21, place 20, state 5, MSA 1, ZCTA 1). Adding a cohort is an owner commit (the file says so). |

## Design (defaults; tagged)

| # | Decision | Tag |
| --- | --- | --- |
| D1 | `resolve_geography` stops taking a sentence. `query` is removed from execution. Inputs become: `places` (each `"Name, ST"`), `parents` (each `"Name, ST"`), `level`/`levels` (required), and a new `listing: bool` (true = every `level` unit inside `parents`). The state of an entity is read from the model's own `"Name, ST"` entry (exact lookup in `STATES`), never from a sentence. | default |
| D2 | No national / latest / total fallback. "No place named" is the model's explicit `level="us"` (null level + no place = refused with a bounded-repair message). `_nation`, `_US`, `_HAS_YEAR`, the `query="nationwide"` repair and `_NOISE` go. | default (ticket AC4) |
| D3 | `finish.py` redoes only from structured state already on the record (`asked_levels`, `geo_queries`, `geo_status`, `geographies`), compared by `geography_level_mismatch`. `_LISTING`, `_BY_COUNTY`, `_listing_*`, `_wrong_*`, `_split_parents`' English query are deleted. | default |
| D4 | One intent representation: `plan_split`'s frame and the main loop's `resolve_geography` args both land in the same fields on the record (requested vs executed vs default vs inferred kept apart). `incomplete()` trusts the model's report of what was written, split into `stated` and `inferred` parents so an inferred state cannot satisfy `_NEEDS` (AC5); it no longer searches the question for the report's strings. | default |
| D5 | `compare.py:107` (`_COMPARE` on the question) is judged in implementation: if it only decides a warning, it moves to the model's `compare` flag; otherwise it is left and listed as a finding. | default |
| D6 | Prompt: the GEOGRAPHY paragraph is rewritten to the new fields and must come out shorter (1095/1200 tokens today). | default |
| D7 | Leakage baseline (`28560dc`) and any waiver for inherited p95 / answered_rate are the owner's commits. I do not cherry-pick or waive. | owner rule |
| D8 | Cohort: `geography` = the `long_tail` and `trap` goldens that carry `expect_geo_level`, plus a new fixed-intent fixture set for the deterministic AC/TC. Freezing it is an owner commit to `evals/metric_protocol.toml` before P is measured. Until then the comparison runs on the existing three cohorts. | default; **owner to confirm** |

## Owner answers (2026-11-11)

- D1 **owner**: structured fields (`places`/`parents` as "Name, ST", required `level`/`levels`, new `listing`; `query` dropped from execution).
- D7 **owner**: land the leakage baseline on `main` first. CC-104 code waits for it. `28560dc` is one clean commit
  (`evals/leakage_baseline.txt`, +18 lines, written for the post-CC-114 state) on `chore/leakage-baseline-cc-114`;
  the owner puts it on `main` as their own commit (`git cherry-pick 28560dc` on a branch from `main`). Then this branch
  is rebased on that `main`, the three `geo_level.py` and two `geo.py` (`united states`) lines are deleted in the same
  change that removes their code (a stale baseline line fails the build), and p95 / answered_rate stay reported against A.
- D8 **owner**: the owner commits `[cohorts.geography]` to `evals/metric_protocol.toml`. Default definition: `long_tail`
  and `trap` goldens that carry `expect_geo_level` (long_tail 48, trap 8 of 18). Nothing is measured against it before it lands.

## State at 2026-11-11 (after #129 and #130 merged; supersedes the NOT RUN columns below only where stated)

Branch rebased on `main` 261c18f. `check_invariants --base origin/main` all ok (regex sites 55, delta +0);
`check_budgets`: only `answered_rate` 0.683 < 0.700 red (p95 waived for the 2026-11-09 run by #130).
Baseline `uv run pytest api/tests`: 1397 passed, 34 skipped, 8 xfailed (3 min). Cohort block: owner has not yet confirmed it landed.

## Design refinement (default; implementation notes from reading every caller)

- **Tool** `ResolveGeographyInput`: drop `query`. `places` (direct: one = single, 2+ = comparison), `parents` (non-empty means
  listing, so no separate `listing` flag: a flag restating `parents` is the ambiguity this story removes; D1 shortened),
  `parent_level` (new: level of the parents, null = state), `level`/`levels` (required), `dataset`, `vintage`.
  `level="us"` with no places = the United States; null level and no place is refused for bounded repair (no national guess).
- **Entities**: an entry is "Name, ST" or a bare state. The state comes from `STATES` by exact match on the part after the last
  comma (or the whole entry); the NAME token is the part before the first comma, matched with `named_rows`. A 5-digit entry at
  the ZCTA level is an exact code. `find_state`/`place_token`/`WILDCARD`/`WITHIN`/`detect_level`/`split_comparison`/`_nation`/
  `_US`/`_HAS_YEAR`/`_IN_PLACE`/`_NOISE`/`_AVERAGE` are deleted; `track_geo_query` keys on the entry, not a query.
- **Frame** (`plan_split`, the auxiliary report): `parents`/`unit`/`listing` returned for 1+ parents (was 2+), `places` for a direct
  comparison, `given` = hierarchy levels the question itself states (state, county, tract), `numbered` = levels of places
  identified only by number, `pointing` = bool. `incomplete()` uses `given` + exact GEOID parsing only; it no longer searches the
  question for the report's strings. A part the model supplied from its own knowledge is not in `given` (AC5).
- **finish.py**: `_LISTING/_BY_COUNTY/_listing_level/_listing_query/_wrong_listing/_wrong_comparison` deleted; redo compares the
  frame (`unit`, `parents`, `places`) with the record's geographies. The `query="nationwide"` repair is deleted (AC4).
- **LEVELS** alias table: kept only for `zcta`/`zip` -> the published name, written once (one `geo_level.py` baseline line remains,
  two are deleted in this change). Plural and city/cities spellings go; an unknown spelling is refused with the published list.
- Left for CC-129 (time and product): `wants_acs1`, `requested_years`, `guards.py` reads. Left, listed as a finding (D5):
  `compare.py:107` `_COMPARE` on the question (a warning trigger, not execution).

## AC / TC matrix (IDs are the ticket's; evidence goes in `evidence/closure/CC-104.toml`)

| ID | Expected | Command / test | Status |
| --- | --- | --- | --- |
| AC1 | Structured scope, level, entities, parents determine execution; prose absent from deterministic inputs | `test_execution_isolation.py` (CC104 xfails flip to pass) | NOT RUN |
| AC2 | WILDCARD/WITHIN, `detect_level`, `split_comparison`, sentence `find_state`/`place_token`, finish rescans, English reconstruction removed; exact lookups stay | `check_invariants` regex delta < 0; grep; mutants | NOT RUN |
| AC3 | Main-loop and auxiliary reports feed one intent; requested/executed/default/inferred distinct; CC-114 checks kept | new fixed-intent tests; `test_geography_report.py`, `test_level_*` | NOT RUN |
| AC4 | Recovery uses complete validated intent or returns missing fields to bounded repair; no national/latest/total fallback; late/missing report never parses prose | repair tests with the scripted model | NOT RUN |
| AC5 | Inferred/hallucinated parents cannot satisfy completeness | `test_geography_completeness.py` additions | NOT RUN |
| TC1 | Listing with no historical keyword executes correctly | fixed-intent test | NOT RUN |
| TC2 | Same intent, different/absent wording: identical execution | isolation harness | NOT RUN |
| TC3 | Changed structured level changes execution, wording unchanged | isolation harness | NOT RUN |
| TC4 | Comparison, wildcard parents, ambiguous names, incomplete numeric chains keep behavior | existing suites, unchanged assertions | NOT RUN |
| TC5 | Missing report, invalid level, finish recovery cannot fall back to prose | repair/finish tests | NOT RUN |
| MET | >=95% correct level / single / listing / comparison intent on the frozen cohort (case AND trial); P vs B, A, L at `--repeat 3` | `metric_compare.py compare ... --refs A,A0` | NOT RUN |
| INH | api LOC, files, prompt tokens, docs no higher; regex call sites lower; leakage hits no more than main; p95 and answered_rate reported against A | `make check`, E2E | NOT RUN |

## Outward writes (listed before they happen)

- repo: branch `cc-104/structured-geography`, commits, `evidence/slice-6/cc-104/`, `evidence/closure/CC-104.toml`.
- Jira CC-104: one pre-flight comment (the table above), then the close card after post-merge E2E.
- PR: draft until every row is PASS. The owner merges. No waiver, no budget edit, no sealed read.
