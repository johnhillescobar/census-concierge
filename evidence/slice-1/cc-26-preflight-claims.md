# CC-26 pre-flight — claims vs measured

Raw command output: `evidence/slice-1/cc-26-preflight.txt`.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| `scripts/run_demo.py` is missing; `make demo` already invokes it | glob `scripts/`; `Makefile` `demo:` target | **Holds.** Makefile line 32 is `uv run python scripts/run_demo.py --repeat 3`. The file is absent. |
| Run real questions through live `POST /ask` | `app.routes` includes `/ask`; `run_ask` is the handler | **Holds.** Harness must POST `/ask` (ASGI TestClient in-process is still that route), not call tools in isolation. |
| Write `answered_rate` and `p95_latency_seconds` without wiping slice-0 retrieval keys | `evidence/latest.json` keys; `eval_retrieval.py` merge (`existing.update` / selective keys) | **Holds as a requirement.** Latest has retrieval keys only. Demo must load-merge like `--rerank`/`--holdout`, not replace the file. |
| `check_budgets.py` already gates those two fields | `answered_rate_min` 0.70, `p95_latency_seconds` 20.0; skipped when absent | **Holds.** `t_llm` / `t_census_api` / `t_ours` are **not** read. Do not add independent thresholds. |
| Record `t_llm`, `t_census_api`, `t_ours` plus `prompt_hash` and `index_hash` | `index.index_hash()` exists (12 hex); `prompts.ROLE` is the durable prompt; `ask.py` times tools into `record.timings` but not `_openai_complete` | **Holds, with a constraint.** `ask.py` is **400/400** `max_file_loc`. Do not add LLM timing there. Wrap `_openai_complete` and `dispatch` in the demo process (shared with TestClient) and compute `t_ours` as remainder of wall clock. Hash `ROLE` (not the date-injected render — that would change every day). |
| Per-question detail without exposing API keys | `CensusURL` strips `key=`; `redact_text` exists | **Holds.** Persist table_id, url, http_ok, answered, warnings, latency. Refuse to write evidence if `&key=` with a real value appears. HTTP 200 and answered stay separate fields (CC-22 Jira note on this ticket). |
| Slice 1 floors: `answered_rate >= 0.70` and `p95 <= 20` at the same `--repeat` | `budgets.toml`; PLAN slice 1; long_tail is the scoreboard | **Holds as the gate.** Default `--repeat 3`. Gated `answered_rate` is **long_tail** (core proves nothing; same rule as retrieval). p95 is across the run. Producing metrics without clearing floors is exit 1, still write the file. |
| Slice 3 series/comparison traps are not this ticket | `evals/golden_questions.toml` section headers t09–t18; PLAN slice 1 "Not in this slice" | **Holds.** Exclude holdout (`h01`–`h08`) and `t09`–`t18`. In-scope n=52 (4 core, 40 long_tail, 8 slice-1 traps). q23/q24 stay: they are long_tail. |
| t05 empty URL is answered; t01 empty URL is not | golden notes; Jira comment on CC-26 | **Holds.** `ambiguous_place` scores on the warning, URL may be empty. `expect_table` + `expect_warning` (t01) needs the warning **and** a URL. Empty URL is not a passed trap except t05. |
| Room in the budgets | `check_budgets.py --structural-only` | **Holds.** No new tool, route, model, or `api/src` file. `doc_lines` 1796/1800 — do not add prescriptive docs; `ARCHITECTURE.md` is excluded and must name the harness. `ask.py` 400/400 — no lines there. |

## Decision

Add `scripts/run_demo.py` only. POST `/ask` via FastAPI TestClient with live keys. Score long_tail for the gated rate; keep HTTP success off that field. Merge demo keys into `evidence/latest.json`. Do not grow `ask.py`, do not add `urls[]`, do not run t09–t18 or the holdout.
