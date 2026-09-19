# CC-76 pre-flight — claims vs measured

Raw command output: `evidence/slice-3/cc-76-preflight.txt`.

Settled on `origin/main` @ `4391323` (CC-75 post-merge E2E). Jira `CC-76` To Do, parent CC-2, supersedes CC-66. CC-74 and CC-73 are Done (ticket dependency). CC-75 is Done.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| Comparisons calculate `MOE_diff = sqrt(MOE_1^2 + MOE_2^2)` from matching margins | `guards.moe_not_significant`: `abs(e1-e2) <= math.sqrt(m1*m1 + m2*m2)` over E/M pairs. Equal-to is already not distinguishable (`10 == sqrt(6²+8²)`). No named `MOE_diff`. Tests cover below and above, not equal-to | **Holds as a formula.** Extract one pairing helper so the guard and structured output cannot diverge. Keep `<=` as the Census 90% test. |
| A difference is “not distinguishable at 90%” unless it exceeds `MOE_diff`; indistinguishable values are not ranked | Warning code `moe_not_significant`; detail is prose only. `_COMPARE` plus `len(rows) < 2` skips. Overlapping ACS5 suppresses the guard. Versus series already skip same-place years | **Holds.** Fire only after two comparable fetched legs. Missing MOE already skips the pair (`CENSUS_MISSING`). |
| Structured output exposes both estimates, both MOEs, threshold, and conclusion rather than prose alone | `AskResponse` fields: no `comparisons`. `AskWarning` is `code` + `detail` | **Holds as a gap.** Add `Comparison` on `AskResponse.comparisons` (domain models 6→7 / 15). Regenerate the TS client. |
| `q23` returns Austin and Texas data plus the conclusion and shared-sample caveat | `q23` is `B25064` long_tail, no `expect_warning`. `split_versus` already emits place then state. Independent RSS overstates variance for a place inside its state; no `shared_sample` guard | **Holds as a gap.** Caveat is independent of significance (Austin vs Texas is likely distinguishable). Warning `shared_sample` when one spec nests in the other. |
| Tests cover below, equal-to, and above-threshold, missing MOE, year-over-year, and parent/place | Below/above and missing MOE exist. No equal-to. YoY for a single-geo series already pairs when `_COMPARE` matches and vintages do not overlap. No parent/place caveat test | **Holds as a gap.** Add those cases. Mutation-check every new/changed test. |
| `make demo` includes `q23` and `t15`–`t18`; `is_slice1()` gone except holdout | `is_slice1` drops `q23` by name and `t>=15`. n=57. Holdout already out | **Holds as a gap.** Keep holdout only. n becomes 62. Quote `q23` from `evidence/latest.json`. |
| `moe_not_significant` / `MOE_diff` run only after two comparable fetched legs. `t03`: two tract specs or fail closed with `geography_unsupported` plus candidates/URLs | `t03` is “tract 1201 higher than tract 1305”. `split_versus` is None (`higher than` is not a splitter). `detect_level` is tract; no state/county. Listing a parentless tract is not a legal fetch. Live miss is 0 rows, then missing warning | **Holds as a gap.** Fail closed: two candidate tract specs, `legal=False`, `compare=True`, `geography_unsupported`. Change `t03` `expect_warning` to `geography_unsupported` so the harness never scores a missing MOE warning against 0 rows. Do not silently pick a county. |
| A comparison that already has its warning still ships `urls[]`. `t06` empty URL is a miss | `_WARNING_WITHOUT_FETCH` is only `ambiguous_place` / `geography_not_nested`. `finish_tools` runs only for `device_table` or `overlapping_vintage`. `t06` has no place and `_nation` is False (no year / “United States”), so resolve returns no specs and no URL | **Holds as a gap.** Finish search/resolve/build/fetch for `universe_mismatch` and for `legal=False` when `nested` is not false. Default a geo-less question to `us:1` so a URL exists. Do not finish `geography_not_nested` (t16). |
| CC-74/CC-73 Done; no new tool; no budget raise | Both Done. `ask.py` 398/400; `fetch.py` 400/400; `geo.py` 382/400; `guards.py` 391/400; `doc_lines` 1781/1800; tools 4/6 | **Holds as a constraint.** New pairing lives in `api/src/compare.py` (files 23→24 / 40). `ask.py` gains at most the `comparisons=` kwarg via `finish_aggregation`. No PLAN/DESIGN prose beyond the two slice-3 checkboxes; ARCHITECTURE only for shape. |

## Decision

Keep the RSS test. Emit `comparisons[]` for every `_COMPARE` pair with matching E/M. Warn `shared_sample` on a nested place/parent (or county/state) pair. Fail-close parentless tract-vs-tract as `geography_unsupported` with two candidate specs and URLs. Finish `t06` so `universe_mismatch` ships a URL. Include `q23` and `t15`–`t18` in `make demo`.

## Out of this ticket

Cousin-table long-tail misses (`q05`, `q10`, `q11`, `t08`). Plan strip / charts (slice 4). Raising any budget. Regression modeling, multiple-comparison correction, causal claims. Changing `t09`/`t14` (CC-75).
