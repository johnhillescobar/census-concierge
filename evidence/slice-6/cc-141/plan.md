# CC-141 plan (read this first after any context reset)

Branch `cc-141/golden-state`, cut from origin/main 9a36dff. Jira CC-141 is the status source of truth.
Rules: `CLAUDE.md`, `docs/playbooks/run-slice.md`. CC-141 blocks CC-104 (final E2E, AC11/TC14); its result is
rebased into `cc-104/structured-geography` afterwards (that rebase is CC-141 AC4).

## Pre-flight (2026-11-22, `preflight.py` / `preflight.txt`, live ACS5 2024 listings)

A golden is "shared and stateless" when the resolver's own match (`geo_list.filter_rows`, grounded NAME match) over
the nationwide listing at the level the golden expects returns more than one place, and the question writes no state.

| Claim in the ticket | Result |
| --- | --- |
| candidate list of about 18 ids | all 18 confirmed shared (q13 included: 9 matches) |
| q42, q43 "name no place at all" | FALSE. Fayetteville matches 11 places, Suffolk County 2. They are shared-name cases and fall under scope item 1 |
| t01, t06, t14 name no place | true (no place in the text) |
| "scorer hash changes" | only if a scorer symbol in `scripts/run_demo.py` changes; a text edit moves the three COHORT hashes (`text` is an expectation field) and not the scorer hash |

Stateless and shared, to curate (26): core q03, q04; long_tail q05, q13, q16, q18, q20, q23, q31, q36, q38, q39, q40,
q42, q43; trap t07, t09, t13, t16, t18; holdout h01, h02, h03, h04, h06, h07.
Already carry a state (leave): q01, q22, t11, t17, h08. Unique (leave): q10, q14, q19, q25, q26, q27, q30, q33, q34,
q35, q41, q44, t08, t10, t12. No place name to carry a state (leave): q02, q06-q09, q12, q15, q28, q29, q32, q37, q24,
t02-t04, t15, h05, and t01, t06, t14.
Not name-matched places (leave, recorded): q11 (one metro area), q17 and q21 (informal regions; the model names the
counties, no shared name is written).
t05 "Population of Springfield" is DELIBERATELY ambiguous (`expect_warning = ambiguous_place`): leave it; its
expected behaviour is the refusal this ticket is about.

## Decisions (tag: owner = the owner said it; default = mine, revertible)

1. default: q42 and q43 are curated here (pre-flight shows they name shared places). Amendment A in CC-104 keeps
   its t01, t06, t14 only; the owner updates it.
2. default: t01, t06, t14 (scope item 3) are NOT curated: they name no place, so no state can be added without
   changing what they measure. They stay with CC-104 amendment A.
3. default: holdouts are curated too (AC1 says "every visible golden"; they sit in the same file and the script
   scans the whole file). They are retrieval-only and never reach the resolver. Revert by dropping h01-h07 from the edit.
4. default: the state written is the one a user asking that question most plausibly means (Cook -> Illinois,
   Detroit -> Michigan, Portland -> Oregon, Wayne County -> Michigan ...). It is inserted as `, State` straight after the
   place name and nothing else changes; the script checks that removing it gives the old text back.
5. default: the grid files (`evals/cc103_phrasing_grid.toml`, `url_breadth_grid.toml`) are not goldens and are out of
   scope. They carry unqualified counties too; that is a CC-104 follow-up, reported not fixed here.
6. default: the bridge is a relabel. The scorer is unchanged, so "the reference's trials re-scored by the new
   scorer" is the reference's trials as they were, pinned by sha256 in `evidence/metrics/bridges.json` with a note
   saying the old trials answered the old wording. Comparing a candidate with it mixes the curation with the code.
   CC-104's B block must therefore run on the curated goldens.

## AC / TC (ticket IDs) and how each is proven

| ID | Proof |
| --- | --- |
| AC1 / TC1 | `scripts/verify_golden_places.py` over the whole golden file against live listings: zero stateless shared places. Command and output in `evidence/slice-6/cc-141/` |
| AC2 / TC2 | same script with `--base origin/main`: per id, every field but `text` equal, and `text` minus the inserted state equals the old text |
| AC3 / TC3 | new cohort hashes from `metric_compare.py freeze`; `bridges.json` entry; one candidate run on the curated goldens at frozen code; `metric_compare compare` over it and A completes under the bridge |
| AC4 | after merge, CC-104 is rebased onto main; its closure rows are re-run at the new head (a CC-104 step, evidence linked from here) |

Tests (`api/tests/test_verify_golden_places.py`, real chain: real TOML, real `filter_rows`, listing rows as fixtures):
shared+stateless fails; shared+state passes; unique+stateless passes; an unannotated golden id fails; an annotated state
the text does not carry fails; a stale exemption (t05 no longer shared) fails; a changed non-text field fails the diff;
an edit that adds more than the state fails the diff. Every test mutation-checked (Gate 1, subagent).

## Order

pre-flight (done) -> implement (edit goldens, script, tests; commit) -> Gate 1 (subagent, `gate1.txt`) -> Gate 2
(`/code-review`, then `review-pr`) -> fix -> E2E once on frozen code in an isolated worktree (`make demo` recipe,
`--repeat 3`, HEAD equal at start and end, gated keys + `demo.misses` only) -> bridge + compare -> PR (draft until every
row PASS) -> owner merges -> post-merge E2E -> `jira_transition.py CC-141 --done`.
Never raise a budget. Never read sealed sets, `demo.trials` or E2E transcripts.
