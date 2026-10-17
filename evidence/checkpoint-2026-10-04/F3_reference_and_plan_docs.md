# F3 — Reference and plan docs: provenance, claim audit, contradictions

Scope: read-only audit of the 7 files in `C:\Users\johnh\Dropbox\Census US\census_concierge_analysis\` against the repo (`docs/slices.md`, `.claude/PLAN.md`, `docs/ARCHITECTURE.md`, `budgets.toml`, `api/src`, `evals/`, `evidence/`). Jira was not queried (ticket statuses/descriptions below come from the plan docs, not verified). Sealed set never read. Labels: **V** = verified by me in the repo/run today; **I** = inference; **U** = unverified.

Phase-1 yardstick used throughout (memory `feedback_phase1_yardstick_url_is_product`, consolidated L7): sound/flexible/robust URL, nothing from model memory. Analytical agent = phase 2.

---

## 1. Per-document profile

| Doc (mtime 2026-10-04) | Purpose | Provenance | Horizon |
|---|---|---|---|
| `census_concierge_analysis.md` (10:39) | "What has worked" scoreboard summary | Session `4c0cf10d` (jsonl mtime 10:39, also named in `861b236c`) — **I** | Phase-1 status, **stale** |
| `census-data-api-user-guide.md` (09:41) | Markdown conversion of the Census Bureau *Data API User Guide*, May 21 2026 (L3); PDF sits beside it | Census Bureau (official); converted locally | Phase-1 mechanics (authoritative, vintage-bound examples) |
| `CENSUS_DISCUSSION.md` (08-08) | Q&A map of dataset categories, geography hierarchy, crosswalks | Predecessor `census_tool` repo (header L4 points at its `agent-first-grounded-planning.md`) | Predecessor mechanics map. **Never an architecture** (memory). Contains errors (see §3) |
| `census_concierge_agentic_architecture_insight.md` (11:29) | End-goal narrative: analytical agent, API URL as "intermediate artifact" | Author unknown; first referenced in `861b236c`. The checkpoint prompt's product-intent quote (prompt L48-50) is copied from it (insight L467, L471) — **V** | **Phase-2 end-goal** (direction only) |
| `census_tool_main_postmortem.md` (09:58) | Why predecessor `main` failed | Mentioned by a `census-tool` project session `6451f634` and `861b236c` — **I**: written from the census_tool side | Predecessor lessons |
| `revised_stories_phase1.md` (18:49) | 6 draft stories, proposals only | Session `861b236c` | Phase 1. **Marked SUPERSEDED** (L3) |
| `consolidated_plan_phase1.md` (19:32) | "Single source for the checkpoint review outcome" (L3): map, order, verification | Session `861b236c` = the "other session". **This file is its summary.** | Phase 1, current |

Claims that matter, per doc:

**analysis.md** — L14-20 scoreboard (retriever@10 0.90 at floor, selector@1 0.88, answered 0.74, api src 4296/4300); L22 CC-103 143/144 vs 138/144; L28 regex ratchet commit `b8692cb`; L34 p95 21.7s over ceiling; L37 trap tier weak (@1 0.21, @10 0.57); L38 README predates CC-103.

**user guide** — L30/L68 "up to 50 variables" (silent on whether `NAME`/`GEO_ID` count); L121, L130 `county (or part)` under a place is documented (supports CC-105 rewrite); L196-202 `group(TABLE)` returns all variables, exempt from 50 cap (supports CC-82); L322-328 `ucgid` is not available for every dataset; L355 `310M600US26420`, "M6 = 2020-vintage metro variant"; L383 must use the correct variant; L405-425 pseudo-geos; L451 "Max 50 per get (not for group())".

**CENSUS_DISCUSSION** — L4 "harness validates grounded IDs only"; L176-178 "hybrid" URL creation and per-variable vector collections (L180: "NOT commands"); L187-216 and L306-316 CBSA/MDIV/CSA/NECTA tokens and crosswalks, **including "counties within a given MSA" (L214, L308)**; L322-336 friendly-name → token map; L346-350 "no official JSON of valid geography levels".

**insight** — L7 "not primarily a Census Q&A chatbot"; L342-353 lists "an agent that generates Census API URLs" and "a RAG app for Census tables" as *too narrow*; L274-287 join/percent/aggregate/chart; L477-512 design "from the user's analytical request backward".

**postmortem** — L7 "~19k lines of source and 519 tests" on `main`; L25-26 decorative tests / fake that returns B01003 for any input; L34 `success` = HTTP call; L63 15-node graph; L73 no retrieval benchmark; L80-83 corpus structure (1,458 → 636 docs), @10≈90% vs @1≈42%, generative rerank only; L115 ~50% pass, nondeterministic; L147 option B = census-concierge slice 0; L158-159 compare at same `--repeat`, don't loosen guards.

**consolidated** — see §2.

---

## 2. Audit of `consolidated_plan_phase1.md` and `revised_stories_phase1.md`

### 2.1 Ticket map (consolidated L38-63, revised L3)

| Key | New or rewrite | Epic | Revised-stories id |
|---|---|---|---|
| CC-116 leakage invariant | NEW | CC-3 | not in draft |
| CC-117 table choice without phrase pins | NEW | CC-3 | not in draft |
| CC-118 never present URL over 50-var limit | NEW | CC-77 | Story 1 |
| CC-119 full parent chain | NEW | CC-3 | Story 4 |
| CC-120 URL breadth grid | NEW | CC-77 | Story 6 |
| CC-121 answer states figures not in data | NEW | CC-3 | not in draft |
| CC-82 `group()` first, chunk only if needed | rewrite | CC-77 child | Story 2 |
| CC-106 published level token, fail closed | rewrite | CC-3 | Story 3 |
| CC-105 `county (or part)` first | rewrite | CC-3 | Story 5 |
| CC-77 epic wording; CC-113 comment | edit | — | — |

6 new tickets: 4 land in CC-3 ("Slice 6 follow-ups", slices.md L19), 2 in CC-77. Docs `slices.md` lists none of CC-116..121; `.claude/PLAN.md` L44, L70-71 mention CC-116/118/120/121/82 only.

### 2.2 Claims checked (V = verified today)

| Claim (doc:line) | Result |
|---|---|
| api_src_loc 4396/4400; web 3349/3350 (consol. L26, L124) | **V** (`check_budgets.py` today). |
| doc_lines 1709/1800 (L26, L124) | **Stale: 1723 today** (+14; PR #100 doc text). |
| "one file at its 410 cap" (revised L27; consol. L115) | **Two files at ~410** by my line count: `geo.py`, `ask.py` (**I**: my count approximates `check_budgets`). |
| p95: top-level 19.207 stale; `demo.p95_latency_seconds` 21.701 (L24-25) | **V** in `evidence/latest.json`. CC-103 C1 `demo.json`: p95 17.149, long_tail answered 0.725, **n=120** (not the repeat-3 n=186 of the Jira comment, L132). |
| 42 `re.compile` in 11 files (L27) | **V**. But the ratchet (`check_invariants.py:272-349`) counts every `re.<fn>()` call site by AST: **63**. `vintages.py` alone has 13. |
| Seven pins at `vintages.py:23-29,97` (L29) | **V**. Introduced by CC-75 (`7c0cb61`, 09-18) and CC-76 (`7a0c245`, 09-19) as ticket fixes. |
| `rerank.py:34` Sibling rules (L29) | **V** (`api/src/retrieval/rerank.py:34`; path omitted in plan). |
| `build_url` no cap, `ok=True` over 50; for_spec gate (L31, L33) | **V**: `tools.py:269` (`if not variables`), `:299-302` (for/in gate), no column count before `get_cols`. |
| Resolver reaches 6 levels (L33) | **V**: `geo.py:28-44`, 15 aliases → 6 levels. |
| Override binding knows 7 summary levels (L70, L127) | **V**: `contract.py:22-30` `_AFF` = 010/040/050/140/150/160/860. |
| `ResultPlan.variables` rejects `group(...)` (L72) | **V**: `contract.py:176-180` rejects anything not ending `E` or outside `{table}_`. |
| Discovery URL hidden on success (L125) | **V**: `geo_list.py:218-224` URL only inside `RuntimeError`; returns names only. |
| No leakage check in `check_invariants.py` (L36) | **V** (grep: only `KEY_LEAK`, contextvars text). |
| Leakage scan found **one** location, `tools.py:39` (L128) | **Undercount.** My 4-gram re-run on visible evals finds `tools.py:39` **and** `retrieval/build.py:95` (comment quoting a golden question). Worse: 6 of the 7 pin regexes are phrases lifted from visible golden question texts (`evals/golden_questions.toml` L385 median family income, L429 income distribution, L441 cell phones, L502 households with a computer, L554 without health insurance, L571 median gross rent). A 4-word scan cannot see 2-3 word phrases, and `\bhouseholds` glues `\b` to the first token. **The prototype is blind to the largest leak by construction.** |
| 19 of 39 answers carry a number ≥100 not in data (L30) | **Partly V.** Scratchpad `prose_results2.json`: 40 questions, 20 answers had a ≥100 number, **19 of those 20** had ≥1 unmatched. The earlier run `prose_results.json`: **25/40** with unmatched. Checker excludes <100 and years 1900-2100; rows are flat string dicts so parsing is fine (`contract.py:361`). So the signal is strong, but "19" swings by 6 between two runs of the same script. Latest `prose_out.txt` is a failed run (`errors=40`). Contexts (q30: E=12634 and M=762 both unmatched with 1 row) look like real mismatches, but **U**: no human spot-check, and derived arithmetic would count as "unmatched". |
| CC-103 post-merge evidence `cc-103-e2e-post-*` absent (L133) | **V**: no `*e2e*` entries under `evidence/slice-6/`. |
| PR #100 merged `c6ef956` (L147) | **V**: `origin/main` top; local `main` is behind. |
| 4,396 vs budget log | **Discrepancy (new):** `b4aa5f0` changed `api_src_loc` **4300 → 4400** but its own log line says **4300 → 4340** ("measured 4332"). 60 lines of cap have no written reason; CC-103 then grew to 4396. Plan and analysis.md both treat 4400 as settled. |
| `analysis.md` api src 4296/4300 (L20) | Stale (pre-CC-103 raise). |
| 12 long_tail questions fail 3/3; "about 20 pts swing from one example" (L28, L116) | **U** (review agent / CC-103 report not re-read here). |
| All Jira statuses, comments, links (L100-105, L132) | **U**. |
| Live Census claims (50 cap, `group()`, hierarchy, ucgid) | **U** here (not re-run); consistent with official guide where the guide speaks (L196-202, L121, L130, L383). |

### 2.3 Scope vs the phase-1 yardstick

All six new tickets and three rewrites sit inside the yardstick:
- URL soundness: CC-118, CC-120. Flexibility: CC-82, CC-106, CC-119, CC-105. Phrase robustness + regex reduction: CC-117. No-model-memory: CC-121 (direct hit on the stated goal). Process guard: CC-116 (promised by CC-3 per consol. L36).
- Nothing recommends derived measures, joins, regression or analytical evals. `revised` L204-206 states this explicitly.
- Unfiled and in-scope per CLAUDE.md "URL is the product": the hidden geography-discovery call (consol. L125). Owner must pick epic; do not file (memory `feedback_epic_scope_discipline`).

### 2.4 Conflicts with CLAUDE.md / budgets

1. **Budget cannot hold.** 4 lines of headroom (V) against: CC-118 guard, CC-82 whole-table mode, CC-106 level validation, CC-119 chain, CC-105, CC-115 override binding (consol. L70), CC-121 figure rendering. Plan says "net-neutral or remove code" (revised L27; consol. L115). Order puts line-consuming CC-121/CC-118 (steps 1, 3) **before** the only line-freeing story CC-117 (step 4; removes `pinned_table` + 7 regexes + Sibling rules; **I**: amount unmeasured). Ask for per-story line estimates up front.
2. **CC-116 ↔ CC-117 loop (I).** CC-116 blocks CC-117 (L46, L103). A strict leakage invariant fails today on the 6 pins until CC-117 deletes them. CC-116 must ship as a baseline ratchet, or the dependency inverts.
3. **CC-121 "deterministic checker guards prose"** (L45). A number scan of LLM prose is a new regex unless written with `str`/`float` parsing; `check_no_new_regex` (`check_invariants.py:333-350`) fails the build otherwise. Also touches CLAUDE.md "Do not assert on LLM prose" if the check is tested on wording. "Code renders figures" is open decision L150.
4. **Tools/models/nodes OK:** tools 4/6, tool schemas 8/12, domain models 11/15, graph nodes 0/8, dependencies 8/25, so no cap blocks the stories except `api_src_loc` and `max_file_loc` (geo.py/ask.py at cap; Stories 3/4 touch `geo.py`: revised L112 says "replace, not add").
5. **ARCHITECTURE.md** must change in the same commit for CC-82 (whole-table representation) and CC-106 (level tokens), per CLAUDE.md. It currently says "CC-77 ... not yet built" (ARCHITECTURE L~135).
6. **p95 gate is blind.** CLAUDE.md says budgets are enforced; closes accepted over ceiling at slice 2 (24.5s, slices.md L38), slice 4 (L53), slice 5 (21.7s, L62), CC-103 (21.701, consol. L132). `check_budgets` passes on stale 19.207. Fix is CC-3 AC13 (PLAN.md L50-52), not yet landed.

### 2.5 Conflicts with memory rules

- *No ticket in an epic without asking*: satisfied by owner decision 3 (L12), but CC-3 now holds 4 breadth children that are not "follow-ups/reference resolution". Its close condition widened (L79) and it gates slices 7-8 (PLAN.md Rule 1). The memory warns about exactly this accumulation.
- *CC-11 capped*: untouched. *CC-77 phase-1*: consistent in consol. L7, PLAN.md L67-74, slices.md L22, ARCHITECTURE.
- *Regex last resort*: plan stories comply on paper; the 7 pins (CC-75/76) are the existing violation CC-117 targets.
- *Phase-1 yardstick*: consolidated L7 complies.

### 2.6 Internal tension

- `revised_stories` is circular: Story 3 depends on Story 4 (L100) and Story 4 on Story 3 (L126); its order (L199) runs Story 4 before 3. Consolidated L91 fixes it (CC-106 → CC-119 → CC-105). The body of `revised_stories` still reads as live below its header.
- Consolidated step 11 (L95) lists CC-42's blockers as CC-104/105/114; §9.5 (L149) adds CC-82/CC-120/CC-106/CC-119/CC-118. Order text not updated.
- `PLAN.md` L39-46 keeps the old order and labels itself "superseded in part"; PLAN.md L45 puts CC-106 "on its own timeline" while consolidated step 7 places it inside the gating chain. Two orders in one file.
- Plan L72 and L70 are verified problems (ResultPlan whole-table, override binding) but **no acceptance criteria were edited** ("nothing edited", L66). CC-106/CC-119/CC-82 can pass their own ACs while breaking the shipped plan strip (slice 4) for every new level. Highest-risk unhandled interaction.
- §3 L26 says 4396 "not re-measured"; §8 L124 says verified.

### 2.7 Tension with `docs/checkpoint_review.md` (12:22; predates both plans)

- Prompt L46-54 and L1193 define the target as the full analytical agent and ask "will remaining tickets deliver it". Memory: this exact framing was corrected twice ("you forgot that again"). The prompt has no phase gate.
- Prompt §3 table rows *Multi-API composition / Transformation / Visualization*: slices.md L40-42 (aggregation, `MOE_diff`, series legs) and L50-54 (`ChartSpec`) show limited versions exist; CC-107/108 plan separate legs with no join. Score as "exists (limited)" or "phase 2", not "missing".
- Prompt §7 `RequestPlan` (tables[], operations[], dependencies[], output_requirements[]) collides with CLAUDE.md "no abstraction before a second caller", `domain_models` cap 15, phase-2 foundations ("build nothing before slice 8"). The one phase-1 representation gap is whole-table/level token in `ResultPlan`.
- Prompt L275 treats "38k vs 4.3k" as like-for-like. Postmortem L7 says ~19k source lines + 519 tests (**I**: 38k ≈ source + tests; `api_src_loc` excludes tests).
- Prompt §1 names 3 docs; the three that decide the outcome (consolidated plan, insight, postmortem) are not named. CENSUS_DISCUSSION is cited as evidence; memory says mechanics only.
- Prompt §10 requires every open Jira ticket; repo docs lag Jira (no CC-116..121 in `slices.md`).

---

## 3. Contradictions between the seven documents, and which wins

Precedence I recommend: live-verified behavior and code > CLAUDE.md/budgets (rules) > consolidated plan (map) > Jira (status) > official guide (mechanics, vintage-bound) > end-goal/insight (direction) > Q&A transcripts.

| # | Topic | A says | B says | Winner |
|---|---|---|---|---|
| 1 | Product | insight L342-353: URL agent is "too narrow" | CLAUDE.md "URL is the product"; consol. L7 | Phase ≤8: CLAUDE.md + consolidated. Insight = phase-2 direction |
| 2 | Counties inside a metro area | CENSUS_DISCUSSION L214, L308 legal | live HTTP 400; `geography.json` `requires` (consol. L34; revised L22) | Live + `geography.json`. The error is in the Q&A doc, not the official guide (plan calls both "the guide") |
| 3 | ucgid variant | guide L355 `M6` = 2020 metro | live: Denver 2023 `310M700US19740` | Both right per vintage; guide example is vintage-bound. Plan's "M5" appears in **no** folder doc (grep) — unsourced |
| 4 | 50-variable cap | guide L30, L451 silent on `NAME`/`GEO_ID` | live: counted (consol. L31) | Live; guide incomplete, not wrong |
| 5 | `group()` | guide L198 exempt from cap | live confirms | Agree; supports CC-82 |
| 6 | `county (or part)` in place | guide L121, L130 | live NYC 5 counties | Agree; supports CC-105 |
| 7 | Retrieval design | CENSUS_DISCUSSION L178 per-variable vector collections | postmortem L80-83, L147 measured table-family corpus; repo 636 families | Postmortem + repo; L180 disclaims |
| 8 | Compute/transform | insight L274-287 core product | memory phase-2 foundations; slices.md L40-42 shipped aggregation/MOE_diff | slices.md for what exists; memory for what is deferred |
| 9 | Predecessor size | CLAUDE.md/budgets 38,184 lines/116 files | postmortem L7 ~19k source + 519 tests | Unresolved; use only like-for-like |
| 10 | Budget numbers | analysis.md 4296/4300 | live 4396/4400; budgets log 4340 | Live; fix the log mismatch |
| 11 | p95 | analysis.md L34 + README stale | consol. §8 L132-134 | Quote `demo.p95_latency_seconds`; plan flags 21.701 duplicate as unverified |
| 12 | Order | PLAN.md L39-46 | consolidated §5 | Consolidated; PLAN.md says "superseded in part" |

---

## 4. Drift-prevention measures (tied to findings above)

1. **Phase gate in `checkpoint_review.md`.** Open with the phase-1 yardstick, re-label rows Transformation/Multi-API/Visualization, list reference docs with horizon (§1 table). Prevents the third repeat of the documented framing error.
2. **Stamp every plan claim** with file:line, re-run command and sha. Numbers already moved (doc_lines 1709 → 1723; "one file" → two).
3. **Redesign the leakage detector before CC-116 merges:** 2-3 word content n-grams, strip regex metacharacters, include comments, baseline ratchet. Known hits: 6 pins, `tools.py:39`, `build.py:95`.
4. **Budget-log integrity invariant:** `budgets.toml` value must equal the last logged target. Today 4400 vs 4340.
5. **Spot-check 5 prose answers by hand** (q30, q36, q38 are candidates) and report both runs (25/40, 19/40) before CC-121 takes first position.
6. **Line estimates per story, CC-117's freed-line measurement first**; any raise stays a human commit.
7. **Add override/plan-strip and `ResultPlan` whole-table criteria** to CC-106, CC-119, CC-82 so "capability gained without losing slice-4 behavior" is testable.
8. **Epic hygiene note** on CC-3 (now 4 breadth children; gates slices 7-8) and a `slices.md` row for CC-116..121; owner decides whether to rename or split.

## 5. Unverified, for the parent

Jira text/status/links; CC-103 repeat-3 numbers (n=186); the "12 questions fail 3/3" list; live Census facts; that deleting pins (CC-117) keeps selector@1 ≥0.70; sealed-set overlaps.
