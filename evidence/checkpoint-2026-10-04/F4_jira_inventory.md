# F4 - Jira CC inventory (read-only)

Pulled 2026-10-04 ~19:45 CDT via `scripts/jira_fetch.py` helpers (REST GET / POST `/search/jql`; no writes). Timestamps are Jira-reported (-0500). 121 issues total: 80 Done, 39 To Do, 2 In Progress. Raw dump: `f4_all_issues.json` in this folder.

## 1. Non-Done issues (41)

| Key | Type | Status | Epic | Created | Updated | Labels | Links | Summary | Capability |
|---|---|---|---|---|---|---|---|---|---|
| CC-3 | Epic | In Progress | - | 2026-08-23 | 2026-10-04 18:58 | follow-ups, multi-turn | - | Slice 6 — follow-ups and reference resolution | conversation (epic) |
| CC-7 | Epic | To Do | - | 2026-08-23 | 2026-09-30 05:17 | auth, hosting, lean-showcase | - | Slice 8 — auth and hosting | auth/hosting (epic) |
| CC-10 | Epic | To Do | - | 2026-08-23 | 2026-09-30 05:17 | pdf-export | - | Slice 7 — PDF export | PDF/export (epic) |
| CC-39 | Story | To Do | CC-3 | 2026-08-23 | 2026-10-01 22:24 | follow-ups, multi-turn | is blocked by CC-42, CC-43 | Warn with candidate interpretations when a follow-up reference cannot be resolved | conversation |
| CC-42 | Story | To Do | CC-3 | 2026-08-23 | 2026-10-04 18:58 | eval, multi-turn | is blocked by CC-82, CC-103, CC-104, CC-105, CC-114, CC-120; blocks CC-39, CC-43, CC-107, CC-108 | Add multi-turn evaluation cases and score them across repeats | process/eval |
| CC-43 | Story | To Do | CC-3 | 2026-08-23 | 2026-10-04 18:54 | follow-ups, multi-turn | is blocked by CC-42, CC-113; blocks CC-39, CC-107, CC-108 | Give the ask loop the prior turn's plan for follow-ups | conversation |
| CC-44 | Story | To Do | CC-7 | 2026-08-23 | 2026-09-30 05:02 | hosting, lean-showcase, pinned-index | - | Build one container that serves the API and the web app with the pinned index | auth/hosting |
| CC-45 | Story | To Do | CC-7 | 2026-08-23 | 2026-09-30 05:02 | auth, lean-showcase, user-plans | - | Integrate Clerk auth and tie conversation ownership to real users | auth/hosting |
| CC-46 | Story | To Do | CC-10 | 2026-08-23 | 2026-09-30 05:17 | object-storage, pdf-export | - | Store finished PDFs in object storage and return signed download URLs | PDF/export |
| CC-47 | Story | To Do | CC-10 | 2026-08-23 | 2026-09-30 05:17 | pdf-export, report-jobs | - | Create asynchronous report job endpoints for PDF export | PDF/export |
| CC-48 | Story | To Do | CC-7 | 2026-08-23 | 2026-09-30 05:17 | lean-showcase, question-quota | - | Enforce the per-user monthly question quota | auth/hosting |
| CC-50 | Story | To Do | CC-10 | 2026-08-23 | 2026-09-30 05:17 | pdf-export, report-content | - | Include questions, answers, charts, tables, and every API URL in the report | PDF/export |
| CC-77 | Epic | To Do | - | 2026-09-16 | 2026-10-04 18:11 | full-table, spatial-crosswalk, zcta | - | Spatial crosswalks and complete ACS table extraction | geography + API construction (epic) |
| CC-78 | Story | To Do | CC-77 | 2026-09-16 | 2026-09-21 21:22 | offline-artifact, spatial-crosswalk | - | Build a versioned place-to-ZCTA spatial crosswalk artifact | geography (crosswalk) |
| CC-79 | Story | To Do | CC-77 | 2026-09-16 | 2026-09-21 21:22 | multi-geography, spatial-crosswalk | - | Execute bounded multi-ZCTA request legs with complete provenance | execution (multi-leg) |
| CC-80 | Story | To Do | CC-77 | 2026-09-16 | 2026-09-21 21:23 | golden-eval, spatial-crosswalk | - | Define place-to-ZCTA semantics and golden evaluation cases | process/eval (+geography) |
| CC-81 | Story | To Do | CC-77 | 2026-09-16 | 2026-09-21 21:23 | gazetteer, spatial-crosswalk | - | Integrate evidence-earned place and ZCTA crosswalk resolution | geography (crosswalk) |
| CC-82 | Story | To Do | CC-77 | 2026-09-16 | 2026-10-04 18:58 | acs, chunking, full-table | is blocked by CC-118; relates to CC-120, CC-121; blocks CC-42 | Retrieve complete ACS tables: group() first, chunked requests only where group() cannot be used | API construction (whole table) |
| CC-83 | Story | To Do | CC-77 | 2026-09-16 | 2026-09-21 21:23 | allocation, methodology, spatial-crosswalk | - | Prove which block-level allocation methods are defensible | geography (allocation method) |
| CC-84 | Story | To Do | CC-77 | 2026-09-16 | 2026-09-21 21:23 | allocation, spatial-crosswalk | - | Implement approved city-intersection allocation modes | geography (allocation) |
| CC-85 | Task | To Do | CC-77 | 2026-09-16 | 2026-09-21 21:23 | agent-tool, decision, golden-eval | - | Decide whether a fifth agent tool is earned by crosswalk evaluations | other (tool decision) |
| CC-86 | Story | To Do | CC-77 | 2026-09-16 | 2026-09-21 21:23 | full-table, spatial-crosswalk, ui | - | Expose crosswalk modes and complete tables in the analyst UI | other (UI) |
| CC-102 | Bug | To Do | CC-3 | 2026-09-27 | 2026-10-04 00:11 | - | relates to CC-100, CC-101, CC-103 | Bare numeric geography comparisons let a model-hallucinated parent defeat the "needs more info" | geography (guard) / latency |
| CC-104 | Bug | To Do | CC-3 | 2026-09-27 | 2026-10-04 18:54 | - | blocks CC-42, CC-106; is blocked by CC-114 | finish.py re-derives "is this a listing" via regex instead of trusting the model's own level fi | geography (level) |
| CC-105 | Bug | To Do | CC-3 | 2026-09-27 | 2026-10-04 18:54 | - | blocks CC-42; is blocked by CC-119 | A single named place spanning multiple counties/states (e.g. New York City = 5 counties) never  | geography (multi-county) |
| CC-106 | Story | To Do | CC-3 | 2026-09-27 | 2026-10-04 18:55 | - | is blocked by CC-104; blocks CC-119; relates to CC-120 | Reach CBSA/Metro-Division/PUMA/Urban-Area geography levels already present in geography.json bu | geography (level reach) |
| CC-107 | Story | To Do | CC-3 | 2026-09-30 | 2026-10-01 23:00 | follow-ups, multi-turn | is blocked by CC-42, CC-43 | Follow-up geography swap ("what about Texas?") | conversation |
| CC-108 | Story | To Do | CC-3 | 2026-09-30 | 2026-10-01 23:00 | follow-ups, multi-turn | is blocked by CC-42, CC-43 | Follow-up variable addition ("add median income") | conversation |
| CC-109 | Task | To Do | CC-10 | 2026-09-30 | 2026-09-30 05:35 | pdf-export, spike | - | Spike: how are ChartSpecs rendered in the PDF report? | PDF/export (spike) |
| CC-110 | Story | To Do | CC-7 | 2026-09-30 | 2026-09-30 05:36 | hosting, lean-showcase | - | Host the container on Render with managed Postgres at a stable URL | auth/hosting |
| CC-111 | Story | To Do | CC-7 | 2026-09-30 | 2026-09-30 05:36 | lean-showcase, spend-cap | - | Enforce a per-user spend cap in the model-calling path | auth/hosting |
| CC-112 | Story | To Do | CC-7 | 2026-09-30 | 2026-09-30 05:36 | lean-showcase, tracing | - | Emit production tracing from the complete and dispatch paths | auth/hosting (tracing) |
| CC-113 | Story | To Do | CC-3 | 2026-09-30 | 2026-10-04 18:54 | eval, latency, research | blocks CC-43 | Research where /ask latency comes from (LLM, Census API, our code) and recommend reductions per | process/eval (latency research) |
| CC-114 | Bug | In Progress | CC-3 | 2026-10-01 | 2026-10-04 18:54 | - | blocks CC-42, CC-104 | Questions that name a geography level (tract, county, metro) can be answered with a different l | geography + process/eval (scorer) |
| CC-115 | Bug | To Do | CC-3 | 2026-10-03 | 2026-10-03 22:12 | - | - | Clicking an alternative table after a listing result returns 422: the override re-sends wildcar | other (override contract / UI bug) |
| CC-116 | Story | To Do | CC-3 | 2026-10-04 | 2026-10-04 18:54 | - | blocks CC-117; relates to CC-121 | Add the leakage invariant: no eval phrasing or place in prompts, tool descriptions or api/src l | process/eval (leakage invariant) |
| CC-117 | Story | To Do | CC-3 | 2026-10-04 | 2026-10-04 18:54 | - | is blocked by CC-116 | Choose the table through retrieval and the selector, not phrase pins or measure-specific siblin | retrieval (table choice) |
| CC-118 | Story | To Do | CC-77 | 2026-10-04 | 2026-10-04 18:54 | - | blocks CC-82; relates to CC-120 | Never present a URL that exceeds the Census 50-variable limit | API construction (50-var cap) |
| CC-119 | Story | To Do | CC-3 | 2026-10-04 | 2026-10-04 18:55 | - | is blocked by CC-106; blocks CC-105; relates to CC-120 | Compose the full parent chain from the published geography hierarchy | geography (parent chain) |
| CC-120 | Story | To Do | CC-77 | 2026-10-04 | 2026-10-04 18:58 | - | relates to CC-82, CC-106, CC-118, CC-119; blocks CC-42 | URL breadth grid: score variables, geography levels and time settings as URL soundness | process/eval (URL breadth grid) |
| CC-121 | Bug | To Do | CC-3 | 2026-10-04 | 2026-10-04 19:32 | - | relates to CC-82, CC-116 | The answer text states figures that are not in the fetched data | other (answer prose / presentation) |

### Done since CC-98 and other Done in the last ~10 days (context)

| Key | Resolved | Epic | Summary |
|---|---|---|---|
| CC-103 | 2026-10-04 00:08 | CC-3 | Multi-parent wildcard detection only reliably fires for the exact worked-example phrasing; othe |
| CC-6 | 2026-10-01 22:46 | - | Slice 5 — conversation persistence |
| CC-38 | 2026-10-01 21:28 | CC-6 | Restore an existing conversation after restart or page reload |
| CC-41 | 2026-10-01 10:00 | CC-6 | Add create, append, and read conversation endpoints |
| CC-40 | 2026-10-01 06:37 | CC-6 | Store conversations in Postgres with thread and user ownership |
| CC-36 | 2026-09-29 21:43 | CC-9 | Compare direct persistence against LangGraph checkpointer cost and value |
| CC-33 | 2026-09-29 21:43 | CC-9 | Write a dated architectural decision and update design docs from the spike |
| CC-9 | 2026-09-29 21:08 | - | Spike (Pre Slice 5)— does LangGraph earn its place? |
| CC-11 | 2026-09-28 09:37 | - | Slice 4 — living data workspace, refinement, charts, and CSV |
| CC-49 | 2026-09-28 08:54 | CC-11 | Export the active normalized dataset as CSV |
| CC-101 | 2026-09-27 22:39 | CC-11 | Multi-state wildcard geography listings silently collapse to one state ("all counties in Texas  |
| CC-100 | 2026-09-26 05:48 | CC-11 | Multi-geography comparisons silently drop all but the last-resolved place |
| CC-87 | 2026-09-25 16:29 | CC-11 | Render validated multi-series charts with Vega-Lite |
| CC-37 | 2026-09-24 22:11 | CC-11 | Render the editable plan strip and alternatives picker |
| CC-88 | 2026-09-24 19:39 | CC-11 | Build the two-pane living workspace shell |
| CC-89 | 2026-09-24 15:09 | CC-11 | Validate and apply explicit plan overrides on POST /ask |
| CC-90 | 2026-09-24 08:42 | CC-11 | Return a structured executable ResultPlan with every answer |
| CC-99 | 2026-09-22 20:57 | CC-91 | Do not resolve unpublished region names via last-word NAME hits |
| CC-98 | 2026-09-21 22:40 | CC-91 | Extract a published place name when finish resolves the raw question |

## 2. Epics: stated scope vs current children

13 epics. Done: CC-1, 2, 4, 5, 6, 8, 9, 11, 91. Open: CC-3 (In Progress), CC-7, CC-10, CC-77 (To Do).

### CC-3 Slice 6, follow-ups and reference resolution (In Progress; 17 children, 1 Done)
- **Stated Objectives (epic description, unchanged):** resolve follow-ups like "what about Texas?" / "add median income"; score multi-turn across repeats; warn with candidates instead of blocking. **Scope:** "Reference resolution and multi-turn behavior on top of existing persistence." Notes say "No auth or PDF in this slice."
- **What the description also carries:** AC1-5 (2026-10-02), anti-drift AC6-13 (2026-10-01) incl. sealed set A+B+C, 10-pt gap ceiling, leakage invariant (AC8), re-anchored baseline (AC9), p95 gate (AC13). Owner decisions 2026-10-01: CC-106 stays in CC-3; the epic closes only when every child is closed.
- **Children matching the stated scope (5 of 16 open):** CC-39, CC-42, CC-43, CC-107, CC-108.
- **Children that do NOT match the stated scope (11 of 16 open):**
  - CC-102 (single-turn "needs a parent" guard and latency bug)
  - CC-104 (level taken from the model rather than re-derived by regex)
  - CC-105 (multi-county place)
  - **CC-106 (capability expansion: new geography levels)**
  - CC-113 (latency research)
  - CC-114 (wrong-level scoring and classification)
  - CC-115 (alternative-table click returns 422; UI/contract)
  - CC-116 (leakage invariant tooling)
  - CC-117 (table pins and sibling rules; retrieval)
  - CC-119 (parent-chain composition)
  - CC-121 (answer text states figures not in the data; presentation)
- Plus the one Done child, CC-103 (multi-parent repair), which is also single-turn geography.
- **Inference:** the epic title and Objectives describe the multi-turn chain, but the open work is mostly single-turn URL soundness. Per the 2026-10-04 comments, the multi-turn chain (CC-42, 43, 107, 108, 39) is sequenced last, behind the breadth stories. The Objectives text was not updated; the change lives in comments (18:55, 18:58) and AC text.
- This matches the memory note that CC-3 absorbed CC-102 to CC-106 and CC-114; it has since grown by CC-115, 116, 117, 119 and 121.

### CC-11 Slice 4 (Done; 10 of 10 children Done)
Scope was the two-pane workspace, plan strip, ChartSpec and CSV. Last accepted children: CC-100 and CC-101. **No open children, so the epic-cap rule held.**

### CC-77 Spatial crosswalks and complete ACS table extraction (To Do; 11 children, 0 Done)
- **Stated scope (description rewritten 2026-10-04 14:35; "future-slice" label removed 18:11):** a phase 1 intermediary epic. Place to ZCTA crosswalk; gazetteer lookup only if evidence-earned; versioned block-level artifacts; whole-ZCTA versus city-clipped as explicit modes; full ACS distribution-table retrieval (split across request legs when limits require); a fifth tool only if a named golden question proves it. Out of scope includes "a generic routing graph, clarification subsystem" and raising any budget.
- **Matching children:** CC-78, 79, 80, 81, 83, 84, 85, 86 (crosswalk/allocation; unscheduled) and CC-82 (full table).
- **Not matching the stated scope:**
  - **CC-118** (a `build_url` 50-variable guard; a bug fix in the existing URL tool)
  - **CC-120** (URL breadth grid; an eval harness spanning variables, levels and time that also scores CC-106 and CC-119, which sit in CC-3)
- **Cross-epic coupling:**
  - CC-82's own text says it "is not blocked by the crosswalk stories under CC-77", yet it sits inside CC-77.
  - CC-82 and CC-120 now block CC-42, a CC-3 ticket.
  - The epic ACs still describe chunking as the mechanism, while CC-82 now makes `group()` the first mechanism (the epic text was not updated).
- Per PLAN.md, the crosswalk children are "not yet scheduled" (an owner decision, still open).

### CC-7 Slice 8 auth and hosting (To Do; 6 children, 0 Done)
Unchanged since 2026-09-30: CC-44, 45, 48, 110, 111, 112. No scope drift seen.

### CC-10 Slice 7 PDF export (To Do; 4 children, 0 Done)
Unchanged since 2026-09-30: CC-46, 47, 50, 109. No scope drift seen.

## 3. Jira vs docs/slices.md vs .claude/PLAN.md

Both docs were last changed by merged PR #100 (origin/main `c6ef956`). The local branch `docs/cc-77-phase1-wording` is at `9094aac`, behind that merge.

- **Epic set matches:** the 13 epics on the board equal the 13 in Jira. PLAN's "Closed: slices 0-5, CC-9, CC-4, CC-91" matches Jira Done.
- **Status mismatch:** slices.md lists CC-3 as "To Do (current)", while Jira says In Progress.
- **PLAN.md Slice 8 cites the wrong key for two features:** it says "Spend cap and Langfuse in the complete/dispatch path (CC-48)". In Jira CC-48 is the per-user monthly question quota, the spend cap is CC-111 and tracing is CC-112. Neither CC-111 nor CC-112 appears in PLAN.md.
- **Open tickets that no prescriptive doc names (grep of PLAN.md, slices.md, ARCHITECTURE, requirements, ask-path, retrieval, DESIGN):**
  - **CC-115, CC-117, CC-119** are not named anywhere. PLAN.md's Slice 6 order and CC-3's Done-when never mention them, but CC-3's epic-close rule now requires them.
  - **Slice 7/8 children:** CC-44, 45, 46, 47, 50, 109, 110, 111, 112 are not named, which is fine because they are covered by epic.
  - **Range-covered:** CC-104 and CC-105 appear only inside the range "CC-103/104/105". CC-79, 80, 84 and 85 appear only inside "CC-78 to CC-81, CC-83 to CC-86".
- **Done-when coverage:** PLAN's Slice 6 "Done when" lists every child "CC-102 and CC-106 included". It does not mention that CC-116, 117, 119 and 121 must also close, though the CC-3 18:55 comment says so.
- **Slice-board item with no ticket:** none found. Every board epic exists in Jira.
- **Jira tickets not on the board:** the board lists epics only, so child tickets are unlisted by design. PLAN.md's Slice 6 "Order" paragraph is the only place children are sequenced, and it points to Jira ("Jira holds the current order").

## 4. Architecturally relevant open tickets: detail

Each entry lists the ticket's purpose, the code paths it would touch (grepped in the repo), its dependencies, and the last comments. The tickets read here are CC-77, 82, 102, 104, 105, 106, 113, 114, 115, 116, 117, 118, 119, 120, 121, 42 and 43.

**Shared hot spots (confirmed by `scripts/check_budgets.py` run on this tree):**
- `api_src_loc` 4396 / 4400, `largest file LOC` 410 / 410, `web_src_loc` 3349 / 3350, `doc_lines` 1723 / 1800. Headroom is 4, 0, 1 and 77 lines.
- My own line counts (non-blank, non-comment) put `geo.py` and `ask.py` both at 410, the per-file cap. `finish.py` is 223 and `geo_list.py` is 212.
- Budget log mismatch: the human commit `b4aa5f0` (2026-10-02, CC-103) changed `api_src_loc` 4300 -> **4400**, but the log line it added says 4300 -> **4340**. The cap in force (4400) is 60 lines above what the log records.
- **Stale-p95 trap is live right now:** `check_budgets` prints `p95 latency 19.207 <= 20 ok`, while `evidence/latest.json` has `demo.p95_latency_seconds` = **21.701** (over the ceiling). CLAUDE.md names this trap; CC-3 AC13 is the ticket that removes it.
- `api/src/prompts.py` `ROLE` is a single prompt (line 10).
- Regex call sites under `api/src`: **64** by the repo's own AST counter (`check_invariants._regex_calls`):
  - geo_list 18
  - vintages 13
  - geo 11
  - guards 8
  - compare 3
  - ask 2, contract 2, finish 2, metadata 2, text 2
  - census_url 1
- The `check_no_new_regex` ratchet only blocks increases; it does not remove existing ones.
- Eval-place leakage still present in `tools.py`: line 39 ("Oregon") and line 46 ("Chicago"). These are exactly the items CC-116 is meant to catch.

| Ticket | What it does | Code it would touch | Depends on / blocks | Latest comments (dates 2026-10-0x) |
|---|---|---|---|---|
| **CC-77** epic | Crosswalk plus whole-table; phase 1 | See children | Children only | none; description edited 14:35 on the 4th, label edited 18:11 |
| **CC-82** | Whole ACS table via `group()` first, chunked only if needed | `api/src/tools.py` (`BuildUrlTool` line 230; `get_cols = ["NAME","GEO_ID",*paired]` at line 311), `api/src/fetch.py` (`FetchDataTool` line 208), `api/src/contract.py` (row/column shapes), web table render | Blocked by CC-118; relates to CC-120, CC-121; **blocks CC-42** | 4th 14:42: scope revised after live pre-flight (`group()` returned 3,222 counties x 200 columns in 4.1s) |
| **CC-102** | Bare numeric comparisons let a hallucinated parent defeat the "needs more info" guard (700s+ latency) | `api/src/compare.py:61 parentless_tracts`, `compare.py:131 comparison_rows` (O(rows^2)), `geo_list.py:85 find_state`; compare.py has 3 regexes | Relates to CC-100, 101, 103; must close before CC-3 closes | 9/27 17:42: p95 impact table; 10/04 00:11: t03 hit 820.4s again (810s in our own code) |
| **CC-104** | Trust the model's `level`, stop re-deriving "is this a listing" by regex | `api/src/finish.py:36 _LISTING`, `:41 _BY_COUNTY`, `:75 _wrong_listing`; `geo.py:129 detect_level`, `geo.py:28 _LEVELS`; `prompts.py:10 ROLE` | Blocked by CC-114; blocks CC-106 and CC-42 | 10/03 21:18: Gate 2 notes: `plan_split` is an extra model call on every request, and `tools.py:39` uses an eval place |
| **CC-105** | A named multi-county place (NYC = 5 counties) uses `county (or part)` under the place first; `parents` is the fallback | `geo.py` (`legal_predicate:100`, `nests_in:123`), `finish.py:121 plan_split`, `prompts.py`, `tools.py:46` (NYC/Chicago in tool text) | Blocked by CC-119; blocks CC-42 | 10/04 14:42: scope revised (live: NYC returned 5 counties, Houston 4) |
| **CC-106** | Reach the other published levels (CBSA, metro division, PUMA, urban area, school district...) by validating the model's `level` against `geography.json` | `geo.py:28 _LEVELS` (only 15 aliases for 6 levels today), `geo.py:180 ResolveGeographyTool`, `prompts.py`, `geo_list.py` | Blocked by CC-104; blocks CC-119; relates to CC-120 | 10/04 14:42: scope revised: "do not grow `_LEVELS`" |
| **CC-114** | Classify and fix questions answered at a different level than they name (In Progress) | `scripts/classify_geo_levels.py` (exists); `evidence/slice-6/cc-114-rule.md`, `cc-114-classification.md` exist; goldens; later `geo.py`, `finish.py`, `compare.py` | Blocks CC-104 and CC-42 | 10/02 18:21: classification done (18 trials: 10 pipeline_wrong strict, 3 golden_arguable, 3 golden_misspecified, 2 table_cannot_serve); no product code changed |
| **CC-113** | Research where `/ask` latency comes from | Read-only research; `scripts/run_demo.py`, `evidence/slice-6` | **Blocks CC-43** | 10/04 00:11: q18 over 20s in all 6 trials; 14:42: p95 over ceiling "accepted as known" (owner decision recorded) |
| **CC-115** | Alternative-table click after a listing returns 422 | `api/src/contract.py:228 bind_override_geographies`, `:345 bind_plan_geographies`; `web/src/plan.ts:80 tableOverride`; `web/src/PlanStrip.tsx:301` | Independent; CC-119 must keep it working | none |
| **CC-116** | Leakage invariant in `check_invariants.py` | `scripts/check_invariants.py`; remedies in `prompts.py`, `tools.py` (lines 39, 46), `geo.py` literals | Blocks CC-117; relates to CC-121 | none; should be first merged per its text |
| **CC-117** | Table choice by retrieval and selector only; remove pins and sibling rules | `api/src/vintages.py:97 pinned_table` + 7 pin regexes (lines 23-29), `tools.py:108 _with_device_table`, `finish.py` injection, `api/src/retrieval/rerank.py:34` ("Sibling rules") | Blocked by CC-116 | none |
| **CC-118** | Never present a URL over the 50-variable cap | `api/src/tools.py:311` (`BuildUrlTool`), `tools.py` line budget | Blocks CC-82; relates to CC-120 | none |
| **CC-119** | Compose the full parent chain from the published hierarchy | `geo.py:100 legal_predicate`, `geo.py:123 nests_in`, `finish.py` (CC-103 repair), `contract.py:228` | Blocked by CC-106; blocks CC-105; relates to CC-120 | none |
| **CC-120** | URL breadth grid: score variables x levels x time as URL soundness | New script beside `scripts/run_grid.py`; `evidence/`; cells generated from `geography.json` | Relates to CC-118, 82, 106, 119; **blocks CC-42** | none |
| **CC-121** | Answer prose states figures not in the fetched data (49% of 39 answers by the author's counter) | `api/src/contract.py:374 take_chart` (prose passes through at lines ~389-390), `prompts.py:40`, new deterministic figure rendering | Relates to CC-116, CC-82 | 10/04 19:32: author corrects the evidence section (numbers come from two separate runs; the q11 derivation claim was not verified; acceptance numbers are the author's proposal, not owner-approved) |
| **CC-42** | Multi-turn eval set plus baseline | `evals/multiturn.toml` (new), `scripts/run_demo.py`, `scripts/check_invariants.py`; runs through the conversation routes | Blocked by CC-103 (Done), 104, 105, 114, **82, 120**; blocks CC-43, 107, 108, 39 | none |
| **CC-43** | Give the ask loop the prior turn's plan | `run_ask` (`api/src/ask.py`), `prompts.py`, conversation routes (`api/src/main.py`, `store.py`) | Blocked by CC-42, **CC-113**; blocks CC-107, 108, 39 | none |

### Dependency chain after today's linking (from the Jira link graph)
`CC-114 -> CC-104 -> CC-106 -> CC-119 -> CC-105 -> CC-42`, `CC-118 -> CC-82 -> CC-42`, `CC-120 -> CC-42`, `CC-116 -> CC-117`, `CC-113 -> CC-43`, `CC-42 -> CC-43 -> {CC-107, CC-108, CC-39}`.
- **Not linked as blockers:** CC-121, CC-117, CC-102, CC-115.
- CC-42 is directly blocked by five open tickets (CC-104, 105, 114, 82, 120) and transitively by eight (adding CC-106, 118, 119). Every other multi-turn ticket sits behind CC-42.
- Two of those eight, CC-82 and CC-120 (plus CC-118 via CC-82), are in the other epic (CC-77).

## 5. Created or edited in the last 24 hours (since 2026-10-03 19:40 CDT)

Read from the Jira issue changelogs. Every write since 2026-10-04 14:35 carries the author `Johndataanalytics`.
- **Inference:** `Johndataanalytics` is the identity behind the REST token used by `scripts/` (the user's own account); `John Hill Escobar` is the identity that closed CC-103 and wrote the 10/03 to 10/04 00:11 comments. Both display names appear on the same project.

**Created (7 tickets in the window):**
- CC-115 on 10/03 22:12
- CC-116, CC-117, CC-118, CC-119 on 10/04 14:41, and CC-120 at 14:42
- CC-121 on 10/04 18:19

**Descriptions edited:**
- CC-77 at 14:35
- CC-82, CC-105 and CC-106 at 18:12
- CC-121 at 18:48

**Other field edits:**
- CC-82 summary changed at 18:12, from "Retrieve complete ACS distribution table" to "Retrieve complete ACS tables: group() first, chunked requests only where group() cannot be used"
- CC-77 labels changed at 18:11: `future-slice` removed, `zcta` added

**Links created at 18:54 to 18:58:**
- About 30 link changes across CC-42, 43, 82, 104, 105, 106, 113, 114, 116, 117, 118, 119, 120 and 121
- These produced the dependency chain shown above

**Comments added by the other session:**

| Time | Ticket | What it says |
|---|---|---|
| 10/04 14:42 | CC-82 | Revised scope (`group()` first) |
| 10/04 14:42 | CC-105 | Revised scope (`county (or part)` first) |
| 10/04 14:42 | CC-106 | Revised scope (level token validated against `geography.json`) |
| 10/04 14:42 | CC-113 | "Owner decision (recorded 2026-10-04)": p95 over the ceiling is accepted as known |
| 10/04 18:55 | CC-3 | Implementation order, 11 steps |
| 10/04 18:58 | CC-3 | "Owner decision (2026-10-04): the multi-turn chain waits for the breadth stories" |
| 10/04 19:32 | CC-121 | Correction to its own evidence section |

**Edited by `John Hill Escobar` in that window:**
- CC-103 moved to Done at 10/04 00:08
- Comments on CC-3, CC-102, CC-103, CC-104 and CC-113 between 10/03 21:18 and 10/04 00:11

**Items to flag for the parent (facts, not conclusions):**
- Two comments are phrased as "Owner decision" and were written under the token identity (CC-113 at 14:42 and CC-3 at 18:58). Jira alone cannot show whether the owner said them or an assistant session recorded them. Check against the other session's transcript. CC-121's own correction states its ACs are "not owner-approved" and that "the owner asked for a story" while it was filed as a Bug, so the author/owner distinction is explicit there.
- The CC-3 comment of 18:55 lists "open owner decisions" (crosswalk scheduling, who refreshes `latest.json`/README, deterministic figure sentences for CC-121). Those remain open in Jira as of the pull.
- CC-121 (answer prose) is first in the sequence by owner decision, ahead of every URL ticket.
- The user's memory notes say tickets should not be added to an epic without asking. Jira shows six tickets created on 10/04 (CC-116 to CC-121). CC-116, CC-117, CC-119 and CC-121 landed in CC-3; CC-118 and CC-120 landed in CC-77. Whether the owner approved each placement is not recorded in Jira.
- Inference marks: in section 4, the code paths for CC-43 (`main.py`, `store.py`), CC-120 (a new script beside `scripts/run_grid.py`) and CC-42 are inferred from the ticket text plus file names. I confirmed the function names and line numbers for every other entry by grep.
