# F5 — Code & architecture audit (read-only)

Repo at `9094aac` (branch `docs/cc-77-phase1-wording`, == main + 2 docs commits). Yardstick = **phase 1** (URL validity, flexibility across datasets/geographies/vintages, robustness to phrasing, nothing from model memory), per memory `feedback_phase1_yardstick_url_is_product`. Phase-2 constraints are in §7 only. Citations are `file:line` on this HEAD; **[inf]** marks inference. Ran only `check_budgets.py` and `check_invariants.py --base origin/main` (offline, both green) plus AST counters; no live APIs, no sealed set, no repo/Jira/memory edits.

## 0. Headline findings

1. **Regex is not shrinking; it plateaued at 64 call sites and the ratchet froze it there.** 32 (09-16, CC-71) → 53 (09-19) → 66 (09-25, CC-100 start) → 64 (09-26 on) → 64 at HEAD. Api src LOC over the same span: 2,711 → 4,396 (+62%). **51 of the 64 sites run over question prose**, 12 over IDs/Census NAMEs/URL syntax, 1 over the loop's own error string (§3).
2. **Model-composed fields (`places`, `parents`, `level`, `plan_split`) were layered on top of the regex, not in place of it.** The model's structured output is serialized back into prose so the regex can re-parse it: `finish.py:171` builds `query=f"every {unit} in {', '.join(parents)}"` next to `parents`, and `geo.py:213` only honours `parents` if `WILDCARD`/`WITHIN` also match that string. Every surface named in the 2026-09-27 audit still exists (§3.3).
3. **`finish_tools` has 4 redo-gates that read the question and 1 that reads the loop's result.** `_wrong_listing` (`finish.py:75`, regexes `:36/:41`), `_wrong_comparison` (`:83`, `split_comparison`), `_wrong_parentless` (`:100`, `_TRACT_VS`), `wants_acs1(question)` (`:210`) vs the CC-103 `_split_parents` structural gate (`:159-188`). CLAUDE.md says "Gate on the loop's own result".
4. **`pinned_table` (`vintages.py:97-110`) is six keyword→table-ID pins that mirror golden-set phrasings** ("cell phones", "median gross rent", "median family income", "income distribution", "poverty", "without health insurance" ↔ `evals/golden_questions.toml` t09, q23/rent, tract-poverty, q-distribution, Wayne County insurance). Added in CC-76 (`25b79c8`/`7a0c245`, 09-19). They inject a table into search hits even when retrieval missed it (`tools.py:108-130`, called at `tools.py:213`; `finish.py:214`), so `selector_at_1` (measured by `scripts/eval_retrieval.py`, which does not go through them) does not measure the path the demo uses. Eval phrasing in `api/src` literals is the CLAUDE.md "Tuning to the instrument" trap. [inf: the mirroring is by content match of the six patterns to golden text, not by commit message.]
5. **The p95 budget gate passes on a stale key.** `check_budgets` prints `p95 19.207 <= 20`; `evidence/latest.json` `demo.p95_latency_seconds` is **21.701** (n=186, 2026-10-02T02:25Z). Known trap (CLAUDE.md, CC-3 AC13) but live: `make check` is green while the measured ceiling is exceeded. `run_demo.py:182-196` only promotes an under-ceiling run to the top-level key.
6. **Variable choice is the model's memory, validated only for existence.** `search_tables` returns title/universe/members, no variable labels (`tools.py:179-228`); labels exist in metadata (`retrieval/metadata.py:37-40`) but are used only to build the index (`retrieval/build.py:30-32`). `build_url` accepts whatever suffixes exist in the table (`tools.py:268-297`) and defaults to `_001E`. In the latest demo **171 of 177 URLs request exactly one estimate variable** (3 two, 2 three, 1 sixteen). The demo scorer `is_answered` (`scripts/run_demo.py:124`) checks table ID and geography level only, so a wrong variable is scored "answered" (e.g. q04 "Poverty rate…" fetched `B17001_001E`, the universe total). This is a URL-soundness gap on the phase-1 yardstick that CC-77's whole-table extraction would remove [inf].
7. **Geography resolution is one 200-line function that grew by ticket** (`geo.py:243-453`; commits CC-71, 73, 75, 76, 95, 98, 100, 101, 103). `geo.py` and `ask.py` are both **410/410** `max_file_loc`; total **4396/4400**. Any ticket touching resolution or the loop has zero headroom, so only net-deleting changes fit [inf].
8. **Budget log and budget value disagree.** `budgets.toml` `api_src_loc = 4400`; the last log line (`2026-10-02 … 4300 -> 4340 … CC-103`) says 4340. Commit `b4aa5f0` changed 4300→4400. 60 lines of headroom are unlogged. Needs a human to confirm intent.
9. **Prompts outside `api/src/prompts.py` are unbudgeted.** `system_prompt_tokens` counts only `prompts.py` (977/1200, `check_budgets.py:168`). `retrieval/rerank.py:24-44` `PROMPT` ≈297 tokens (includes hand-written "sibling rules" for commute, SNAP, college major, which track golden topics) and `finish.py:22-29` `_SPLIT_PARENTS` ≈149 tokens add ≈446 more; there are 3 LLM call sites (loop gpt-4o-mini `ask.py:40`, selector `gemini-3.7-flash` `rerank.py:22`, parent splitter). The budget text says "One loop has one prompt."
10. **`plan_split` is an extra model call on every `/ask` without an override** (`ask.py:415`, `record.override is None`), including single-place questions where it returns None [inf: cost, not wall-clock, since it runs beside the loop]. `finish_tools` waits up to `SPLIT_WAIT_SECONDS = 6.0` for it (`finish.py:34,204`), a 6 s tail against a 20 s p95 ceiling.
11. **Intermediate Census calls are not in provenance.** `list_census_names` (`geo_list.py:206-242`) issues a live Census request per `resolve_geography` listing; nothing records it in `retained_urls`/`urls[]` (grep: only `fetch.py`, `finish.py` snapshot, `ask.py:64`). The answer URL is shown; the call that turned "Queens" into `county:081 state:36` is not [inf: confirmed by absence of any writer].

## 1. Architecture as built

**Loop** (`ask.py:391-456` `run_ask`): hand-rolled; `_openai_complete` (`:295`, `MODEL="gpt-4o-mini"` `:40`) then `dispatch` (`:266`); `MAX_TURNS=8`, `MAX_TOOL_CALLS=12` (`:38-39`); two consecutive failures of a tool raise (`:291`); the model stops by emitting text. System prompt = one string `ROLE` (`prompts.py:10`) with injected date and latest ACS5/ACS1 vintages. After the loop: `finish_tools` (`finish.py:190`) re-runs missing steps, then `assemble` (`ask.py:210`) builds `AskResponse` from the `ExecutionRecord` (`ask.py:46`, last-wins mutable fields: `geography`, `url`, `rows`, `table_id`…).

| tool | file | inputs | output |
|---|---|---|---|
| `search_tables` | `tools.py:179` | `question`, `k` | candidate pool (`table_id,title,universe,members`) after `index.search` (OpenAI embedding, top-10) → `rerank.choose` (Gemini, `_picks` cache) → `pinned_table` injection |
| `resolve_geography` | `geo.py:180` | `query`, `places[]`, `parents[]`, `level`, `dataset`, `vintage` | `ResolveGeographyResult{specs[GeoSpec], wildcard, legal, detail, nested, compare, compare_count}` (`geo.py:60`) |
| `build_url` | `tools.py:230` | `table_id`, `variables[]`, `dataset`, `vintage`, `for_spec`, `in_spec` | one `CensusURL` `…/{year}/acs/{acs5|acs1}?get=NAME,GEO_ID,<E,M…>&for=…&in=…`, gated on pool membership, availability matrix, and `(for,in,dataset)` ∈ resolved geographies (`tools.py:302-310`) |
| `fetch_data` | `fetch.py:208` | `years[]` | `FetchDataResult` with per-request `RequestLeg`s; fans out geos × years (§4) |

Counts (budget / measured): graph nodes 0/8 (no LangGraph), tools 4/6, routes 4/10 (`main.py`: `/ask`, `POST /conversations`, `POST …/turns`, `GET …/{id}`), tool schemas 8/12, domain models 11/15, direct deps 8/25, api files 26/40. Store: one Postgres row per thread, turns in jsonb, 48 h from creation, ownership and cap enforced in SQL (`store.py:22-45`).

**Ask path, question → rendered answer:** POST `/ask` → `answer()` (`main.py:68`, validates optional `plan` override, 422 before the model) → `run_ask` → [loop: search → resolve → build → fetch] ∥ `plan_split` → `finish_tools` (redo gates, §0.3) → `assemble` (alternatives from pool `ask.py:210-262`, `finish_aggregation` guards `guards.py:389`, `stamp_provenance`, `moe_rows`, `plan_from_record`, `take_chart`) → `AskResponse`. `/conversations/{id}/turns` calls the same `answer(body)` with **only the new question**: no prior turns reach the model (`main.py:121-137`, `ask.py:406-413` messages = system + user).

**Retrieval** (`api/src/retrieval/`, 9 modules, 636 family docs): embed → top-10 → LLM pick. Latest scoreboard (`evidence/latest.json`, 2026-10-02, `prompt_hash cbf19…`, which is **not** the CC-103 v4 prompt `c0e048…`, so it predates CC-103): retriever@10 0.90 (floor 0.90), selector@1 0.875, demo answered (long_tail) 0.742 vs floor 0.70, demo p95 21.701. Demo misses 42/186: 22 wrong table, 18 wrong geography level, 2 missing warning. 11 questions miss 3/3 (q04, q10, q11, q14, q17, q18, q20, q26, q34, t07, q23) and 7 miss intermittently.

## 2. Intermediate representations (checkpoint §8) — existence and observed need

| Representation | Status | Where | Observed failure from its absence? |
|---|---|---|---|
| UserIntent | **absent** as an object. De facto = the model's tool-call args; the question string is re-parsed by regex downstream (`finish.py`, `guards.py`, `vintages.py`, `compare.py`) | — | **Yes, indirectly:** every redo-gate in §0.3 and the `parents`→prose→regex round trip (§0.2) exist because nothing carries the model's interpretation to the code that needs it. CC-100/101/103 each fixed a phrasing family; the grid shows the class (CC-103 visible grid 4/209 before repair → 143/144 tract after, per commits `0903ffa`, `9a237c3`). |
| CensusSemanticRequest | **partial**: typed *geography* intent is `ResolveGeographyInput` (`tools.py:36-60`, `places/parents/level/dataset/vintage`); table/variable intent is `BuildUrlInput` (`tools.py:63-72`). They are two tool schemas with no join, and `geo_status` is an untyped dict (`ask.py:58`, written `ask.py:~85-100`) read by `finish.py`/`guards.py`/`compare.py` | | `level` still fallbacks to `detect_level` regex (`geo.py:273,283`); `_resolve` re-derives state and place from prose with `find_state`/`place_token` even when the model supplied "Place, ST". Observed: q04, q14, q26 "wrong geography level place" 3/3. |
| CandidateDataSources | **exists** | `ExecutionRecord.pool` (`ask.py:47`), `Alternative[]` in the response (`contract.py:75`) | No. Works; alternatives are generated from the pool in `assemble`. |
| RetrievalPlan / APIRequestPlan | **partial**: `ResultPlan` (`contract.py:151`: table, variables, dataset, years, requested_years, `GeoSpec[]`, overlap flag). It is built **after** execution (`plan_from_record`, `contract.py:186`) and used as an override pin (`pin_tool_args`, `apply_override`). The model never emits or reasons over it | | Not for phase 1: the shape (one table × geos × years) matches what the URL generator can do. |
| ExecutedEvidence | **exists** | `RequestLeg` per URL (`contract.py:109`), `FetchDataResult` (`fetch.py:43`), `AskResponse.legs/urls/rows` | Gap only for the NAME-listing calls (§0.11). |
| AnalyticalResult | **minimal**: `Comparison[]` (MOE_diff pairs `compare.py:131`), one summed "combined (N areas)" row with RSS MOE (`guards.py:296-360`), `ChartSpec` | | Both computations are gated by question keywords (`compare.py:14` `_COMPARE`, `guards.py:30/37` `_COMBINE`/`_DERIVED`). |

Recommendation filter: only UserIntent/CensusSemanticRequest have observed-failure support, and what the evidence supports is "carry the model's structured `level/parents/places/dataset/years` to every consumer and stop re-parsing the question", not a new schema family. Phase-1 does not need RetrievalPlan/AnalyticalResult objects.

## 3. Regex / rule inventory

### 3.1 The ratchet (`scripts/check_invariants.py:259-352`, commit `b8692cb`)
- **What it is:** per-file ratchet. `_regex_calls` (`:272`) AST-counts `re.<fn>(…)` where `<fn>` ∈ {compile, search, match, fullmatch, sub, subn, findall, finditer, split} and the receiver is the bare name `re`. `check_no_new_regex` (`:333`) fails if any file's count rises versus `--base`. Runs in `make check` against `origin/main` (`Makefile:70-71`) and in CI against the PR base / push parent (`.github/workflows/check.yml:83-87`); with an empty or all-zero base CI falls back to **no `--base`**, which skips both new-regex and budget-weakened checks.
- **Current count:** 64 call sites (42 `re.compile`, 22 inline) in 11 files. `main` and HEAD are equal, so the check passes trivially.
- **It is a freeze, not a reduction:** 64 → 64 since 09-26. Nothing forces count down.
- **Bypasses [inf, from reading `_regex_calls`; not exercised]:** `import re as _re`, `from re import compile`, `import regex`, and swapping one pattern for another inside a file (count unchanged); moving a regex to another file *is* caught (the receiving file's count rises); **keyword/substring/dict heuristics over question text are not counted at all** (`_LEVELS` dict + substring loops `geo.py:129-134`, `_NOISE`, `"median" in title` `ask.py:190`, `token in _AVERAGE` `geo.py:~277`, `_UNIVERSES` needle loop `guards.py:230-236`, which is a regex but over a table). 46 further method calls on compiled patterns (`_X.search(question)`) are not counted but are covered by the compile that defines them.
- Test: `api/tests/test_invariants.py` (+25 lines in `b8692cb`).

### 3.2 All 64 sites, grouped (keep = syntax/validation over IDs, NAMEs, URLs)

| Where (file:line) | Purpose | Operates on | Generalizable? | Class | Keep/remove |
|---|---|---|---|---|---|
| `ask.py:136` `_RACE` | A–I race-iteration table ID | table ID | yes | syntax | keep |
| `ask.py:454` | match own `"<tool> failed twice"` string | own error text | n/a | fragile sentinel | replace with a flag on the exception/record |
| `census_url.py:15` | strip `&key=` | URL text | yes | validation/redaction | keep |
| `contract.py:11` `_CLAUSE` | parse `for=`/`in=` clauses | URL syntax | yes | syntax | keep |
| `contract.py:121` | reject markup in chart title | LLM output | yes | validation | keep |
| `retrieval/metadata.py:58,65` | table-family and survey-quality ID shapes | table IDs | yes | syntax | keep |
| `retrieval/text.py:17,18` | normalize dollar-vintage text; tokenize | metadata text | yes | normalization | keep |
| `geo_list.py:158,170,192×2` | Census NAME class words (city/CDP/county…), name-head match, rank | Census NAME | yes | NAME matching | keep |
| **`geo_list.py:11,17`** `WILDCARD`,`WITHIN` | decide "listing" vs "direct", extract parent text | question prose | **no** (fixed verbs/units/connectors) | prose-inference | **remove** (model supplies `level`+`parents`; code validates) |
| **`geo_list.py:79,89,94`** `find_state` | state from free text | prose (and model "Place, ST" strings) | partial (50-state table) | prose-inference | replace: take state from the model field, validate against `STATES` |
| **`geo_list.py:107,111,137-151`** `place_token` | pull the place name out of a sentence | prose | **no** (capitalization, `in/for/of`, "County") | prose-inference | remove (model gives `{name,state,level}`) |
| **`geo.py:46,47`** `_VERSUS`,`_COMPARE_TO` | two-way compare split | prose | no | prose-inference | remove (`places` already exists) |
| **`geo.py:52,53,54,172,174`** `_nation` | infer "United States" from absence of a place | prose | **no** | prose-inference | remove (model emits `level:"us"` or empty) |
| **`geo.py:132`** `detect_level` | level from any alias in text | prose | no | prose-inference | remove after `level` is trusted (CC-104 intent) |
| **`geo.py:351,377,381`** | "US" in parent; ZCTA code from "zip 10001"; "in/within" after ZCTA | prose | no | prose-inference | remove (ZCTA is a 5-digit field the model can pass; fail-closed already validates) |
| **`compare.py:14`** `_COMPARE` | gate whether `comparisons[]` is computed | prose keywords | no | prose-inference | remove; compute whenever ≥2 comparable legs |
| **`compare.py:19,24`** `_TRACT_VS`,`_COUNTY` | "tract 1201 higher than tract 1305" parentless pair | prose (golden-shaped) | **no** | prose-inference | remove |
| **`finish.py:36,41`** `_LISTING`,`_BY_COUNTY` | gate a listing redo, rewrite query | prose | **no** | prose-inference | remove (gate on `geographies[0].level` vs model `level`) |
| **`guards.py:20,143`** | ACS5 range in question; "every year" | prose | no | prose-inference | remove; use fetched/attempted years |
| **`guards.py:30,37`** `_COMBINE`,`_DERIVED` | decide whether to append a **combined row** | prose keywords | **no** | prose-inference with data effect | remove; model flag or explicit user plan |
| **`guards.py:42,43,268`** | zip warning; 5-digit code; "median" | prose | no | prose-inference (warnings) | replace with resolved level / selected-table title |
| **`guards.py:234`** | universe words in question | prose | partial (4 words) | prose-inference (warning) | keep until universe is carried by the selected table's metadata (it already is: `universe_mismatch` could compare question-selected vs table universe) |
| **`vintages.py:23-29`** (7) | `pinned_table` keyword→table ID | prose | **no** (6 golden phrasings) | hard-coded routing | **remove**; fix in retrieval/selector, measure with eval |
| **`vintages.py:30`** `_ACS1` | dataset choice | prose | no | prose-inference | remove (model has `dataset`) |
| **`vintages.py:31-35`** (5) | year parsing: since/from/through/in/for/range/span; **unioned into `fetch_data` years** (`fetch.py:307`) | prose | no | parsing with semantics | remove or demote to a warning; the model supplies `years` |

Counts: **12 keep** (IDs/NAMEs/URL/normalization), **1** fragile sentinel, **51** prose-inference.

### 3.3 Reconciliation with the 2026-09-27 audit
| Named in audit | Status at HEAD |
|---|---|
| `find_state`, `place_token`, `detect_level` | **all still present** (`geo_list.py:85,120`, `geo.py:129`); `place_token` called at `geo.py:275,285,336,419`; `detect_level` at `geo.py:168,273,283,421`; `find_state` at `geo.py:168,266`, `compare.py:65` |
| `_LISTING`/`_BY_COUNTY` (`finish.py`) | present (`:36,:41`), still gate `_wrong_listing`/`_listing_query` |
| `_TRACT_VS`/`_COUNTY`/`_COMPARE` (`compare.py`) | present (`:14,19,24`) |
| Migrated | CC-100: comparison *list* splitting retired for model `places` (`geo.py:204-229`), 2-way `versus` split kept. CC-101: `parents` field added (`geo.py:213`), **gated by the same regexes**. CC-103: `plan_split` model call + structural gate (`finish.py:121-188`), the only gate on the loop's own result. |

Net: three tickets added three model-composed paths and removed essentially no prose-inference code (regex count 66→64).

## 4. Multi-API composition

**Mechanism today (general but narrow):** `fetch_data` builds one template URL for **one table and one variable set** and fans out **geographies × years** (`fetch.py:344-366`: `asyncio.gather(*(one(year, spec) for spec in geos for year in planned.attempted))`, `MAX_IN_FLIGHT=5`, `MAX_YEARS=12`, `fetch.py:26-27`). `plan_years` picks ACS1 vs non-overlapping ACS5 per year and replans on 204/404 (`fetch.py:326-388`). Multi-geography arrives as `places`/`parents` (`geo.py:204-229`); wildcard listings stay one GET (`for=tract:*&in=state:X county:Y`). Multi-parent tract listings = N `resolve_geography` legs, each a wildcard spec, fetched as N URLs. The CC-103 repair re-dispatches `resolve_geography` with all parents then `build_url`/`fetch_data` (`finish.py:159-188`).

**What it cannot compose:** multiple tables or variable groups in one answer, different datasets per leg (except the ACS1→ACS5 fallback), `group()`/`ucgid`/pseudo-geographies, requests whose second call depends on the first call's rows (the only dependency chain is the hidden NAME listing inside `resolve_geography`, `geo.py:334,417` → `list_census_names`). One `ExecutionRecord` holds one `table_id`, one `url`, one `rows` list (`ask.py:46-68`); `clear_series` wipes them whenever geography changes (`fetch.py:78-85`).

**Judgement:** composition is a general *Cartesian* mechanism (geo × year over one table) plus per-pattern code for the dependent cases (multi-parent, parentless tract pair, ACS1 retry, nationwide fallback, device pin). On the phase-1 yardstick, that is adequate for "one table, any geographies, any years"; the per-pattern code is where phrasing-fragility lives (§0.2-0.4). Hard limits that are phase-1-relevant and verified in memory pre-flight: `get` cap 50 including NAME/GEO_ID (24 E+M pairs) is **not** enforced by `build_url` (`tools.py:297-326` returns `ok=True` over cap); that is CC-77 scope.

## 5. Budget headroom (`budgets.toml` vs measured; `check_budgets.py` at HEAD)

| budget | cap | measured | headroom | binding on |
|---|---|---|---|---|
| api_src_loc | 4400 | 4396 | **4** | every api ticket; geo/ask/finish edits must net-delete |
| max_file_loc | 410 | 410 (`geo.py`, `ask.py`) | **0** | any edit to resolution or the loop |
| api_src_files | 40 | 26 | 14 | none |
| web_src_loc | 3350 | 3349 | **1** | any UI ticket (CC-43/slice 6 canvas, CC-77 UI) |
| doc_lines | 1800 | 1723 | 77 | catalogs/playbooks only |
| system_prompt_tokens | 1200 | 977 | 223 | but see §0.9: +446 outside the counter |
| graph_nodes / agent_tools | 8 / 6 | 0 / 4 | 8 / 2 | CC-56: a 5th tool needs a named failing golden question |
| api_routes / tool_schemas / domain_models / deps | 10/12/15/25 | 4/8/11/8 | 6/4/4/17 | CC-77 models (whole-table, crosswalk) fit; route-per-feature does not |
| p95_latency_seconds | 20.0 | **19.207 (stale key)**, demo.p95 **21.701**, CC-103 long_tail demo 17.15 (not the same run) | negative on the demo key | any latency-adding ticket |
| retrieval_at_10 floor | 0.90 | 0.90 | **0** | any retrieval/index change |
| selector_at_1 floor | 0.70 | 0.875 | 0.175 | |
| answered_rate floor | 0.70 | 0.742 (pre-CC-103) | 0.042 | |

Ratchets: regex count 64 (no headroom to add); budget raise needs human commit.

## 6. Docs ↔ code cross-check

- All 15 warning codes in `docs/requirements.md` exist in code and vice versa (`guards.evaluate` 12 + `compare.py` + `vintages.py` sites).
- `docs/ask-path.md` is accurate on the loop, finish path, CC-103 beside-the-loop call, years, geography ranking, comparisons. It says "wording pins live in `vintages.pinned_table`" but does not list the six pins or note that they bypass `selector_at_1`.
- `docs/ARCHITECTURE.md`: header **stale** ("Status (2026-09-25)… slice 4 in progress… CC-37 pending" while slices 0–5 are closed per `census_concierge_analysis.md`); file list and tool count are correct; golden count line says "4 core, 40 long-tail, 18 trap, 8 holdout" (file has 48 long_tail incl. holdout; consistent). Does not mention that conversations pass no history to the model (true and documented in slice table as slice 6 work).
- No doc describes the unbudgeted prompts (`rerank.PROMPT`, `_SPLIT_PARENTS`) or that `plan_split` runs on every request.

## 7. Where the code constrains phase 2 (not phase-1 gaps; do not ticket)

- Single-table `ExecutionRecord`/`ResultPlan` cannot hold a list of datasets or derived datasets without reshaping state (`ask.py:46-68`, `contract.py:151`). Decided and parked per `project_phase2_foundations`.
- Rows are `list[dict[str,str|None]]` strings (`contract.py`, `AskResponse.rows`); `_numeric` is duplicated (`compare.py:81`, `guards.py:155`); phase-2 compute tools need typed columns.
- Existing computations (comparisons, combined row, median decline) are triggered by question keywords. Phase-2 compute must be model-invoked typed tools; extending the `_COMPARE`/`_COMBINE` pattern would repeat the drift.
- `/turns` does not pass prior turns (`main.py:121-137`); slice 6 owns this.
- Place identity ("Chicago"→"Chicago, IL") comes from the model's geographic knowledge (`prompts.py` GEOGRAPHY block; `finish.py:19-27`), validated for existence in the Census NAME listing, with `ambiguous_place` as the net. Acceptable for phase 1 (identity, not data values); cross-region phase 2 raises the cost of a wrong guess.

## 8. Not verified

- Did not run `make eval`/`make demo`; all runtime numbers are from committed `evidence/latest.json` (pre-CC-103).
- Did not read Jira (CC-104/105/106/114/77 status) or tests; "migrated" claims rest on code at HEAD and commit messages.
- Did not exercise the ratchet bypasses; they are read off `_regex_calls`.
- `pinned_table`↔golden mirroring is by content comparison; did not read the sealed set and did not check whether the pins were derived from golden questions or found independently.
