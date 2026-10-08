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
stories run ahead of the multi-turn chain, its crosswalk children are unscheduled.

CC-103 closed: tract grid 47/48 post-merge, long_tail answered 0.733/0.750, demo p95 21.701s then 18.928s (ceiling missed in run 1, closed by owner; p95 work continues). `evidence/slice-6/cc-103-e2e-post-*`, epic [CC-3](https://johnhillescobar.atlassian.net/browse/CC-3).

---

## Slice 6 — Follow-ups (CC-3)

Resolve "what about Texas?" against prior turns. Score multi-turn cases
across `--repeat`. Unresolved references are warnings with candidates, never
a blocking question.

**Order:** CC-114 classification (no code) → CC-103/104/105 → CC-114
pipeline fix → CC-42 (multi-turn set + baseline; re-anchors the single-turn
baseline) → CC-43 (after CC-113 findings, or under its 1.0s `t_llm` cap) →
CC-107 / CC-108 (separate legs, no join) → CC-39. CC-102 and CC-106 run on
their own timeline but are in scope. **Superseded in part** by the CC-3 order
comment of 2026-10-04: CC-121 first (with CC-116), then the breadth stories;
the multi-turn chain waits for them. Jira holds the current order.

**Done when:** every child story is closed (CC-102 and CC-106 included) and a
three-turn refinement produces the right dataset at these case-level floors
(a case passes when right in 2 of 3 repeats): swaps >= 5/6, additions >= 4/6,
unresolvable >= 5/6, and the multi-turn rate >= single-turn long_tail - 10
points. The p95 gate reads the real number (CC-3 AC13): `run_demo` promotes
p95 every run and `check_budgets` passes on it. CC-113 ends with a draft fix
story the owner files, or a written case for a ceiling decision.

**Generalization (CC-3 AC6–12):** dev / regression / sealed sets; sealed set
is owner-held outside the repo and read-denied to agents; regression minus
sealed rate <= 10 points at every story close. No eval phrasing or place in
prompts, tools or `api/src` literals (leakage invariant). Golden or scorer
changes re-baseline on main and are reported apart from code gains; the
scorer may get more precise, never looser. Single-turn long_tail stays within
3 points of the re-anchored baseline and of each ticket's pre-run, same
`--repeat`, geography-level scorer.
**Not in this slice:** auth, PDF.

---

## CC-77 — Crosswalks and complete table extraction (phase 1, intermediary epic)

Part of phase 1, not future work; its CC-11 foundations have shipped. Its URL
breadth stories (CC-118 variable-limit guard, CC-82 whole-table retrieval,
CC-120 URL breadth grid) are already sequenced ahead of the slice 6 multi-turn
chain in the CC-3 order comment of 2026-10-04. The crosswalk children (CC-78
to CC-81, CC-83 to CC-86) are **not yet scheduled**: where they sit relative to
slices 7 and 8 is an owner decision, still open. No budget raised.

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
- `docs/ARCHITECTURE.md` updated if the shape changed.
- Under ~15 files, or an explanation why not.
