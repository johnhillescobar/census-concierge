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

---

## Status at 5c803da (2026-11-08, evening) - supersedes the NOT RUN column above

Evidence: `evidence/slice-6/cc-114/{gate1.txt, gate2.txt, anchor/}`. Gate 2 reviewed c2589c5; its findings
are fixed in 5c803da and need one re-run (non-trivial fixes). Anchor = unmodified origin/main 4b24f77,
`--repeat 3`, existing harness (CC-133 protocol not frozen), HEAD 4b24f77 at start and end.

Anchor A: long_tail answered 0.708 (floor 0.70); overall 0.79; **demo.p95 25.565s (ceiling 20; slowest
trial 77.5s)**; retriever@10 0.9; selector@1 0.825; geography grid 0.948 (11 misses of 210). Baseline
already breaches the p95 ceiling: not ship-ready on latency without an explicit owner waiver.

| ID | Status | Basis |
|---|---|---|
| AC1 | NOT RUN | Reuse of merged PR #97. Rule precedes outcomes by git order. `classify_geo_levels.py` not re-run. |
| AC2 | NOT RUN | Offline: stated level run exactly, refusal stands, URL level guarded (incl. override vs own plan). Live demo/grid not run. Owner decision pending on "with candidates" (default: executable candidates -> CC-131; the warning lists published level names meanwhile). |
| AC3 | PASS (Gate 2 to verify) | No change under `evals/`; `budgets.toml`, leakage baseline unchanged. Scalar scorer behaviour identical. |
| AC4 | NOT RUN | Anchor done; post-fix E2E not run. |
| AC5 | PASS | Gate 1: 40 mutations, 36 caught, 4 survivors closed by 9 added tests. Every later fix/test mutation-checked (this file's commits 977bf2a..5c803da); one weak test found and strengthened. |
| AC6 | **FAIL** | `budgets.toml` untouched, but api/src is 4804 > 4800. Owner decision requested. |
| GC1 | PASS | Git order. |
| GC2 | PASS (offline) | Per-leg scorer + per-leg execution, mutation-checked. No golden uses a list: q23 needs owner approval. |
| GC3 | NOT RUN | Old/new scorer on unchanged trials not run. |
| TC1 | NOT RUN | Tract case needs the live grid. |
| TC2 | PASS | |
| TC3 | PASS | |
| TC4 | NOT RUN | Needs post-fix run against anchor. |
| TC5 | PASS offline | Other-level URL, nationwide guess, refused level, override vs its own plan. Raw `for_spec` is unreachable by construction (`build_url` only accepts resolved geographies). |

Deviations from the design table, recorded: D1 the schema cannot list dataset-specific names, so the
refusal detail does; D2 candidates are level names in `detail`, not executable specs (CC-131);
D3 a wrong-length `levels` is now refused for repair; D5 an override is checked against its own plan.
Known silent-by-design: a stated null with a bare name resolves to state/place by NAME match, unflagged.
Leakage invariant: 6 violation entries vs 5 on main, only because the level table moved to geo_level.py.

---

## Status at fef4f1e (2026-11-08, night) - supersedes the status tables above

Rebased onto origin/main 94566f5 (budget PRs #123 and #124 merged: api_src_loc 4890). The tree equals the
E2E-tested head 828042c apart from `budgets.toml`. Hashes changed on every rebase; subjects identify commits.

Decisions (owner, this session): AC2 split (Jira comment 10829); leakage baseline lines approved as a
standalone commit that follows the CC-114 merge; p95 waiver approved per run (log line written once a run
has `demo.generated_at` and p95, as its own commit before the evidence PR).

- **AC2a delivered:** tracts inside one named place -> the containing counties' tracts, county-wide candidate
  with `geography_unsupported` naming the counties (`api/src/geo_within.py`, `test_tracts_in_place.py`).
  Verified live: Detroit -> `for=tract:*&in=state:26+county:163`, 627 tracts, 3 of 3 runs.
- **AC2b moved to CC-131 AC4:** nearest-supported executable candidates for an unpublished level (t15).
- **Leakage:** `chore/leakage-baseline-cc-114` (11 lines, exact counts, written for the post-merge state) must
  land after this PR merges, not before: before it the three geo_level.py lines are stale entries.
- **Budgets:** api src 4876/4890, largest file 408/410, docs 1819/1820. No other limit touched.
- **Gate 2:** one re-run done (gate2.txt on c2589c5, gate2-r2.txt on e0be1ee). Round-2 fixes and the
  derivation are tested and mutation-checked (34 of 34) but have no independent cold review: the playbook
  allows no further re-run, so a third review is the owner's call.
- **E2E pre-PR:** running on 828042c (isolated worktree); results go to `evidence/slice-6/cc-114/e2e-pre/`.
  AC4, TC1, TC4, GC3 and the INH rows stay NOT RUN until they are in.

Column the matrix lacked (run-slice.md): tested head. Offline rows are tested at fef4f1e (= 828042c + budget
file); live rows at 828042c; the anchor at 4b24f77.

---

## Status at 3945694 (2026-11-09) - supersedes the status tables above

Shipping head 3945694 on `cc-114/level-fidelity`, base origin/main 94566f5. Tested head for every row below is 3945694 unless stated.

New since fef4f1e: the tracts-in-place result warns `geography_not_nested` (06886a4); a refused level the model stated stays
unmet, so a later place answer is flagged (7fadbf8; found live on q11: 4 of 5 trials answered at place with no warning, now
5 of 5 flagged); `ask-path.md` updated (3945694). 42 of 42 mutations caught (`gate1-fixes.txt`). Full suite 1149 passed;
the one failure (`test_invariants_print_every_named_pattern`) is inherited and fails on main. ruff and mypy clean.

| ID | Status | Evidence |
|---|---|---|
| AC1 | NOT RUN | Rule committed before outcomes (ae3358e, ccca747). Reuse of PR #97 evidence; `classify_geo_levels.py` not re-run; rationale not yet written. Owner call. |
| AC2 | PASS for AC2a; AC2b moved to CC-131 AC4 (owner, Jira comment 10829) | Offline tests; live: t16 and q04 pass, q11 flagged 5 of 5. Grid 0.976 at 3945694; all 5 misses are `This portal is not running` harness crashes (anchor had 2). |
| AC3 | PASS | No `evals/` path differs from main; `run_demo.py` change is per-leg only (Gate 2: stricter or equal). |
| AC4 | **RED, owner decision** | long_tail 0.692 at 3945694 vs 0.708 anchor and 0.708 same-window main control. Median of six runs 0.708 (`long-tail-median.md`). Pooled head 0.706 vs main 0.708. Below the 0.700 floor; recorded, not rerun. |
| AC5 | PASS | 42 of 42 mutations caught. |
| AC6 | **RED** | No budget raised by this work. Budgets pass except `answered_rate` 0.692 < 0.700 and p95 25.809 > 20. Invariants fail only on the 6 inherited leakage entries, covered by the post-merge baseline commit (28560dc). |
| GC1, GC2 | PASS | Git order; per-leg scorer tests. |
| GC3 | NOT RUN | Old vs new scorer on unchanged trials. |
| TC1 | PASS | Grid `level=tract` 0.979 at 3945694, the only miss a harness crash; q04 live. |
| TC2, TC3, TC5 | PASS | Offline. TC3 caveat: an exact published name is accepted; a half of a slash-joined name (metro) is refused and flagged, not served (CC-106). |
| TC4 | PASS | No golden edited; anchor run first. |
| INH | **RED on p95** | demo p95 25.809s (cap 20; anchor 25.565s; same-window main 22.065s; earlier head runs 34.218s and 25.470s). Regex delta +0. Sealed gap owner-held. |

Same-window control (`control/`): main 22.065s vs head 25.470s; slowest trials are rerank-dominated in both. The 3945694 window
was slower overall (`t_ours` 0.311 vs 0.153, `t_census_api` 3.39 vs 2.38), so its latency is weakly informative.

Open owner decisions: the answered_rate floor and p95 for this run (the p95 waiver line is prepared in the PR body, not committed);
q14, q23, q26 and q17 goldens; AC1 reuse rationale; CC-106 follow-up for metro levels.
