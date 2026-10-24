# CC-102 plan

Ticket: CC-102 (bug, epic CC-3). Branch `fix/cc-102-original-question-parent-guard`, built on
`origin/main` 1160bde in its own worktree. The CC-121 branch and its dirty files are untouched.
Yardstick (phase 1): a sound URL, nothing from model memory. Jira holds status; this file holds the plan.
Local commits only (see `git log`); nothing pushed, no PR, no Jira write.

## Owner decisions (2026-10-24)

| Decision | Tag |
| --- | --- |
| A question must carry what Census requires for its GEOGRAPHY LEVEL, the **minimum for the kind of question asked** (the user may give more); one that carries less cannot be answered: say so at once, **no URL**, no search, no fetch, no candidates | `owner` |
| Needs table (owner-approved, then corrected by live probes): every tract or block group in a state, the state; one county by number, the state; one tract by number, state and county; one block group by number, state, county and tract | `owner` + measured |
| "Follow-up" means a question typed in a chat bar after an earlier answer; that does not exist yet, so "these five tracts" in isolation is malformed; no `refers_back` carve-out | `owner` |
| Table-discovery questions ("Which table has poverty by tract?") are answered with no geography | `owner` (Google examples supplied) |
| t03 golden becomes `expect_no_url = true` (the warning, and nothing shown); t17 is fixed (text now names Cook County, Illinois); scorer change approved; re-baseline and report apart from code gains | `owner` |
| `CLAUDE.md`: MOE, GEOID, universe and alternatives are "in every answer that returns data"; a refusal returns no rows | `owner` |
| Detection is model-composed, validated by code; never a word or token scan | `owner` (CLAUDE.md) |
| Defense in depth: a work bound on pair materialization ships too (amendment 2026-10-22) | `owner` |
| Every expected URL is shown in `urls[]` and the UI (the UI already renders every entry; no web change) | `owner` |
| CC-121 stays open until CC-102 and CC-120 are both complete; no Jira write made | `owner` |
| Four gate rounds (Gate 1 + cold Gate 2 each), E2E once after and once post-merge; credits approved | `owner` |
| Answer text is written by code (the model supplies the missing state, so it cannot write the explanation) | `default` |
| Partial cases are judged by the table: below the minimum is refused, at or above it goes through with its own warnings. A county name with no state, a tract in a city, and "my county" (a deictic the model will not drop, so it fails open) are for the owner to ratify | `default`, **open** |
| Work bound `MAX_COMPARISON_WORK = 50_000` and warning code `comparison_too_large` | `default` |
| Wait up to `FRAME_WAIT_SECONDS = 3.0` for the model's report before the first tool runs; past it, treat the question as complete | `default` |

## Built

**1. Level-completeness check (`finish.incomplete`).** The split call that already runs beside the loop
(`plan_split`) also reports `level`, `named` (places by name, or by a code that identifies one alone, each
written "Name, State"), `numbered` (places identified only by a number inside another place), `county_named`
and `asks_for`. After the loop's first model turn and before any tool runs, code compares that with
`_NEEDS`, the minimum the live Census API accepts (ACS5 2023, 81 requests, `cc-102-geography-probes.md`;
documented grammar in `cc-102-geography-docs.md`). `_NEEDS` equals `geography.json` `requires` less the
parents `wildcard` lets a listing leave to the URL; a test derives it from the metadata rows. Rules:
- any name the model writes carries its state; `county_named` carries the county; a numbered tract or
  county the user wrote verbatim carries its own level; a numbered place with no model level names it;
- `asks_for == "tables"` is never stopped and sets `record.tables_only`, so no geography warning follows;
- a pinned plan that names geographies skips the check; one that only picks a table does not;
- a state is never matched against the question's words (measured: that refused 38 of 60 valid
  "Calif."/"Penn"/"tx" questions); a wrong report only lets a trap through, which is where the loop was.

Below the minimum `run_ask` returns at once through `assemble`: `geography_unsupported`, a code-written
answer naming the level, what it needs, what the question names and what is missing, empty `urls[]`,
`rows`, `alternatives`; no search, fetch, URL or candidates. No report, a failed or late one, fails open.
Complete questions pay no extra call: the split call already existed. Code: `finish.py`.

**2. Work bound (`compare.py`, `guards.py`).** `comparison_rows` returns `[]` before any pair is built when
row pairs x estimate columns exceeds 50,000, and `finish_aggregation` adds a visible
`comparison_too_large` warning. It never limits the fetch, rows, URL, MOE, GEOID or universe.

**3. Instrument.** `evals/golden_questions.toml` t03 gains `expect_no_url = true`, t17's text is fixed;
`scripts/run_demo.py` scores `expect_no_url` as answered only with the warning and nothing searched or shown
(no URL, rows, table or alternatives). Stricter than before, so no loosening.

**4. Removed.** The token scanner, the tool-level guard, `FetchDataTool.refuse`, the `needs_parent`
plumbing, the old `parentless_tracts` regex pair, the metadata-based completeness check and the
state-word scan. Regex call sites 64 -> 62.

**5. Docs and rules (net-zero lines; `doc_lines` is at its cap).** `CLAUDE.md` "Geography is level-complete"
and the four fields "in every answer that returns data"; `docs/requirements.md`; `docs/ask-path.md`;
`.cursor/rules/00-guardrails.mdc`, `20-web-typescript.mdc`, `40-census-domain.mdc`; `.claude/DESIGN.md`;
`docs/playbooks/review-pr.md`.

## Verified without a live key

`make check` equivalents (no `make` on this machine): ruff and format clean, mypy clean, 824 passed / 34
skipped, invariants held, budgets met with no raise: `api_src_loc` 4487/4600, largest file 407/410,
`doc_lines` 1800/1800, `web_src_loc` 3349/3350, `system_prompt_tokens` 977/1200.
The split prompt lives in `finish.py`, so the prompt-token check does not count it: it is ~500 tokens
(origin/main: ~150). Counted, the system prompts would be ~1480 of 1200. The owner decides whether that
matters; it was not moved into `prompts.py` because that would exceed the budget.

Post-fix `comparison_rows`, `evidence/slice-6/cc-102-measure.py`: 6,896 rows x 1 or 2 columns: 0.0 s,
~31 MB, 0 comparisons; 200 x 25: 0.0 s; 60 x 25 (largest legitimate fan-out, 44,250): 0.27 s, 95 MB.
Pre-fix, measured: 400 rows x 2 cols 1.10 s / 269 MB; 150 x 25 1.77 s / 450 MB (~6.5 us and 1.5 KB per
comparison). The full 6,896-row shape was never run pre-fix; extrapolation does not reconcile with the
recorded 697 s / ~5 GB, so no extrapolated figure is quoted.

## Live probe of the model's report (credits approved 2026-10-24)

Model calls only (gpt-4o-mini, the loop's model), hand-written questions, no Census calls. `false trap` = a
valid question refused (the costly error). `miss` = a trap let through, which fails open, so no worse than
before. Scripts live in the session scratchpad, not the repo. I tuned against these phrasings, so the rates
are optimistic: the unbiased tests are the golden set and the owner's sealed set.

| Iteration | Change | False traps | Misses |
| --- | --- | --- | --- |
| 1 | `named` only; "a bare number is not a name" | 0 of 20 | 6 of 10 |
| 2 | add a `numbered` slot | 2 of 20 | 4 of 10 |
| 3 | spelled-out state counts; ignore the model's `listing` flag | 1 of 20 | 1 of 10 |
| 4-5 | prompt: a code that identifies a place goes in `named`; a bare tract/county number does not | 0 of 130 | 11 of 75 |
| 6 | prompt: numbered "wherever it sits, even as the first words" | 0 of 130 | 5 of 75 ("my county") |
| 7 | needs table, parallel `named_levels`, compact prompt | **15 of 185** | **53 of 85** (the short prompt degraded reports) |
| 8 | needs table, restored wording, `county_named` boolean | **0 of 360** | **11 of 180** ("my county" 10/10; one flaky "county 20 or county 28") |
| 8b | 12 state nicknames and abbreviations x5 ("Calif.", "tx", "Lone Star State") | 1 of 60 | |

Split-call latency in these runs: p50 1.0 s, p95 1.3 s, max 3.2 s (5 of 540 over the 3 s wait), beside the loop.

## Not verified: needs the full E2E

- `answered_rate`, the golden set and p95 against the 20 s ceiling (PLAN.md records 18.9-21.7 s) with the
  detector in place, at the same `--repeat`; and the regression-minus-sealed gap (the sealed run is the
  owner's: see the command given in chat; I never read the sealed set).
- t03 and t17 under `make demo` with the new scorer.
- The pre-flight claim of 6,896 tract rows for Texas (recorded in the ticket, not re-run).

## Known limits and issues found, not fixed (owner decides whether to file)

- "my county" and other deictic phrasings are not dropped by the model and fail open (the loop runs as
  before this change).
- A nationwide county or place listing is valid for the API (3,222 and 32,325 rows) but the resolver has no
  URL path for it (Gate 2 r3 F2, pre-existing).
- A block-group listing under a state needs `county:*` written in the URL (without it HTTP 400); the
  pipeline builds it without, so golden t04's expectation may be stale (pre-existing).
- A state-wide tract listing is HTTP 200, but the resolver flags it `geography_unsupported` (pre-existing).
- `_NEEDS` covers the five levels the program names. County subdivision, state legislative districts,
  school districts and PUMAs need the state, but `detect_level` never returns them.
- ZCTA with a state parent is HTTP 400 in 2021 and 2023: a ZCTA URL must carry no `in`.
- CC-123 (demo process memory, reaped before E2E completes) is still To Do and may affect E2E.

## Gate rounds (owner asked for four, 2026-10-24; round 1 counts the first Gate 1 and Gate 2)

Each round is a Gate 1 (tests, mutation-checked) and a cold Gate 2, then the fixes. Lenses for the cold
reviewers: round 2 async and fail-open correctness; round 3 behavior against `CLAUDE.md`,
`docs/requirements.md` and the scorer and golden changes; round 4 red team (force false traps and misses).
The E2E runs once after the rounds, and once more after the merge.

**Round 1.** Gate 1 (`cc-102-gate1.txt`): 51 mutations, 49 killed, 1 equivalent, 0 survivors. Gate 2
(`cc-102-gate2.txt`): not ready, 8 findings, all dispositioned (names the model remembers count; late
report checked on the first turn only; non-list `parents`; "in" is not Indiana; cap and slow-split tests;
t17 fixed; stale docs; `CLAUDE.md` carve-out).

**Round 2.** Gate 1 (`cc-102-gate1-r2.txt`): 28 mutations, 0 survivors, 2 source defects found and fixed.
Gate 2 (`cc-102-gate2-r2.txt`, async and fail-open lens): fixed (state-word scan removed, fail-open on any
exception, first turn by index).

**Round 3.** Gate 2 (`cc-102-gate2-r3.txt`, policy lens): F1 `_writes_a_state` contradicts the rule: removed.
F2 nationwide county listing has no URL path: pre-existing, listed above. F3 docs disagree: reconciled
net-zero. F4 table question at tract level got `geography_unsupported`: `tables_only`. F5 scorer blind to
whether the stop fired: now also requires no rows, table or alternatives. F6 any plan override disabled the
check: only one with geographies does. F7 3 s wait versus p95 headroom and F8 a parent filed inside a numbered
entry: to be measured in the E2E. F9 split prompt tripled: reported above, not shrunk (shorter wording
degraded the reports, iteration 7). F10 harmless.
Gate 1 round 3 was stopped (no mutation live) because the needs-table rewrite supersedes it; it runs once
on the final design with a trimmed suite runtime.

**Owed.** Gate 1 round 3 on the final design; Gate 1 and Gate 2 round 4 (red team); then E2E.

## Outward writes

None. No push, PR or Jira write. Close comment only after the owner merges, via
`scripts/jira_transition.py`.
