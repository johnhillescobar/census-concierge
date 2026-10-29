# CC-121 baseline E2E: unmodified code (2026-10-18)

Code: worktree at `a3f0930` (api code identical to `main` `f9f67b9`; only `scripts/ask_one.py` and its test differ). `--repeat 3`, run as the Makefile `eval` and `demo` recipes (`e2e_capture.py` could not be used: it accepts only `--phase pre|post`, does not run the grid, and adds a conversation step the recipe lacks). Transcript: `cc-121-e2e-base.txt`. Scoreboard source: `cc-121-e2e-base-latest.json`.

## Demo (complete, valid)

| key | baseline |
|---|---|
| long_tail `demo.answered_rate` | 0.725 (87 of 120) |
| overall answered rate | 0.785 (n=186); core 0.833 (n=12), trap 0.907 (n=54) |
| `demo.p95_latency_seconds` | 16.664; slowest trial t06 r2 at 40.595 s (trap tier) |
| selector@1 / retrieval@10 | 0.85 / 0.9 |
| retrieval@1 (holdout; reranked) | 0.475 (0.625; 0.85) |
| synthetic self-retrieval / alignment | 0.452 / 0.544 |
| mean seconds: model / Census API / ours | 5.287 / 2.2 / 2.25 |
| `demo.misses` (ids, three repeats) | stable: q10 q14 q17 q20 q26 q29 q34 q41 t07 q23; flapping: q04 q11 q18 t15 t16 |

`prompt_hash` c0e048fc86b5, `index_hash` 377cd59fe62a. Every tier had `http_ok_rate` 1.0.

## Grid (INCOMPLETE)

Visible grid `evals/cc103_phrasing_grid.toml`, 70 cells x 3 = 210 trials. One trial hung about 55 minutes and was killed; the resume (`--batch 26`) crashed on all 26 remaining trials with `RateLimitError 429: You have no credits remaining`. The raw 0.871 (183/210) is contaminated by those crashes and must not be quoted. Valid trials: 183 of 184 pass (county 151/152, tract 32/32 of 48 planned); the one miss is g030 r3. The held-out grid is owner-held and was not run.

To finish after credits are added: in the worktree, drop the rows with a non-empty `crashed` field from `evidence/grid-trials.jsonl`, then `uv run python scripts/run_grid.py --repeat 3 --batch 26`.

## Credits

The OpenAI account had no credit by about 17:20 local. The demo finished at about 15:29 and is unaffected. The CC-121 re-measure (`base-fixed`, `after-fixed`, and their judge runs) finished between 17:20 and 17:23 with 0 errored trials and 0 judge errors; no answer text carries a quota error. The branch half of the E2E cannot run until credits are added.
