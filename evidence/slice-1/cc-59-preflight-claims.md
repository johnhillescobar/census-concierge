# CC-59 pre-flight — claims vs measured

Raw command output: `evidence/slice-1/cc-59-preflight.txt`.
Settled on `feat/cc-54-search-select` @ `a2456e0` (PR #21 / CC-58 merged).
Branch `feat/cc-59-p95` targets `feat/cc-54-search-select`, not `main`. Umbrella PR #19 stays open against `main`.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| CC-57 and CC-58 are merged into `feat/cc-54-search-select` | `git log origin/main..HEAD`: PR #20 `d516bd3`, PR #21 `a2456e0` | **Holds.** |
| Umbrella PR #19 remains open against `main` | `gh pr view 19`: OPEN, base `main`, head `feat/cc-54-search-select` | **Holds.** |
| First action is a clean-process `make demo --repeat 3`; no production code unless p95 still fails | ticket purpose + CC-58 transcript | **Holds as protocol.** CC-58 already recorded long_tail 90/117=0.769 and p95 15.356s. That run was on `feat/cc-58-ranked-geography` before the merge; this ticket still requires a fresh measure on the merged umbrella HEAD. |
| `scripts/run_demo.py` already records `answered_rate`, `overall_answered_rate`, `p95_latency_seconds`, `t_llm`, `t_census_api`, `t_ours`, `prompt_hash`, `index_hash` | grep of `run_demo.py` | **Holds.** Use those fields to decide whether the selector round-trip is causal. Do not add timers. |
| Immediate predecessor (CC-58) rates | `evidence/latest.json` / `cc-58-e2e-pre.txt` | **Holds.** long_tail 90/117=0.769; core 9/12=0.750; trap 10/24=0.417; overall 109/153=0.712; p95 15.356s; `t_llm` 3.753 / `t_census_api` 3.377 / `t_ours` 3.658; `prompt_hash` `45b4e3d20ca0`; `index_hash` `377cd59fe62a`; retriever @10=0.900; selector @1=0.825 (33/40 on that run); raw @1=0.475 @3=0.700 @5=0.825 MRR=0.61; alignment=0.544; self-retrieval @1=0.450 @5=0.820. |
| PR A reference 37/117=0.316 / 21.240s | CC-54 Jira comment 10326 | **Holds as the weaker floor.** Immediate predecessor controls. |
| `index.search()` stays LLM-free | `api/src/retrieval/index.py`: no `openai`/`genai`; `choose` appears only in the docstring | **Holds as a constraint.** Query embedding is not a selector call. |
| Selector errors fall back to retrieval top | `rerank.choose`: `fallback = candidates[0].table_id`; `except Exception: return fallback` | **Holds as a constraint.** Keep it. |
| `--rerank --holdout` overwrites gated `selector_at_1` | `eval_retrieval.py`: `if args.rerank` before `elif args.holdout` | **Holds as a constraint.** Capture holdout stdout; rerun `make eval` last so `evidence/latest.json` stores the 40-question tuning selector, not n=8. Do not inspect individual holdout misses. |
| Allowed change surface if p95 fails | `rerank.py` 79 loc; `ask.py` 395/400 | **Holds as a constraint.** No cache, fifth tool, graph node, dependency, route, or extra model call. Do not raise the 20s budget. |
| Live keys; no API already bound to :8000 | dotenv present; `netstat` empty on :8000 | **Holds.** Demo uses in-process TestClient; start from this clean process. |

## Decision

Measure unchanged post-CC-58 code first (`make eval`, `make demo --repeat 3`, then `--tier long_tail --rerank --holdout`, then `make eval` again). If the same run clears long_tail >= 0.70, p95 <= 20, retriever @10 >= 0.90, selector @1 >= 0.70, alignment >= 0.50, and no tier/overall regression vs CC-58, attach the transcript and stop. Do not edit `rerank.py` speculatively.
