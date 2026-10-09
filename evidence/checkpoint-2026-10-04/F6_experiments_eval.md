# F6 — Experiments, evaluation instrument, evidence (read-only audit)

Yardstick: phase 1 = sound, flexible, robust Census URL generation; nothing from model memory.
Method: read `evidence/`, `evals/`, `experiments/`, `scripts/`, `api/src`, `api/tests`, memory files; ran only
offline checks (`check_budgets.py`, an AST regex count, local JSON analysis). No sealed set read, no live API.
"(inf.)" marks inference. Everything else cites a file.

## 0. Bottom line

1. **There is no "context examples vs seal examples" experiment in the repo.** What is recorded: CC-103 option A vs B
   (extra parent-split model call vs none), then C0/C1/C2 (prompt v4 with/without that call). "Sealed" is the owner-held
   *held-out* set, not a prompt technique. The only worked examples in shipped literals are one format example
   ("Lancaster County, Nebraska", `api/src/finish.py:26`) and the selector's hand-written "Sibling rules"
   (`api/src/retrieval/rerank.py:37-45`). Search of repo only; Jira/other sessions not checked.
2. **CC-103 is a real, structure-over-pattern gain** on the stage it targets (geography resolution, multi-parent listings):
   tract grid 138/144 -> 143/144, held-out 108/114. It is the one place the "model composes, code validates" design is
   measured. It is not visible on the golden scoreboard (answered 0.725 before and after).
3. **Selector@1 0.875 is in-sample and partly hand-fitted.** The three "Sibling rules" map 1:1 to three golden misses
   (q11, q21, q41); the +7.5 pt gain *is* those three flips (`evidence/prompt-tuning.json` focus block). 5-run mean is 0.855.
4. **`make check` is green on a stale p95** (top-level 19.207 <= 20) while the real all-tier `demo.p95_latency_seconds`
   on main is 21.701 (over). No post-CC-103 all-tier E2E exists.
5. **The anti-overfit machinery is mostly policy, not gates**: no grid floor, no held-out gap check, no leakage check,
   no multi-turn floors in `budgets.toml`/`check_budgets.py`/`check_invariants.py`. A known leak remains
   (`api/src/tools.py:39` "all counties in Oregon" = golden q02).
6. **No Gate 1 transcript for slice 6** (`evidence/slice-6/` has no `gate1.txt`; mutation checks are asserted in a commit
   message and the report only).

## 1. The experiments as recorded

| Experiment | Hypothesis | Pre-set rule | Metric | Result | Stage improved | Abstraction or pattern? |
|---|---|---|---|---|---|---|
| Repair rounds v1-v3 (`0903ffa`, `cc103-grid-post-v1..v3`) | Re-ask model once after loop for `{parents, unit, listing}` | none recorded | visible grid pass | 41%-83% | geography resolution | abstraction (model composes; code checks closed unit set, parent count, nesting) |
| Base `5d16fb0` | Remove comparison skip + single-place gate | n/a | visible tract 43/48 = 89.6% | p95 22.80s (ineligible) | geography | abstraction; too slow (serial extra call) |
| **A vs B** (`cc103-option-selection.md`) | A: split call beside loop. B: loop's own `level`/`parents`, no extra call | Agreed 2026-10-03 before numbers: p95 <= 20s eligible; then held-out tract, gap <= 10 pts, 5-pt tie band, smaller code | held-out tract (114 trials), gap, clean demo p95 | A 107/114 = 93.9%, p95 15.63s. B 83/114 = 72.8% and 74/114 = 64.9%, p95 21.33s. Base 108/114, p95 22.80s | geography / planning (one call -> N-parent wildcard plan) | A: abstraction with a repair crutch. B (less code, 80+/417-) lost 21+ pts held-out and broke the 10-pt gap ceiling in run 2 |
| Gate 2 fixes -> C0 (`78d3e45`) | Harden repair; remove eval place from split prompt | n/a | tract x3, held-out | visible 138/144 = 95.8%; held-out 98/114 (86.0%) and 101/114 (88.6%, build unverified); gap +9.8/+7.2 | geography | Removing the eval place and using "generic wording" dropped visible to 116/144 then 107/144; a **one-shot format example with a non-eval place restored it** (`b84430f`). The model copies the example's shape (inf.: examples are load-bearing here, not decoration) |
| **C0/C1/C2** prompt (`prompt-v4-c0e048fc86b5.txt`) | Owner's v4 loop prompt (listing-vs-comparison first, `parents`+`level` in one call, "Place, ST") beats C0; does prompt alone replace the call? | Agreed 2026-10-03: one condition per branch, prompt hash recorded, 1,200-token cap | tract x3 (48 trials each), held-out, long_tail p95, answered | **C1 (shipped)** 143/144 = 99.3%, held-out 108/114 = 94.7%, gap +4.6, p95 17.15s, answered 0.725. C2 (call off) 1/144 | geography + planning | C1 vs C0 held-out +6.1 / +8.7 pts; Wilson 95% C1 [89.0, 97.6] vs C0 [78.4, 91.2] overlap. Direction is clear, size is within noise (inf.) |
| Selector prompt tuning (`prompt-tuning-sibling.json`, 600e4de) | Sibling rules fix in-pool sibling misses | none pre-registered for this prompt | selector@1 on golden 40 | baseline [.80,.80,.775,.775,.775]; sibling_rules [.85,.875,.85,.85,.85] | **table selection** | **Pattern.** Rules name commute length, SNAP, field of bachelor's degree, the topics of q11/q21/q41. Same 40 questions tune and score (the repo's own matrix row: "ranking change measured on the tuning set alone, SE ~7 pts") |

Leakage check (my scan of every capitalized golden/grid token against `api/src` literals):
- `api/src/tools.py:39`: "all counties in Oregon" = golden q02 text (flagged LOW in `gate2-c1.txt`, left for owner).
- `rerank.py:37-45`: topic-level (not phrase-level) leakage via sibling rules.
- Everything else clean. Grid places were chosen to avoid eval places (`evals/cc103_phrasing_grid.toml` header).
- v4 prompt itself contains no worked example and no place names.

Held-out caveats (`cc103-option-selection.md`): 38 cells x 3 repeats, **tract only**, split from the visible grid *by verb*, so it
**shares place sets with the visible cells**: it measures phrasing generalization, not new places. The sealed set was used to
pick A over B and then C1 over C0, so the winner's score is optimistic. Visible tract = **16 distinct cells** (x3 repeats x3 runs).
Sealed sets "B" (generated at ticket close) and "C" (about 10 owner questions at epic close) do not exist yet
(memory `project_slice6_anti_overfit`), so no untouched confirmation set exists.

## 2. Scoreboard integrity

| Metric | README / main `evidence/latest.json` | CC-103 evidence | Status |
|---|---|---|---|
| retriever@10, long_tail | 0.90 (36/40), generated 2026-10-02T01:24Z | copied unchanged into every CC-103 demo.json | Current; CC-103 did not touch retrieval (inf.). Exactly at the 0.90 floor: one lost question fails the build. SE ~4.7 pts |
| selector@1, long_tail | 0.875 (35/40) | same | In-sample (see s.1). 4 of 5 misses are out-of-pool (retrieval), so selector conditional on pool = 35/36 |
| answered_rate, long_tail | 0.742 = 89/120 (n=186 all tiers, repeat 3, 2026-10-02) | pre 0.725, A 0.742, C0 0.742, **C1 0.725 (87/120)**, C2 0.725 | Flat across CC-103 (+/-2 trials). Floor 0.70 = 84/120. Trials are 40 questions x 3: **9 questions fail 3/3** in latest.json, so repeat adds little; question-level SE ~6.9 pts, floor margin 4.2 pts |
| p95 (`demo.p95_latency_seconds`) | **21.701s, n=186 (all tiers), over the 20s ceiling** | long_tail only (`--tier long_tail`, n=120): pre 20.19, C0 19.80, **C1 17.15** | **Different populations.** README/latest = all tiers; CC-103 = long_tail. Same-population change is 20.19 -> 17.15 (-3.0s). No all-tier post-CC-103 run exists, so "is the ceiling met by `make demo` as defined" is unanswered |
| top-level `p95_latency_seconds` | **19.207 (stale)**, from an earlier under-ceiling run | C2/pre/opt-b demo.json copy 19.207 at top level while `demo.p95` is 15.6-21.3 | **The trap is live.** `check_budgets.py` prints `ok p95 19.207 <= 20`. `t_ours` has the same split (3.231 top-level vs 10.138 in `demo`) |
| tract grid, visible | n/a | C0 138/144 -> C1 143/144 (runs 48, 47, 48) | 3 runs x 16 cells x 3 repeats. Wilson 95% [96.2, 99.9] on trials; cell-level n=16 is the honest unit |
| tract grid, held-out | n/a | C1 108/114 = 94.7% | Wilson [89.0, 97.6]; origin/main was 10/114 and 7/114 |
| api src LOC | README 4296 | now **4396 / 4400** (run `check_budgets.py`) | README predates CC-103. Headroom 4 lines; `max_file_loc` 410/410; `web_src_loc` 3349/3350 |
| `evidence/latest.json` mtime | 2026-10-04 10:34 | n/a | Content is the 2026-10-02 CC-38 run; the mtime is a checkout touch, not a re-run |

Other integrity flags:
- Untracked `evidence/grid-latest.json` + `grid-trials.jsonl`: 70 cells (54 county, 16 tract), 210 trials, 97.1%, 2026-10-04 00:06 local. Build unknown (inf.: post-C2 working run). Do not quote.
- CC-114 changed the scorer (geography level): `answered_rate` before CC-38 is **not comparable** (README says so). CC-114's rule was committed before outcomes, but Amendment 3 is explicitly post-hoc. Of 18 level-mismatched trials: 10 pipeline_wrong, 3 golden_arguable, 3 golden_misspecified, 2 table_cannot_serve (`cc-114-classification.md`), so 8/18 are not pipeline faults and the scorer is "never loosened".
- The CC-103 grid is one synthetic template family ("All counties in X and Y."): verb x connector x parent count x level.
- Churn hidden by the flat aggregate, C1 vs pre: q38 3/3 -> 1/3 and q09 3/3 -> 2/3 and q36 3/3 -> 2/3, against q08/q13/q18/q24 gains. q38 failures are *table* picks (C02015 over B02015), q09 is one `state` fetch for "by county in North Carolina". C2 repeats q38 1/3 and q09 2/3, so the v4 prompt, not the repair call, is the likelier cause (inf.).
- `core` q04 ("Poverty rate by census tract in Detroit") fetched `place` 3/3 in latest.json. CC-103's grid is multi-parent; single-place-to-tract is CC-104/105 territory and not in any CC-103 demo (long_tail only).

## 3. What the instrument measures (checkpoint s.14, s.9 categories A-J)

Instruments (none gated except the first):
1. Retrieval eval (`make eval`): table@10 and selector@1 vs `expect_table`, 40 tuning + 8 holdout (holdout raw retrieval only, last run 2026-09-19).
2. Golden demo (`run_demo.py`, `is_answered`): HTTP ok + exact `expect_table` + `expect_geo_level` + `expect_warning` + rows > 0.
3. Phrasing grid (`run_grid.py`): one wildcard URL per expected parent, right level, rows, county-identity check at tract.
4. Sealed held-out (owner-held, counts only).
5. Unit tests (fakes). Unrepresented: **CC-100's 30-question comparison list** lives in a Jira comment (10602), not in `evals/`.

Category coverage:
| Category | Measured? | By |
|---|---|---|
| A Retrieval | Yes | retriever@10; 4/40 long_tail out of pool (q17, q18, q20, q34); trap tier @10 only 0.571 (n=14) |
| B Semantic interpretation | Weakly | table match only; variables, vintage and measure are never scored |
| C Geography | Yes, best-covered | golden level + grid + CC-114 buckets (q04, q11, q26 pipeline_wrong) |
| D/E Planning / composition | Only multi-parent listings and 2-leg comparisons | grid; no multi-table, multi-year x multi-geo, or multi-call-dependency cell |
| F URL validity | Indirect | HTTP 200 + rows; `http_ok_rate` 1.0 everywhere. No offline URL-grammar check against metadata (the checkpoint's "50-variable cap / ucgid / for-in" claims are untested by evals; memory notes `build_url` returns ok=True above the 50 cap) |
| G Execution | Yes | `http_ok` separate from `answered` |
| H/I Transformation / presentation | MOE columns, GEOID, universe, alternatives, chart | unit tests only. **No check that answer prose numbers appear in fetched rows** (grep of `guards.py`, `ask.py`, `contract.py`, `loop.py`, found none). "No data from model memory" rests on prompt text plus chart-spec shape, not a test (inf.) |
| J Evaluation | Documented | CC-114 buckets; q10 expects a `C` table the index deliberately folds into `B` (and the selector prompt says prefer B), q23 two legs vs one expected level |

Persistent long_tail failures at C1 (9 questions 0/3): A: q17, q18, q20, q34. J or arguable: q10, q14, q23 (+q26 under the any-coterminous reading). C: q11 (Atlanta metro, CBSA not reachable, CC-106), q26.

Can a local gain hide a global loss? **Yes, today.** The grid, golden and held-out are separate numbers; only golden has floors. The 10-pt gap ceiling, multi-turn floors, and leakage invariant are in Jira ACs and `CLAUDE.md`, not in a script (inf.: grep of `scripts/` and `budgets.toml`; Jira text not read). The one mechanized anti-drift gate on structure is the regex ratchet (`check_invariants.py --base`, commit `b8692cb`): 64 `re.*` call sites in `api/src` now (geo_list 18, vintages 13, geo 11, guards 8). It counts `re.` calls only, not keyword or set heuristics on question text.

## 4. "Do not regress" table

| Capability | Evidence | Code | Protecting tests | Open work that could break it |
|---|---|---|---|---|
| Long-tail retrieval @10 >= 0.90 | `latest.json` 0.90 (36/40), exactly at floor | `api/src/retrieval/*`, `index_store/` | `test_index.py` (6; includes `test_different_questions_reach_different_tables`, the fake-retriever trap); the floor is live-only (`make eval`, needs keys) | CC-77 whole-table extraction (index changes); any metadata/index rebuild |
| Selector @1 >= 0.70 | 0.875 (5-run mean 0.855) | `rerank.py` | `test_rerank.py` (2: thinking off, fallback). **Nothing protects accuracy in `make check`** | CC-77, any rerank prompt edit; sibling rules are fitted to 3 goldens |
| Geography-level answering | golden level scorer, CC-114 | `geo.py`, `geo_list.py`, `compare.py`, `finish.py` | `test_ask_tools.py` (102), `test_ask_loop.py` (56) | CC-104/105/106, CC-77 |
| Multi-parent listings (CC-103) | visible 143/144, held-out 108/114 | `finish.py` (`plan_split`, `split_beside`, `_split_parents`), v4 `ROLE` in `prompts.py`, `finish.py:26` example | `test_finish.py` (38, fake model), `test_ask_loop.py::test_split_call_runs_beside_the_loop_and_finish_reuses_it`, `test_grid_scorer.py` (12), `test_grid_labels.py` (5) | CC-104 (`level` as trusted signal), CC-105 (`parents` for single places), any prompt/tool-description edit. **No grid floor in `budgets.toml`; `run_grid.py` has no pass-rate threshold** (exit codes at lines 148 and 170 only), so a regression passes `make check` and `make demo` |
| Multi-place comparisons (CC-100) | 30-question list in Jira comment 10602 | `compare.py`, `geo.py` | `test_ask_tools.py::test_springfield_*` (2) | CC-104/105/106; the list is not runnable from the repo |
| MOE / GEOID / universe / alternatives in response | unit-level | `contract.py`, `guards.py`, `ask.py` | `test_ask_loop.py`: `test_each_estimate_is_returned_with_its_matching_margin`, `test_missing_margin_stays_visible_as_none`, `test_every_row_carries_an_affgeoid`, `test_scripted_loop_fills_url_rows_geoid_and_universe`, `test_universe_mismatch_finishes_with_a_url`, `test_alternatives_say_how_they_differ`; `test_ask_tools.py::test_pair_margins_adds_m_beside_every_e` | CC-77: whole-table `group()` extraction, "24 E+M pairs max" per memory |
| URL redaction (`CensusURL`) | `check_census_key_not_in_artifacts` | `census_url.py` | `test_ask_tools.py::test_build_url_pairs_margins_and_redacts_the_key`, `test_invariants.py`, invariant `key attached only via CensusURL` | any new URL builder (CC-77) |
| Chart behavior | web + api | `contract.py` `take_chart`, `web/src/chart.ts` | `test_chart.py` (19), `web/src/chart.test.tsx` | `web_src_loc` 3349/3350: any chart fix needs a budget raise |
| Conversation persistence | slice 5 evidence | `store.py` | `test_store.py` (17, Postgres), `test_conversation_routes.py` (14), `web/src/restore.test.tsx`, `evidence/slice-5/*-gate1.txt` | CC-43 follow-ups (CC-3) |
| p95 <= 20s | long_tail 17.15s; all-tier 21.7s | `ask.py`, `finish.py` | none in `make check`; stale-key pass | any extra model call per request. `gate2-c1.txt` INFO: the split call runs on every request even when skipped |

## 5. Mutation-check evidence (Gate 1 rule: `evidence/slice-<N>/gate1.txt`, GOOD/BAD labels)

- Present for slices 0-5 (e.g. `evidence/slice-5/gate1.txt`, `cc-41-gate1.txt`, `evidence/slice-4/cc-101-gate1.txt`, `evidence/slice-1/cc-23-*mutations.txt`).
- **Absent for slice 6 / CC-103.** `git ls-files evidence/slice-6` has no `gate1*`. Claims exist only in commit `90feb4b` ("Each change has a test that fails under its mutation") and `cc103-experiment-report.md` s.4.4/5. The report also records a bad `sed -i` mutation that corrupted source (runs quarantined in `invalid-corrupted-build/`).
- `gate2-code-review.txt` item 12 asked for mutation checks on `test_finish.py` gaps "before Gate 1 sign-off"; no transcript shows they were done.
- Not independently verified. Doing so means running save-copy / mutate / test / restore in a scratch worktree.

## 6. Not verified here
- Jira ACs, comments and ticket state (CC-3, CC-104/105/106, CC-77, CC-100 comment 10602): not read. Claims about "Jira-only" guards are inferred from the repo.
- The other session's transcript and the three reference docs: out of scope for this fork.
- `make eval` / `make demo` were not run: no post-merge numbers produced.
