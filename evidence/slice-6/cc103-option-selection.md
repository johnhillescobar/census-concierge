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

Scores below use the county-identity check (a trial passes only if it fetched the counties the
cell names; `scripts/rescore_grid.py`). The first-pass A/B scores did not have it: B's rescored
numbers are lower, A's and the base's are unchanged.

| | Visible tract | Held-out tract | Gap | Clean demo p95 | long_tail answered | Eligible |
|---|---|---|---|---|---|---|
| A (earlier head `035a5f3`) | 131/144 = 91.0% | 107/114 = 93.9% | -2.9 pts | 15.63s | 0.742 | yes |
| B | 110/144 = 76.4% | 83/114 = 72.8% and 74/114 = 64.9% (two runs) | +3.6 and +11.5 pts | 21.33s | 0.775 | no (p95) |
| Base | 43/48 = 89.6% | 108/114 = 94.7% | -5.2 pts | 22.80s | 0.767 | no (p95) |

Final build (`78d3e45`, after the Gate 2 fixes), which is what ships:

| | Visible tract | Held-out tract | Gap | Clean demo p95 |
|---|---|---|---|---|
| Final | 138/144 = 95.8% | 98/114 = 86.0% (`_sealed_final2`, verified build) | +9.8 pts | 19.80s (marginal) |
| Final, other run | | 101/114 = 88.6% (`_sealed_final`, build not verified) | +7.2 pts | |
| `origin/main` | 5.2% | 10/114 = 8.8% and 7/114 = 6.1% (two runs) | | |

Reading: A beats B on held-out by 21 or more points, so the choice stands. The final build is
about 82 points above `origin/main` on held-out, and its held-out score is 5 to 8 points below
the earlier A head (93.9%); that is at the edge of the ~5-point noise band, and the Gate 2
prompt changes may account for part of it. The gap for the final build is inside the 10-point
ceiling in both runs but close to it in one (+9.8). B's second run exceeds the ceiling (+11.5).

Held-out is 38 cells x 3 repeats from the owner-held sealed set, tract level only, split from the
visible grid by verb, so it shares place sets with the visible cells and measures phrasing
generalization, not new places. 95% Wilson intervals are about +/-5 points. Only aggregates
are recorded here; the sealed question text and logs are not in the repository. The sealed set
was used to choose between A and B, so the winner's score is slightly optimistic.
