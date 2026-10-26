# CC-113 run incidents

## Concurrent sealed run overlapped the main arm run (2026-10-25)

The owner started a sealed-set probe run while `arms.jsonl` was running (same machine,
same network, same API keys). Facts from file metadata only; no sealed content was read:

- `evidence/latency-sealed-cc113.jsonl` (gitignored): created 21:43:53, last write 21:45:09,
  no probe process left by 21:46.
- `arms.jsonl` started 21:31:00, 84 trials at 21:46:16, so about 11 s per trial. The overlap
  falls on trials roughly 72 to 87, which is repeat 1 of arm `C1` (trials 73 to 96, in
  question order). Interleaving is repeat, arm, question, so an arm is one contiguous block
  and the overlap hits `C1` repeat 1 alone, not every arm equally.

Treatment, decided before looking at any result:

1. Exclude all 24 `C1` repeat-1 trials from `arms.jsonl` in every statistic.
2. After the main run ends, rerun `C1` repeat 1 alone into `arms-c1-r1-rerun.jsonl` and use
   that block in its place. It runs hours later than the other arms, which the results
   file states.
3. The sealed run's own timings for those 76 s are contaminated the same way. The owner
   decides whether to rerun it.
