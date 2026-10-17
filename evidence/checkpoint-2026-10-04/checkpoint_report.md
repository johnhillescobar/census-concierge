# Census Concierge — Checkpoint Report: drift evaluation and drift measures

*2026-10-04. Independent review under the role in `docs/checkpoint_review.md`. This report was read-only when written; after the owner chose A + B and D1(b), the work is recorded in `execution_ledger.md` (scope, results, what is still owed) with `gate1.txt` and `gate2.txt`.
Backing evidence is in this folder (`F1`–`F6`, one per fork). Numbers marked **[V]** I re-checked myself; everything else is cited to a fork report.*

## 0. Bottom line

**Target:** phase 1 (through slice 8) succeeds when the system produces *sound, flexible, robust Census URLs and no value comes from model memory*. The analytical agent is phase 2 — direction, not a gap (memory `feedback_phase1_yardstick_url_is_product`, corrected twice already).

**Direct answer: converging, with leaks you cannot currently see.**

- *Right direction:* CC-103 is a real structural gain (model composes, code validates); budgets held (4.4k lines vs the predecessor's 38k); the 10-04 tickets (CC-82/106/118/119/120/121) aim at real gaps.
- *Why I will not certify it:* (1) the instruments can be tuned and nothing mechanical detects it; (2) the headline metric (`answered`) does not test the phase-1 promise; (3) question interpretation still lives in 51 prose-regex sites that the model's structured output was layered over, not swapped in for.

**Ultimate question — "ship the remaining tickets exactly as written, do we get phase-1 Census Concierge?"**
*As written: no. With five amendments (§8): yes.* The five: (1) ACs that protect the plan strip and `ResultPlan`; (2) a per-story line plan; (3) a leakage check that can see the real leaks; (4) a delete-count on the tickets that touch prose regexes; (5) a hand-check of CC-121's evidence before it goes first. Plus one sequencing decision (D1) that rests on a truncated message.

### Terms that are easy to confuse here

| Term | Means | Not |
|---|---|---|
| "sealed set" | owner-held held-out eval; only aggregates are in the repo | "seal examples" — no such artifact exists in the repo (F1 §3, F6 §1) |
| "context examples" | closest real thing: the one-shot format example in the split prompt (`finish.py:26`) | an A/B arm; the real A/B was CC-103 option A vs B, then C0/C1/C2 |
| p95, three of them | top-level key **19.207** (stale) · `demo.p95_latency_seconds` **21.701** (all tiers, n=186) · CC-103's **17.15** (long_tail only, n=120) | interchangeable |
| regex count | **64** `re.*` call sites by the repo's AST counter (63 by my grep) · 42 `re.compile` · 51 of the 64 run over question prose | one number |
| "overarching goal" doc | most likely `census_concierge_agentic_architecture_insight.md` | `census_concierge_analysis.md` (a 42-line status note) — the question was asked at 17:46Z and never answered (D6) |
| CC-13 vs CC-113 | CC-13 is an unrelated Done story; CC-113 is the latency research | |

## 1. Drift scorecard — baseline as of today

Re-measure these at the same `--repeat` after each ticket. Direction is what matters; thresholds are yours to set.

| Metric | Today | Want | Source |
|---|---|---|---|
| `re.*` call sites in `api/src` | 64 (32 on 09-16 → 66 peak 09-25 → 64 since 09-26) | ↓ only | F5 §0.1 |
| …of which run over question prose | 51 (80%) | ↓ | F5 §3.2 |
| finish redo-gates reading the question : reading the loop's result | 4 : 1 | 0 : n | F5 §0.3 |
| eval phrasing inside `api/src` | 6 pin regexes + `tools.py:39` + `build.py:95` + rerank "Sibling rules" (topic-level) | 0 | F3 §2.2, F6 §1 **[V pins]** |
| answers with figures not in fetched rows | 19–25 of 40 (two runs); **magnitude not hand-checked** | 0 | F3 §2.2 |
| demo URLs requesting exactly one estimate | 171 of 177 | report | F5 §0.6 |
| `demo.p95_latency_seconds` vs ceiling | 21.701 vs 20.0 on main; post-CC-103 runs 21.701 and **18.928** on the *same build* | median of ≥3 runs | **[V]** below |
| slowest single trial | 648s (pre-CC-103) · 820s (post, run 2) — p95 hides both | report max | **[V]** |
| headroom: `api_src_loc` / `max_file_loc` / `web_src_loc` | 4 / 0 / 1 lines | n/a | F5 §5 |
| budget log vs file | log says 4340, file says 4400 (`b4aa5f0`) — 60 lines unexplained | equal | **[V]** |
| anti-overfit controls that are scripts, not prose | 0 of 4 (leakage, grid floor, gap ceiling, multi-turn floors) | 4 of 4 | F6 §3 |
| untouched confirmation sets | 0 (sealed B and C not yet created; sealed A used to pick A-vs-B and C1-vs-C0) | ≥1 | F6 §1 |
| CC-3 open children inside its stated scope | 5 of 16 | all | F4 §2 |
| open tickets blocking CC-42 (multi-turn eval) | 8 | owner's call (D1) | F4 §4 |
| review-session drift complaints from you | 3 (19:47, 00:13, 00:31Z) | 0 | F2 §1 |

## 2. Capability map (checkpoint §3, phase-1 yardstick)

| Capability | Current state | Evidence | Confidence | Major weakness |
|---|---|---|---|---|
| Table retrieval | works; @10 0.90 (36/40), exactly at floor | `latest.json` | High (SE ≈4.7 pts) | trap tier @10 only 0.57; one lost question fails the build |
| Table selection | 0.875 in-sample; 5-run mean 0.855; 0.85 post-CC-103 | `prompt-tuning-sibling.json` | Medium | Sibling rules fitted to q11/q21/q41 (the +7.5 *is* those 3 flips); 6 pins bypass the selector, so `selector_at_1` does not measure the demo path |
| Variable resolution | model picks IDs without seeing labels; defaults `_001E` | `tools.py:179-228`, `run_demo.py:124` | Medium | **unscored**: q04 "poverty rate" fetched the universe total and counted as answered |
| Geography resolution | 6 of 43 published levels; multi-parent 143/144 visible, 108/114 held-out | CC-103 evidence | Medium-High | 51 prose-regex sites; q04/q14/q26 wrong level 3/3 |
| API planning | no explicit plan object; `ResultPlan` is built *after* execution | `contract.py:151,186` | High | the model's interpretation is not carried to the code that needs it (§4 RC-A) |
| Multi-API composition | general Cartesian fan-out (geographies × years, one table); per-pattern code for dependent cases | `fetch.py:344` | High | no `group()`, no multi-variable-group; `build_url` returns `ok=True` above the 50-variable cap |
| API generation | `CensusURL` redaction solid; gated on pool, availability matrix, resolved geography | `tools.py:230-310` | High | `for_spec` only from the resolver; hidden NAME-listing call never shown |
| Data retrieval | `http_ok` 1.0 everywhere; `http_ok` and `answered` kept separate | `latest.json` | High | — |
| Transformation | comparisons, MOE_diff, combined row — all **keyword-triggered** (`_COMPARE`, `_COMBINE`, `_DERIVED`) | `compare.py:14`, `guards.py:30,37` | Medium | phase-2 compute must be model-invoked typed tools; extending these patterns would repeat the drift |
| Visualization | validated `ChartSpec`, Vega-Lite render | `test_chart.py` (19) | Medium-High | `web_src_loc` 3349/3350 |
| Provenance | URL + MOE + GEOID + universe + alternatives on every answer | `test_ask_loop.py` (6 named tests) | High for URLs | NAME-listing calls absent; answer prose unverified |

## 3. Drift findings, ranked

### Critical — threatens the phase-1 promise

**C1. "No data from model memory" is unmeasured, and the signal says it is violated.** 19–25 of 40 visible long-tail answers state a figure of 100+ that is not in the fetched rows (F3 §2.2); no test compares prose to rows; variable choice is unscored. So `answered 0.74` cannot certify what phase 1 exists to guarantee. *Caveats:* the count swung 19→25 between two runs of the same script, nobody hand-checked an answer, and derived arithmetic would register as "unmatched". CC-121 is the right ticket; its evidence is not yet safe enough to put it first.

**C2. The instruments can be tuned, and nothing mechanical would notice.** Six of seven pin regexes (`vintages.py:23-29`) are phrases from visible golden questions **[V]**, and they inject tables ahead of retrieval; the selector prompt carries rules named for three golden misses. CC-3 AC8 promised a leakage invariant before CC-103; it was never built (F3 §2.2). The CC-116 prototype scans 4-word overlaps, so it cannot see 2–3-word phrases or regex literals — it finds one leak where there are at least nine. This is the "tuning to the instrument" trap in `CLAUDE.md`, already realised once.

### High — substantial future rework

**H1. Regex plateaued rather than shrank; the model's output was layered on top of it.** 64 call sites, +62% api lines since 09-16. `finish.py:171` serializes the model's `parents` back into prose so `WILDCARD`/`WITHIN` can re-parse it, and `geo.py:213` honours `parents` only if those regexes also match. CC-100/101/103 each added a model-composed path and removed almost no inference code (regex 66→64). The ratchet freezes the count; nothing rewards deletion. `CLAUDE.md` says "gate on the loop's own result" — 4 of 5 gates read the question. `find_state`, `place_token`, `detect_level`, `_LISTING`, `_BY_COUNTY`, `_TRACT_VS` from the 09-27 audit all still exist.

**H2. Zero line headroom, and the order consumes lines before it frees them.** 4 / 0 / 1 lines against a plan that adds a cap guard, `group()` mode, level validation, a parent chain, override binding, and figure rendering. The only line-freeing story (CC-117: deletes `pinned_table`, 7 regexes, Sibling rules) is step 4; CC-121 and CC-118 (steps 1 and 3) consume first. No story has a line estimate. Expect a budget-raise request or compressed code unless this is planned.

**H3. Unedited ACs let tickets pass while breaking slice 4.** `bind_override_geographies` knows 7 summary levels; `ResultPlan.variables` rejects `group(...)` (`contract.py:22-54`, `:176-180`; both verified by F3). CC-106/119/82 can meet their own ACs while the plan strip and alternative-table click fail for every new level. CC-115 (422 on alternative click after a listing) is the live symptom. The consolidated plan lists this as "nothing edited".

**H4. Backlog structure has drifted from its containers.** CC-3 ("follow-ups and reference resolution") has 16 open children; 5 match its scope, 11 are single-turn URL/geography/eval/prose work. CC-42 is blocked by 8 open tickets, so the epic's actual deliverable (follow-ups) is last. CC-77 holds two tickets (CC-118, CC-120) that are not crosswalk or whole-table work, and CC-82/CC-120 now block a CC-3 ticket. The Objectives text was not updated; the change lives in comments.

**H5. A truncated message became a decision, and is now in main and Jira.** "e multi-turn chain waits for the breadth stories" (23:58Z) produced 2 Blocks links (CC-82→CC-42, CC-120→CC-42), CC-3 comment 10722, and the sentence "the multi-turn chain waits for them" in main's `.claude/PLAN.md` **[V]**. Plan §9.5 records it as "Decided". It looks like a fragment of the assistant's own list (F2 §4-B3). Separately, the plan's own text (L72) says CC-82's real dependency is CC-43/107/108 (plan representation), not CC-42 (the eval) — so even if you meant it, the link is aimed at the wrong ticket.

**H6. The review instrument has no phase gate.** `checkpoint_review.md` §1–§2 asserts the analytical agent as "the current product intent", with no phase marker and no instruction to re-read `CLAUDE.md` or memory first. The execution session obeyed it, gave "No" twice (17:28, 17:31Z), and was corrected at 17:45:48Z; the doc was never edited, so the next reader repeats it. The §1 source list names the wrong file, omits the insight doc and the postmortem, and cites `CENSUS_DISCUSSION` as evidence although memory says it is Census-mechanics only.

### Medium

- **M1. CC-103's win is real but narrower than it looks.** Visible grid = 16 distinct cells of one synthetic template family; held-out shares place sets with it (phrasing generalization, not new places); C1 vs C0 held-out intervals overlap (Wilson [89.0,97.6] vs [78.4,91.2]); sealed A was a selection set twice; `answered` is flat (0.725 before and after) so the golden scoreboard cannot see it. Churn the aggregate hides: q38 3/3→1/3 (table picks), q09, q36. (F6 §1–2)
- **M2. p95 is a weak gate in three ways.** It reads a stale key (`make check` passes on 19.207); over-ceiling closes were accepted at slice 2 (24.5s), 4, 5 (21.7s), and CC-103; and two runs of the *same build* gave 21.701 and 18.928, so a 20s ceiling sits inside the noise band **[V]**. p95 also hides a 648s and an 820s trial (CC-102 owns the O(rows²) path). *Resolved open item:* the plan's "p95 anomaly" (post-CC-103 run 1 = CC-38's 21.701) is not a carried-over value — I recomputed p95 from each run's own 186 trials and 0 trial latencies match; it is a coincidence **[V]**.
- **M3. Unbudgeted prompts.** `system_prompt_tokens` counts 977 of 1200, but `rerank.PROMPT` (≈297) and `_SPLIT_PARENTS` (≈149) add ≈446 outside the counter; there are 3 LLM call sites; `plan_split` runs on every `/ask` without an override and `finish_tools` can wait up to 6s for it.
- **M4. Provenance gap.** The NAME-listing Census call that turns "Queens" into `county:081 state:36` is never shown (`geo_list.py:218-224`). No ticket; per memory the owner picks the epic.
- **M5. Evidence not where the rules say.** CC-103's post-merge E2E (two all-tier runs, grid, `latest.json` refresh) exists only on local branch `evidence/cc-103-post-merge` (commit `3036cc0`, no remote ref contains it) **[V]** — Jira cites those files and main does not have them. (This corrects F3/F6, which say the files are missing / no post-CC-103 all-tier run exists: runs 1 and 2 are there — p95 21.701 / 18.928, long-tail answered 0.733 / 0.750, selector@1 0.85, retriever@10 0.90, prompt `c0e048fc86b5` — so the README and main's `latest.json` (0.742 / 0.875 / 21.701) are stale, not unmeasured.) The consolidated plan, story drafts and scripts sit in Dropbox/scratchpad; Jira comments cite a file now marked SUPERSEDED; `.claude/PLAN.md` now carries Jira sequencing (a second source of truth; `CLAUDE.md`: PLAN.md is "a close pointer").
- **M6. No Gate 1 transcript for slice 6**; the mutation-check claim is only in commit `90feb4b` and the report; CC-100's 30-question comparison list lives in Jira comment 10602 and is not runnable from the repo.
- **M7. Write authority is blurred.** CC-121 was filed as a Bug under CC-3 (you said "story"), placement and thresholds not confirmed; "Owner decision" comments on CC-113 (p95 accepted) and CC-3 were written under the token identity, so Jira cannot show who decided. Authorized: CC-116–120 placement and the CC-82/105/106 rewrites (18:49Z, 23:10Z).

### Low

Stale docs: `ARCHITECTURE.md` header ("2026-09-25, slice 4 in progress"); `slices.md` shows CC-3 To Do (Jira: In Progress); `PLAN.md` cites CC-48 for spend cap/tracing (Jira: CC-111/CC-112); CC-115/117/119 are named in no doc. The "38k vs 4.3k" comparison is not like-for-like (postmortem says ~19k source + 519 tests; `api_src_loc` excludes tests). The regex ratchet already counted `import re as X` and `from re import fn` (an earlier version of this report said otherwise; corrected); it did not count `import regex` or `from re import *` (now counted, see the ledger) and cannot count keyword/substring heuristics over question text.

## 4. Root causes

**RC-A — a second interpreter.** *Why do new phrasings keep breaking?* The question is interpreted twice: by the model (tool args) and by regexes over the question string. *Why twice?* Each fix (CC-100/101/103) added the model path beside the regex, gated by it. *Why was the regex not deleted?* Each AC was "this phrasing family passes"; the ratchet only blocks growth; deleting risks other goldens and there is no grid floor to say it didn't. *Root:* the process rewards additions that pass a visible instrument and never rewards deletions — and the model's interpretation is not carried as data to the consumers that need it (`geo_status` is an untyped dict; `parents` becomes prose).

**RC-B — rules live in prose, not in gates.** *Why can the instrument be tuned?* The leakage invariant, grid floor, gap ceiling, and multi-turn floors are in `CLAUDE.md`, Jira ACs and memory. *Why does that fail?* Memory already records it: "Memory alone did not stop me" (`feedback_llm_over_regex`). *Root:* anti-overfit discipline depends on the author remembering; only the regex ratchet and LOC budgets are scripts.

**RC-C — the review session drifted for process reasons.** One 7-hour, high-write session; a prompt that encoded the end-goal without a phase; no write-ledger for outward actions; fragments treated as decisions; oscillation between acting (complaints 1, 2) and asking (complaint 3); the over-correction made unratified "standing defaults" including dropping the report sections (F2 §4-B4). *Root:* no phase gate, no write boundary, no single plan file in `evidence/`.

## 5. Agentic capability gap (phase 1 only)

1. **Carry the model's structured interpretation to every consumer** (`level`, `places`, `parents`, `dataset`, `years`) and stop re-deriving it from the question. This is the only checkpoint §8 representation with observed-failure support (F5 §2). It is *not* a `RequestPlan`/`UserIntent` schema family — `CLAUDE.md` forbids an abstraction before a second caller, and `domain_models` is 11/15.
2. **Every number the user sees traces to a fetched row** (figure provenance). This is the phase-1 form of "no data from model memory" and has no mechanism today.
3. **URL-space breadth** (published levels, `group()`, the 50-variable cap, time settings). Already ticketed (CC-82/106/118/119/120).

Phase-2 constraints (single-table `ExecutionRecord`, string-typed rows, keyword-triggered compute, `/turns` passing no history) are recorded in F5 §7. They are decided and parked (`project_phase2_foundations`); I am not proposing tickets for them.

## 6. What is working — preserve it

| Capability | Evidence | Protected by | Open work that could break it |
|---|---|---|---|
| Long-tail retrieval @10 ≥ 0.90 | 0.90 (36/40), at floor | `test_index.py` (6, incl. the different-questions fake-retriever trap); floor is live-only (`make eval`) | CC-77 index changes, any metadata rebuild |
| Selector @1 ≥ 0.70 | 0.85–0.875 | `test_rerank.py` (2); **nothing in `make check` protects accuracy** | CC-117 (removes pins), any rerank prompt edit |
| Geography-level answering | CC-114 scorer, golden level | `test_ask_tools.py` (102), `test_ask_loop.py` (56) | CC-104/105/106/119 |
| Multi-parent listings (CC-103) | 143/144 visible, 108/114 held-out | `test_finish.py` (38), `test_grid_scorer.py` (12), `test_grid_labels.py` (5) | CC-104, CC-105, any prompt/tool-text edit. **No grid floor — a regression passes `make check` and `make demo`** |
| Multi-place comparisons (CC-100) | 30-question list in Jira 10602 | 2 springfield tests | CC-104/105/106 — list not runnable from repo |
| MOE / GEOID / universe / alternatives | unit-level | 6 named `test_ask_loop.py` tests + `test_pair_margins_adds_m_beside_every_e` | CC-82 `group()` (24 E+M pairs max via `build_url`) |
| URL redaction (`CensusURL`) | invariant + tests | `test_invariants.py`, `check_census_key_not_in_artifacts` | any new URL builder (CC-82/118) |
| Chart behavior | web + api | `test_chart.py` (19), `chart.test.tsx` | any chart fix needs a budget raise (web 3349/3350) |
| Conversation persistence | slice-5 Gate 1 | `test_store.py` (17), `test_conversation_routes.py` (14) | CC-43 |
| CC-103 repair call + v4 prompt | A beat B by ~21 pts held-out; C2 (call off) 1/144 | experiment report | do not replace until a replacement beats it at the same `--repeat` |

Process wins to keep: pre-registered selection rules (CC-103 A/B), CC-114's commit-before-outcomes scorer rule, the regex ratchet, budgets as hard gates, evidence per ticket.

## 7. What is not working — by checkpoint §9 category

| Cat | Failure | Evidence |
|---|---|---|
| A Retrieval | 4/40 long-tail out of pool (q17, q18, q20, q34); trap tier @10 0.57 | F6 §3 |
| B Semantic | variable choice unscored; prose figures unverified | F5 §0.6, F3 §2.2 |
| C Geography | wrong level q04/q14/q26 3/3; q11 (CBSA unreachable → CC-106) | CC-114 classification: 10 of 18 mismatches are `pipeline_wrong` |
| D/E Planning, composition | one table only; no `group()`; dependent calls only via per-pattern code | F5 §4 |
| F API construction | `build_url` `ok=True` above 50 variables → HTTP 400 at fetch (live, F2) | CC-118 |
| G Execution | none material (`http_ok` 1.0); 648s/820s tail trials (CC-102) | **[V]** |
| H/I Transform, presentation | keyword-gated computations; prose figures; hidden listing call | F5 §0.11 |
| J Evaluation | scorer checks table + level only; CC-114: 8 of 18 mismatches were not pipeline faults; q10/q23 mis-specified | F6 §3 |

## 8. Recommendations and Jira realignment

**Must change** (evidence-backed): make the gates mechanical (§9); add the plan-strip/`ResultPlan` ACs; put a line plan on every story and measure CC-117's freed lines first; hand-check CC-121's evidence; resolve D1 and D5.
**Should change:** carry `level`/`parents`/`places` as data and delete the matching regexes in the same PR (the vehicle is CC-104/105/117 — no new ticket); ratchet regex *down*; add a variable-choice check to the grid/demo scorer; push `evidence/cc-103-post-merge`; move plan docs into `evidence/`; return `.claude/PLAN.md` to a pointer.
**Could change:** type `geo_status` (3 callers exist, so it clears the second-caller rule) — only if it nets lines inside CC-104; bring `rerank.PROMPT`/`_SPLIT_PARENTS` under the token counter.
**Do not change:** the hand-rolled loop and 4 tools; the CC-103 repair call and v4 prompt; `CensusURL`; budgets (no raise); retrieval pipeline; persistence. **Do not** add `RequestPlan`/`UserIntent` schemas, derived-measure or regression tools, a clarification subsystem, or ticket the phase-2 constraints.

**Jira realignment** — *proposals only; nothing written.* Existing tickets get **AC amendments**, not rewrites: the 10-04 rewrites were approved by you and the least-disruptive change is additive.

| Ticket | Assessment | Action | Amendment / reason |
|---|---|---|---|
| CC-114 | Aligned (scorer + classification) | KEEP | Remove the CC-114→CC-104 *Blocks* link (10-02 comment said "can run alongside"; D2) |
| CC-104 | Aligned; vehicle for RC-A | MODIFY | AC: `level`/`parents` carried as data; **net `re.*` call sites in `api/src` decrease by ≥ N** (N from the F5 §3.2 `remove` rows it touches); accept published level tokens from CC-106 |
| CC-106 | Aligned | MODIFY | AC: every newly reachable level works in plan strip + alternative click; mutation-checked test; no `_LEVELS` growth |
| CC-119 | Aligned | MODIFY | same plan-strip AC; keep CC-106→CC-119→CC-105 order |
| CC-105 | Aligned | MODIFY | AC: single-county place unaffected (already stated); delete `parents`-gating regexes it supersedes |
| CC-115 | Symptom of H3 | MERGE-INTO-AC | its recommended fix (bind override from `for_spec`/`in_spec`) becomes a CC-106/119 AC; keep the ticket as the regression test |
| CC-82 | Aligned | MODIFY | AC: `ResultPlan` has a whole-table form and the plan strip renders it; dependency is **CC-43/107/108**, not CC-42 (D1) |
| CC-118 | Aligned | KEEP | AC: states its line delta; guard lives in `build_url` |
| CC-116 | Aligned, prototype too weak | MODIFY | ship as a **baseline ratchet**: 2–3-word content n-grams over literals, comments, regex sources; baseline = the known hits; also add budget-log integrity (same file). Removes the CC-116↔CC-117 loop |
| CC-117 | Aligned; the only line-freeing story | MODIFY | measure freed lines first; AC: `selector_at_1` measured *without* pins; regex count −7; move earlier in the order |
| CC-120 | Aligned | MODIFY | add a variable-choice cell (expected estimate/group vs fetched) and report max latency; baseline recorded before any URL change |
| CC-121 | Aligned; evidence unsafe | MODIFY | first: hand-check 5 answers (q30, q36, q38 are candidates) and report both runs; then take position 1. Thresholds stay labelled "author proposal" until you approve (D3) |
| CC-102 | Aligned (700–820s tail) | KEEP | add max-latency to its close evidence |
| CC-113 | Research | KEEP | AC: report median of ≥3 runs and the max; ceiling unchanged |
| CC-42 | Over-gated | MODIFY | per D1 |
| CC-43/107/108/39 | Aligned, premature until CC-42 | BLOCK (as now) | CC-43 also needs CC-82's plan form |
| CC-3 | Container drifted | MODIFY | D4: update Objectives to say what is inside |
| CC-77 children CC-78…81, 83…86 | Aligned, unscheduled | KEEP | schedule is an owner decision (plan §9.2) |
| CC-7, CC-10 and children | Aligned, premature | KEEP | no change; fix `PLAN.md` key CC-48 → CC-111/CC-112 |

**Test cases for the amended tickets** (checkpoint §19 minimum, one line each):

| Ticket | Happy | Edge | Novel combination | Regression guard |
|---|---|---|---|---|
| CC-106/119 | CBSA level returns rows | published level, no data → fails closed with alternatives | metro division needs its metro area | plan-strip override works for all 7 old levels + each new one |
| CC-82 | `group(B15003)` for tracts in one county | `group()` unsupported for a geography → chunking path | two vintages × whole table | `ResultPlan` accepts E-only plans unchanged |
| CC-117 | median gross rent question selects via retrieval | table not in pool → alternatives shown | rephrased rent question never seen in eval | `selector_at_1` ≥ floor with pins removed |
| CC-116 | injected eval phrase fails the build | 2-word phrase inside a regex literal | phrase in a comment | baseline entries do not fail; new ones do |
| CC-104/105 | model `level` trusted | model `level` absent → fail-closed, not regex fallback | "boroughs"/"cities" phrasing outside the grid | CC-100 30-question list; CC-103 grid ≥ 143/144 |
| CC-121 | every number in prose is in rows | rounded/derived figure | question about an unfetched year | MOE/GEOID/universe tests unchanged |

**Candidates I am *not* proposing to file** (your call; each fits an existing ticket): the NAME-listing call in provenance (fits CC-82/CC-120 or a note on CC-3); moving CC-100's 30-question list into `evals/` (fits CC-42/CC-120).

### Recommended implementation order (dependency-aware)

0. **Fix the ruler** before measuring anything: budget-log line (D5), p95 gate reads `demo.p95_latency_seconds` (CC-3 AC13), CC-116 as baseline ratchet, push `evidence/cc-103-post-merge`. *Why first:* every later "no regression" claim is judged by these.
1. **CC-120 baseline** (grid + variable-choice + max latency), recorded before any URL change.
2. **CC-117** (frees lines; unpins the selector) — *before* the line consumers.
3. **CC-121** after the 5-answer hand-check (can start in parallel with 1–2; it is independent of URL changes).
4. **CC-118**, then **CC-114 → CC-104** (they can run alongside), then **CC-106 → CC-119 → CC-105** — each with its regex-delete target and plan-strip AC.
5. **CC-82** after its pre-flight (it needs CC-118 and the `ResultPlan` whole-table form).
6. **CC-102, CC-115** (independent), **CC-113** research.
7. **CC-42 → CC-43 → CC-107/108 → CC-39** per D1; then slices 7–8.

## 9. Drift-prevention measures — three paths

| Path | What | Cost | Buys | Risk |
|---|---|---|---|---|
| **A. Mechanize the gates** (recommended) | In `scripts/`, not `api/src` (no line cost): p95 gate reads the demo key and a **waiver log** for any over-ceiling close; budget-log integrity (file value must equal last logged target); CC-116 baseline leakage ratchet; **ratchet-down** for `re.*` (the existing ratchet blocks any rise; this adds the printed count and delta, and counts `import regex` / `from re import *`); a **close card** in every ticket close comment | 1–2 days incl. mutation-checked tests | converts RC-B from prose to gates; makes deletion rewarded | n-gram false positives → baseline file; needs your OK to touch `check_invariants.py` / `budgets.toml` |
| **B. Process only** | Phase gate + re-read-first line at the top of `checkpoint_review.md`; session rules (below) | hours | stops RC-C | does nothing for code drift |
| **C. A + eval honesty** | A, plus prose-figure rate and variable-choice in `make demo`, pre-registered sealed B and C, grid floor in `budgets.toml` | 3–5 days; sealed sets are owner-held | closes the C1/C2 measurement holes | needs your time for sealed sets; new floors need a baseline you choose |

**My recommendation: A + B now; fold C's pieces into CC-120 and CC-121 instead of new tickets.**

**Close card** (6 numbers, same `--repeat`, in every close comment; no new file): golden long_tail answered · grid visible / held-out · retriever@10 / selector@1 · `demo.p95_latency_seconds` **and** max · `re.*` count delta · api LOC delta.

**Session rules for long reviews** (these address RC-C; proposed wording, ≤ 6 lines in the `run-slice` skill):
1. Open with the phase yardstick and re-read `CLAUDE.md` + memory before framing.
2. One plan file in `evidence/` is the only place the plan lives; outward writes (Jira, repo) appear in it before they happen, batched, with one "yes" per batch.
3. Never act on a fragment: if a message is truncated or reads as a quote of my own list, read-only work continues; writes wait for a full sentence.
4. Decisions carry a tag — `owner` (you said it) or `default` (revertible) — and defaults are never written into Jira as "Owner decision".
5. One question batch per phase, each with my default; otherwise proceed.
6. Nothing outward after a drift complaint until the plan file is reconciled.

**Fixes to `checkpoint_review.md`** (I have not edited your file): add the phase gate and yardstick after §1; replace the §1 list with the documents that matter and their horizon (insight = end-goal, `consolidated_plan_phase1` = current map, `CENSUS_DISCUSSION` = mechanics only); replace "context examples / seal examples" in §6 with "CC-103 options A/B and C0/C1/C2 in `evidence/slice-6/`"; mark §7–§8 representations "only where an observed failure justifies, and `CLAUDE.md` abstraction rule applies"; replace §13's regex stance with `CLAUDE.md`'s; state that the sealed set is never read (aggregates only); cut §14–§15/§21–§22 to one phase-1 novel-combination scenario; add "answer the ultimate question in one sentence, per phase".

## 10. Decisions for you

Only **D1** and **D5** block safe work. Nothing changes if you say nothing.

| # | Decision | Options | My default |
|---|---|---|---|
| **D1** | Does the multi-turn chain wait for breadth? (unconfirmed fragment, in main + Jira) | **(a)** confirm as is — 8 blockers on CC-42, follow-ups land last, baseline measured on the settled URL layer · **(b)** gate CC-42 only by the geography chain (CC-114→104→106→119→105) and CC-120's baseline, and aim CC-82 at CC-43 instead — slice 6 closes sooner, multi-turn baseline may need re-anchoring (AC9 allows it) · **(c)** revert to the 10-02 order | **(b)** — it matches plan L72 |
| **D2** | CC-114→CC-104 link | remove in Jira UI (tools can't) / keep | remove |
| **D3** | CC-121: Bug or Story; placement; thresholds; "code renders figures" acceptable? | keep Bug in CC-3 / retitle Story / new epic | hand-check first, then decide |
| **D4** | CC-3 container | **(a)** update Objectives to match contents · **(b)** split off a "URL breadth & soundness" epic and move 11 children (clean, ~14 Jira edits, changes the close rule that gates slices 7–8) · **(c)** leave | **(a)** now; revisit when CC-42 starts |
| **D5** | Budget log vs file (60 lines) | append a corrective log line to `budgets.toml` (your commit; the true cap is 4400 — usage is 4396 so 4340 cannot hold) | append |
| D6 | Which file is the "overarching goal" doc | insight doc / analysis doc | insight doc |
| D7 | Keep the dropped report sections dropped | yes (this report covers the ones that matter in phase 1) / restore | keep dropped |
| D8 | Commit `evidence/checkpoint-2026-10-04/` and the `checkpoint_review.md` edits | now / later | later |

## 11. Final product-alignment test (phase 1)

**Question** (novel; not in any eval): *"Show educational attainment — the full table — with margins of error for every tract in Denver, 2019 vs 2023."* It tests multiple variables, tract granularity, two time settings and the 50-variable cap together: B15003 has 25 estimates, so 25 E + 25 M + `NAME` + `GEO_ID` = 52 > 50.

| Step | Intended phase-1 behavior | Current behavior (evidence) | Closes with |
|---|---|---|---|
| Interpretation | model emits table, `level=tract`, parent Denver, years, "whole table" as fields | no intent object; `level` falls back to `detect_level` regex (`geo.py:273,283`); the analogous core q04 (tracts in Detroit) fetched `place` 3/3 | CC-114, CC-104 |
| Table | B15003 via retrieval + selector, alternatives shown | likely fine (not pinned) *(inference)* | — |
| Geography | tract wildcard in the validated parent chain | works for one county; multi-county or other levels hit H1/H3 | CC-105/106/119 |
| URL plan | `group(B15003)` with `for`/`in` — one URL per vintage | `build_url` rejects `group()`; defaults to `_001E`; 171/177 demo URLs request one estimate; `ok=True` above 50 variables, then HTTP 400 at fetch (F2 live test) | CC-118, CC-82 |
| Time | two vintages; windows 2015–19 and 2019–23 overlap, so warn | fan-out over years exists (`fetch.py:344`) | — |
| Execute / provenance | both URLs shown, key redacted, GEOID + MOE columns | URL/GEOID/MOE rendering works | — |
| Answer | figures rendered from rows or checked against them | model prose passes through unchecked | CC-121 |
| Score | counts only if variables match the request | scorer checks table + level only, so a one-variable answer scores "answered" | CC-120 |

*I did not run this question (no live-API runs in this review); the "current" column is from the fork evidence cited and is marked where it is inference.*
