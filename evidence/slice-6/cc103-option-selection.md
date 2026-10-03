# CC-103: choosing between options A and B

Rule, agreed on 2026-10-03 before the numbers: (1) eligible only if the clean demo p95 is at
or under 20s and tests, budgets and invariants pass; (2) rank eligible options by held-out
tract pass rate (114 trials) and by the gap, visible minus held-out, ceiling 10 points;
(3) held-out scores within about 5 points are a tie, then the smaller gap, then the smaller
code; (4) the base build is run on the held-out set as well.

Options, all branched from base `24cbf43`:
- A: the parent-split model call runs beside the ask loop (`76a4e32`). Chosen.
- B: no extra call; the loop's own `level` and `parents` carry the structure. Kept at the
  tag `cc-103-opt-b-rejected`, evidence under `opt-b/`.
- Base: the same call run serially after the loop (`91b0c57`).

| | Visible tract | Held-out tract | Gap | Clean demo p95 | long_tail answered | Eligible |
|---|---|---|---|---|---|---|
| A | 131/144 = 91.0% | 107/114 = 93.9% | -2.9 pts | 15.63s | 0.742 | yes |
| B | 124/144 = 86.1% | 93/114 = 81.6% | +4.5 pts | 21.33s | 0.775 | no (p95) |
| Base | 43/48 = 89.6% | 108/114 = 94.7% | -5.2 pts | 22.80s | 0.767 | no (p95) |

Held-out is 38 cells x 3 repeats from the owner-held sealed set, tract level only, split from the
visible grid by verb, so it shares place sets with the visible cells and measures phrasing
generalization, not new places. 95% Wilson intervals are about +/-5 points. Only aggregates
are recorded here; the sealed question text and logs are not in the repository.

Not measured: the code before any repair (`origin/main`) on the held-out set under the strict
scorer; see the baseline files in this directory once recorded.
