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

Closed slices 0–3 (CC-8, CC-1, CC-5, CC-2) and the harness epic (CC-4) are
Done. Do not re-open them. Residual misses after CC-2 are CC-91.

---

## Now

[CC-91](https://johnhillescobar.atlassian.net/browse/CC-91) reliability is
**Done**. CC-99 Done (last-word NAME; q17 0/3 table unpinned; answered_rate
0.867; p95 18.664s; `evidence/slice-3/cc-99-e2e-post.txt`). CC-98 Done
(finish/`place_token`; q39 3/3; answered_rate held; p95 over-ceiling recorded
not promoted; `evidence/slice-3/cc-98-e2e-post.txt`). CC-95 Done (ambiguous
place candidates); floors met; `evidence/slice-3/`;
https://johnhillescobar.atlassian.net/browse/CC-95. CC-94 Done (classification;
CC-98 finish/geo leaf). CC-96 Done (informal/alias geography is the ask loop
plus tools). CC-97 Done (`acs1_geography_ineligible`; answered_rate held; p95
over-ceiling recorded not promoted; `evidence/slice-3/cc-97-e2e-post.txt`).
Slice 4 ([CC-11](https://johnhillescobar.atlassian.net/browse/CC-11))
is **To Do** in Jira (epic and all eight stories). CC-77 waits on CC-11
table/plan-strip foundations. Spike CC-9 before slice 5.

---

## Slice 4 — Canvas (CC-11)

Living workspace, not a card stack. One active dataset. Explicit plan
overrides are typed fields on `POST /ask`, not follow-up language (that is
slice 6).

- [ ] Two-pane shell; table with GEOID, estimate, MOE.
- [ ] Backend `ResultPlan`; editable plan strip; re-run on override.
      Typed fields include the existing `allow_overlapping_acs5` fetch override
      (consecutive ACS5; `overlapping_vintage` still warns). Not follow-up language.
- [ ] `ChartSpec` from the agent; frontend renders (never chart code or SVG).
- [ ] Alternatives panel.
- [ ] CSV export.

**Done when:** a wrong-ish table is fixed in one click and the CSV matches.
**Not in this slice:** memory, auth, PDF.

---

## Spike — LangGraph checkpointer (CC-9)

Half a day. Throwaway branch. Does the Postgres checkpointer justify two
dependencies against ~30 lines under a **hand-rolled loop**? If the spike
overruns, pick the 30 lines.

Evaluate on:

- Lines of code each way, and the delta to `direct_dependencies`.
- What LangGraph gives *beyond* persistence — interrupts, time-travel,
  streaming state. Does anything in slices 5–8 need them?
- How well the checkpointer sits under a **hand-rolled loop** rather than a
  graph. If using it means reintroducing a `StateGraph` to hold the loop, the
  cost is much larger than two dependencies.
- Cost of switching later, in each direction.

**Done when:** a dated decision is in DESIGN §9, the branch is deleted,
`budgets.toml` is untouched.

---

## Slice 5 — Conversation persistence (CC-6)

Storage only. Concurrency law (no globals, pass arguments, never SQLite) is
already in DESIGN §5 — do not rediscover it here. A conversation survives a
restart; it does not yet understand "what about Texas?".

Postgres. **Never SQLite.** `thread_id` owned by `user_id` from day one.
`POST /conversations`, append, `GET /conversations/{id}` (refresh must not
lose the canvas). Implement whichever way CC-9 decided.

**Done when:** restart the server, reload, the canvas is still there.
**Not in this slice:** reference resolution, auth, PDF.

---

## Slice 6 — Follow-ups (CC-3)

Resolve "what about Texas?" against prior turns. Score multi-turn cases
across `--repeat`. Unresolved references are warnings with candidates, never
a blocking question.

**Done when:** a three-turn refinement produces the right dataset at a
measured pass rate. **Not in this slice:** auth, PDF.

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

Do not plan this yet. Parked: CC-77 (spatial crosswalks / full-table extract,
after CC-11 foundations). Later, with usage data: clarification only where
the demo suite requires it, more datasets, GeoJSON export.

## Every PR

- One sentence on what a user can now do.
- `make check` green, **no budget raised**.
- Long-tail retrieval, answered rate, and p95 did not regress.
- URL, MOE, GEOID, universe still on every response path.
- No new blocking clarification prompt.
- `docs/ARCHITECTURE.md` updated if the shape changed.
- Under ~15 files, or an explanation why not.
