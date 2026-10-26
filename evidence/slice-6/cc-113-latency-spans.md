# CC-113: time breaks for `t_ours`

Run 2026-10-25 on merged main `a39290f` (PR #112). Aggregates and single-question traces only; no sealed data.

## What was wrong with the old split

- `t_llm` wraps only the loop's chat call; `t_census_api` wraps only `fetch_data` and `resolve_geography`.
- `search_tables` also calls a Gemini rerank (`rerank.choose`) and an OpenAI query embedding (`embed_query`). Neither was clocked, so both landed in `t_ours`.
- The first loop turn issues two overlapping chat calls, and `t_llm` summed both. Timeline for q40: `0.24 -> 3.09` and `1.46 -> 2.89`.

## Before: rerank and embed timed beside the old clocks

`cc-113-rerank-embed-split-before.txt` (q40, q18, q11, 4 repeats each). The residual is negative (-0.5 to -0.9 s) because of the LLM double count.

## After: `scripts/run_demo.py` with the new buckets (q40 and q18, 3 repeats each)

```
q40 r1 total= 25.2 llm=11.2 census= 9.6 rerank= 3.4 embed=0.7 ours= 0.3
q40 r2 total= 10.7 llm= 5.9 census= 2.5 rerank= 1.8 embed=0.3 ours= 0.2
q40 r3 total=  9.8 llm= 4.5 census= 1.6 rerank= 3.1 embed=0.4 ours= 0.3
q18 r1 total= 18.4 llm= 5.5 census= 6.2 rerank= 6.0 embed=0.6 ours= 0.2
q18 r2 total= 36.7 llm=10.9 census= 8.5 rerank=15.9 embed=1.1 ours= 0.2
q18 r3 total= 48.9 llm= 8.0 census= 6.9 rerank=32.9 embed=1.0 ours= 0.1
```

`t_ours` is the remainder (elapsed minus the union of all clocked spans), so the parts sum to the total by construction. What the run shows is that the remainder is 0.1 to 0.3 s.

## One q18 trial as a timeline (seconds from request start)

```
 2.53 -> 14.92  tool:search_tables   (rerank 3.04 -> 14.92 = 11.9 s)
16.04 -> 18.66  tool:search_tables   (rerank 2.2 s)
19.39 -> 33.96  tool:search_tables   (rerank 14.2 s)
```

Three searches in one question; same-size Gemini calls took 2.2 s to 14.2 s.

## Not shown

q40 r3 in the post-merge E2E had `t_ours` = 47.8 s. It did not reproduce in 12 isolated runs (ours 1.0 to 5.4 s). Cause unknown; a rerank stall or process state (CC-123) are candidates only.

## Reproduce

Run `scripts/run_demo.py` on this branch; the report prints `t_rerank` and `t_embed`, and each trial record carries them.
