# CC-114 rebuild plan (the one plan file for this slice)

Branch `cc-114/level-fidelity`, cut from `origin/main` 4b24f77 on 2026-11-08. No CC-114 branch existed
locally or on the remote. The prior implementation (7367cf7 and parents) was never merged and is
reachable from no branch; nothing of it is reused: not its fields, guard, goldens, scorer changes or
tests. Direction: owner, 2026-11-08 (PLAN.md "CC-114 correction"), repeated in session: **fix the root
cause, no workaround, nothing that fails silently.**

Yardstick (slice <= 8): a sound, flexible, robust URL; nothing from model memory.

## Root cause (pre-flight, read from `origin/main`)

1. **The level is not structured intent.** `resolve_geography.level` is an optional free string
   ("omit if unknown", `tools.py:68`). When absent, `geo._resolve` decides the level by scanning the
   query's words (`detect_level`, `geo.py:269`), then defaults to `place` (`geo.py:277`) and, for a
   place with no hit, to the county listing (`geo.py:417`). A comparison drops `level` entirely
   (`geo.py:223`). The level a user named is therefore whatever a word scan and two defaults say.
2. **Nothing compares the level asked with the level fetched.** `finish_tools` can rewrite the geography
   (`_listing_level` regex, nationwide fallback `us:1` on universe mismatch, `geo.py:248`), `build_url`
   accepts a model-written `for_spec`, and an override plan can carry any level. Each can fetch a
   level the question did not ask for, with no warning. The only check is the demo scorer (CC-38),
   which measures it after the fact and tells the user nothing.
3. **The existing level check fails open.** `finish.incomplete` returns `None` on any error or a late
   report, so a missing level report is indistinguishable from "no level asked".

## Design (each item is a root-cause fix, not a catch-all)

| # | Change | Owner of the decision |
|---|---|---|
| D1 | `level` becomes a **required, nullable** field of `resolve_geography`: a published level name, or `null` meaning "the question names no level". Omission is a validation error the loop already surfaces and bounds (two failures stop the tool). The schema lists the dataset's published level names from `geography.json` metadata, not from a phrase table. | default |
| D2 | `_resolve` executes the declared level **exactly**. An unpublished level is `geography_unsupported` listing the published levels (candidates). The word scan is no longer consulted when `level` is declared. A declared `null` keeps today's bare-place behaviour (CC-104 owns removing it). | default |
| D3 | Comparison legs carry their own level: optional `levels` parallel to `places`, validated for length; no leg's level is dropped. | default |
| D4 | The execution record keeps the **declared** level(s) (`asked_levels`), set from the tool arguments, never from the question. `finish_tools` re-resolves with the record's declared level, never an invented one. | default |
| D5 | One end-to-end invariant in `guards.py`: every URL built/fetched has a `for=` level equal to its declared level. Otherwise `geography_level_mismatch` (asked vs fetched, candidates at the asked level, URL still rendered, never counted as answered). The nationwide fallback, `build_url` raw specs and overrides are covered because the check is on the URL, not on one path. | default |
| D6 | A geography resolved with **no declared intent at all** is `geography_level_unverified`, visible in the response, instead of fail-open silence. | default |
| D7 | Scorer: `expect_geo_level` accepts a per-leg list (precision, not loosening); the answered rule is otherwise unchanged. Old and new scorer run on unchanged code and bridged before any gain is claimed. | default (CC-133 protocol) |
| D8 | Goldens change only by `evidence/slice-6/cc-114-rule.md`, one reason per commit, and **only with the owner's approval**: none are changed in this plan. | owner |

Out of scope, tracked elsewhere: removing the remaining prose scanners in `finish.py` and `geo.py`
(CC-104); metro reach, q11 (CC-106); nearest-supported candidates for t15 (CC-131); crosswalks (CC-77).

## AC / TC matrix (IDs fixed before implementation; filled with evidence at the shipping head)

| ID | Criterion | Expected | Command / test | Status |
|---|---|---|---|---|
| AC1 | Mismatch classification committed with the command | `cc-114-rule.md` committed before outcomes; classification reproducible | `git log --reverse -- evidence/slice-6/cc-114-rule.md evidence/slice-6/cc-114-classification.md`; `uv run python scripts/classify_geo_levels.py` | NOT RUN (reuse of merged PR #97 evidence, rationale to record) |
| AC2 | Named level fetched at that level, or `geography_unsupported`/mismatch warning with candidates; URL renders | no silent other-level answer | matrix tests T1-T5 below + demo grid | NOT RUN |
| AC3 | Golden changes only by rule, with reason; scorer not loosened | zero golden edits without owner approval; scorer diff reviewed | `git diff origin/main -- evals scripts/run_demo.py` | NOT RUN |
| AC4 | `long_tail` answered_rate before/after, same `--repeat`, stricter scorer both times | anchor A vs P at `--repeat 3` | `make demo` equivalent, both runs | NOT RUN |
| AC5 | New tests mutation-checked | each new test fails on its reverted behaviour | `evidence/slice-6/cc-114/gate1.txt` | NOT RUN |
| AC6 | No budget raise; `geo.py`/`compare.py` headroom re-measured | `check_budgets` + `check_invariants --base origin/main` exit 0 | `make check` recipe lines | NOT RUN |
| GC1 | Rule written before outcomes read | already true on main | git order of ae3358e before ccca747 | NOT RUN |
| GC2 | Per-leg expected levels | q23-shaped fixture scored per leg | scorer unit test | NOT RUN |
| GC3 | Gains from scorer/golden changes reported apart from code gains; re-run on main | bridge table | old/new scorer on unchanged anchor trials | NOT RUN |
| TC1 Happy | Named level fetched and scored at that level | `for=tract` for a tract question | matrix test + grid | NOT RUN |
| TC2 Edge | Multi-leg with different expected levels scored per leg | pass per leg, fail on a wrong leg | scorer + `levels` tests | NOT RUN |
| TC3 Novel | A metadata-published level absent from prompts/aliases is accepted and validated with no new phrase rule | e.g. a published level name resolved by exact metadata match | test using fixture metadata | NOT RUN |
| TC4 Regression | Every golden change has a written reason and a re-baseline on main first | none made; anchor first | anchor evidence | NOT RUN |
| TC5 Failure | A different-level fetch is never answered: warning with candidates or a recorded miss | guard fires for nationwide fallback, raw `for_spec`, override | guard tests | NOT RUN |
| INH | Inherited: response contract (URL, MOE, GEOID, universe, alternatives), no regex growth (`re.*` delta <= 0), sealed gap <= 10, leakage invariant, `demo.p95_latency_seconds` <= 20, no non-regression vs anchor | per CLAUDE.md | `make check`, demo, grid | NOT RUN |

Owner-only items: merge; any golden flip; any waiver. Not mine to decide: the CC-133 sampling protocol.

## Sequencing and blockers (tagged)

1. **Anchor first** (PLAN: pre-fix anchor before implementation). `origin/main` 4b24f77 *is* the
   post-rollback state, so the anchor is a demo + grid run at `--repeat 3` in an isolated worktree,
   HEAD recorded at start and end. CC-133 (To Do) has not frozen its protocol: this anchor is labelled
   `existing harness, protocol unfrozen` and may need re-labelling under CC-133. Tag: default.
2. Implement D1-D7, Gate 1 (tests + mutation), Gate 2 (`/code-review` then `review-pr.md`), E2E pre-PR.
3. Owner merges; E2E again on merged `main`; refresh the matrix; then Jira Done.

## Conflict found: Jira description is stale

The CC-114 Jira description (updated 14:07 today) still says "Continue ... on cc-114/level-substitution
(reviewed local head 7367cf7). Reuse implemented asked_levels/refused_specs, substitution guard,
scorer". That contradicts the owner direction in PLAN.md (a5b8e57, later). PLAN.md is followed. The
Jira text needs an owner-approved edit; I have not changed it.

## Outward writes (listed before they happen; none done yet)

- repo: branch `cc-114/level-fidelity`, commits, evidence under `evidence/slice-6/cc-114/`
- Jira: comment with the matrix and numbers at close; description correction only if the owner says so
- PR: opened for the owner to merge; I do not merge
