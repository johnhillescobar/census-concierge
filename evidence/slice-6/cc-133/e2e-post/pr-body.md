CC-133 post-merge evidence: the E2E on merged main and the `[post_merge]` block in `evidence/closure/CC-133.toml`. No code change.

## Post-merge E2E (main d327f4d at start and end, repeat 3; `evidence/slice-6/cc-133/e2e-post/`)
long_tail answered 0.675 (floor 0.700) | overall 0.790 | demo.p95 24.001s (ceiling 20) | retriever@10 0.900 | selector@1 0.800 | synthetic_alignment 0.544 | geography grid 0.976 | 39 demo misses.
`metric_compare compare --refs A,A0`: VERDICT FAIL. This is main with the new instrument, so no product code differs from A apart from this story's tooling: long_tail trial rate vs A is an observed decrease (-0.008 over 40 families), case rate -0.025, selector@1 0.800 vs 0.825, rows per family (3 families), response contract (3 of 179 trials), answered_rate floor (0.675 < 0.700), p95 ceiling, A0 (no bridge). trap and core INCONCLUSIVE (18 and 4 families). The branch E2E at 0853a63 gave long_tail 0.700 and +0.017 vs A: the two runs of the same code differ by 0.025 on the same cohort, which is the run-to-run noise the strict no-observed-decrease rule cannot tolerate (owner item: tolerance).

## What this means for closing
- `uv run python scripts/closure.py check evidence/closure/CC-133.toml --ref origin/main` exits 0: all 13 rows PASS at 0853a63, the post-merge E2E is recorded and pinned, and main d327f4d contains the tested work.
- The gate requires that the post-merge E2E ran, not that it passed. It did not pass: answered_rate and p95 are under their floors on main, as they were before this story (main measured 25.472s and 0.683 earlier).
- This story ships no product capability and claims no gain.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
