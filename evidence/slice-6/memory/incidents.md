# CC-123 incidents

Things that went wrong while running the experiment, in order. None is dropped.

## 1. First validity attempt failed the high-water control (harness bug, before any W1 run)

The five injection cases ran inside one process. `native-retained` leaks 20 MB per trial by
design (about 1.2 GB over 62 trials, never freed), so the later cases started from a 1.33 GB
baseline. `high-water` (500 MB allocated at trial 5, freed at trial 8) then reported a pre-GC
peak of 1829 MB against a median of about 1330 MB, a ratio of 1.37, below the 1.5 bar, and was
classified `plateau` instead of `high-water, not growth`. The other four cases passed.

Cause: the harness, not the rule. Fix: one fresh process per case (`validity` now spawns one
per case). The design already said "one run per injection"; its "30 trials" was also wrong
(the windows need 62) and was corrected. The raw output of the failed attempt was deleted
before the re-run and is not on disk; the numbers above are from the console output of that
attempt, copied here. The re-run is `evidence/slice-6/memory/validity.jsonl`: 5 of 5 pass.

## 2. Kill limit lowered from 9 GB to 6 GB before any W1 run

The incident that opened CC-123 was reaped near 5 GB on this machine. The design is amended
and committed; the 2 GB reproduction threshold is unchanged.
