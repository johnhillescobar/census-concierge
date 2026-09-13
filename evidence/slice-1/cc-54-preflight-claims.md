# CC-54 PR A pre-flight — claims vs measured

Raw command output: `evidence/slice-1/cc-54-preflight.txt`.
Settled on `origin/main` @ `97482e4`.

PR A only. PR B (empty `variables` → universe total) and PR C (ranked geography default) are later PRs on this ticket.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| `choose()` already exists in `api/src/retrieval/rerank.py` | `rg def choose` | **Holds.** Line 91. Default model `gemini-3.7-flash`. Fallback is `candidates[0]` on failure or a hallucinated ID. |
| The ask loop does not use that selector | `ask.py` `default_tools`; `choose(` callers | **Holds.** Callers are `eval_retrieval.py`, `taxonomize_rerank_misses.py`, and the definition. `SearchTablesTool._arun` calls `self.search` only. |
| Do not call `choose()` from `index.search()` | `rg rerank\|choose` in `index.py`; no `openai`/`google` import | **Holds as a constraint.** `search()` is ranking only. Loader stays free of the LLM. |
| `make eval --rerank` promotes the pick to rank 1 over the same top-10 pool | `eval_retrieval.py` `search_and_rerank` | **Holds.** `return [picked, *(t for t in ranked if t != picked)][:k]`. Empty pool returns `[]` without calling `choose()` (`candidates[0]` would crash). Copy that guard. |
| Neighbor-table demo misses are siblings already in the pool | CC-26 e2e-post; `rerank.py` sibling rules | **Holds.** q12 `B27010` not `B27001`; q35 `B25095` not `B25091`. Selector @1 is 0.875 on `--rerank`; the loop never asks it. |
| No fifth tool | 4 `BaseTool` subclasses; `agent_tools` 4/6 | **Holds.** Wire inside `search_tables`. |
| `ask.py` is at the file cap | `_loc` 400/400 | **Holds as a constraint.** Do not add lines there. Call `choose()` from `SearchTablesTool`, defaulting when `select` is omitted. |
| Room in `tools.py` | `_loc` 290/400 | **Holds.** Promotion is ~20 lines. |
| `doc_lines` 1798/1800 | `check_budgets.py --structural-only` | **Holds as a constraint.** Do not edit PLAN/DESIGN. `ARCHITECTURE.md` is excluded and must name that `search_tables` calls `choose()`. |
| `choose()` needs `GEMINI_API_KEY` | `rerank.py`; dotenv probe | **Holds.** Key is set in this environment (value not logged). A missing key already falls back to rank-1 inside `choose()`. |
| Empty `variables` means every E (50-variable Census cap) | `BuildUrlInput` description | **Out of this PR.** That is PR B. |
| Several place matches refuse a single URL | `record.geography = None` unless `len(matches)==1`; `allowed_geographies` empty unless one match | **Out of this PR.** That is PR C. t05 still scores on `ambiguous_place`. |

## Decision

Promote `choose()`'s table to `hits[0]` inside `SearchTablesTool._arun`, same order as `make eval --rerank`. Inject `select` for tests so unit tests never call Gemini. Skip `choose()` on an empty pool. Do not touch `index.search()`, `ask.py`, `build_url`, or `resolve_geography`.
