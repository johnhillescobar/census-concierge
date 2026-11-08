# PLAN — census-concierge

Execution order. What and why: `.claude/DESIGN.md`. What runs:
`docs/ARCHITECTURE.md`. Board and closed-slice STATUS: `docs/slices.md`.
Jira is the status source of truth.

## Rules

1. **Slices ship in order.** Nothing in slice N+1 starts until N is demoed.
   CC-91 (residual reliability) is the exception: it does not block CC-11.
2. Each open slice has a **Not in this slice** list. That list is the point.
3. **Done means a user got an answer.** Quote `make demo`. Tests are not done.
4. A budget raise is a human commit with a reason in `budgets.toml`.
5. **A spike is not a slice.** Timeboxed, throwaway branch, written decision.

Closed: slices 0–5 (CC-8, CC-1, CC-5, CC-2, CC-11, CC-6), the CC-9 spike
(direct psycopg, DESIGN §9), the harness epic (CC-4) and CC-91. Do not re-open
them. What each shipped and its evidence: `docs/slices.md`. Per-ticket numbers
live in Jira and `evidence/`, never here.

---

## Now

Slice 6 ([CC-3](https://johnhillescobar.atlassian.net/browse/CC-3)) is current.
Baseline: CC-38 post-merge on main, geography-level scorer, long_tail
answered_rate 0.742, p95 21.701s (`evidence/slice-5/cc-38-e2e-post.txt`).
CC-77 is a phase 1 intermediary epic (see its section below); its breadth
stories run alongside slice 6, while CC-120 now belongs to CC-3 and measures
their URL breadth. Its crosswalk children are unscheduled.

CC-103 closed: tract grid 47/48 post-merge, long_tail answered 0.733/0.750, demo p95 21.701s then 18.928s (ceiling missed in run 1, closed by owner; p95 work continues). `evidence/slice-6/cc-103-e2e-post-*`, epic [CC-3](https://johnhillescobar.atlassian.net/browse/CC-3).

---

## Slice 6 — Grounded understanding, structured intent and follow-ups (CC-3)

Owner direction (2026-11-08): model-owned structured intent, no downstream prose heuristics or legacy fallbacks. DESIGN §5/§8 defines the target; Jira owns live scope/status. No new budgets.
**CC-114 correction:** Owner direction (2026-11-08) is to remove/revert the entire previously delivered CC-114 implementation because it worked around the issues and could fail silently. Do not preserve its added fields, substitution guard, goldens/scorer changes, tests or fallback behavior as the foundation for the fix. Rebuild against the original AC/TC and evidence; missing/invalid intent must be surfaced for explicit bounded repair or as unsupported, never hidden by silent substitution or refusal. This does not add a retroactive 95/98% target or restart unrelated classification. Metro reach remains CC-106; deferred candidates remain CC-131.
**Instrument first:** CC-133 owns early oracle/cohort freezes, B/P/A/L baselines and automated AC/TC enforcement, split from CC-132. Record the pre-rollback main baseline, then establish a post-rollback, pre-fix anchor before corrected CC-114 implementation or migration shipping; neither baseline treats workaround behavior as an earned correctness floor. CC-132 owns final certification only. CC-102/103/113/116/117/120/121/123 are Done.

| Story | Required owned outcome (in addition to inherited gates) | Prerequisites |
|---|---|---|
| CC-114 | Remove/revert the prior workaround implementation; rebuild against original AC/TC with no silent substitution, fallback or masked failure | CC-133 pre-fix anchor |
| CC-133 | 100% measurement/manifest/isolation-harness AC/TC; freeze pre-rollback baseline and post-rollback, pre-fix anchor; no claimed product gain | — |
| CC-104 | 100% isolation; >=95% currently-supported geography intent | CC-114, CC-133 |
| CC-106 | >=95% new published level + entity selection | CC-104 |
| CC-119 | >=95% exact parent chains across vintages | CC-106 |
| CC-105 | >=95% supported exact coverage; separate >=95% negative-control outcomes | CC-119 |
| CC-129 | >=95% joint product/period/year interpretation; exact execution-year fixtures | CC-104 |
| CC-130 | >=95% required cell-set/universe selection; no total fallback | CC-104 |
| CC-118 | 100% limit/count fixtures and required live boundary cases | CC-133 |
| CC-82 | >=95% supported complete-table outcomes; 100% chunk identity/completeness fixtures | CC-102, CC-118, CC-130 |
| CC-115 | 100% valid override journeys/round-trips; no lost scope or unexpected 422 | CC-119 |
| CC-131 | >=98% joint single-turn understanding, >=95% each category and coverage | CC-105, CC-119, CC-129, CC-130 |
| CC-122 | 100% numerical/MOE fixtures; >=95% operation/operand/row selection | CC-129, CC-130, CC-82 |
| CC-42 | 100% scorer tests, frozen multi-turn oracle and bridged re-anchor; no claimed product gain | CC-131, geography chain, CC-120 |
| CC-43 | 100% prior-state/override/no-history fixtures; t_llm p50 increase <=1s | CC-42, CC-82, CC-113 findings |
| CC-107 | >=95% swap cohort, plus >=5/6 cases and >=80% standalone equivalence | CC-43 |
| CC-108 | >=95% addition cohort, plus >=4/6 cases and >=80% equivalence | CC-43 |
| CC-39 | >=95% unresolved cohort, >=5/6 cases; retain false-positive caps and coverage | CC-107, CC-108 |
| CC-132 | Final >=98% overall/>=95% category understanding AND all earned floors/AC/TC | CC-133, CC-39, CC-122, CC-115 |

**Progression:** freeze each owned cohort before implementation (>=30 independent families for stochastic cohorts); meet targets in both repeat-3 case and trial rates. All deterministic AC/TC fixtures pass 100%. If baseline is below target, meet it with positive paired improvement (95% lower bound >0); if already above, preserve it. These are requirements, not predicted gains. Previously earned floors never reset.
**No regression:** compare candidate P against same-window main B, the post-rollback/pre-fix anchor A and latest accepted post-merge L on identical supported cohorts/hashes/settings. Protected: long_tail answers, retrieval@10, selector@1, response compliance, supported coverage and earned categories. Require nonnegative observed differences AND paired family-level 95% lower bounds >=-2 percentage points. Do not count prior workaround behavior as an earned correctness floor; retain both B and A so rollback effects and corrected-fix effects are visible. This uncertainty bound never permits an observed decline; older 3-point tolerances do not override it. Inconclusive means not cleared.
CC-133 freezes balanced sampling/replication/stopping rules before results; retain all runs, cluster repeats/paraphrases by family, never rerun until green. Scorer changes get an unchanged-code old/new bridge; CC-42 re-anchoring cannot erase A or earned floors. Post-merge main must pass the same gates before becoming L. No cherry-picked high watermark or shrinking denominators.
**Latency:** actual full-run demo.p95 <=20s, no observed worsening against comparable B/A/L, plus specific caps; report uncertainty/work/failures without censoring outages or rewarding faster failures. Existing over-ceiling baselines remain blockers absent explicit run-specific owner waivers. CC-125/126 remain Phase 2 backlog, not promised current-slice prerequisites. Diagnose a failing baseline before feature work; any scheduling/budget decision remains explicit.
**Final gate:** DESIGN §8/CC-132 also require >=95% overall confidence lower bound, >=200 independent families per regression AND sealed suite, >=30/category, and supported determinate coverage >=95%/accuracy >=98%. Interpretation and semantic end-to-end answers are scored separately. No blanket refusal or unavailable-data invention. Targets are not present performance guarantees.
**Every close:** all AC/TC verified PASS with head/input evidence and mutations where required; Gate 2 verifies, post-merge E2E precedes Done. Only explicit dated owner amendments remove scope. Apply the canonical run-slice matrix. CC-133's automation is not yet installed.
Retain leakage protection, frozen dev/regression/sealed rules, one permitted sealed close look and gap <=10 points; never read sealed/E2E transcripts. Existing absolute quality floors and three-turn trial rate >=single-turn long_tail minus 10 points remain. Historical >=0.712 single-turn floor applies until CC-42 re-anchor, without weakening the new cumulative checks.
**Not in slice:** auth/PDF, new product families, general clipped crosswalk/allocation, saved derived datasets, regression/correlation. CC-122 is limited to bounded operations.

---

## CC-77 — Crosswalks and complete table extraction (phase 1, intermediary epic)
CC-11 foundations shipped. CC-118/82 run alongside slice 6 using the table above; CC-120's completed grid remains the URL baseline. Crosswalk children CC-78–81/83–86 remain unscheduled pending owner placement relative to slices 7/8. No budget raised.

---

## Slice 7 — PDF export (CC-10)

`POST /reports` → job id. Background worker. **Never a request handler.**
Write to object storage; signed URL. The container filesystem is ephemeral.
Every API URL in the document.

**Done when:** you download a document you would attach to a grant report.

---

## Slice 8 — Auth and hosting (CC-7)

Clerk. One container (Render / Fly) serving API + static frontend + pinned
index asset. Spend cap and Langfuse in the complete/dispatch path (CC-48).
Stateless workers; the read-only index is the sanctioned module-state
exception.

**Done when:** someone who is not you logs in and answers a real question.

---

## After

Do not plan this yet. Later, with usage data: clarification only where the
demo suite requires it, more datasets, GeoJSON export. (CC-77 is not here: it
is a phase 1 intermediary epic, above.)

## Every PR

- One sentence on what a user can now do.
- `make check` green, **no budget raised**.
- Long-tail retrieval, answered rate, and p95 did not regress.
- URL, MOE, GEOID, universe still on every response path.
- No new blocking clarification prompt.
- Every in-scope AC/TC is cleared in the PR/Jira evidence matrix before shipping;
  post-merge E2E is recorded before Done. No unverified requirement is a pass.
- `docs/ARCHITECTURE.md` updated if the shape changed.
- Under ~15 files, or an explanation why not.
